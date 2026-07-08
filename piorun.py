import os
import json
import sqlite3
import time
import subprocess
import warnings
from datetime import datetime
import sys
try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS

# Moduły narzędziowe
import core.brain as brain
import tools.mailer as mailer
import tools.sandbox as sandbox
import tools.memory as memory
import tools.study_deadlines as study
import core.scheduler_engine as ste
import tools.gcal as gcal
import core.db_schema as db_schema
from core.config import get_settings
from prompt_toolkit import PromptSession
from prompt_toolkit.completion import WordCompleter

# Wyciszenie ostrzeżeń o zmianie nazwy pakietu (DDGS RuntimeWarning)
warnings.filterwarnings("ignore", category=RuntimeWarning, module='duckduckgo_search')

# --- KONFIGURACJA ---
DB_PATH = brain.HIST_DB
TASKS_DB_PATH = brain.TSKS_DB
SETTINGS = get_settings()
LECTURE_CLEANUP_AFTER_PROCESS = os.environ.get("PIORUN_LECTURE_CLEANUP_AFTER_PROCESS", "true").strip().lower() in {"1", "true", "yes", "y", "on"}

def get_system_prompt():
    # Jedno zrodlo prawdy dla persony i stylu odpowiedzi.
    return brain.get_system_prompt()

# --- OBSŁUGA BAZY ---

def setup_db():
    """Inicjalizuje wymagane tabele i ustawienia baz."""
    try:
        db_schema.ensure_all(DB_PATH, TASKS_DB_PATH)
    except Exception as e:
        print(f"[!] Błąd inicjalizacji baz: {e}")

def save_message(session_id, topic, role, content):
    conn = sqlite3.connect(DB_PATH, timeout=20)
    cursor = conn.cursor()
    cursor.execute("INSERT INTO history (session_id, topic, role, content) VALUES (?, ?, ?, ?)",
                   (session_id, topic, role, content))
    conn.commit()
    conn.close()

def update_topic(session_id, new_topic):
    conn = sqlite3.connect(DB_PATH, timeout=20)
    cursor = conn.cursor()
    cursor.execute("UPDATE history SET topic = ? WHERE session_id = ?", (new_topic, session_id))
    conn.commit()
    conn.close()

def get_history(session_id):
    conn = sqlite3.connect(DB_PATH, timeout=20)
    cursor = conn.cursor()
    cursor.execute("SELECT role, content FROM history WHERE session_id = ? ORDER BY id ASC", (session_id,))
    rows = cursor.fetchall()
    conn.close()
    return [{"role": r[0], "content": r[1]} for r in rows]

def list_sessions():
    conn = sqlite3.connect(DB_PATH, timeout=20)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT session_id, topic, timestamp FROM history GROUP BY session_id ORDER BY timestamp DESC")
    rows = cursor.fetchall()
    conn.close()
    return rows

# --- NARZĘDZIA DODATKOWE ---

def web_search(query):
    try:
        with DDGS() as ddgs:
            results = [r for r in ddgs.text(query, region="pl-pl", max_results=3)]
            formatted = ""
            for r in results:
                formatted += f"Source: {r['href']}\nTitle: {r['title']}\nSnippet: {r['body']}\n\n"
            return formatted if formatted else "Brak wyników wyszukiwania."
    except Exception as e:
        return f"Błąd wyszukiwania: {str(e)}"

def shell_exec(command):
    forbidden = ["rm ", "del ", "format ", "dd "]
    if any(f in command.lower() for f in forbidden):
        print(f"\n[!] PIORUN ⚡ wykrył krytyczną komendę: {command}")
        confirm = input("Czy zatwierdzasz wykonanie? [y/N]: ")
        if confirm.lower() != 'y': return "Operacja odrzucona przez użytkownika."
    
    try:
        result = subprocess.run(["powershell", "-Command", command], capture_output=True, text=True, timeout=60)
        return f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
    except Exception as e:
        return f"Błąd: {str(e)}"


def cleanup_lecture_artifacts(session_path):
    removed = []
    for name in ("audio.wav", "audio_16k.wav"):
        p = os.path.join(session_path, name)
        if os.path.exists(p):
            try:
                os.remove(p)
                removed.append(name)
            except Exception:
                pass
    return removed


def _bool_env(name, default=False):
    return os.environ.get(name, str(default)).strip().lower() in {"1", "true", "yes", "y", "on"}


def process_session(session_path, cleanup=None):
    """Przetwarza jedna sesje wykladu: transkrypcja (jesli trzeba) -> notatki -> HTML (+ opcjonalny DOCX).

    Wspoldzielone przez /process (batch) i /stop (auto-process). Zwraca sciezke HTML.
    Rzuca wyjatek przy bledzie - to caller decyduje, czy przerwac, czy isc dalej.
    """
    import tools.whisper_bridge as wb
    import tools.note_generator as ng
    import core.html_builder as hb

    if cleanup is None:
        cleanup = LECTURE_CLEANUP_AFTER_PROCESS

    folder_name = os.path.basename(os.path.normpath(session_path))
    parts_folder = folder_name.split("_", 2)
    subject = parts_folder[2] if len(parts_folder) > 2 else folder_name

    transcript_path = os.path.join(session_path, "transcript.json")
    if os.path.exists(transcript_path):
        print("  [1/3] Transkrypcja już istnieje - pomijam (resume).")
    else:
        print("  [1/3] Transkrypcja GPU (Whisper large-v3)...")
        wb.transcribe_session(session_path)

    print("  [2/3] Analiza Pioruna -> notatki...")
    ng.generate_academic_notes(session_path, subject)

    print("  [3/3] Generowanie HTML...")
    html_path = hb.build_lecture_page(session_path, subject)

    if _bool_env("PIORUN_LECTURE_EXPORT_DOCX", False):
        try:
            import tools.docx_export as dx
            docx_path = dx.build_lecture_docx(session_path, subject)
            if docx_path:
                print(f"  [DOCX] {docx_path}")
        except Exception as e:
            print(f"  [!] Eksport DOCX nie powiódł się: {e}")

    if cleanup:
        removed = cleanup_lecture_artifacts(session_path)
        if removed:
            print(f"  [CLEANUP] Usunięto: {', '.join(removed)}")

    return html_path

# --- SCHEMATY NARZĘDZI ---

tools_v4 = [
    {"type": "function", "function": {"name": "web_search", "description": "Szuka w Google/DuckDuckGo.", "parameters": {"type": "object", "properties": {"query": {"type": "string"}}, "required": ["query"]}}},
    {"type": "function", "function": {"name": "shell_exec", "description": "PowerShell Command.", "parameters": {"type": "object", "properties": {"command": {"type": "string"}}, "required": ["command"]}}},
    {"type": "function", "function": {"name": "list_dir", "description": "Lista plików.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}}}},
    {"type": "function", "function": {"name": "read_file", "description": "Czyta plik.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]}}},
    {"type": "function", "function": {"name": "write_file", "description": "Zapisuje plik.", "parameters": {"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]}}},
    {"type": "function", "function": {"name": "test_code", "description": "Sandbox test.", "parameters": {"type": "object", "properties": {"code": {"type": "string"}, "language": {"type": "string"}}, "required": ["code"]}}},
    {"type": "function", "function": {"name": "send_report_email", "description": "E-mail raport.", "parameters": {"type": "object", "properties": {"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}}, "required": ["to", "subject", "body"]}}},
    {"type": "function", "function": {"name": "schedule_task", "description": "Planuje zadanie na przyszłość.", "parameters": {"type": "object", "properties": {"name": {"type": "string"}, "time": {"type": "string", "description": "Format ISO (YYYY-MM-DD HH:MM:SS)"}, "subject": {"type": "string"}, "body": {"type": "string"}, "task_type": {"type": "string"}}, "required": ["name", "time", "subject", "body"]}}},
    {"type": "function", "function": {"name": "get_calendar_events", "description": "Pobiera listę nadchodzących wydarzeń z Google Calendar.", "parameters": {"type": "object", "properties": {"max_results": {"type": "integer"}}}}},
    {"type": "function", "function": {"name": "add_calendar_event", "description": "Dodaje nowe wydarzenie do Google Calendar.", "parameters": {"type": "object", "properties": {"summary": {"type": "string"}, "start_time": {"type": "string", "description": "Format ISO (YYYY-MM-DDTHH:MM:SSZ)"}, "description": {"type": "string"}}, "required": ["summary", "start_time"]}}}
]

from prompt_toolkit.completion import Completer, Completion

class PiorunCompleter(Completer):
    def get_completions(self, document, complete_event):
        text = document.text_before_cursor
        if text.startswith("/"):
            commands = [
                '/help', '/clear', '/exit', '/tasks', '/schedule',
                '/lecture', '/stop', '/process', '/notes', '/resume', '/restart', '/study', '/autonomy',
                '/recall', '/find', '/flashcards', '/quiz'
            ]
            for cmd in commands:
                if cmd.startswith(text):
                    yield Completion(cmd, start_position=-len(text))

def ensure_core_running():
    """Sprawdza czy Piorun Core działa, puszczając 'ping' przez socket."""
    import socket
    try:
        # Próba połączenia z portem 9999
        with socket.create_connection(('127.0.0.1', 9999), timeout=1):
            return # Żyje i ma się dobrze
    except (socket.timeout, ConnectionRefusedError):
        # Nikt nie odbiera, odpalamy go
        try:
            print("[*] Budzę Serce: Piorun Core Service...")
            subprocess.Popen([sys.executable, "C:\\Users\\gamin\\Desktop\\mat\\piorun_core.py"], 
                             creationflags=0x00000008, 
                             close_fds=True)
            time.sleep(2) # Chwila na start
        except Exception as e:
            print(f"[!] Błąd startu Core: {e}")

def piorun_cli():
    # Obsługa kodowania UTF-8 dla emoji w terminalach
    if sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8')
        except:
            pass

    # Pancerna inicjalizacja bazy
    setup_db()
    
    # Przekazanie obsługi zadań do serwisu w tle
    ensure_core_running()
    # ste.start_engine() - USUNIĘTO: Czat nie obsługuje już zadań.
    
    session_id = f"SESS_{datetime.now().strftime('%Y%m%d_%H%M')}"
    topic = "Nowa konwersacja"
    
    try:
        session = PromptSession(completer=PiorunCompleter())
    except Exception:
        session = None # Fallback dla środowisk bez konsoli (np. automatyzacja)

    # Obsługa pojedynczej komendy z argumentu -c (dla Agenta)
    one_shot_cmd = None
    if "-c" in sys.argv:
        idx = sys.argv.index("-c")
        if len(sys.argv) > idx + 1:
            one_shot_cmd = sys.argv[idx+1]
    one_shot_mode = one_shot_cmd is not None

    try:
        print("\n" + "="*50)
        print("      PIORUN \u26a1 Sovereign Core v4.0 Active")
        print("="*50)
        print("Wpisz /help aby zobaczyć komendy. Użyj / aby zobaczyć podpowiedzi.")
    except:
        print("\n[PIORUN \u26a1 SOVEREIGN CORE v4.0]")

    history = [{"role": "system", "content": get_system_prompt()}]

    while True:
        try:
            if one_shot_cmd is not None:
                user_input = one_shot_cmd
                one_shot_cmd = None
                print(f"Piorun [{topic}] \u26a1 > {user_input}")
            elif session is not None:
                user_input = session.prompt(f"Piorun [{topic}] \u26a1 > ")
            else:
                user_input = input(f"Piorun [{topic}] \u26a1 > ")
            if not user_input.strip(): continue
            
            if user_input.strip().startswith("/"):
                cmd = user_input.strip().split()[0].lower()
                if cmd == "/exit": break
                elif cmd == "/help":
                    print("\n[POMOC] Komendy: /exit, /resume, /restart, /help, /tasks")
                    print("[STUDY] /study add | /study list | /study done | /study week")
                    print("[AUTONOMIA] /autonomy status | queue | tick | approve <id> | reject <id> [powod]")
                    print("[WYKLADY] /lecture <przedmiot> | /stop | /process [przedmiot] | /notes")
                    print("[PAMIEC] /recall <fraza> - semantyczne szukanie w notatkach i rozmowach")
                    print("[WIEDZA] /find <fraza> - pelnotekstowe szukanie w notatkach | /flashcards <przedmiot>")
                    print("[NAUKA] /quiz <przedmiot> - odpytywanie z pytan kontrolnych z ocena")
                    continue
                elif cmd == "/restart":
                    session_id = str(int(time.time()))
                    topic = "Nowa konwersacja"
                    history = [{"role": "system", "content": brain.get_system_prompt()}]
                    print("\n[+] System zrestartowany. Nowa sesja.")
                    continue
                elif cmd == "/resume":
                    sessions = list_sessions()
                    print("\n[HISTORIA KONWERSACJI]:")
                    for i, s in enumerate(sessions[:10]):
                        print(f"{i+1}. [{s[2]}] {s[1]} (ID: {s[0]})")
                    sel = input("\nWybierz numer sesji do wznowienia (lub enter by wrócić): ")
                    if sel.isdigit() and int(sel) <= len(sessions):
                        session_id = sessions[int(sel)-1][0]
                        topic = sessions[int(sel)-1][1]
                        history = [{"role": "system", "content": brain.get_system_prompt()}] + get_history(session_id)
                        print(f"\n[+] Wznowiono sesję: {topic}")
                    continue
                elif cmd == "/tasks":
                    conn = sqlite3.connect(TASKS_DB_PATH, timeout=20)
                    cursor = conn.cursor()
                    cursor.execute("SELECT name, schedule_time, status FROM tasks ORDER BY schedule_time DESC LIMIT 5")
                    tasks = cursor.fetchall()
                    print("\n[OSTATNIE ZADANIA]:")
                    for t in tasks:
                        print(f"- {t[0]} | Plan: {t[1]} | Status: {t[2]}")
                    conn.close()
                    continue
                elif cmd == "/lecture":
                    parts = user_input.strip().split(None, 1)
                    subject = parts[1] if len(parts) > 1 else "Wyklad"
                    import tools.lecture_recorder as lr
                    globals()['_active_recorder'] = lr.LectureRecorder(subject)
                    if globals()['_active_recorder'].start():
                        print(f"\n[PIORUN REC] Nasłuchuję wykładu: {subject}...")
                        print("[!] Piorun zapisuje slajdy i dźwięk systemowy (Teams). Wpisz /stop aby zakończyć.")
                    continue
                elif cmd == "/stop":
                    rec = globals().get('_active_recorder')
                    if rec:
                        path = rec.stop()
                        globals()['_active_recorder'] = None
                        print(f"\n[OK] Sesja zakończona i zapisana: {path}")
                        # Auto-process: zaproponuj natychmiastowe przetworzenie (domyślnie TAK).
                        answer = "n"
                        try:
                            answer = input("[?] Przetworzyć teraz (transkrypcja + notatki)? [T/n]: ").strip().lower()
                        except Exception:
                            answer = "n"
                        if answer in ("", "t", "tak", "y", "yes"):
                            try:
                                print(f"[*] Przetwarzanie: {os.path.basename(path)}")
                                html = process_session(path)
                                if html:
                                    import webbrowser
                                    webbrowser.open(f"file:///{html}")
                                    print(f"[OK] Gotowe: {html}")
                            except Exception as e:
                                print(f"[!] Przetwarzanie nie powiodło się: {e}")
                                print("[*] Możesz spróbować później: /process [nazwa_przedmiotu]")
                        else:
                            print("[*] Aby wygenerować notatki później użyj: /process [nazwa_przedmiotu]")
                    else:
                        print("\n[!] Brak aktywnej sesji nagrywania.")
                    continue
                elif cmd == "/process":
                    parts = user_input.strip().split(None, 1)
                    subject_filter = parts[1] if len(parts) > 1 else None
                    sessions_dir = str(SETTINGS.sessions_root)

                    # Znajdź WSZYSTKIE sesje bez notatek (batch mode)
                    all_sessions = sorted(os.listdir(sessions_dir))
                    pending = []
                    for s in all_sessions:
                        # Filtruj po przedmiocie jeśli podano
                        if subject_filter and subject_filter.lower() not in s.lower():
                            continue
                        session_path = os.path.join(sessions_dir, s)
                        notes_done = os.path.join(session_path, "notes_structured.json")
                        audio_exists = os.path.exists(os.path.join(session_path, "audio.wav"))
                        transcript_exists = os.path.exists(os.path.join(session_path, "transcript.json"))
                        if (audio_exists or transcript_exists) and not os.path.exists(notes_done):
                            pending.append(session_path)

                    if not pending:
                        if subject_filter:
                            print(f"\n[!] Brak nieprzetworonych sesji dla: {subject_filter}")
                        else:
                            print(f"\n[!] Brak nieprzetworonych sesji. Wszystko jest już gotowe!")
                        continue

                    print(f"\n[BATCH] Znaleziono {len(pending)} nieprzetworzone sesje:")
                    for p in pending:
                        print(f"  - {os.path.basename(p)}")
                    print()

                    last_html = None
                    done_count = 0
                    failed = []
                    for i, session_path in enumerate(pending):
                        print(f"[{i+1}/{len(pending)}] Procesowanie: {os.path.basename(session_path)}")
                        try:
                            last_html = process_session(session_path)
                            done_count += 1
                            print(f"  [OK] Gotowe: {last_html}\n")
                        except Exception as e:
                            failed.append(os.path.basename(session_path))
                            print(f"  [!] Sesja pominięta z powodu błędu: {e}\n")

                    import webbrowser
                    if last_html:
                        webbrowser.open(f"file:///{last_html}")
                    print(f"\n[BATCH DONE] Przetworzone: {done_count}/{len(pending)} sesji.")
                    if failed:
                        print(f"[!] Nieudane (do ponowienia przez /process): {', '.join(failed)}")
                    if last_html:
                        print("[*] Otwieram dashboard...")
                        webbrowser.open(f"file:///{SETTINGS.notes_root / 'index.html'}")
                    continue
                elif cmd == "/notes":
                    import webbrowser
                    index_path = str(SETTINGS.notes_root / "index.html")
                    if os.path.exists(index_path):
                        webbrowser.open(f"file:///{index_path}")
                    else:
                        print("\n[!] Baza notatek jest pusta.")
                    continue
                elif cmd == "/study":
                    parts = user_input.strip().split()
                    subcmd = parts[1].lower() if len(parts) > 1 else "help"
                    if subcmd == "help":
                        print("\n[STUDY HELP]")
                        print("/study add <przedmiot> | <tytul> | <YYYY-MM-DD HH:MM> | [priority] | [notatka]")
                        print("/study list [all]")
                        print("/study done <id>")
                        print("/study week")
                        continue
                    if subcmd == "add":
                        payload = user_input.strip()[len("/study add"):].strip()
                        parts_pipe = [p.strip() for p in payload.split("|")]
                        if len(parts_pipe) < 3:
                            print("\n[!] Format: /study add <przedmiot> | <tytul> | <YYYY-MM-DD HH:MM> | [priority] | [notatka]")
                            continue
                        subject = parts_pipe[0]
                        title = parts_pipe[1]
                        due_raw = parts_pipe[2].replace(" ", "T")
                        priority = parts_pipe[3] if len(parts_pipe) >= 4 and parts_pipe[3] else "medium"
                        notes = parts_pipe[4] if len(parts_pipe) >= 5 else ""
                        try:
                            created_id = study.add_deadline(subject, title, due_raw, priority=priority, notes=notes)
                            print(f"\n[OK] Dodano termin ID={created_id}: {subject} | {title} | {due_raw} | {priority}")
                        except Exception as e:
                            print(f"\n[!] Nie udalo sie dodac terminu: {e}")
                        continue
                    if subcmd == "list":
                        include_done = len(parts) > 2 and parts[2].lower() == "all"
                        rows = study.list_deadlines(limit=50, include_done=include_done)
                        if not rows:
                            print("\n[*] Brak terminow.")
                            continue
                        try:
                            import tools.knowledge_index as ki
                        except Exception:
                            ki = None
                        print("\n[TERMINY STUDY]")
                        for r in rows:
                            note_hint = ""
                            if ki is not None:
                                info = ki.notes_for_subject(r['subject'])
                                if info["count"]:
                                    note_hint = f" | notatki: {info['count']}"
                            print(
                                f"- ID:{r['id']} | {r['subject']} | {r['title']} | due: {r['due_at']} "
                                f"| prio:{r['priority']} | status:{r['status']}{note_hint}"
                            )
                        continue
                    if subcmd == "done":
                        if len(parts) < 3 or not parts[2].isdigit():
                            print("\n[!] Uzycie: /study done <id>")
                            continue
                        ok = study.mark_done(int(parts[2]))
                        if ok:
                            print(f"\n[OK] Oznaczono DONE: ID={parts[2]}")
                        else:
                            print(f"\n[!] Nie znaleziono ID={parts[2]}")
                        continue
                    if subcmd == "week":
                        plan = study.week_plan()
                        if not plan:
                            print("\n[*] Brak otwartych terminow na najblizsze 7 dni.")
                            continue
                        print("\n[PLAN TYGODNIA - PRIORYTETY]")
                        for p in plan:
                            print(
                                f"- ({p['priority']}) {p['due_at']} | {p['subject']} | {p['title']} "
                                f"| ID:{p['id']}"
                            )
                        continue
                    print("\n[!] Nieznana komenda /study. Uzyj: /study help")
                    continue
                elif cmd == "/recall":
                    query = user_input.strip()[len("/recall"):].strip()
                    if not query:
                        print("\n[!] Uzycie: /recall <fraza>")
                        continue
                    try:
                        import tools.vector_memory as vector_memory
                        hits = vector_memory.recall(query)
                        print("\n" + vector_memory.format_recall_for_human(hits))
                    except Exception as e:
                        print(f"\n[!] Blad pamieci: {e}")
                    continue
                elif cmd == "/find":
                    query = user_input.strip()[len("/find"):].strip()
                    if not query:
                        print("\n[!] Uzycie: /find <fraza>")
                        continue
                    try:
                        import tools.knowledge_index as ki
                        print("\n" + ki.format_for_human(query, ki.search(query)))
                    except Exception as e:
                        print(f"\n[!] Blad wyszukiwania: {e}")
                    continue
                elif cmd == "/flashcards":
                    subject = user_input.strip()[len("/flashcards"):].strip()
                    if not subject:
                        print("\n[!] Uzycie: /flashcards <przedmiot>")
                        continue
                    try:
                        import tools.flashcards as fc
                        path, n = fc.export_tsv(subject)
                        if path:
                            print(f"\n[FISZKI] {n} fiszek zapisano: {path}")
                            print("[*] Import do Anki: File → Import, typ 'Basic', separator TAB.")
                        else:
                            print(f"\n[!] Brak pytan kontrolnych w notatkach dla: {subject}")
                    except Exception as e:
                        print(f"\n[!] Blad fiszek: {e}")
                    continue
                elif cmd == "/quiz":
                    subject = user_input.strip()[len("/quiz"):].strip()
                    if not subject:
                        print("\n[!] Uzycie: /quiz <przedmiot>")
                        continue
                    try:
                        import tools.quiz as quiz
                        quiz.run_quiz(subject, n=5)
                    except Exception as e:
                        print(f"\n[!] Blad quizu: {e}")
                    continue
                elif cmd == "/autonomy":
                    import core.ops_runtime as ops
                    parts = user_input.strip().split()
                    subcmd = parts[1].lower() if len(parts) > 1 else "status"
                    try:
                        if subcmd == "status":
                            state = ops.get_autonomy_state()
                            print("\n[AUTONOMIA]")
                            for key in ("enabled", "interval_seconds", "autoexec_count_this_hour",
                                        "ticks_count", "last_tick_at", "queue_size"):
                                print(f"- {key}: {state.get(key)}")
                            print(f"- notes_dir: {state.get('notes_dir')}")
                        elif subcmd == "queue":
                            limit = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 20
                            items = ops.list_autonomy_queue(limit=limit)
                            if not items:
                                print("\n[AUTONOMIA] Kolejka pusta.")
                            else:
                                print(f"\n[AUTONOMIA] Kolejka ({len(items)}):")
                                for item in items:
                                    action = item.get("action", {}) if isinstance(item.get("action", {}), dict) else {}
                                    print(
                                        f"- {item.get('id','')} | {item.get('title','')[:60]} | "
                                        f"akcja={action.get('type','')} | conf={item.get('confidence','')} | "
                                        f"blokada={str(item.get('reason_blocked',''))[:50]}"
                                    )
                        elif subcmd == "tick":
                            result = ops.run_autonomy_tick_now()
                            print(
                                f"\n[AUTONOMIA] Tick: wykonane={len(result.get('executed', []))}, "
                                f"zakolejkowane={len(result.get('queued', []))}, "
                                f"pominiete={len(result.get('skipped', []))}, "
                                f"bledy={len(result.get('errors', []))}"
                            )
                        elif subcmd in {"approve", "reject"} and len(parts) > 2:
                            reason = " ".join(parts[3:]) if len(parts) > 3 else ""
                            result = ops.decide_autonomy_queue_item(
                                item_id=parts[2], decision=subcmd, reviewer="cli", reason=reason
                            )
                            print(f"\n[AUTONOMIA] {subcmd}: {result}")
                        else:
                            print("\n[!] Uzycie: /autonomy status | queue [limit] | tick | approve <id> | reject <id> [powod]")
                    except Exception as e:
                        print(f"\n[!] Blad /autonomy: {e}")
                    continue

            # --- BRAIN EXECUTION ---
            if not brain.save_message(session_id, topic, "user", user_input):
                print("[!] Blad: Baza danych zajeta.")
                continue
                
            history.append({"role": "user", "content": user_input})
            
            def cli_callback(content, is_status=False):
                if is_status:
                    print(content)
                else:
                    print(f"\nPiorun \u26a1: {content}")
                    # Update topic if needed
                    nonlocal topic
                    if (topic == "Nowa konwersacja" or "..." in topic) and len(history) >= 4:
                        new_topic = user_input[:40] if len(user_input) < 40 else user_input[:37] + "..."
                        topic = new_topic
                        update_topic(session_id, topic)
            print("[*] Piorun myśli...", end="\r")
            history = brain.execute_brain_loop(history, session_id, topic, print_callback=cli_callback)
            print(" " * 20, end="\r")
            if one_shot_mode:
                break

        except KeyboardInterrupt: break
        except Exception as e:
            err_msg = str(e).lower()
            if "database is locked" in err_msg or "busy" in err_msg:
                time.sleep(0.5)
                continue
            else:
                print(f"\n[BŁĄD KRYTYCZNY]: {str(e)}")

def _dispatch(argv):
    """Ujednolicone CLI: piorun.py [chat|doctor|digest|autonomy ...].

    Bez argumentow (albo 'chat') = interaktywny czat. Zgodne z istniejacymi
    launcherami .bat i trybem jednorazowym '-c'.
    """
    cmd = argv[0].lower() if argv else "chat"

    if cmd == "doctor":
        import core.doctor as doctor
        raise SystemExit(0 if doctor.print_report() else 1)

    if cmd == "digest":
        try:
            import tools.weekly_digest as wd
            raise SystemExit(wd.main(argv[1:]))
        except ImportError:
            print("[!] Digest jeszcze niedostepny w tej wersji.")
            raise SystemExit(1)

    if cmd == "autonomy":
        scripts_dir = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts")
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
        sys.argv = ["autonomy_ops"] + argv[1:]
        import autonomy_ops
        autonomy_ops.main()
        return

    # 'chat' albo dowolne inne (np. -c "...") -> interaktywny/one-shot czat.
    if cmd == "chat":
        sys.argv = [sys.argv[0]] + argv[1:]
    piorun_cli()


if __name__ == "__main__":
    _dispatch(sys.argv[1:])

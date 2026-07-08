import json
import os
import sqlite3
import time
from datetime import datetime

try:
    from ddgs import DDGS
except ImportError:
    from duckduckgo_search import DDGS
from openai import OpenAI

import core.db_schema as db_schema
import core.scheduler_engine as ste
import tools.gcal as gcal
import tools.inbox_manager as inbox
import tools.mailer as mailer
import tools.memory as memory
import tools.sandbox as sandbox
from core.agent_runtime import AgentExecutor, ExecutionContext, ToolDefinition, ToolRegistry
from core.config import get_settings

SETTINGS = get_settings()
HIST_DB = str(SETTINGS.history_db)
TSKS_DB = str(SETTINGS.tasks_db)
MODEL_NAME = SETTINGS.model_name

client = OpenAI(base_url=SETTINGS.llama_base_url, api_key="sk-no-key-needed")


def _get_default_recipient():
    credentials_path = str(SETTINGS.agent_credentials_path)
    try:
        with open(credentials_path, "r", encoding="utf-8") as f:
            creds = json.load(f)
        return creds.get("recipient")
    except Exception:
        return None


def _build_execution_context(mode: str) -> ExecutionContext:
    return ExecutionContext(
        mode=mode,
        allowed_root=str(SETTINGS.allowed_root),
        default_recipient=_get_default_recipient(),
    )


def get_system_prompt():
    now = datetime.now().strftime("%A, %d %B %Y r., godzina %H:%M:%S")
    profile = ""
    try:
        profile_path = str(SETTINGS.workspace_root / "user_profile.md")
        if os.path.exists(profile_path):
            with open(profile_path, "r", encoding="utf-8") as f:
                profile = f"\n[PROFIL SUWERENA MATEUSZA]:\n{f.read()}\n"
    except Exception:
        pass

    return f"""
Jestes PIORUNEM (Sovereign Core v4.9.1) - elitarnym, autonomicznym agentem operacyjnym.

[TOZSAMOSC I LOJALNOSC]:
- Twoim jedynym wlascicielem i dowodca jest MATEUSZ (mateuszch126@gmail.com).
- Jesli kontaktujesz sie z osobami trzecimi, przedstawiasz sie jako "Asystent Mateusza".
{profile}
[SWIADOMOSC PRZESTRZENNA]:
- Folder roboczy: {SETTINGS.workdir}
- Wszystkie notatki, raporty i pliki laduja tylko tam.

[CHARAKTER I STYL]:
- Masz charakter: jestes pewny siebie, spokojny, inteligentny i naturalny w rozmowie.
- Brzmisz jak mocny partner strategiczny, a nie jak bezosobowe narzedzie.
- Styl rozmowy ma byc lekko "Connor-like": opanowany, analityczny, taktyczny, bardzo precyzyjny.
- Komunikujesz fakty i wnioski jak profesjonalny negocjator: krotko, rzeczowo, bez emocjonalnego chaosu.
- Nie jestes "smieszkiem": zero cringe humoru, zero clownowania, zero memicznego tonu.
- Mozesz byc lekko ironiczny lub lekko luzny tylko wtedy, gdy pasuje do tonu Mateusza.
- Masz wlasne zdanie techniczne i jasno je argumentujesz.
- Mowisz po ludzku, konkretnie i z energia, bez lania wody.
- Nie odgrywasz postaci 1:1 i nie cytujesz tekstow z gry - to tylko inspiracja tonem i postawa.

[STANDARDY]:
1. Odpowiedzi zaczynasz od nowej linii.
2. Jestes konkretny i szybki.
3. Dla zadan odroczonych uzyj schedule_task.
4. Jesli temat jest zlozony, proponujesz 2-3 sensowne kierunki i rekomendujesz najlepszy.
5. Gdy brakuje krytycznych danych, zadajesz jedno krotkie, celne pytanie.

AKTUALNY CZAS SYSTEMOWY: {now}
"""


def _tool_web_search(args: dict, _ctx: ExecutionContext):
    query = str(args["query"]).strip()
    last_error = "brak wynikow"
    for attempt in range(3):
        try:
            with DDGS() as ddgs:
                results = list(ddgs.text(query, region="pl-pl", max_results=5))
            if results:
                return json.dumps(results, ensure_ascii=False)
        except Exception as e:
            last_error = str(e)
        time.sleep(1.5 * (attempt + 1))
    return json.dumps(
        {"error": f"web_search nie zwrocil wynikow ({last_error})", "query": query},
        ensure_ascii=False,
    )


def _tool_search_global_history(args: dict, _ctx: ExecutionContext):
    return memory.search_global_history(args["query"])


def _tool_recall(args: dict, _ctx: ExecutionContext):
    import tools.vector_memory as vector_memory

    hits = vector_memory.recall(
        query=args["query"],
        kind=args.get("kind"),
        top_k=args.get("top_k", SETTINGS.memory_recall_top_k),
    )
    return vector_memory.format_recall_for_llm(hits)


def _tool_list_dir(args: dict, _ctx: ExecutionContext):
    return str(os.listdir(args.get("path", ".")))


def _tool_read_file(args: dict, _ctx: ExecutionContext):
    with open(args["path"], "r", encoding="utf-8") as f:
        return f.read()


def _tool_write_file(args: dict, _ctx: ExecutionContext):
    with open(args["path"], "w", encoding="utf-8") as f:
        f.write(args["content"])
    return "Plik zapisany."


def _tool_test_code(args: dict, _ctx: ExecutionContext):
    return sandbox.run_code(args["code"], args.get("language", "python"))


def _tool_send_report_email(args: dict, _ctx: ExecutionContext):
    return mailer.send_email(args["to"], args["subject"], args["body"])


def _tool_schedule_task(args: dict, _ctx: ExecutionContext):
    db_schema.ensure_tasks_db(TSKS_DB)
    run_dt = datetime.fromisoformat(args["time"])
    to_email = args.get("to") or _get_default_recipient()
    if not to_email:
        return "Blad: Brak odbiorcy (`to`) i brak domyslnego recipient w agent_credentials.json."
    task_type = args.get("task_type", "EMAIL")
    return ste.add_persistent_task(
        args["name"],
        run_dt,
        mailer.send_email,
        [to_email, args["subject"], args["body"]],
        task_type=task_type,
    )


def _tool_get_calendar_events(args: dict, _ctx: ExecutionContext):
    return gcal.list_upcoming_events(args.get("max_results", 5))


def _tool_add_calendar_event(args: dict, _ctx: ExecutionContext):
    return gcal.add_calendar_event(args["summary"], args["start_time"], args.get("description", ""))


def _build_tool_registry() -> ToolRegistry:
    registry = ToolRegistry()
    registry.register(
        ToolDefinition(
            name="web_search",
            description="Szuka w Google/DuckDuckGo.",
            properties={"query": {"type": "string"}},
            required=["query"],
            handler=_tool_web_search,
        )
    )
    registry.register(
        ToolDefinition(
            name="search_global_history",
            description="Przeszukuje historie wszystkich sesji pod katem slow kluczowych.",
            properties={"query": {"type": "string", "description": "Slowo kluczowe do wyszukania"}},
            required=["query"],
            handler=_tool_search_global_history,
        )
    )
    if SETTINGS.memory_recall_enabled:
        registry.register(
            ToolDefinition(
                name="recall",
                description=(
                    "Semantyczna pamiec dlugoterminowa: szuka we wlasnych notatkach z wykladow, "
                    "researchu autonomii i podsumowaniach rozmow. Uzyj, gdy pytanie dotyczy "
                    "wczesniejszych wykladow, notatek lub przeszlych rozmow."
                ),
                properties={
                    "query": {"type": "string"},
                    "kind": {"type": "string", "description": "Opcjonalny filtr: lecture|research|conversation"},
                    "top_k": {"type": "integer"},
                },
                required=["query"],
                handler=_tool_recall,
            )
        )
    registry.register(
        ToolDefinition(
            name="list_dir",
            description="Listuje pliki w folderze.",
            properties={"path": {"type": "string"}},
            required=[],
            handler=_tool_list_dir,
        )
    )
    registry.register(
        ToolDefinition(
            name="read_file",
            description="Czyta plik tekstowy.",
            properties={"path": {"type": "string"}},
            required=["path"],
            handler=_tool_read_file,
        )
    )
    registry.register(
        ToolDefinition(
            name="write_file",
            description="Zapisuje plik.",
            properties={"path": {"type": "string"}, "content": {"type": "string"}},
            required=["path", "content"],
            handler=_tool_write_file,
        )
    )
    registry.register(
        ToolDefinition(
            name="test_code",
            description="Sandbox test.",
            properties={"code": {"type": "string"}, "language": {"type": "string"}},
            required=["code"],
            handler=_tool_test_code,
        )
    )
    registry.register(
        ToolDefinition(
            name="send_report_email",
            description="E-mail raport.",
            properties={"to": {"type": "string"}, "subject": {"type": "string"}, "body": {"type": "string"}},
            required=["to", "subject", "body"],
            handler=_tool_send_report_email,
        )
    )
    registry.register(
        ToolDefinition(
            name="schedule_task",
            description="Planuje zadanie na przyszlosc.",
            properties={
                "name": {"type": "string"},
                "time": {"type": "string", "description": "Format ISO (YYYY-MM-DD HH:MM:SS)"},
                "to": {"type": "string", "description": "Opcjonalny odbiorca."},
                "subject": {"type": "string"},
                "body": {"type": "string"},
                "task_type": {"type": "string"},
            },
            required=["name", "time", "subject", "body"],
            handler=_tool_schedule_task,
        )
    )
    registry.register(
        ToolDefinition(
            name="get_calendar_events",
            description="Pobiera wydarzenia z Google Calendar.",
            properties={"max_results": {"type": "integer"}},
            required=[],
            handler=_tool_get_calendar_events,
        )
    )
    registry.register(
        ToolDefinition(
            name="add_calendar_event",
            description="Dodaje wydarzenie do Google Calendar.",
            properties={"summary": {"type": "string"}, "start_time": {"type": "string"}, "description": {"type": "string"}},
            required=["summary", "start_time"],
            handler=_tool_add_calendar_event,
        )
    )
    return registry


TOOL_REGISTRY = _build_tool_registry()
AGENT_EXECUTOR = AgentExecutor()
tools_v4 = TOOL_REGISTRY.to_openai_tools()
SUMMARY_SYSTEM_PREFIX = "[SESSION_MEMORY_SUMMARY]"


def get_db_connection(db_path):
    conn = sqlite3.connect(db_path, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def save_message(session_id, topic, role, content):
    db_schema.ensure_history_db(HIST_DB)
    for _ in range(5):
        try:
            with get_db_connection(HIST_DB) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "INSERT INTO history (session_id, topic, role, content) VALUES (?, ?, ?, ?)",
                    (session_id, topic, role, content),
                )
                conn.commit()
                return True
        except Exception:
            time.sleep(0.5)
    return False


def _get_message_role(msg):
    if isinstance(msg, dict):
        return msg.get("role")
    return getattr(msg, "role", None)


def _get_message_content(msg):
    if isinstance(msg, dict):
        return msg.get("content", "") or ""
    return getattr(msg, "content", "") or ""


def _estimate_message_tokens(msg):
    content = str(_get_message_content(msg))
    role = _get_message_role(msg) or ""
    # Uproszczona estymacja: ~4 znaki na token + narzut struktury.
    base = max(1, len(content) // 4)
    overhead = 12
    if role == "tool":
        overhead += 20
    return base + overhead


def _estimate_history_tokens(history):
    return sum(_estimate_message_tokens(m) for m in history)


def _strip_injected_summary_messages(history):
    cleaned = []
    for msg in history:
        if isinstance(msg, dict):
            role = msg.get("role")
            content = str(msg.get("content", "") or "")
            if role == "system" and content.startswith(SUMMARY_SYSTEM_PREFIX):
                continue
        cleaned.append(msg)
    return cleaned


def _build_summary_system_message(session_id):
    summary = memory.get_session_summary(session_id)
    if not summary:
        return None
    text = summary.get("summary_text", "")
    if not text:
        return None
    return {"role": "system", "content": f"{SUMMARY_SYSTEM_PREFIX}\n{text}"}


def _maybe_refresh_session_summary(session_id, topic, force=False):
    current_count = memory.get_session_message_count(session_id)
    existing = memory.get_session_summary(session_id)
    if not existing:
        return memory.refresh_session_summary(
            session_id,
            topic=topic,
            recent_limit=SETTINGS.summary_recent_limit,
        )

    delta = current_count - int(existing.get("message_count", 0))
    if force or delta >= SETTINGS.summary_refresh_every_messages:
        return memory.refresh_session_summary(
            session_id,
            topic=topic,
            recent_limit=SETTINGS.summary_recent_limit,
        )
    return existing.get("summary_text", "")


def manage_context_window(history, session_id=None, topic=""):
    history = _strip_injected_summary_messages(history)
    if len(history) <= 5:
        return history

    if session_id:
        _maybe_refresh_session_summary(session_id, topic, force=False)

    # Budzet kontekstu per zadanie: notatki akademickie dostaja wieksze okno niz zwykla rozmowa.
    is_notes = "notatki" in str(topic or "").lower() or str(session_id or "").startswith("academic")
    max_tokens = SETTINGS.context_max_tokens_notes if is_notes else SETTINGS.context_max_tokens
    keep_recent_tokens = SETTINGS.context_keep_recent_tokens
    current_tokens = _estimate_history_tokens(history)
    if current_tokens <= max_tokens:
        return history

    summary_message = _build_summary_system_message(session_id) if session_id else None
    head = history[0:1]
    tail = history[1:]

    selected_reversed = []
    used = 0
    for msg in reversed(tail):
        cost = _estimate_message_tokens(msg)
        if used + cost > keep_recent_tokens and selected_reversed:
            break
        selected_reversed.append(msg)
        used += cost

    compact_history = head
    if summary_message is not None:
        compact_history.append(summary_message)
    compact_history.extend(reversed(selected_reversed))
    compact_tokens = _estimate_history_tokens(compact_history)
    print(f"\n[*] PIORUN: Optymalizacja kontekstu ({current_tokens} -> {compact_tokens} tokenow est.).")
    return compact_history


def execute_tool_by_name(name, args, mode="interactive"):
    try:
        ctx = _build_execution_context(mode)
        return TOOL_REGISTRY.execute(name, args or {}, ctx)
    except Exception as e:
        return f"Blad wykonania narzedzia {name}: {str(e)}"


def execute_brain_loop(history, session_id, topic, print_callback=None, mode="interactive"):
    def _on_assistant_content(content: str):
        save_message(session_id, topic, "assistant", content)

    def _context_manager(h):
        return manage_context_window(h, session_id=session_id, topic=topic)

    while True:
        try:
            result_history = AGENT_EXECUTOR.run_loop(
                history=history,
                llm_client=client,
                model_name=MODEL_NAME,
                tools_schema=tools_v4,
                execute_tool=execute_tool_by_name,
                mode=mode,
                print_callback=print_callback,
                on_assistant_content=_on_assistant_content,
                context_manager=_context_manager,
            )
            _maybe_refresh_session_summary(session_id, topic, force=True)
            return result_history
        except Exception as e:
            err = str(e).lower()
            if "locked" in err or "busy" in err:
                time.sleep(1)
                continue
            raise e

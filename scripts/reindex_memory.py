"""Backfill pamieci wektorowej z istniejacych danych (idempotentny).

Uzycie:
  python scripts/reindex_memory.py --all
  python scripts/reindex_memory.py --lectures --research
  python scripts/reindex_memory.py --wipe --all   # po zmianie modelu embeddingow
"""
import argparse
import os
import re
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.config import get_settings

SETTINGS = get_settings()


def reindex_lectures(vm) -> int:
    total = 0
    sessions_root = str(SETTINGS.sessions_root)
    if not os.path.isdir(sessions_root):
        return 0
    for name in sorted(os.listdir(sessions_root)):
        session_dir = os.path.join(sessions_root, name)
        if not os.path.isdir(session_dir):
            continue
        parts = name.split("_", 2)
        subject = parts[2] if len(parts) > 2 else name
        count = vm.upsert_lecture_session(session_dir, subject)
        if count:
            print(f"  [lectures] {name}: {count} fragmentow")
        total += count
    return total


def reindex_research(vm) -> int:
    total = 0
    notes_dir = SETTINGS.allowed_root / "autonomy_notes"
    if not notes_dir.is_dir():
        return 0
    date_re = re.compile(r"^(\d{4}-\d{2}-\d{2})\.md$")
    for path in sorted(notes_dir.glob("*.md")):
        match = date_re.match(path.name)
        if not match:
            continue
        date = match.group(1)
        sections = vm.split_note_sections(path.read_text(encoding="utf-8"))
        for section in sections:
            total += vm.upsert_research_note(
                title=section.title,
                content=section.content,
                date=date,
                time_tag=section.time_tag,
            )
        if sections:
            print(f"  [research] {path.name}: {len(sections)} sekcji")
    return total


def reindex_conversations(vm) -> int:
    import tools.memory as memory

    total = 0
    try:
        with memory.get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT session_id, topic, summary_text FROM session_summaries")
            rows = cursor.fetchall()
    except Exception as e:
        print(f"  [conversations] blad odczytu bazy: {e}")
        return 0
    for session_id, topic, summary_text in rows:
        total += vm.upsert_conversation_summary(str(session_id), str(topic or ""), str(summary_text or ""))
    if rows:
        print(f"  [conversations] {len(rows)} podsumowan")
    return total


def main():
    parser = argparse.ArgumentParser(description="Backfill pamieci wektorowej Pioruna.")
    parser.add_argument("--all", action="store_true", help="Wszystkie zrodla.")
    parser.add_argument("--lectures", action="store_true")
    parser.add_argument("--research", action="store_true")
    parser.add_argument("--conversations", action="store_true")
    parser.add_argument("--wipe", action="store_true", help="Skasuj kolekcje przed budowa (po zmianie modelu).")
    args = parser.parse_args()

    do_lectures = args.all or args.lectures
    do_research = args.all or args.research
    do_conversations = args.all or args.conversations
    if not (do_lectures or do_research or do_conversations):
        parser.error("Podaj --all albo przynajmniej jedno zrodlo.")

    import tools.vector_memory as vm

    if not SETTINGS.memory_recall_enabled:
        print("[!] PIORUN_MEMORY_RECALL_ENABLED=false - reindex nic nie zrobi.")
        return 1

    if args.wipe:
        client = vm._get_client()
        for name in vm.COLLECTIONS:
            try:
                client.delete_collection(name)
                print(f"  [wipe] usunieto kolekcje {name}")
            except Exception:
                pass

    print("[*] Reindeksowanie pamieci wektorowej...")
    counts = {}
    if do_lectures:
        counts["lecture_notes"] = reindex_lectures(vm)
    if do_research:
        counts["research_notes"] = reindex_research(vm)
    if do_conversations:
        counts["session_summaries"] = reindex_conversations(vm)

    print("[*] Zindeksowano dokumentow:", ", ".join(f"{k}={v}" for k, v in counts.items()))
    print("[*] Stan kolekcji:")
    for name, stats in vm.collection_stats().items():
        print(f"  - {name}: {stats}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Pelnotekstowy indeks notatek wykladowych (SQLite FTS5).

Uzupelnia pamiec wektorowa: FTS = dokladne frazy/nazwy, wektor = znaczenie.
Zrodlo: notes_structured.json wszystkich sesji. Komenda /find <fraza>.
"""
import json
import os
import sqlite3

try:
    from core.config import get_settings
except ModuleNotFoundError:
    import sys

    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from core.config import get_settings

SETTINGS = get_settings()
DB_PATH = str(SETTINGS.runtime_root / "knowledge.db")


def _conn():
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=20)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute(
        """
        CREATE VIRTUAL TABLE IF NOT EXISTS notes_fts USING fts5(
            doc_id UNINDEXED,
            subject,
            date UNINDEXED,
            session UNINDEXED,
            time_start UNINDEXED,
            content,
            tokenize='unicode61'
        )
        """
    )
    return conn


def _fts_query(phrase: str) -> str:
    """Buduje bezpieczne zapytanie FTS5: AND cudzyslowionych tokenow."""
    tokens = [t for t in str(phrase or "").replace('"', " ").split() if t]
    return " ".join(f'"{t}"' for t in tokens)


def index_session(session_dir, subject) -> int:
    """Indeksuje notes_structured.json jednej sesji (delete+insert po doc_id)."""
    notes_path = os.path.join(session_dir, "notes_structured.json")
    if not os.path.exists(notes_path):
        return 0
    with open(notes_path, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    session = os.path.basename(os.path.normpath(session_dir))
    date = session[:10]
    with _conn() as conn:
        conn.execute("DELETE FROM notes_fts WHERE session = ?", (session,))
        n = 0
        for chunk in chunks:
            if not isinstance(chunk, dict):
                continue
            doc_id = f"{session}::{chunk.get('chunk_index', 0)}"
            conn.execute(
                "INSERT INTO notes_fts (doc_id, subject, date, session, time_start, content) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (doc_id, str(subject), date, session, int(chunk.get("time_start", 0)),
                 str(chunk.get("notes_markdown", ""))),
            )
            n += 1
        conn.commit()
    return n


def search(query, limit=10):
    fts = _fts_query(query)
    if not fts:
        return []
    try:
        with _conn() as conn:
            rows = conn.execute(
                """
                SELECT subject, date, session, time_start,
                       snippet(notes_fts, 5, '[', ']', ' … ', 12) AS snip
                FROM notes_fts
                WHERE notes_fts MATCH ?
                ORDER BY rank
                LIMIT ?
                """,
                (fts, int(limit)),
            ).fetchall()
    except sqlite3.OperationalError:
        return []
    hits = []
    for subject, date, session, time_start, snip in rows:
        hits.append({
            "subject": str(subject or ""),
            "date": str(date or ""),
            "session": str(session or ""),
            "time_start": int(time_start or 0),
            "snippet": str(snip or "").replace("\n", " ").strip(),
        })
    return hits


def format_for_human(query, hits):
    if not hits:
        return f"[FIND] Brak trafień dla: {query}"
    lines = [f"[FIND] {len(hits)} trafień dla: {query}"]
    for i, h in enumerate(hits, start=1):
        ts = h["time_start"]
        lines.append(f"{i}. {h['subject']} | {h['date']} | {ts // 60:02d}:{ts % 60:02d}")
        lines.append(f"   {h['snippet']}")
        html = SETTINGS.notes_root / h["subject"] / f"{h['date']}.html"
        lines.append(f"   → {html}")
    return "\n".join(lines)


def reindex_all() -> int:
    sessions_root = str(SETTINGS.sessions_root)
    if not os.path.isdir(sessions_root):
        return 0
    total = 0
    for name in sorted(os.listdir(sessions_root)):
        session_dir = os.path.join(sessions_root, name)
        if not os.path.isdir(session_dir):
            continue
        parts = name.split("_", 2)
        subject = parts[2] if len(parts) > 2 else name
        total += index_session(session_dir, subject)
    return total


def notes_for_subject(subject) -> dict:
    """Liczba wykladow z notatkami i najnowszy HTML dla przedmiotu (dla /study)."""
    obj_dir = SETTINGS.notes_root / str(subject)
    if not obj_dir.is_dir():
        return {"count": 0, "latest": None}
    htmls = sorted(obj_dir.glob("*.html"), reverse=True)
    return {"count": len(htmls), "latest": str(htmls[0]) if htmls else None}


if __name__ == "__main__":
    import sys

    if len(sys.argv) > 1 and sys.argv[1] == "--reindex":
        print(f"[OK] Zindeksowano {reindex_all()} fragmentow.")
    elif len(sys.argv) > 1:
        print(format_for_human(" ".join(sys.argv[1:]), search(" ".join(sys.argv[1:]))))
    else:
        print("Uzycie: python knowledge_index.py [--reindex | <fraza>]")

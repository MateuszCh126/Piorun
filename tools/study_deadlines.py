import sqlite3
from datetime import datetime, timedelta

import core.db_schema as db_schema
from core.config import get_settings


SETTINGS = get_settings()
DB_PATH = str(SETTINGS.tasks_db)


def _conn():
    db_schema.ensure_tasks_db(DB_PATH)
    conn = sqlite3.connect(DB_PATH, timeout=30)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def _norm_priority(value: str) -> str:
    raw = (value or "").strip().lower()
    if raw in {"low", "medium", "high", "critical"}:
        return raw
    return "medium"


def add_deadline(subject: str, title: str, due_at: str, priority: str = "medium", notes: str = ""):
    due_iso = datetime.fromisoformat(due_at).isoformat()
    priority = _norm_priority(priority)
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO study_deadlines (subject, title, due_at, priority, status, notes)
            VALUES (?, ?, ?, ?, 'OPEN', ?)
            """,
            (subject.strip(), title.strip(), due_iso, priority, notes.strip()),
        )
        conn.commit()
        return cur.lastrowid


def list_deadlines(limit: int = 30, include_done: bool = False):
    limit = max(1, min(int(limit), 200))
    query = """
        SELECT id, subject, title, due_at, priority, status, notes, created_at, completed_at
        FROM study_deadlines
    """
    params = []
    if not include_done:
        query += " WHERE status != 'DONE'"
    query += " ORDER BY due_at ASC LIMIT ?"
    params.append(limit)
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(query, params)
        rows = cur.fetchall()
    return [
        {
            "id": int(r[0]),
            "subject": str(r[1] or ""),
            "title": str(r[2] or ""),
            "due_at": str(r[3] or ""),
            "priority": str(r[4] or ""),
            "status": str(r[5] or ""),
            "notes": str(r[6] or ""),
            "created_at": str(r[7] or ""),
            "completed_at": str(r[8] or ""),
        }
        for r in rows
    ]


def mark_done(deadline_id: int):
    done_at = datetime.now().isoformat()
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            UPDATE study_deadlines
            SET status = 'DONE', completed_at = ?
            WHERE id = ?
            """,
            (done_at, int(deadline_id)),
        )
        conn.commit()
        return cur.rowcount > 0


def week_plan():
    now = datetime.now()
    week_end = now + timedelta(days=7)
    with _conn() as conn:
        cur = conn.cursor()
        cur.execute(
            """
            SELECT id, subject, title, due_at, priority, notes
            FROM study_deadlines
            WHERE status = 'OPEN'
              AND due_at >= ?
              AND due_at <= ?
            ORDER BY
              CASE priority
                WHEN 'critical' THEN 0
                WHEN 'high' THEN 1
                WHEN 'medium' THEN 2
                ELSE 3
              END ASC,
              due_at ASC
            """,
            (now.isoformat(), week_end.isoformat()),
        )
        rows = cur.fetchall()
    return [
        {
            "id": int(r[0]),
            "subject": str(r[1] or ""),
            "title": str(r[2] or ""),
            "due_at": str(r[3] or ""),
            "priority": str(r[4] or ""),
            "notes": str(r[5] or ""),
        }
        for r in rows
    ]

import os
import sqlite3


def _ensure_parent_dir(db_path):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)


def _apply_pragmas(conn):
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")


def ensure_history_db(history_db_path):
    _ensure_parent_dir(history_db_path)
    with sqlite3.connect(history_db_path, timeout=30) as conn:
        _apply_pragmas(conn)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS history (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                topic TEXT,
                role TEXT NOT NULL,
                content TEXT NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS session_summaries (
                session_id TEXT PRIMARY KEY,
                topic TEXT,
                summary_text TEXT NOT NULL,
                message_count INTEGER DEFAULT 0,
                updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_session_id ON history(session_id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_session_id_id ON history(session_id, id)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_history_timestamp ON history(timestamp)")
        conn.commit()


def ensure_tasks_db(tasks_db_path):
    _ensure_parent_dir(tasks_db_path)
    with sqlite3.connect(tasks_db_path, timeout=30) as conn:
        _apply_pragmas(conn)
        cursor = conn.cursor()
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL,
                job_id TEXT UNIQUE,
                type TEXT NOT NULL,
                status TEXT DEFAULT 'PENDING',
                schedule_time TEXT,
                actual_time TEXT,
                retries_remaining INTEGER DEFAULT 5,
                last_error TEXT,
                payload TEXT,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS audit_logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                event_type TEXT,
                description TEXT,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        cursor.execute(
            """
            CREATE TABLE IF NOT EXISTS study_deadlines (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                subject TEXT NOT NULL,
                title TEXT NOT NULL,
                due_at TEXT NOT NULL,
                priority TEXT DEFAULT 'medium',
                status TEXT DEFAULT 'OPEN',
                notes TEXT DEFAULT '',
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                completed_at TEXT
            )
            """
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_study_deadlines_due_at ON study_deadlines(due_at)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_study_deadlines_status ON study_deadlines(status)")
        conn.commit()


def ensure_all(history_db_path, tasks_db_path):
    ensure_history_db(history_db_path)
    ensure_tasks_db(tasks_db_path)

import json
import os
import sqlite3
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from datetime import datetime, timezone
from pathlib import Path

import core.autonomy_supervisor as autonomy
import core.db_schema as db_schema
from core.config import get_settings

SETTINGS = get_settings()


def _now_iso():
    return datetime.now(timezone.utc).isoformat()


def _safe_int(value, default=0):
    try:
        return int(value)
    except Exception:
        return default


def _fetch_json(url, timeout):
    req = urllib.request.Request(url=url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        body = resp.read().decode("utf-8")
        return json.loads(body) if body else {}


def check_llm_health():
    base = SETTINGS.llama_base_url.rstrip("/")
    timeout = SETTINGS.llm_health_timeout_seconds
    candidates = [f"{base}/models", base]

    errors = []
    for endpoint in candidates:
        try:
            payload = _fetch_json(endpoint, timeout=timeout)
            return {
                "ok": True,
                "endpoint": endpoint,
                "error": None,
                "payload_preview": str(payload)[:240],
            }
        except urllib.error.URLError as e:
            errors.append(str(e))
        except Exception as e:
            errors.append(str(e))

    return {"ok": False, "endpoint": candidates[0], "error": "; ".join(errors), "payload_preview": ""}


def _history_conn():
    db_schema.ensure_history_db(str(SETTINGS.history_db))
    conn = sqlite3.connect(str(SETTINGS.history_db), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def _tasks_conn():
    db_schema.ensure_tasks_db(str(SETTINGS.tasks_db))
    conn = sqlite3.connect(str(SETTINGS.tasks_db), timeout=10)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def _query_one(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    row = cur.fetchone()
    return row[0] if row else None


def _query_rows(conn, sql, params=()):
    cur = conn.cursor()
    cur.execute(sql, params)
    return cur.fetchall()


def get_runtime_health():
    checks = []

    for label, db_path, opener in [
        ("history_db", SETTINGS.history_db, _history_conn),
        ("tasks_db", SETTINGS.tasks_db, _tasks_conn),
    ]:
        try:
            with opener() as conn:
                _query_one(conn, "SELECT 1")
            checks.append({"name": label, "ok": True, "path": str(db_path), "error": None})
        except Exception as e:
            checks.append({"name": label, "ok": False, "path": str(db_path), "error": str(e)})

    llm = check_llm_health()
    checks.append({"name": "llm_endpoint", "ok": llm["ok"], "path": llm["endpoint"], "error": llm["error"]})

    return {"ok": all(c["ok"] for c in checks), "timestamp": _now_iso(), "checks": checks}


def get_runtime_status():
    status = {"timestamp": _now_iso()}

    try:
        with _history_conn() as conn:
            status["history_rows"] = _safe_int(_query_one(conn, "SELECT COUNT(*) FROM history"), 0)
            status["sessions_count"] = _safe_int(_query_one(conn, "SELECT COUNT(DISTINCT session_id) FROM history"), 0)
            status["session_summaries_count"] = _safe_int(_query_one(conn, "SELECT COUNT(*) FROM session_summaries"), 0)
    except Exception as e:
        status["history_error"] = str(e)

    try:
        with _tasks_conn() as conn:
            status["tasks_count"] = _safe_int(_query_one(conn, "SELECT COUNT(*) FROM tasks"), 0)
            rows = _query_rows(conn, "SELECT status, COUNT(*) FROM tasks GROUP BY status")
            status["tasks_by_status"] = {str(r[0]): int(r[1]) for r in rows}
    except Exception as e:
        status["tasks_error"] = str(e)

    status["llm"] = check_llm_health()
    try:
        status["autonomy"] = autonomy.get_autonomy_state()
    except Exception as e:
        status["autonomy_error"] = str(e)
    return status


def list_recent_sessions(limit=20):
    limit = max(1, min(int(limit), 200))
    with _history_conn() as conn:
        rows = _query_rows(
            conn,
            """
            SELECT session_id, MAX(topic) as topic, MAX(timestamp) as last_timestamp, COUNT(*) as message_count
            FROM history
            GROUP BY session_id
            ORDER BY last_timestamp DESC
            LIMIT ?
            """,
            (limit,),
        )
    return [
        {
            "session_id": str(r[0]),
            "topic": str(r[1] or ""),
            "last_timestamp": str(r[2] or ""),
            "message_count": int(r[3] or 0),
        }
        for r in rows
    ]


def list_recent_summaries(limit=20):
    limit = max(1, min(int(limit), 200))
    with _history_conn() as conn:
        rows = _query_rows(
            conn,
            """
            SELECT session_id, topic, summary_text, message_count, updated_at
            FROM session_summaries
            ORDER BY updated_at DESC
            LIMIT ?
            """,
            (limit,),
        )
    return [
        {
            "session_id": str(r[0]),
            "topic": str(r[1] or ""),
            "summary_text": str(r[2] or ""),
            "message_count": int(r[3] or 0),
            "updated_at": str(r[4] or ""),
        }
        for r in rows
    ]


def list_recent_tasks(limit=20):
    limit = max(1, min(int(limit), 200))
    with _tasks_conn() as conn:
        rows = _query_rows(
            conn,
            """
            SELECT id, name, type, status, schedule_time, actual_time, created_at
            FROM tasks
            ORDER BY id DESC
            LIMIT ?
            """,
            (limit,),
        )
    return [
        {
            "id": int(r[0]),
            "name": str(r[1] or ""),
            "type": str(r[2] or ""),
            "status": str(r[3] or ""),
            "schedule_time": str(r[4] or ""),
            "actual_time": str(r[5] or ""),
            "created_at": str(r[6] or ""),
        }
        for r in rows
    ]


def get_autonomy_state():
    return autonomy.get_autonomy_state()


def list_autonomy_queue(limit=50):
    return autonomy.get_autonomy_queue(limit=limit)


def decide_autonomy_queue_item(item_id, decision, reviewer="ops_api", reason=""):
    return autonomy.decide_queue_item(item_id=item_id, decision=decision, reviewer=reviewer, reason=reason)


def run_autonomy_tick_now():
    return autonomy.autonomy_tick()


def _safe_arcname(base_dir: Path, target: Path):
    try:
        rel = target.relative_to(base_dir)
        return str(rel)
    except ValueError:
        return target.name


def create_backup(include_workdir=True):
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = SETTINGS.backup_dir / f"piorun_backup_{ts}.zip"
    SETTINGS.backup_dir.mkdir(parents=True, exist_ok=True)

    files_added = []
    with zipfile.ZipFile(backup_path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in [SETTINGS.history_db, SETTINGS.tasks_db]:
            if path.exists():
                arc = f"runtime/{path.name}"
                zf.write(path, arcname=arc)
                files_added.append(arc)

        if include_workdir and SETTINGS.workdir.exists():
            base = SETTINGS.workdir
            for root, _, files in os.walk(base):
                for name in files:
                    full = Path(root) / name
                    arc = f"workdir/{_safe_arcname(base, full)}"
                    zf.write(full, arcname=arc)
                    files_added.append(arc)

    return {"backup_path": str(backup_path), "files_added": files_added, "timestamp": _now_iso()}

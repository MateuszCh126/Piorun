import json
from datetime import datetime, timedelta, timezone

import tools.weekly_digest as wd
from core.config import get_settings

SETTINGS = get_settings()


def _write_decisions(events):
    path = SETTINGS.autonomy_state_dir / "decisions.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        for e in events:
            f.write(json.dumps(e, ensure_ascii=False) + "\n")


def _iso(days_ago):
    return (datetime.now(timezone.utc) - timedelta(days=days_ago)).isoformat()


def test_collect_digest_counts_recent_only():
    _write_decisions([
        {"kind": "tick", "timestamp": _iso(1),
         "executed": [{"title": "Research AI", "action_type": "web_search"},
                      {"title": "reminder: Kolokwium", "action_type": "send_reminder"}],
         "queued": [{"title": "X"}], "skipped": []},
        {"kind": "queue_decision", "timestamp": _iso(2), "decision": "APPROVED"},
        {"kind": "queue_decision", "timestamp": _iso(3), "decision": "REJECTED"},
        {"kind": "tick", "timestamp": _iso(30),  # poza oknem 7 dni
         "executed": [{"title": "stare", "action_type": "web_search"}], "queued": [], "skipped": []},
    ])
    data = wd.collect_digest(days=7)
    assert data["ticks"] == 1
    assert data["executed"] == 2
    assert data["reminders"] == 1
    assert data["approvals"] == 1
    assert data["rejections"] == 1
    assert "Research AI" in data["executed_titles"]
    assert "stare" not in data["executed_titles"]


def test_render_markdown_has_sections():
    data = wd.collect_digest(days=7)
    md = wd.render_markdown(data)
    assert "# Piorun — digest autonomii" in md
    assert "## Aktywność autonomii" in md
    assert "## Terminy studenckie" in md


def test_build_digest_writes_file_without_maintenance():
    _write_decisions([{"kind": "tick", "timestamp": _iso(1),
                       "executed": [], "queued": [], "skipped": []}])
    path = wd.build_digest(days=7, send=False, maintenance=False)
    import os
    assert os.path.exists(path)
    assert "digest_" in os.path.basename(path)

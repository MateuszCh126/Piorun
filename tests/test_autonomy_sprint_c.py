import json
from datetime import datetime, timedelta, timezone

import core.autonomy_supervisor as sup


# --- 2.4 metryka jakosci zrodel ---------------------------------------------

def test_source_metrics_counts_domains_and_year():
    year = datetime.now().year
    raw = json.dumps([
        {"title": f"Trend {year}", "href": "https://a.pl/x", "body": "cos"},
        {"title": "Bez roku", "href": "https://a.pl/y", "body": "inne"},
        {"title": f"Drugi {year}", "href": "https://b.com/z", "body": f"rok {year}"},
    ])
    m = sup._source_metrics(raw)
    assert m["count"] == 3
    assert m["domains"] == 2  # a.pl, b.com
    assert m["current_year"] == 2


def test_source_footer_and_empty():
    assert sup._source_footer({}) == ""
    footer = sup._source_footer({"count": 5, "domains": 3, "current_year": 4})
    assert "5 wynikow" in footer and "3 unikalnych domen" in footer


# --- 2.3 TTL kolejki --------------------------------------------------------

def _iso_days_ago(days):
    return (datetime.now(timezone.utc) - timedelta(days=days)).isoformat()


def test_prune_failed_queue_drops_old_failed_keeps_rest():
    queue = [
        {"id": "1", "reason_blocked": "execution_failed: x", "created_at": _iso_days_ago(30)},
        {"id": "2", "reason_blocked": "execution_failed: y", "last_try_at": _iso_days_ago(1)},
        {"id": "3", "reason_blocked": "hourly_autoexec_limit", "created_at": _iso_days_ago(60)},
    ]
    kept, changed = sup._prune_failed_queue(queue)
    ids = {i["id"] for i in kept}
    assert changed is True
    assert ids == {"2", "3"}  # stary failed usuniety; swiezy failed i nie-failed zostaja


# --- 2.1 deterministyczne przypomnienia o terminach -------------------------

def _write_credentials():
    import core.config as cfg
    path = cfg.get_settings().agent_credentials_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps({"email": "a@b.pl", "password": "x", "recipient": "owner@example.com"}),
                    encoding="utf-8")


def test_deadline_reminders_send_once_and_dedup(monkeypatch):
    import core.brain as brain
    import tools.study_deadlines as study

    _write_credentials()
    sent = []
    monkeypatch.setattr(brain.mailer, "send_email",
                        lambda to_email, subject, body: sent.append((to_email, subject)) or "OK")

    # Termin za 24h -> w oknie 48h.
    due = (datetime.now() + timedelta(hours=24)).isoformat()
    study.add_deadline("Bazy Danych", "Kolokwium", due, priority="high")

    state, event = {}, {"executed": [], "errors": []}
    sup._process_deadline_reminders(state, event)
    assert len(sent) == 1
    assert sent[0][0] == "owner@example.com"
    assert event["executed"] and event["executed"][0]["action_type"] == "send_reminder"

    # Drugi tick w cooldownie -> zero nowych maili.
    sup._process_deadline_reminders(state, {"executed": [], "errors": []})
    assert len(sent) == 1


def test_reminders_skip_when_no_recipient(monkeypatch):
    import core.config as cfg
    # Usun plik poswiadczen -> brak odbiorcy -> brak przypomnien.
    path = cfg.get_settings().agent_credentials_path
    if path.exists():
        path.unlink()
    state, event = {}, {"executed": [], "errors": []}
    sup._process_deadline_reminders(state, event)
    assert event["executed"] == []

import json

import core.autonomy_supervisor as sup


def test_sanitize_action_web_search_valid():
    action = sup._sanitize_action({"type": "web_search", "query": "  trendy AI  "})
    assert action == {"type": "web_search", "query": "trendy AI"}


def test_sanitize_action_rejects_unknown_type():
    assert sup._sanitize_action({"type": "delete_all_files", "path": "C:\\"}) == {}


def test_sanitize_action_write_note_requires_content():
    assert sup._sanitize_action({"type": "write_note", "title": "X", "content": ""}) == {}


def test_fingerprint_ignores_word_order_and_year():
    fp1 = sup._action_fingerprint({"type": "web_search", "query": "najnowsze trendy AI 2024"})
    fp2 = sup._action_fingerprint({"type": "web_search", "query": "AI trendy najnowsze 2026"})
    assert fp1 and fp1 == fp2


def test_semantic_key_groups_ai_trends_topics():
    key1 = sup._action_semantic_key({"type": "web_search", "query": "najnowsze trendy w AI"})
    key2 = sup._action_semantic_key({"type": "web_search", "query": "aktualne nowosci AI machine learning"})
    assert key1.startswith("web_search_topic::")
    assert key1 == key2


def test_parse_proposals_from_fenced_json():
    raw = """```json
{"thought": "ok", "proposals": [
  {"title": "T", "reason": "R", "risk": "low", "confidence": 90,
   "action": {"type": "web_search", "query": "cos"}}
]}
```"""
    proposals = sup._parse_proposals_from_text(raw)
    assert len(proposals) == 1
    assert proposals[0]["action"]["type"] == "web_search"


def test_parse_proposals_garbage_returns_empty():
    assert sup._parse_proposals_from_text("to nie jest json") == []


def test_format_search_results_produces_markdown():
    raw = json.dumps([
        {"title": "Tytul", "href": "https://example.com", "body": "Opis wyniku."},
    ])
    formatted = sup._format_search_results(raw)
    assert "**Tytul**" in formatted
    assert "Zrodlo: https://example.com" in formatted


def test_format_search_results_error_payload_is_empty():
    raw = json.dumps({"error": "web_search nie zwrocil wynikow", "query": "x"})
    assert sup._format_search_results(raw) == ""
    assert sup._format_search_results("nie-json") == ""
    assert sup._format_search_results("[]") == ""


def test_enqueue_dedupes_and_caps_queue(tmp_path, monkeypatch):
    monkeypatch.setattr(sup, "QUEUE_PATH", tmp_path / "queue.json")

    # Duplikat semantyczny nie wchodzi drugi raz.
    item = sup._proposal_to_queue_item(
        {"title": "A", "reason": "r", "risk": "low", "confidence": 90,
         "action": {"type": "web_search", "query": "kubernetes deployment strategie"}},
        "hourly_autoexec_limit",
    )
    assert sup._enqueue(dict(item))["added"] is True
    assert sup._enqueue(dict(item))["added"] is False

    # Kolejka jest przycinana do 100 pozycji.
    for i in range(130):
        unique = sup._proposal_to_queue_item(
            {"title": f"U{i}", "reason": "r", "risk": "low", "confidence": 90,
             "action": {"type": "web_search", "query": f"unikalny temat numer{i:03d} xyz"}},
            "hourly_autoexec_limit",
        )
        sup._enqueue(unique)
    queue = sup._read_json(sup.QUEUE_PATH, [])
    assert len(queue) <= 100


def test_recent_duplicate_detection(monkeypatch):
    state = {}
    action = {"type": "web_search", "query": "psychologia snu badania"}
    assert sup._is_action_recent_duplicate(state, action) is False
    sup._remember_action(state, action, title="Sen", source="test")
    assert sup._is_action_recent_duplicate(state, action) is True
    other = {"type": "web_search", "query": "kompilatory llvm optymalizacje"}
    assert sup._is_action_recent_duplicate(state, other) is False


def test_execute_low_risk_action_fails_on_empty_search(monkeypatch):
    import core.brain as brain

    monkeypatch.setattr(
        brain, "execute_tool_by_name",
        lambda name, args, mode="interactive": json.dumps({"error": "brak", "query": "x"}),
    )
    result = sup._execute_low_risk_action({"type": "web_search", "query": "cokolwiek"})
    assert result["ok"] is False


def test_execute_low_risk_action_writes_note_on_success(monkeypatch, tmp_path):
    import core.brain as brain

    payload = json.dumps([{"title": "T", "href": "https://x.pl", "body": "B"}])
    monkeypatch.setattr(
        brain, "execute_tool_by_name",
        lambda name, args, mode="interactive": payload,
    )
    # LLM niedostepny -> fallback na sformatowane wyniki.
    monkeypatch.setattr(sup, "_call_llm_text", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("llm off")))
    result = sup._execute_low_risk_action({"type": "web_search", "query": "temat testowy"})
    assert result["ok"] is True
    note_path = result["result"].split("note: ")[-1]
    content = open(note_path, encoding="utf-8").read()
    assert "Zrodlo: https://x.pl" in content

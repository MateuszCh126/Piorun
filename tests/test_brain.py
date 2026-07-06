import json

import core.brain as brain


class _EmptyDDGS:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def text(self, query, **kwargs):
        return []


class _GoodDDGS(_EmptyDDGS):
    def text(self, query, **kwargs):
        return [{"title": "T", "href": "https://x.pl", "body": "B"}]


class _BrokenDDGS(_EmptyDDGS):
    def text(self, query, **kwargs):
        raise RuntimeError("ratelimit")


def test_web_search_success(monkeypatch):
    monkeypatch.setattr(brain, "DDGS", _GoodDDGS)
    result = json.loads(brain._tool_web_search({"query": "cokolwiek"}, None))
    assert isinstance(result, list) and result[0]["href"] == "https://x.pl"


def test_web_search_empty_returns_error_payload(monkeypatch):
    monkeypatch.setattr(brain, "DDGS", _EmptyDDGS)
    monkeypatch.setattr(brain.time, "sleep", lambda _s: None)
    result = json.loads(brain._tool_web_search({"query": "cokolwiek"}, None))
    assert isinstance(result, dict) and "error" in result


def test_web_search_exception_returns_error_payload(monkeypatch):
    monkeypatch.setattr(brain, "DDGS", _BrokenDDGS)
    monkeypatch.setattr(brain.time, "sleep", lambda _s: None)
    result = json.loads(brain._tool_web_search({"query": "cokolwiek"}, None))
    assert isinstance(result, dict) and "ratelimit" in result["error"]


def test_strip_injected_summary_messages():
    history = [
        {"role": "system", "content": "prompt"},
        {"role": "system", "content": f"{brain.SUMMARY_SYSTEM_PREFIX}\nstare podsumowanie"},
        {"role": "user", "content": "pytanie"},
    ]
    cleaned = brain._strip_injected_summary_messages(history)
    assert len(cleaned) == 2
    assert all(not str(m.get("content", "")).startswith(brain.SUMMARY_SYSTEM_PREFIX) for m in cleaned)


def test_estimate_tokens_grows_with_content():
    small = brain._estimate_message_tokens({"role": "user", "content": "ab"})
    big = brain._estimate_message_tokens({"role": "user", "content": "x" * 4000})
    assert big > small

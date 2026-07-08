import json

import pytest

import tools.knowledge_index as ki
from core.config import get_settings

SETTINGS = get_settings()


@pytest.fixture(autouse=True)
def clean_fts():
    try:
        with ki._conn() as c:
            c.execute("DELETE FROM notes_fts")
            c.commit()
    except Exception:
        pass
    yield


def _make_session(tmp_path, name="2026-04-14_2031_BazyDanych", md="## Drzewa B+\nIndeks zgrupowany i haszowanie."):
    session = tmp_path / name
    session.mkdir()
    notes = [{"chunk_index": 0, "time_start": 0, "time_end": 300, "slide": None, "notes_markdown": md}]
    (session / "notes_structured.json").write_text(json.dumps(notes, ensure_ascii=False), encoding="utf-8")
    return str(session)


def test_index_and_search(tmp_path):
    ki.index_session(_make_session(tmp_path), "BazyDanych")
    hits = ki.search("drzewa")
    assert hits and hits[0]["subject"] == "BazyDanych"
    assert hits[0]["date"] == "2026-04-14"
    assert "Drzewa" in hits[0]["snippet"] or "drzewa" in hits[0]["snippet"].lower()


def test_search_no_match(tmp_path):
    ki.index_session(_make_session(tmp_path), "BazyDanych")
    assert ki.search("bigos") == []


def test_index_is_idempotent(tmp_path):
    session = _make_session(tmp_path)
    ki.index_session(session, "BazyDanych")
    ki.index_session(session, "BazyDanych")
    # Ten sam doc_id nie dubluje wynikow.
    assert len(ki.search("haszowanie")) == 1


def test_fts_query_sanitizes_quotes():
    assert ki._fts_query('drzewa "b+"') == '"drzewa" "b+"'
    assert ki._fts_query("   ") == ""


def test_format_for_human_empty():
    assert "Brak trafień" in ki.format_for_human("x", [])


def test_notes_for_subject(tmp_path, monkeypatch):
    obj = SETTINGS.notes_root / "Algo"
    obj.mkdir(parents=True, exist_ok=True)
    (obj / "2026-04-14.html").write_text("<html></html>", encoding="utf-8")
    (obj / "2026-04-21.html").write_text("<html></html>", encoding="utf-8")
    info = ki.notes_for_subject("Algo")
    assert info["count"] == 2
    assert info["latest"].endswith("2026-04-21.html")
    assert ki.notes_for_subject("NieistniejacyPrzedmiot")["count"] == 0

import json

import tools.flashcards as fc
from core.config import get_settings

SETTINGS = get_settings()

NOTES_MD = (
    "## Drzewa B+\n"
    "## Kluczowe pojęcia\n"
    "- **Indeks zgrupowany**: dane wg klucza\n"
    "- **Fill factor**: zapełnienie strony\n"
    "## Pytania kontrolne\n"
    "- Czym różni się indeks zgrupowany od nieklastrowanego?\n"
    "- Co to fill factor?\n"
    "## Podsumowanie tej części\n"
    "Krótko o indeksach.\n"
)


def test_extract_cards_pairs_questions_with_concepts():
    notes = [{"chunk_index": 0, "notes_markdown": NOTES_MD}]
    cards = fc.extract_cards_from_notes(notes, "BazyDanych", "2026-04-14")
    assert len(cards) == 2
    fronts = [c[0] for c in cards]
    assert any("indeks zgrupowany" in f.lower() for f in fronts)
    # tyl zawiera pojecia i odnosnik do zrodla
    assert "Indeks zgrupowany" in cards[0][1]
    assert "(BazyDanych, 2026-04-14)" in cards[0][1]
    # brak znakow rozbijajacych TSV
    assert all("\t" not in f and "\n" not in f for c in cards for f in c)


def test_no_questions_returns_empty():
    notes = [{"chunk_index": 0, "notes_markdown": "## Tytuł\nTreść bez pytań."}]
    assert fc.extract_cards_from_notes(notes, "X", "2026-01-01") == []


def test_export_tsv_writes_file(tmp_path):
    session = tmp_path / "2026-04-14_2031_BazyDanych"
    session.mkdir()
    (session / "notes_structured.json").write_text(
        json.dumps([{"chunk_index": 0, "notes_markdown": NOTES_MD}]), encoding="utf-8"
    )
    # export_tsv skanuje SETTINGS.sessions_root; podmieniamy na katalog testowy
    import tools.flashcards as fcmod
    orig = fcmod.SETTINGS
    try:
        fcmod.SETTINGS = orig.__class__(**{**orig.__dict__, "sessions_root": tmp_path})
        path, n = fcmod.export_tsv("BazyDanych")
    finally:
        fcmod.SETTINGS = orig
    assert n == 2 and path.endswith("flashcards.tsv")
    import os
    lines = open(path, encoding="utf-8").read().strip().split("\n")
    assert len(lines) == 2 and all("\t" in ln for ln in lines)


def test_export_tsv_no_cards(tmp_path):
    import tools.flashcards as fcmod
    orig = fcmod.SETTINGS
    try:
        fcmod.SETTINGS = orig.__class__(**{**orig.__dict__, "sessions_root": tmp_path})
        path, n = fcmod.export_tsv("Pusty")
    finally:
        fcmod.SETTINGS = orig
    assert path is None and n == 0

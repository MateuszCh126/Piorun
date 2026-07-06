import json
import os

import core.html_builder as hb


def test_markdown_to_html_headers_bold_lists():
    md = "## Sekcja\n**wazne** pojecie\n- punkt jeden\n- punkt dwa\n\nzwykly tekst"
    html = hb.markdown_to_html_simple(md)
    assert "<h2>Sekcja</h2>" in html
    assert "<strong>wazne</strong>" in html
    assert "<li>punkt jeden</li>" in html
    assert html.count("<ul>") == html.count("</ul>") == 1


def test_build_lecture_page_creates_html_and_index(tmp_path):
    session_dir = tmp_path / "2026-07-06_1200_TestPrzedmiot"
    session_dir.mkdir()
    notes = [
        {
            "chunk_index": 0,
            "time_start": 0,
            "time_end": 300,
            "slide": None,
            "notes_markdown": "## Wprowadzenie\n**Definicja**: cos waznego.",
        }
    ]
    (session_dir / "notes_structured.json").write_text(
        json.dumps(notes, ensure_ascii=False), encoding="utf-8"
    )

    out = hb.build_lecture_page(str(session_dir), "TestPrzedmiot")
    assert out is not None and os.path.exists(out)
    content = open(out, encoding="utf-8").read()
    assert "TestPrzedmiot" in content
    assert "<strong>Definicja</strong>" in content

    index_path = os.path.join(hb.NOTES_ROOT, "index.html")
    assert os.path.exists(index_path)
    assert "TestPrzedmiot" in open(index_path, encoding="utf-8").read()


def test_build_lecture_page_missing_notes_returns_none(tmp_path):
    empty_dir = tmp_path / "2026-07-06_1300_Pusta"
    empty_dir.mkdir()
    assert hb.build_lecture_page(str(empty_dir), "Pusta") is None

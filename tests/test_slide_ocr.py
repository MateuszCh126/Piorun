import json

import pytest
from PIL import Image

import tools.slide_ocr as ocr


class FakeOCR:
    """Udaje RapidOCR: zwraca (wynik, elapse). wynik = [[box, text, score], ...]."""

    def __call__(self, image_path):
        return ([[[0, 0], "Drzewa B+", 0.99], [[0, 20], "indeks zgrupowany", 0.98]], 0.01)


@pytest.fixture
def fake_ocr(monkeypatch):
    monkeypatch.setattr(ocr, "_OCR", FakeOCR())
    monkeypatch.setattr(ocr, "_OCR_TRIED", True)


def _make_slides(tmp_path, names):
    session = tmp_path / "2026-04-14_2031_Wyklad"
    slides = session / "slides"
    slides.mkdir(parents=True)
    for name in names:
        Image.new("RGB", (100, 60), (255, 255, 255)).save(slides / name, "JPEG")
    return str(session)


def test_ocr_image_joins_lines(fake_ocr, tmp_path):
    img = tmp_path / "s.jpg"
    Image.new("RGB", (100, 60), (255, 255, 255)).save(img, "JPEG")
    text = ocr.ocr_image(str(img))
    assert "Drzewa B+" in text and "indeks zgrupowany" in text


def test_ocr_image_missing_file_returns_empty(fake_ocr):
    assert ocr.ocr_image("nie_istnieje.jpg") == ""


def test_ocr_session_caches(fake_ocr, tmp_path):
    session = _make_slides(tmp_path, ["s0.jpg", "s1.jpg"])
    cache = ocr.ocr_session_slides(session)
    assert set(cache.keys()) == {"slides/s0.jpg", "slides/s1.jpg"}
    assert all("Drzewa B+" in v for v in cache.values())
    # cache zapisany na dysku
    import os
    assert os.path.exists(os.path.join(session, "ocr_cache.json"))
    on_disk = json.load(open(os.path.join(session, "ocr_cache.json"), encoding="utf-8"))
    assert on_disk == cache


def test_ocr_unavailable_graceful(monkeypatch):
    # Symuluj brak biblioteki: _get_ocr zwraca None.
    monkeypatch.setattr(ocr, "_OCR", None)
    monkeypatch.setattr(ocr, "_OCR_TRIED", True)
    assert ocr.ocr_available() is False
    assert ocr.ocr_image("cokolwiek.jpg") == ""


def test_get_slide_text_uses_cache(fake_ocr):
    cache = {"slides/x.jpg": "z cache"}
    assert ocr.get_slide_text("sess", "slides/x.jpg", cache) == "z cache"
    assert ocr.get_slide_text("sess", "", cache) == ""

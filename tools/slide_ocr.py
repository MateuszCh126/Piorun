"""OCR slajdow (opcjonalny). Uzywa rapidocr-onnxruntime, jesli jest zainstalowany.

Gdy biblioteki brak - graceful fallback: zwraca pusty tekst i loguje raz,
nigdy nie wywala pipeline'u notatek. Wynik cache'owany per sesja w ocr_cache.json,
zeby ponowne /process nie liczylo OCR drugi raz.
"""
import json
import os

_OCR = None
_OCR_TRIED = False


def _get_ocr():
    global _OCR, _OCR_TRIED
    if _OCR_TRIED:
        return _OCR
    _OCR_TRIED = True
    try:
        from rapidocr_onnxruntime import RapidOCR

        _OCR = RapidOCR()
    except Exception as e:
        print(f"[!] slide_ocr: rapidocr niedostepny ({e}); OCR slajdow pominiety.")
        _OCR = None
    return _OCR


def ocr_available() -> bool:
    return _get_ocr() is not None


def ocr_image(image_path: str) -> str:
    """Zwraca tekst wykryty na obrazie (linie polaczone \\n) lub '' przy braku/bledzie."""
    ocr = _get_ocr()
    if ocr is None or not image_path or not os.path.exists(image_path):
        return ""
    try:
        result, _elapse = ocr(image_path)
    except Exception as e:
        print(f"[!] slide_ocr: blad OCR {os.path.basename(image_path)}: {e}")
        return ""
    if not result:
        return ""
    lines = []
    for item in result:
        # RapidOCR: [box, text, score]
        if len(item) > 1 and item[1]:
            text = str(item[1]).strip()
            if text:
                lines.append(text)
    return "\n".join(lines)


def ocr_session_slides(session_dir: str) -> dict:
    """OCR wszystkich slajdow sesji, z cache. Zwraca {'slides/plik.jpg': tekst}."""
    cache_path = os.path.join(session_dir, "ocr_cache.json")
    cache = {}
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                cache = json.load(f)
        except Exception:
            cache = {}

    slides_dir = os.path.join(session_dir, "slides")
    if not os.path.isdir(slides_dir):
        return cache

    changed = False
    for name in sorted(os.listdir(slides_dir)):
        rel = f"slides/{name}"
        if rel in cache:
            continue
        cache[rel] = ocr_image(os.path.join(slides_dir, name))
        changed = True

    if changed:
        try:
            with open(cache_path, "w", encoding="utf-8") as f:
                json.dump(cache, f, ensure_ascii=False, indent=2)
        except Exception:
            pass
    return cache


def get_slide_text(session_dir: str, slide_rel: str, cache: dict | None = None) -> str:
    if not slide_rel:
        return ""
    if cache is not None and slide_rel in cache:
        return cache[slide_rel]
    return ocr_image(os.path.join(session_dir, slide_rel))

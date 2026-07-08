"""Fiszki z notatek wykladowych (4.2).

Wyciaga sekcje 'Pytania kontrolne' (przod) i laczy z 'kluczowymi pojeciami'
tego samego fragmentu (tyl) -> TSV importowalny do Anki (Basic: front<TAB>back).
Komenda /flashcards <przedmiot>.
"""
import json
import os
import re

try:
    from core.config import get_settings
except ModuleNotFoundError:
    import sys

    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from core.config import get_settings

SETTINGS = get_settings()


def _is_header(line: str) -> bool:
    s = line.strip()
    return s.startswith("#") or (s.startswith("**") and s.endswith("**") and len(s) > 4)


def _section_items(md: str, needle: str) -> list:
    """Elementy listy pod naglowkiem zawierajacym `needle` (do nastepnego naglowka)."""
    items, capturing = [], False
    for line in str(md or "").split("\n"):
        if _is_header(line):
            capturing = needle in line.strip().lower()
            continue
        s = line.strip()
        if not (capturing and s):
            continue
        if s.startswith("- "):
            items.append(s[2:].strip())
        elif re.match(r"^\d+[.)]\s+", s):
            items.append(re.sub(r"^\d+[.)]\s+", "", s).strip())
    return items


def _clean(text: str) -> str:
    return str(text or "").replace("**", "").replace("\t", " ").replace("\n", " ").strip()


def extract_cards_from_notes(notes, subject, date):
    cards = []
    ref = f"({subject}, {date})"
    for chunk in notes:
        if not isinstance(chunk, dict):
            continue
        md = chunk.get("notes_markdown", "")
        questions = _section_items(md, "pytania")
        concepts = _section_items(md, "kluczow")
        back_concepts = "; ".join(_clean(c) for c in concepts[:6])
        for q in questions:
            front = _clean(q)
            if not front:
                continue
            back = (f"{back_concepts}  " if back_concepts else "") + ref
            cards.append((front, _clean(back)))
    return cards


def build_flashcards(subject):
    cards = []
    sessions_root = str(SETTINGS.sessions_root)
    if not os.path.isdir(sessions_root):
        return cards
    for name in sorted(os.listdir(sessions_root)):
        if subject.lower() not in name.lower():
            continue
        notes_path = os.path.join(sessions_root, name, "notes_structured.json")
        if not os.path.exists(notes_path):
            continue
        try:
            with open(notes_path, "r", encoding="utf-8") as f:
                notes = json.load(f)
        except Exception:
            continue
        cards.extend(extract_cards_from_notes(notes, subject, name[:10]))
    return cards


def export_tsv(subject):
    """Zapisuje fiszki do notes/<subject>/flashcards.tsv. Zwraca (sciezka, liczba)."""
    cards = build_flashcards(subject)
    if not cards:
        return None, 0
    obj_dir = SETTINGS.notes_root / str(subject)
    obj_dir.mkdir(parents=True, exist_ok=True)
    out = obj_dir / "flashcards.tsv"
    with open(out, "w", encoding="utf-8") as f:
        for front, back in cards:
            f.write(f"{front}\t{back}\n")
    return str(out), len(cards)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Uzycie: python flashcards.py <przedmiot>")
    else:
        path, n = export_tsv(sys.argv[1])
        print(f"[OK] {n} fiszek: {path}" if path else "[!] Brak pytan kontrolnych dla tego przedmiotu.")

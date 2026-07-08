"""Ewaluacja jakosci notatek wg rubryki (6.1).

Deterministyczny scorer: sprawdza, czy wygenerowane notatki maja wymagane
sekcje (naglowek, kluczowe pojecia, pytania kontrolne, podsumowanie).
Uruchamiany recznie po zmianie promptu note_generatora, zeby zmierzyc
regresje/poprawe zamiast wierzyc na slowo.

Uzycie: python -m tools.notes_eval <sciezka_do_sesji>
"""
import json
import os
import re

_RUBRIC = {
    "heading": lambda md: bool(re.search(r"(?m)^##\s+\S", md)),
    "concepts": lambda md: "**" in md,
    "questions": lambda md: "pytania" in md.lower(),
    "summary": lambda md: "podsumowanie" in md.lower(),
}


def score_notes(notes):
    """Zwraca {item: frakcja_chunkow_spelniajacych} + 'overall'."""
    chunks = [c for c in notes if isinstance(c, dict)]
    if not chunks:
        return {k: 0.0 for k in _RUBRIC} | {"overall": 0.0, "chunks": 0}
    scores = {}
    for item, check in _RUBRIC.items():
        passed = sum(1 for c in chunks if check(str(c.get("notes_markdown", ""))))
        scores[item] = round(passed / len(chunks), 3)
    scores["overall"] = round(sum(scores[k] for k in _RUBRIC) / len(_RUBRIC), 3)
    scores["chunks"] = len(chunks)
    return scores


def evaluate_session(session_dir):
    notes_path = os.path.join(session_dir, "notes_structured.json")
    if not os.path.exists(notes_path):
        return None
    with open(notes_path, "r", encoding="utf-8") as f:
        notes = json.load(f)
    return score_notes(notes)


def _print_report(session_dir, scores):
    print(f"\n=== EWALUACJA NOTATEK: {os.path.basename(session_dir)} ===")
    if not scores:
        print("[!] Brak notes_structured.json")
        return
    for item in _RUBRIC:
        print(f"  {item:12s}: {scores[item] * 100:5.1f}%")
    print(f"  {'OVERALL':12s}: {scores['overall'] * 100:5.1f}% ({scores['chunks']} chunkow)")


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 2:
        print("Uzycie: python -m tools.notes_eval <sciezka_do_sesji>")
    else:
        _print_report(sys.argv[1], evaluate_session(sys.argv[1]))

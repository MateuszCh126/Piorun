"""Quiz z notatek wykladowych (4.5).

Pytania pochodza z 'Pytan kontrolnych' (deterministycznie, przez flashcards);
ocena odpowiedzi idzie przez LLM. Rdzen (wybor pytan, parsowanie oceny, petla)
jest testowalny bez LLM - grader jest wstrzykiwany.
"""
import json
import random
import re


def select_questions(subject, n=5):
    """Unikalne pytania kontrolne dla przedmiotu (przod, oczekiwane pojecia)."""
    import tools.flashcards as fc

    cards = fc.build_flashcards(subject)
    seen, uniq = set(), []
    for front, back in cards:
        key = front.lower().strip()
        if key in seen:
            continue
        seen.add(key)
        uniq.append((front, back))
    random.shuffle(uniq)
    return uniq[: max(1, int(n))]


def _parse_grade(text):
    match = re.search(r"\{[\s\S]*\}", text or "")
    if match:
        try:
            d = json.loads(match.group(0))
            return {
                "score": max(0, min(100, int(d.get("score", 0)))),
                "feedback": str(d.get("feedback", "")).strip(),
            }
        except Exception:
            pass
    return {"score": 0, "feedback": "Nie udalo sie ocenic odpowiedzi."}


def grade_answer(question, expected, answer):
    import core.brain as brain

    prompt = (
        f"Pytanie: {question}\n"
        f"Oczekiwane pojecia/odpowiedz: {expected}\n"
        f"Odpowiedz ucznia: {answer}\n\n"
        "Ocen odpowiedz w skali 0-100 i podaj krotka informacje zwrotna po polsku. "
        'Zwroc TYLKO JSON: {"score": <0-100>, "feedback": "..."}'
    )
    resp = brain.client.chat.completions.create(
        model=brain.MODEL_NAME,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.2,
        timeout=60,
    )
    return _parse_grade(getattr(resp.choices[0].message, "content", "") or "")


def run_quiz(subject, n=5, input_fn=input, output_fn=print, grader=None):
    grader = grader or grade_answer
    questions = select_questions(subject, n)
    if not questions:
        output_fn(f"[!] Brak pytan kontrolnych dla: {subject}")
        return None

    results = []
    for i, (q, expected) in enumerate(questions, start=1):
        output_fn(f"\n[{i}/{len(questions)}] {q}")
        answer = input_fn("Twoja odpowiedz: ")
        grade = grader(q, expected, answer)
        output_fn(f"  Ocena: {grade['score']}/100 — {grade['feedback']}")
        results.append({"question": q, "score": grade["score"]})

    avg = sum(r["score"] for r in results) / len(results)
    weak = [r["question"] for r in results if r["score"] < 60]
    output_fn(f"\n[WYNIK] Srednia: {avg:.0f}/100 z {len(results)} pytan.")
    if weak:
        output_fn(f"[SLABE OBSZARY] {len(weak)} pytan do powtorki.")
    return {"average": avg, "results": results, "weak": weak}

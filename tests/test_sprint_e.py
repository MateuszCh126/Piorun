import json

import core.config as cfg


# --- 6.3 profile backendu LLM ----------------------------------------------

def test_llm_profile_sets_base_url(monkeypatch):
    monkeypatch.setattr(cfg, "_bootstrap_env", lambda: None)  # pomin .env
    monkeypatch.setenv("PIORUN_LLM_PROFILE", "ollama")
    monkeypatch.delenv("PIORUN_LLM_BASE_URL", raising=False)
    s = cfg._build_settings()
    assert s.llm_profile == "ollama"
    assert "11434" in s.llama_base_url


def test_llm_explicit_base_url_wins(monkeypatch):
    monkeypatch.setattr(cfg, "_bootstrap_env", lambda: None)
    monkeypatch.setenv("PIORUN_LLM_PROFILE", "lmstudio")
    monkeypatch.setenv("PIORUN_LLM_BASE_URL", "http://custom:9999/v1")
    s = cfg._build_settings()
    assert s.llama_base_url == "http://custom:9999/v1"


# --- 6.4 budzet kontekstu per zadanie --------------------------------------

def test_context_budget_larger_for_notes():
    import core.brain as brain
    from core.config import get_settings

    s = get_settings()
    assert s.context_max_tokens_notes > s.context_max_tokens

    history = [{"role": "system", "content": "s"}] + [{"role": "user", "content": "x" * 3000} for _ in range(20)]
    chat = brain.manage_context_window([dict(m) for m in history], session_id=None, topic="Rozmowa")
    notes = brain.manage_context_window([dict(m) for m in history], session_id=None, topic="Notatki Bazy")
    assert len(notes) > len(chat)  # notatki dostaja wieksze okno -> mniej kompresji


# --- 2.5 petla zwrotna plannera (odrzucenia) -------------------------------

def test_recent_rejections_block():
    import core.autonomy_supervisor as sup

    path = sup.DECISIONS_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(json.dumps({"kind": "queue_decision", "decision": "REJECTED", "reason": "za duzo o krypto"}) + "\n")
        f.write(json.dumps({"kind": "queue_decision", "decision": "APPROVED"}) + "\n")
        f.write(json.dumps({"kind": "queue_decision", "decision": "REJECTED", "reason": "nudne newsy"}) + "\n")
    block = sup._recent_rejections_prompt_block(limit=5)
    assert "za duzo o krypto" in block and "nudne newsy" in block


# --- 4.5 quiz (rdzen bez LLM) ----------------------------------------------

def test_quiz_select_questions(monkeypatch):
    import tools.quiz as quiz

    monkeypatch.setattr(
        "tools.flashcards.build_flashcards",
        lambda subject: [("Pytanie A", "pojecia A"), ("Pytanie A", "dup"), ("Pytanie B", "pojecia B")],
    )
    qs = quiz.select_questions("X", n=5)
    fronts = [q[0] for q in qs]
    assert set(fronts) == {"Pytanie A", "Pytanie B"}  # dedup


def test_quiz_parse_grade():
    import tools.quiz as quiz

    assert quiz._parse_grade('{"score": 85, "feedback": "dobrze"}') == {"score": 85, "feedback": "dobrze"}
    assert quiz._parse_grade("smieci")["score"] == 0
    assert quiz._parse_grade('{"score": 500}')["score"] == 100  # clamp


def test_quiz_run_scores_and_weak(monkeypatch):
    import tools.quiz as quiz

    monkeypatch.setattr(quiz, "select_questions", lambda subject, n=5: [("Q1", "e1"), ("Q2", "e2")])
    out = []
    result = quiz.run_quiz(
        "X", n=2,
        input_fn=lambda _p: "odp",
        output_fn=out.append,
        grader=lambda q, e, a: {"score": 40 if q == "Q1" else 90, "feedback": "ok"},
    )
    assert result["average"] == 65
    assert result["weak"] == ["Q1"]


# --- 6.1 ewaluacja notatek --------------------------------------------------

def test_notes_eval_scores():
    import tools.notes_eval as ev

    notes = [
        {"notes_markdown": "## Sekcja\n**Pojecie**\n## Pytania kontrolne\n- Q?\n## Podsumowanie\ntekst"},
        {"notes_markdown": "zwykly tekst bez struktury"},
    ]
    scores = ev.score_notes(notes)
    assert scores["heading"] == 0.5  # 1 z 2 chunkow ma naglowek
    assert scores["questions"] == 0.5
    assert 0.0 < scores["overall"] < 1.0
    assert ev.score_notes([])["overall"] == 0.0


# --- 5.2 wyszukiwarka dashboardu -------------------------------------------

def test_dashboard_has_search():
    import core.html_builder as hb

    obj = hb.NOTES_ROOT
    import os
    os.makedirs(os.path.join(obj, "Algo"), exist_ok=True)
    with open(os.path.join(obj, "Algo", "2026-04-14.html"), "w", encoding="utf-8") as f:
        f.write("<html></html>")
    hb.update_index()
    index_html = open(os.path.join(obj, "index.html"), encoding="utf-8").read()
    assert 'id="searchBox"' in index_html
    assert "addEventListener('input'" in index_html
    assert "Algo" in index_html

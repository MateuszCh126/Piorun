import hashlib
import json
import math

import pytest

import tools.vector_memory as vm


# --- falszywy embedder: deterministyczny wektor z hasha, zero sieci --------

def _fake_vector(text: str) -> list[float]:
    digest = hashlib.sha256(text.encode("utf-8")).digest()
    vec = [b / 255.0 for b in digest[:16]]
    norm = math.sqrt(sum(x * x for x in vec)) or 1.0
    return [x / norm for x in vec]


from chromadb.api.types import EmbeddingFunction


class FakeEmbedder(EmbeddingFunction):
    def __call__(self, input):
        return [_fake_vector(t) for t in input]

    @staticmethod
    def name():
        return "fake-embedder"


@pytest.fixture(autouse=True)
def fake_embeddings(monkeypatch):
    monkeypatch.setitem(vm._EF_CACHE, "ef", FakeEmbedder())
    monkeypatch.setitem(vm._EF_CACHE, "model_name", "fake-test-model")


@pytest.fixture(autouse=True)
def memory_enabled(monkeypatch):
    # conftest wylacza pamiec globalnie (hooki jako no-op w innych testach);
    # tu wlaczamy ja z powrotem, bo testujemy wlasnie te warstwe.
    monkeypatch.setattr(
        vm, "SETTINGS", vm.SETTINGS.__class__(**{**vm.SETTINGS.__dict__, "memory_recall_enabled": True})
    )


@pytest.fixture(autouse=True)
def clean_collections():
    yield
    client = vm._get_client()
    for name in vm.COLLECTIONS:
        try:
            client.delete_collection(name)
        except Exception:
            pass


# --- chunkowanie ------------------------------------------------------------

def test_split_markdown_respects_max_len():
    text = "Zdanie pierwsze jest tutaj. " * 200  # ~5600 znakow, bez naglowkow
    pieces = vm.split_markdown_chunk(text, max_len=1500)
    assert all(len(p) <= 1500 for p in pieces)
    # ciecie po zdaniu: kazdy kawalek (poza ostatnim) konczy sie kropka
    assert all(p.rstrip().endswith(".") for p in pieces[:-1])


def test_split_markdown_merges_crumbs():
    text = "## A\n" + ("tresc sekcji A. " * 60) + "\n## B\nkrotki okruch"
    pieces = vm.split_markdown_chunk(text, max_len=1500)
    assert all(len(p) >= vm._MIN_CHUNK for p in pieces[1:]) or len(pieces) == 1


def test_split_markdown_edge_cases():
    assert vm.split_markdown_chunk("") == []
    assert vm.split_markdown_chunk("   \n  ") == []
    short = "## Naglowek\ntrochę treści"
    assert vm.split_markdown_chunk(short) == [short]


def test_split_note_sections_parses_blocks():
    md = (
        "\n## 18:48:19 | Autonomy Research: temat A\n"
        "tresc A linia 1\ntresc A linia 2\n"
        "\n## 19:02:33 | Notatka B\n"
        "tresc B\n"
        "\n## 20:00:00 | Pusta sekcja\n"
    )
    sections = vm.split_note_sections(md)
    assert len(sections) == 2
    assert sections[0].time_tag == "18:48:19"
    assert sections[0].title == "Autonomy Research: temat A"
    assert "tresc A linia 2" in sections[0].content
    assert sections[1].title == "Notatka B"


# --- upserty ----------------------------------------------------------------

def _make_session(tmp_path, name="2026-04-14_2031_TestWyklad"):
    session_dir = tmp_path / name
    session_dir.mkdir()
    notes = [
        {
            "chunk_index": 0,
            "time_start": 0,
            "time_end": 300,
            "slide": "slides/s1.jpg",
            "notes_markdown": "## Drzewa B+\n**Indeks zgrupowany**: dane ułożone wg klucza.",
        },
        {
            "chunk_index": 1,
            "time_start": 300,
            "time_end": 600,
            "slide": None,
            "notes_markdown": "## Haszowanie\n**Funkcja haszująca**: odwzorowanie klucza.",
        },
    ]
    (session_dir / "notes_structured.json").write_text(
        json.dumps(notes, ensure_ascii=False), encoding="utf-8"
    )
    return str(session_dir)


def test_upsert_lecture_idempotent(tmp_path):
    session_dir = _make_session(tmp_path)
    n1 = vm.upsert_lecture_session(session_dir, "Bazy Danych")
    n2 = vm.upsert_lecture_session(session_dir, "Bazy Danych")
    assert n1 == n2 == 2
    assert vm.get_collection("lecture_notes").count() == 2


def test_upsert_research_note_ids_stable():
    args = dict(title="Research X", content="tresc notatki", date="2026-07-07", time_tag="08:00:00")
    assert vm.upsert_research_note(**args) == 1
    assert vm.upsert_research_note(**args) == 1
    assert vm.get_collection("research_notes").count() == 1


def test_conversation_summary_single_doc():
    vm.upsert_conversation_summary("SESS_1", "Temat", "Podsumowanie pierwsze.")
    vm.upsert_conversation_summary("SESS_1", "Temat", "Podsumowanie nowsze.")
    collection = vm.get_collection("session_summaries")
    assert collection.count() == 1
    stored = collection.get(ids=["conv::SESS_1"])
    assert stored["documents"][0] == "Podsumowanie nowsze."


# --- recall -----------------------------------------------------------------

def test_recall_kind_filter(tmp_path):
    vm.upsert_lecture_session(_make_session(tmp_path), "Bazy Danych")
    vm.upsert_research_note(title="R", content="tresc research", date="2026-07-07", time_tag="09:00:00")
    hits = vm.recall("Drzewa B+ indeks zgrupowany", kind="lecture", max_distance=2.0)
    assert hits and all(h.kind == "lecture" for h in hits)


def test_recall_distance_cutoff(tmp_path):
    vm.upsert_lecture_session(_make_session(tmp_path), "Bazy Danych")
    assert vm.recall("cokolwiek", max_distance=0.0) == []


def test_recall_exact_text_is_closest(tmp_path):
    vm.upsert_lecture_session(_make_session(tmp_path), "Bazy Danych")
    # Falszywy embedder = hash, wiec identyczny tekst ma dystans ~0.
    exact = "## Drzewa B+\n**Indeks zgrupowany**: dane ułożone wg klucza."
    hits = vm.recall(exact, max_distance=0.01)
    assert hits and hits[0].distance < 0.01
    assert "Drzewa B+" in hits[0].document
    assert hits[0].source.startswith("wykład | Bazy Danych | 2026-04-14")


def test_recall_empty_db_returns_empty():
    assert vm.recall("cokolwiek") == []
    assert vm.format_recall_for_llm([]) == vm.NO_MEMORIES_MESSAGE
    assert vm.NO_MEMORIES_MESSAGE in vm.format_recall_for_human([])


def test_model_mismatch_raises(monkeypatch):
    vm.get_collection("lecture_notes")  # utworzona modelem fake-test-model
    monkeypatch.setitem(vm._EF_CACHE, "model_name", "inny-model")
    with pytest.raises(vm.EmbeddingModelMismatch):
        vm.get_collection("lecture_notes")


def test_recall_disabled_flag(tmp_path, monkeypatch):
    session_dir = _make_session(tmp_path)
    vm.upsert_lecture_session(session_dir, "Bazy Danych")
    monkeypatch.setattr(
        vm, "SETTINGS", vm.SETTINGS.__class__(**{**vm.SETTINGS.__dict__, "memory_recall_enabled": False})
    )
    assert vm.recall("Drzewa B+") == []
    assert vm.upsert_lecture_session(session_dir, "Bazy Danych") == 0
    assert vm.upsert_research_note("t", "c", "2026-07-07", "10:00:00") == 0


def test_recall_infra_error_returns_empty(monkeypatch):
    def _boom(name):
        raise RuntimeError("uszkodzony klient")

    monkeypatch.setattr(vm, "get_collection", _boom)
    assert vm.recall("cokolwiek") == []


def test_format_recall_for_llm_shows_source(tmp_path):
    vm.upsert_research_note(
        title="Autonomy Research: GPU", content="fakty o GPU", date="2026-07-07", time_tag="11:00:00"
    )
    hits = vm.recall("Autonomy Research: GPU\nfakty o GPU", max_distance=0.01)
    text = vm.format_recall_for_llm(hits)
    assert text.startswith("[research | 2026-07-07 | Autonomy Research: GPU]")

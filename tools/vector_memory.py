"""Pamiec wektorowa Pioruna (projekt: docs/vector-memory-design.md).

Cztery kolekcje chromadb (cosine): lecture_notes, research_notes,
session_summaries, documents. Deterministyczne ID = idempotentne upserty.
Zasada nadrzedna: pamiec jest ulepszeniem, nie zaleznoscia - awaria tej
warstwy nigdy nie psuje operacji glownej (notatki, rozmowy).
"""
import hashlib
import json
import os
import re
import threading
from dataclasses import dataclass
from datetime import datetime

import chromadb

try:
    from core.config import get_settings
except ModuleNotFoundError:
    import sys

    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from core.config import get_settings

SETTINGS = get_settings()

COLLECTIONS = ("lecture_notes", "research_notes", "session_summaries", "documents")
_KIND_TO_COLLECTION = {
    "lecture": "lecture_notes",
    "research": "research_notes",
    "conversation": "session_summaries",
    "document": "documents",
}
_MIN_CHUNK = 300
_MAX_CHUNK = 1500


class EmbeddingModelMismatch(RuntimeError):
    """Kolekcja byla budowana innym modelem embeddingow niz skonfigurowany."""


@dataclass(frozen=True)
class RecallHit:
    document: str
    distance: float
    kind: str
    source: str
    metadata: dict


@dataclass(frozen=True)
class NoteSection:
    time_tag: str
    title: str
    content: str


# --- infrastruktura -------------------------------------------------------

_EF_LOCK = threading.Lock()
_EF_CACHE: dict = {"ef": None, "model_name": None}
_CLIENT = None


def _load_embedding_function():
    """Zwraca (embedding_function, model_name). Model laduje sie raz na proces."""
    with _EF_LOCK:
        if _EF_CACHE["ef"] is not None:
            return _EF_CACHE["ef"], _EF_CACHE["model_name"]
        model_name = SETTINGS.memory_embedding_model
        try:
            from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

            ef = SentenceTransformerEmbeddingFunction(model_name=model_name)
        except Exception as e:
            print(
                f"[!] vector_memory: model '{model_name}' niedostepny ({e}); "
                "fallback na wbudowany model angielski - jakosc PL obnizona."
            )
            from chromadb.utils import embedding_functions

            ef = embedding_functions.DefaultEmbeddingFunction()
            model_name = "default-all-MiniLM-L6-v2"
        _EF_CACHE["ef"] = ef
        _EF_CACHE["model_name"] = model_name
        return ef, model_name


def _get_client():
    global _CLIENT
    if _CLIENT is None:
        _CLIENT = chromadb.PersistentClient(path=str(SETTINGS.memory_vector_db))
    return _CLIENT


def get_collection(name: str):
    """Kolekcja z przestrzenia cosine i wersjonowaniem modelu embeddingow.

    Raises: EmbeddingModelMismatch, gdy istniejaca kolekcja byla budowana
    innym modelem (mieszanie przestrzeni embeddingow po cichu psuje wyniki).
    """
    ef, model_name = _load_embedding_function()
    client = _get_client()
    collection = client.get_or_create_collection(
        name=name,
        embedding_function=ef,
        metadata={"hnsw:space": "cosine", "embedding_model": model_name},
    )
    existing_model = str((collection.metadata or {}).get("embedding_model", ""))
    if existing_model and existing_model != model_name:
        raise EmbeddingModelMismatch(
            f"Kolekcja '{name}' zbudowana modelem '{existing_model}', "
            f"skonfigurowany '{model_name}'. "
            "Uruchom: python scripts/reindex_memory.py --wipe --all"
        )
    return collection


def collection_stats() -> dict:
    """Licznosc i model per kolekcja - dla komendy doctor i skryptu reindex."""
    stats = {}
    for name in COLLECTIONS:
        try:
            collection = get_collection(name)
            stats[name] = {
                "count": collection.count(),
                "embedding_model": str((collection.metadata or {}).get("embedding_model", "")),
            }
        except Exception as e:
            stats[name] = {"error": str(e)}
    return stats


# --- chunkowanie (czyste funkcje) -----------------------------------------

def _hard_split(text: str, max_len: int) -> list[str]:
    """Tnie sciane tekstu; cofa ciecie do konca zdania/linii, min. 200 znakow."""
    out = []
    rest = text.strip()
    while len(rest) > max_len:
        window = rest[:max_len]
        cut = max(window.rfind(". "), window.rfind("\n"))
        cut = cut + 1 if cut >= 200 else max_len
        out.append(rest[:cut].strip())
        rest = rest[cut:].strip()
    if rest:
        out.append(rest)
    return out


def split_markdown_chunk(text: str, max_len: int = _MAX_CHUNK) -> list[str]:
    """Dzieli fragment markdownu: naglowki '##' -> akapity -> twarde ciecie.

    Nigdy nie tnie w srodku zdania; okruchy (< _MIN_CHUNK) scala z poprzednikiem.
    """
    text = (text or "").strip()
    if not text:
        return []
    if len(text) <= max_len:
        return [text]

    pieces: list[str] = []
    blocks = [b.strip() for b in re.split(r"(?m)(?=^##\s)", text) if b.strip()]
    for block in blocks:
        if len(block) <= max_len:
            pieces.append(block)
            continue
        for para in re.split(r"\n\s*\n", block):
            para = para.strip()
            if not para:
                continue
            if len(para) <= max_len:
                pieces.append(para)
            else:
                pieces.extend(_hard_split(para, max_len))

    merged: list[str] = []
    for piece in pieces:
        if merged and (
            len(piece) < _MIN_CHUNK or len(merged[-1]) < _MIN_CHUNK
        ) and len(merged[-1]) + len(piece) + 1 <= max_len:
            merged[-1] = f"{merged[-1]}\n{piece}"
        else:
            merged.append(piece)
    return merged


_SECTION_RE = re.compile(r"^##\s+(\d{2}:\d{2}:\d{2})\s*\|\s*(.+?)\s*$")


def split_note_sections(md_text: str) -> list[NoteSection]:
    """Parsuje bloki '## HH:MM:SS | tytul' z plikow autonomy_notes."""
    sections: list[NoteSection] = []
    current: dict | None = None

    def _close():
        if current and current["content"].strip():
            sections.append(
                NoteSection(current["time"], current["title"], current["content"].strip())
            )

    for line in (md_text or "").splitlines():
        match = _SECTION_RE.match(line)
        if match:
            _close()
            current = {"time": match.group(1), "title": match.group(2), "content": ""}
        elif current is not None:
            current["content"] += line + "\n"
    _close()
    return sections


# --- zapis ----------------------------------------------------------------

def _upsert(collection, ids, documents, metadatas) -> int:
    if not ids:
        return 0
    collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    return len(ids)


def upsert_lecture_session(session_dir: str, subject: str) -> int:
    """Indeksuje notes_structured.json jednej sesji. Zwraca liczbe dokumentow."""
    if not SETTINGS.memory_recall_enabled:
        return 0
    notes_path = os.path.join(session_dir, "notes_structured.json")
    if not os.path.exists(notes_path):
        return 0
    with open(notes_path, "r", encoding="utf-8") as f:
        chunks = json.load(f)

    session = os.path.basename(os.path.normpath(session_dir))
    date = session[:10]
    ids, documents, metadatas = [], [], []
    for chunk in chunks:
        if not isinstance(chunk, dict):
            continue
        chunk_index = int(chunk.get("chunk_index", 0))
        for i, piece in enumerate(split_markdown_chunk(str(chunk.get("notes_markdown", "")))):
            ids.append(f"lec::{session}::{chunk_index}::{i}")
            documents.append(piece)
            metadatas.append(
                {
                    "kind": "lecture",
                    "subject": str(subject),
                    "session": session,
                    "date": date,
                    "time_start": int(chunk.get("time_start", 0)),
                    "time_end": int(chunk.get("time_end", 0)),
                    "slide": str(chunk.get("slide") or ""),
                }
            )
    return _upsert(get_collection("lecture_notes"), ids, documents, metadatas)


def upsert_research_note(title: str, content: str, date: str, time_tag: str) -> int:
    """Indeksuje jedna sekcje notatki autonomii."""
    if not SETTINGS.memory_recall_enabled:
        return 0
    title = str(title or "").strip()
    content = str(content or "").strip()
    if not content:
        return 0
    digest = hashlib.sha1(f"{title}|{time_tag}".encode("utf-8")).hexdigest()[:10]
    base_id = f"res::{date}::{digest}"
    pieces = split_markdown_chunk(f"{title}\n{content}")
    ids = [base_id if len(pieces) == 1 else f"{base_id}::{i}" for i in range(len(pieces))]
    metadatas = [
        {"kind": "research", "title": title, "date": str(date), "time_tag": str(time_tag)}
        for _ in pieces
    ]
    return _upsert(get_collection("research_notes"), ids, pieces, metadatas)


def upsert_conversation_summary(session_id: str, topic: str, summary_text: str) -> int:
    """Indeksuje podsumowanie sesji (1 dokument na sesje, nadpisywany)."""
    if not SETTINGS.memory_recall_enabled:
        return 0
    summary_text = str(summary_text or "").strip()
    if not summary_text:
        return 0
    return _upsert(
        get_collection("session_summaries"),
        [f"conv::{session_id}"],
        [summary_text],
        [
            {
                "kind": "conversation",
                "topic": str(topic or ""),
                "updated_at": datetime.now().isoformat(timespec="seconds"),
            }
        ],
    )


# --- odczyt ---------------------------------------------------------------

def _format_seconds(seconds: int) -> str:
    seconds = int(seconds)
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def _format_source(metadata: dict) -> str:
    kind = str(metadata.get("kind", ""))
    if kind == "lecture":
        return (
            f"wykład | {metadata.get('subject', '')} | {metadata.get('date', '')} | "
            f"{_format_seconds(metadata.get('time_start', 0))}-{_format_seconds(metadata.get('time_end', 0))}"
        )
    if kind == "research":
        return f"research | {metadata.get('date', '')} | {metadata.get('title', '')}"
    if kind == "conversation":
        return f"rozmowa | {metadata.get('topic', '')} | {str(metadata.get('updated_at', ''))[:10]}"
    return f"plik | {metadata.get('path', '')}"


def recall(query: str, kind: str | None = None, top_k: int = 5,
           max_distance: float | None = None) -> list[RecallHit]:
    """Semantyczne wyszukiwanie we wszystkich kolekcjach (lub jednej po kind).

    Nigdy nie rzuca wyjatku do rozmowy: blad infrastruktury -> [] + log.
    """
    if not SETTINGS.memory_recall_enabled:
        return []
    query = str(query or "").strip()
    if not query:
        return []
    top_k = max(1, min(int(top_k), 10))
    if max_distance is None:
        max_distance = float(SETTINGS.memory_recall_max_distance)

    names = [_KIND_TO_COLLECTION[kind]] if kind in _KIND_TO_COLLECTION else list(COLLECTIONS)
    hits: list[RecallHit] = []
    for name in names:
        try:
            collection = get_collection(name)
            count = collection.count()
            if count == 0:
                continue
            result = collection.query(
                query_texts=[query],
                n_results=min(top_k, count),
                include=["documents", "metadatas", "distances"],
            )
            for doc, meta, dist in zip(
                result["documents"][0], result["metadatas"][0], result["distances"][0]
            ):
                if dist is None or float(dist) > max_distance:
                    continue
                meta = meta or {}
                hits.append(
                    RecallHit(
                        document=str(doc),
                        distance=float(dist),
                        kind=str(meta.get("kind", name)),
                        source=_format_source(meta),
                        metadata=dict(meta),
                    )
                )
        except Exception as e:
            print(f"[!] vector_memory.recall ({name}): {e}")
            continue
    hits.sort(key=lambda h: h.distance)
    return hits[:top_k]


NO_MEMORIES_MESSAGE = "Brak wspomnień pasujących do zapytania."


def format_recall_for_llm(hits: list[RecallHit]) -> str:
    if not hits:
        return NO_MEMORIES_MESSAGE
    return "\n\n".join(f"[{h.source}]\n{h.document}" for h in hits)


def format_recall_for_human(hits: list[RecallHit]) -> str:
    if not hits:
        return f"[PAMIĘĆ] {NO_MEMORIES_MESSAGE}"
    lines = [f"[PAMIĘĆ] {len(hits)} trafień:"]
    for i, h in enumerate(hits, start=1):
        preview = h.document.replace("\n", " ")
        if len(preview) > 160:
            preview = preview[:157] + "..."
        lines.append(f"{i}. ({h.distance:.2f}) {h.source}")
        lines.append(f"   {preview}")
        if h.kind == "lecture":
            subject = str(h.metadata.get("subject", ""))
            date = str(h.metadata.get("date", ""))
            if subject and date:
                lines.append(f"   → {SETTINGS.notes_root / subject / (date + '.html')}")
    return "\n".join(lines)

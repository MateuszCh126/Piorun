import os
import sqlite3

import chromadb
from chromadb.utils import embedding_functions

import core.db_schema as db_schema

try:
    from core.config import get_settings
except ModuleNotFoundError:
    import sys

    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from core.config import get_settings

SETTINGS = get_settings()
HISTORY_DB = str(SETTINGS.history_db)
MEMORY_VECTOR_DB = str(SETTINGS.memory_vector_db)


def get_db_connection():
    db_schema.ensure_history_db(HISTORY_DB)
    conn = sqlite3.connect(HISTORY_DB, timeout=20)
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA synchronous=NORMAL;")
    return conn


def search_global_history(query):
    """Przeszukuje cala historie (wszystkie sesje) pod katem slow kluczowych."""
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            search_term = f"%{query}%"
            cursor.execute(
                """
                SELECT session_id, role, content, timestamp
                FROM history
                WHERE content LIKE ?
                ORDER BY timestamp DESC LIMIT 10
                """,
                (search_term,),
            )
            rows = cursor.fetchall()
        if not rows:
            return f"Nie znaleziono wzmianek o '{query}' w historii globalnej."
        results = [f"[{r[3]}] Sesja: {r[0]} | {r[1]}: {r[2]}" for r in rows]
        return "\n---\n".join(results)
    except Exception as e:
        return f"Blad przeszukiwania pamieci: {e}"


def get_session_message_count(session_id):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM history WHERE session_id = ?", (session_id,))
            row = cursor.fetchone()
            return int(row[0]) if row else 0
    except Exception:
        return 0


def get_session_summary(session_id):
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT summary_text, message_count, updated_at FROM session_summaries WHERE session_id = ?",
                (session_id,),
            )
            row = cursor.fetchone()
        if not row:
            return None
        return {"summary_text": row[0], "message_count": int(row[1] or 0), "updated_at": row[2]}
    except Exception:
        return None


def list_recent_session_summaries(limit=5):
    limit = max(1, min(int(limit), 100))
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT session_id, topic, summary_text, message_count, updated_at
                FROM session_summaries
                ORDER BY updated_at DESC
                LIMIT ?
                """,
                (limit,),
            )
            rows = cursor.fetchall()
        return [
            {
                "session_id": str(r[0]),
                "topic": str(r[1] or ""),
                "summary_text": str(r[2] or ""),
                "message_count": int(r[3] or 0),
                "updated_at": str(r[4] or ""),
            }
            for r in rows
        ]
    except Exception:
        return []


def upsert_session_summary(session_id, topic, summary_text, message_count):
    with get_db_connection() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO session_summaries (session_id, topic, summary_text, message_count, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(session_id) DO UPDATE SET
                topic = excluded.topic,
                summary_text = excluded.summary_text,
                message_count = excluded.message_count,
                updated_at = CURRENT_TIMESTAMP
            """,
            (session_id, topic, summary_text, int(message_count)),
        )
        conn.commit()


def _clip(text, max_len=200):
    if text is None:
        return ""
    text = str(text).strip().replace("\n", " ")
    if len(text) <= max_len:
        return text
    return text[: max_len - 3] + "..."


def _build_summary_text(topic, user_msgs, assistant_msgs, total_msgs):
    parts = []
    if topic:
        parts.append(f"Temat sesji: {topic}.")
    parts.append(f"Liczba wiadomosci: {total_msgs}.")
    if user_msgs:
        joined_user = " | ".join(_clip(m, 180) for m in user_msgs[-3:])
        parts.append(f"Ostatnie intencje uzytkownika: {joined_user}.")
    if assistant_msgs:
        joined_assistant = " | ".join(_clip(m, 180) for m in assistant_msgs[-3:])
        parts.append(f"Ostatnie odpowiedzi/asercje agenta: {joined_assistant}.")
    return " ".join(parts)


def refresh_session_summary(session_id, topic="", recent_limit=40):
    """
    Tworzy zwiezle podsumowanie sesji na bazie ostatnich wiadomosci
    i zapisuje je w tabeli session_summaries.
    """
    try:
        with get_db_connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT role, content
                FROM history
                WHERE session_id = ?
                ORDER BY id DESC
                LIMIT ?
                """,
                (session_id, int(recent_limit)),
            )
            rows = cursor.fetchall()
        if not rows:
            return None

        rows = list(reversed(rows))
        user_msgs = [r[1] for r in rows if r[0] == "user"]
        assistant_msgs = [r[1] for r in rows if r[0] == "assistant"]
        total_msgs = get_session_message_count(session_id)
        summary_text = _build_summary_text(topic, user_msgs, assistant_msgs, total_msgs)
        upsert_session_summary(session_id, topic, summary_text, total_msgs)
        # Indeks pamieci wektorowej - nigdy nie blokuje odswiezenia summary.
        try:
            import tools.vector_memory as vector_memory

            vector_memory.upsert_conversation_summary(session_id, topic, summary_text)
        except Exception:
            pass
        return summary_text
    except Exception as e:
        return f"Blad odswiezania summary sesji: {e}"


# Uzywamy domyslnego modelu (lekki i darmowy, dziala lokalnie)
default_ef = embedding_functions.DefaultEmbeddingFunction()


def get_client():
    return chromadb.PersistentClient(path=MEMORY_VECTOR_DB)


def index_file(collection_name, path):
    """Indeksuje tresc pliku w bazie wektorowej."""
    client = get_client()
    collection = client.get_or_create_collection(name=collection_name, embedding_function=default_ef)

    try:
        with open(path, "r", encoding="utf-8") as f:
            content = f.read()

        chunks = [content[i : i + 1000] for i in range(0, len(content), 1000)]
        ids = [f"{path}_chunk_{i}" for i in range(len(chunks))]
        metadatas = [{"path": path} for _ in range(len(chunks))]

        collection.add(documents=chunks, metadatas=metadatas, ids=ids)
        return f"Zindeksowano {len(chunks)} fragmentow z {path}."
    except Exception as e:
        return f"Blad indeksowania {path}: {str(e)}"


def search_memory(collection_name, query, n_results=3):
    """Wyszukuje najbardziej pasujace fragmenty kodu/tekstu."""
    client = get_client()
    collection = client.get_collection(name=collection_name, embedding_function=default_ef)

    results = collection.query(query_texts=[query], n_results=n_results)

    formatted = ""
    for i in range(len(results["documents"][0])):
        path = results["metadatas"][0][i]["path"]
        doc = results["documents"][0][i]
        formatted += f"--- PLIK: {path} ---\n{doc}\n\n"

    return formatted if formatted else "Nie znaleziono nic pasujacego."


if __name__ == "__main__":
    print("Inicjalizacja pamieci...")

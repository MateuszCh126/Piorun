# Pamięć wektorowa Pioruna — projekt struktury i plan wdrożenia

Stan na: 2026-07-06. Dokument projektowy dla zadania **4.4 z ROADMAP** (pamięć
wektorowa w rozmowie). Sam projekt — bez implementacji.

## 0. Fakty zastane (zweryfikowane w repo i na maszynie)

- W `tools/memory.py` istnieje **zalążek**: `chromadb.PersistentClient` na
  ścieżce `SETTINGS.memory_vector_db` (`.memory_db/`, dziś pusty katalog),
  funkcje `index_file` / `search_memory` z naiwnym chunkowaniem co 1000 znaków.
  Używa ich wyłącznie legacy `gemma_agent_v3.py` — w działającej aplikacji
  pamięć wektorowa jest martwa.
- Embedding: `DefaultEmbeddingFunction` = **all-MiniLM-L6-v2 (ONNX, angielski)**
  — słaby do polskich notatek z wykładów. To główny powód przeprojektowania.
- Na maszynie jest już **torch 2.12 (CUDA 12.8)** i onnxruntime → doinstalowanie
  `sentence-transformers` jest tanie (bez pobierania torcha) i pójdzie na GPU.
- `.memory_db/` nie jest śledzony przez git (pliki chromy łapią wzorce
  `*.sqlite3`/`*.bin`), ale **brakuje jawnego wpisu `.memory_db/` w
  `.gitignore`** — do dodania przy wdrożeniu.
- Treści do zindeksowania już istnieją i mają naturalną strukturę:
  notatki wykładowe (`notes_structured.json` — fragmenty po ~5 minut),
  notatki researchu autonomii (`autonomy_notes/*.md` — sekcje z nagłówkami),
  podsumowania sesji rozmów (SQLite `session_summaries`).

## 1. Po co ta baza (3 przypadki użycia)

1. **Recall w rozmowie** — Piorun dostaje narzędzie `recall`: „co mówiliśmy
   o drzewach B+?" znajduje fragment notatki z wykładu sprzed miesiąca, mimo że
   padły inne słowa. Uzupełnia (nie zastępuje) `search_global_history` (LIKE)
   i planowane FTS5 (zad. 4.1): LIKE/FTS = dokładne frazy, wektor = znaczenie.
2. **Kontekst autonomii** — planner przed zaproponowaniem researchu sprawdza,
   co już wiemy na dany temat (mniej powtórek, głębsze follow-upy).
3. **Baza pod quiz/fiszki (4.2, 4.5)** — wyszukiwanie materiału do pytań
   z całego przedmiotu, nie tylko jednej sesji.

## 2. Struktura bazy

Jeden `PersistentClient` (ścieżka jak dziś: `SETTINGS.memory_vector_db`),
**cztery kolekcje**. Wszystkie tworzone z `metadata={"hnsw:space": "cosine"}`
— uwaga: domyślna przestrzeń chromy to L2, dla embeddingów zdaniowych chcemy
cosine.

### 2.1 Kolekcja `lecture_notes` (rdzeń wartości)

Dokument = markdown jednego fragmentu notatki (naturalny podział po ~5 min już
istnieje w `notes_structured.json`; fragmenty > 1500 znaków tniemy dodatkowo po
nagłówkach `##`/liniach, nigdy w środku zdania).

| Pole | Przykład | Uwagi |
|---|---|---|
| id | `lec::2026-04-14_2031_Wyklad::3::0` | `lec::<folder_sesji>::<chunk_index>::<subchunk>` — deterministyczne → ponowne indeksowanie nadpisuje (upsert), zero duplikatów |
| document | „## Drzewa B+…" | tekst fragmentu |
| subject | `Algorytmy` | z nazwy folderu sesji |
| session | `2026-04-14_2031_Wyklad` | klucz do źródła |
| date | `2026-04-14` | ISO, do filtrów `where` |
| time_start / time_end | `900` / `1200` | sekundy — link do miejsca w wykładzie |
| slide | `slides/slide_0004_930s.jpg` | opcjonalnie |
| kind | `lecture` | wspólne pole wszystkich kolekcji |

### 2.2 Kolekcja `research_notes`

Dokument = jedna sekcja notatki autonomii (blok `## HH:MM:SS | tytuł`).

| Pole | Przykład |
|---|---|
| id | `res::2026-07-06::sha1(tytuł+godzina)[:10]` |
| title | `Autonomy Research: faster-whisper GPU…` |
| date | `2026-07-06` |
| kind | `research` |

### 2.3 Kolekcja `session_summaries`

Dokument = `summary_text` z SQLite (surowa historia rozmów jest za szumna —
indeksujemy podsumowania, które już utrzymujemy).

| Pole | Przykład |
|---|---|
| id | `conv::SESS_20260706_1830` (1 dokument na sesję, upsert przy odświeżeniu) |
| topic | `Pytania o grafy` |
| updated_at | ISO |
| kind | `conversation` |

### 2.4 Kolekcja `documents` (zachowanie zgodności)

Obecne `index_file`/`search_memory` (dowolne pliki, np. kod projektu) — zostaje,
ale przechodzi na wspólny schemat ID (`doc::<ścieżka>::<i>`) i upsert.

### 2.5 Embedding — decyzja

**Rekomendacja: `paraphrase-multilingual-MiniLM-L12-v2`** przez
`SentenceTransformerEmbeddingFunction` (sentence-transformers).

- Za: wielojęzyczny (polski!), 118M parametrów — na RTX z torch cu128 embeddingi
  liczą się w milisekundach; sprawdzony standard; zero prefiksów-pułapek.
- Alternatywa rozważona: `intfloat/multilingual-e5-small` — nieco lepsza jakość,
  ale wymaga prefiksów `query:`/`passage:` (łatwo o cichą degradację, gdy ktoś
  zapomni) → odrzucona na start, można podmienić później dzięki wersjonowaniu.
- Fallback: gdy `sentence-transformers` nieobecne → `DefaultEmbeddingFunction`
  z głośnym ostrzeżeniem w logu i w `doctor` (system działa, jakość PL słaba).

**Wersjonowanie:** każda kolekcja dostaje w metadanych
`embedding_model: "<nazwa>"`. Moduł przy starcie porównuje z konfiguracją —
niezgodność = twardy błąd z komunikatem „uruchom reindex" (mieszanie przestrzeni
embeddingów po cichu psuje wyniki; to ma być niemożliwe).

## 3. Przepływy danych

### Zapis (indeksowanie przyrostowe, synchronidzne — pojedyncza notatka to <1 s)

1. `note_generator.generate_academic_notes` — po zapisaniu
   `notes_structured.json` → `upsert_lecture_session(session_dir, subject)`.
2. `autonomy_supervisor._append_note` — po dopisaniu sekcji →
   `upsert_research_note(title, content, date, time)`.
3. `memory.refresh_session_summary` — po upsercie w SQLite →
   `upsert_conversation_summary(session_id, topic, summary_text)`.
4. **Backfill**: `scripts/reindex_memory.py [--all | --lectures | --research |
   --conversations]` — iteruje istniejące `sessions/`, `autonomy_notes/`
   i `session_summaries`; idempotentny (deterministyczne ID + upsert), więc
   można odpalać wielokrotnie; wypisuje licznik dokumentów per kolekcja.

Błąd indeksowania NIGDY nie wywala głównej operacji (notatka > indeks):
hooki łapią wyjątki i logują ostrzeżenie.

### Odczyt

**Narzędzie `recall` dla modelu** (rejestrowane w `core/brain.py`, dozwolone
też w trybie autonomicznym — jest read-only):

- parametry: `query` (wymagane), `kind` (opcjonalny filtr: lecture / research /
  conversation), `top_k` (domyślnie 5, max 10);
- zapytanie idzie do wszystkich (lub przefiltrowanych) kolekcji, wyniki łączone
  i sortowane po dystansie; odcinamy `distance > 0.65` (cosine; próg do
  skalibrowania na realnych danych przy wdrożeniu — patrz krok 7);
- format wyniku dla modelu: `[wykład | Algorytmy | 2026-04-14 | 15:00-20:00]
  <fragment>` — źródło zawsze na wierzchu, żeby model cytował, nie zmyślał;
- pusta odpowiedź zwraca jawne „Brak wspomnień pasujących do zapytania"
  (nie pusty string — model ma wiedzieć, że szukał).

**Komenda `/recall <fraza>` w CLI** — ten sam kod, wynik dla człowieka z linkami
do plików HTML notatek. (Planner autonomii podpinamy dopiero po okresie próbnym
recall w rozmowie — osobna decyzja, żeby nie wydłużać promptu od razu.)

## 4. Konfiguracja (nowe zmienne w `.env.example`)

```
PIORUN_MEMORY_EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2
PIORUN_MEMORY_RECALL_TOP_K=5
PIORUN_MEMORY_RECALL_MAX_DISTANCE=0.65
```

Plus istniejące `PIORUN_MEMORY_VECTOR_DB` (ścieżka bazy — bez zmian).

## 5. Jak to dodać — plan implementacji krok po kroku

Kolejność zaprojektowana tak, by każdy krok był osobno testowalny i osobno
commitowalny; łącznie ~1 wieczór + kalibracja.

| Krok | Co | Pliki | Rozmiar |
|---|---|---|---|
| 1 | `pip install sentence-transformers` + wpis w `requirements.txt`; `.memory_db/` jawnie do `.gitignore` | requirements, .gitignore | S |
| 2 | Nowy moduł `tools/vector_memory.py`: `get_collection(name)` (cosine + weryfikacja `embedding_model`), `_load_embedding_function()` (ST z fallbackiem), czyste funkcje chunkowania (`split_markdown_chunk`, `split_note_sections`), `upsert_lecture_session`, `upsert_research_note`, `upsert_conversation_summary`, `recall`, `format_recall_for_llm` | nowy plik | M |
| 3 | Testy jednostkowe z **fałszywym embedderem** (deterministyczny wektor z hasha — zero pobierania modeli w testach): idempotencja upsertów, chunkowanie, filtr `kind`, próg dystansu, wykrycie niezgodności modelu | `tests/test_vector_memory.py` | M |
| 4 | `scripts/reindex_memory.py` (backfill z licznikami) + **przebieg na realnych danych** z repo (`sessions/`, `autonomy_notes/`) | nowy plik | S |
| 5 | Hooki zapisu (3 linie każdy, w try/except): `note_generator`, `autonomy_supervisor._append_note`, `memory.refresh_session_summary` | 3 istniejące pliki | S |
| 6 | Narzędzie `recall` w `core/brain.py` (ToolDefinition + handler) i komenda `/recall` w `piorun.py` | 2 istniejące pliki | S |
| 7 | **Kalibracja progu**: 10 ręcznych zapytań o treści, o których wiadomo, że są w notatkach + 5 o treści, których nie ma; dobór `MAX_DISTANCE`, żeby te drugie zwracały „brak” | — | S |
| 8 | `doctor` (gdy powstanie, zad. 3.2): liczność kolekcji + zgodność modelu embeddingów; wpis w README i CHANGELOG | doki | S |

**Kryterium ukończenia:** (a) `reindex --all` przechodzi na istniejących danych
i raportuje >0 dokumentów w 3 kolekcjach; (b) pytanie w rozmowie o temat
z kwietniowego wykładu zwraca właściwy fragment z metryczką źródła;
(c) pytanie o temat spoza notatek zwraca „brak wspomnień", nie halucynację;
(d) pytest zielony bez dostępu do sieci.

## 6. Ryzyka i decyzje odłożone

1. **Pierwsze pobranie modelu embeddingów (~120 MB)** — jednorazowe, przy
   pierwszym użyciu; `doctor` powinien to pokazywać jako osobny check.
2. **Dryf treści** — edycja/kasowanie notatki ręcznie na dysku zostawia stary
   wektor; akceptowalne (notatki są append-only), pełny `reindex` czyści.
   Świadomie NIE budujemy synchronizacji plik-po-pliku.
3. **Backup** — baza jest w 100% odtwarzalna z plików źródłowych przez
   `reindex`, więc NIE wchodzi do backupów (`ops_runtime.create_backup` bez zmian).
4. **Odłożone**: indeksowanie surowej historii rozmów (szum), rerank
   cross-encoderem (przerost na tę skalę), embeddingi przez llama.cpp
   `/v1/embeddings` (Gemma to model generatywny, nie embeddingowy — jakość
   nieprzewidywalna).

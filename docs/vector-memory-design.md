# Pamięć wektorowa Pioruna — projekt struktury i plan wdrożenia

Stan na: 2026-07-06 (wersja rozszerzona). Dokument projektowy dla zadania
**4.4 z ROADMAP** (pamięć wektorowa w rozmowie).
Zakres: struktura bazy, pełna specyfikacja API, algorytmy, kalibracja, testy,
tryby awarii, prywatność, decyzje architektoniczne i 12-krokowy plan wdrożenia.

> **Status wdrożenia (2026-07-07): kroki 1-8 i 11 ZREALIZOWANE.**
> Moduł `tools/vector_memory.py`, 15 testów, `scripts/reindex_memory.py`,
> hooki, narzędzie `recall` + `/recall` — działa. Backfill na realnych danych:
> 39 dokumentów research + 9 podsumowań (lecture_notes=0, bo żadna sesja nie
> była dotąd przetworzona do notatek). Żywa weryfikacja: zapytanie o zagrożenia
> cyber → dystans 0.29; „przepis na bigos" → „brak wspomnień". Odkryty i
> naprawiony bug środowiska: pakiet `chromadb-client` wymuszał tryb http-only
> (PersistentClient nigdy nie działał — stąd pusty `.memory_db`).
> Do zrobienia: krok 9 (kalibracja progu wg sekcji 8 — wymaga dziesiątek
> realnych zapytań właściciela), krok 10 (`doctor` — powstanie w zad. 3.2),
> krok 12 (pomiar po tygodniu użycia).

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
niezgodność = twardy błąd `EmbeddingModelMismatch` z komunikatem „uruchom
reindex" (mieszanie przestrzeni embeddingów po cichu psuje wyniki; to ma być
niemożliwe).

## 3. Specyfikacja API modułu `tools/vector_memory.py`

Kontrakt do implementacji wprost. Moduł nie importuje `core.brain`
(brak cyklu importów — to brain importuje vector_memory, nie odwrotnie).

```python
class EmbeddingModelMismatch(RuntimeError):
    """Kolekcja była budowana innym modelem embeddingów niż skonfigurowany."""

@dataclass(frozen=True)
class RecallHit:
    document: str      # tekst fragmentu
    distance: float    # cosine distance; mniejsza = bliższa (0 = identyczne)
    kind: str          # "lecture" | "research" | "conversation" | "document"
    source: str        # gotowy opis źródła, np. "wykład | Algorytmy | 2026-04-14 | 15:00-20:00"
    metadata: dict     # pełne metadane dokumentu

@dataclass(frozen=True)
class NoteSection:
    time_tag: str      # "18:48:19"
    title: str         # "Autonomy Research: ..."
    content: str       # treść sekcji bez nagłówka

# --- infrastruktura ---
def _load_embedding_function():
    """ST(PIORUN_MEMORY_EMBEDDING_MODEL) albo DefaultEmbeddingFunction + warning.
    Wynik cache'owany w module (model ładuje się raz na proces)."""

def get_collection(name: str):
    """get_or_create z hnsw:space=cosine i metadanym embedding_model.
    Raises: EmbeddingModelMismatch gdy istniejąca kolekcja ma inny model."""

def collection_stats() -> dict:
    """{'lecture_notes': {'count': 214, 'embedding_model': '...'}, ...} — dla doctor."""

# --- chunkowanie (czyste funkcje, bez I/O — patrz sekcja 4) ---
def split_markdown_chunk(text: str, max_len: int = 1500) -> list[str]
def split_note_sections(md_text: str) -> list[NoteSection]

# --- zapis (wszystkie zwracają liczbę upsertowanych dokumentów; nie rzucają
#     wyjątków na uszkodzone pojedyncze rekordy — logują i liczą dalej) ---
def upsert_lecture_session(session_dir: str, subject: str) -> int
def upsert_research_note(title: str, content: str, date: str, time_tag: str) -> int
def upsert_conversation_summary(session_id: str, topic: str, summary_text: str) -> int

# --- odczyt ---
def recall(query: str, kind: str | None = None, top_k: int = 5,
           max_distance: float | None = None) -> list[RecallHit]:
    """Zapytanie do wszystkich kolekcji (lub jednej, gdy kind podany), scalenie
    po distance rosnąco, odcięcie > max_distance (domyślnie z configu),
    przycięcie do top_k. Pusta baza / brak trafień → []. Nigdy nie rzuca
    wyjątku do rozmowy — błąd infrastruktury zwraca [] i loguje."""

def format_recall_for_llm(hits: list[RecallHit]) -> str:
    """'[źródło]\\n<fragment>' po jednym na trafienie; dla [] zwraca
    'Brak wspomnień pasujących do zapytania.' (model ma wiedzieć, że szukał)."""

def format_recall_for_human(hits: list[RecallHit]) -> str:
    """Wersja dla /recall w CLI: numeracja, dystans, ścieżka do HTML notatki."""
```

Feature flag: `PIORUN_MEMORY_RECALL_ENABLED` (domyślnie `true`) — gdy `false`,
`recall` zwraca `[]`, hooki zapisu nic nie robią, narzędzie nie jest
rejestrowane w brain. Rollback bez revertu kodu.

## 4. Algorytmy chunkowania (pseudokod)

### 4.1 `split_markdown_chunk(text, max_len=1500)`

```
jeśli len(text) <= max_len: zwróć [text]
kawałki = podziel text na bloki po nagłówkach "## " (nagłówek zostaje z blokiem)
jeśli jakikolwiek blok > max_len:
    dziel ten blok po pustych liniach (granice akapitów)
    jeśli akapit nadal > max_len:                # ściana tekstu bez struktury
        tnij twardo co max_len, ale cofnij cięcie do ostatniej kropki/nowej linii
        (nigdy w środku zdania; minimum 200 zn., żeby nie produkować okruchów)
scal sąsiednie kawałki < 300 zn. z poprzednikiem (okruchy psują ranking)
zwróć listę kawałków
```

Przypadki brzegowe: tekst pusty → `[]`; sam nagłówek bez treści → scalony
z następnym; tekst bez żadnych nagłówków → ścieżka akapitowa.

### 4.2 `split_note_sections(md_text)`

```
sekcje = []
dla każdej linii pasującej do r"^## (\d{2}:\d{2}:\d{2}) \| (.+)$":
    zamknij poprzednią sekcję, otwórz nową (time_tag, title)
linie przed pierwszym nagłówkiem → ignoruj (nagłówek pliku)
sekcje z pustą treścią → pomiń
zwróć [NoteSection(...)]
```

Format wejścia jest gwarantowany przez `autonomy_supervisor._append_note`
(to my go piszemy) — parser i tak toleruje odstępstwa (pomija, nie wywala się).

## 5. Przepływy danych

### 5.1 Diagram

```
ZAPIS (przyrostowy, synchroniczny — pojedyncza notatka < 1 s)

 note_generator                autonomy_supervisor          memory.refresh_
 .generate_academic_notes      ._append_note                session_summary
        │ (po zapisie JSON)          │ (po dopisaniu sekcji)      │ (po upsercie SQLite)
        ▼                            ▼                            ▼
 upsert_lecture_session      upsert_research_note      upsert_conversation_summary
        │                            │                            │
        └──────────── try/except: błąd indeksu = warning w logu, ─┘
                      operacja główna NIGDY nie pada przez indeks
                                     │
                                     ▼
                        chromadb PersistentClient (.memory_db)
                 [lecture_notes] [research_notes] [session_summaries] [documents]
                                     ▲
        scripts/reindex_memory.py ───┘  (backfill; idempotentny — te same ID)

ODCZYT

 rozmowa (LLM) ── narzędzie "recall" ──► recall() ──► format_recall_for_llm
 CLI /recall ────────────────────────► recall() ──► format_recall_for_human
 planner autonomii (etap późniejszy) ► recall(kind="research"|"lecture")
```

### 5.2 Zapis — szczegóły

1. `note_generator.generate_academic_notes` — po zapisaniu
   `notes_structured.json` → `upsert_lecture_session(session_dir, subject)`.
2. `autonomy_supervisor._append_note` — po dopisaniu sekcji →
   `upsert_research_note(title, content, date, time)`.
3. `memory.refresh_session_summary` — po upsercie w SQLite →
   `upsert_conversation_summary(session_id, topic, summary_text)`.
4. **Backfill**: `scripts/reindex_memory.py [--all | --lectures | --research |
   --conversations]` — iteruje istniejące `sessions/`, `autonomy_notes/`
   i `session_summaries`; idempotentny (deterministyczne ID + upsert), więc
   można odpalać wielokrotnie; wypisuje licznik dokumentów per kolekcja;
   `--wipe` kasuje kolekcję przed budową (jedyna droga po zmianie modelu).

### 5.3 Odczyt — szczegóły

**Narzędzie `recall` dla modelu** (rejestrowane w `core/brain.py`, dozwolone
też w trybie autonomicznym — jest read-only):

- parametry: `query` (wymagane), `kind` (opcjonalny filtr: lecture / research /
  conversation), `top_k` (domyślnie 5, max 10);
- zapytanie idzie do wszystkich (lub przefiltrowanych) kolekcji, wyniki łączone
  i sortowane po dystansie; odcinamy `distance > 0.65` (cosine; próg do
  kalibracji — sekcja 8);
- format wyniku dla modelu: `[wykład | Algorytmy | 2026-04-14 | 15:00-20:00]
  <fragment>` — źródło zawsze na wierzchu, żeby model cytował, nie zmyślał;
- pusta odpowiedź zwraca jawne „Brak wspomnień pasujących do zapytania"
  (nie pusty string — model ma wiedzieć, że szukał).

**Komenda `/recall <fraza>` w CLI** — ten sam kod, wynik dla człowieka z linkami
do plików HTML notatek. (Planner autonomii podpinamy dopiero po okresie próbnym
recall w rozmowie — osobna decyzja, żeby nie wydłużać promptu od razu.)

## 6. Wyszukiwanie hybrydowe — styk z FTS5 (zad. 4.1)

FTS5 (dokładne frazy, definicje, nazwy własne) i wektor (parafrazy, „o czym
było…") mają się uzupełniać, nie konkurować:

- Wspólny interfejs wyników: `RecallHit` — moduł FTS (gdy powstanie) zwraca
  ten sam kształt z `distance` zmapowanym z rankingu BM25 na [0,1].
- Scalanie przez **Reciprocal Rank Fusion**: `score(d) = Σ 1/(60 + rank_i(d))`
  po obu listach; dokument obecny w obu rankingach naturalnie wypływa na górę.
  RRF nie wymaga normalizacji niekompatybilnych miar — dlatego on, a nie
  ważona suma.
- `/find` (FTS, dokładne) i `/recall` (wektor, semantyczne) zostają osobnymi
  komendami; hybryda wchodzi tylko do narzędzia `recall` dla modelu, gdy oba
  indeksy istnieją. Do tego czasu `recall` działa czysto wektorowo — zero
  zależności między zadaniami 4.1 i 4.4.

## 7. Konfiguracja (nowe zmienne w `.env.example`)

```
PIORUN_MEMORY_RECALL_ENABLED=true
PIORUN_MEMORY_EMBEDDING_MODEL=paraphrase-multilingual-MiniLM-L12-v2
PIORUN_MEMORY_RECALL_TOP_K=5
PIORUN_MEMORY_RECALL_MAX_DISTANCE=0.65
```

Plus istniejące `PIORUN_MEMORY_VECTOR_DB` (ścieżka bazy — bez zmian).
Nowe pola w `core/config.py` (`Settings`): `memory_recall_enabled`,
`memory_embedding_model`, `memory_recall_top_k`, `memory_recall_max_distance`.

## 8. Kalibracja progu dystansu (protokół)

Domyślne 0.65 to punkt startowy — właściwy próg wyznaczamy raz, na realnych
danych, po backfillu (krok 9 planu wdrożenia):

1. Ułóż **10 zapytań pozytywnych** — o treści, które NA PEWNO są w notatkach
   (wzięte z kwietniowych sesji i notatek autonomii), sformułowane INNYMI
   słowami niż oryginał (testujemy semantykę, nie frazy).
2. Ułóż **5 zapytań negatywnych** — o treści, których w bazie nie ma
   (np. „przepis na bigos", „historia Rzymu").
3. Uruchom `recall` z `max_distance=1.0` (bez odcięcia) i zapisz najlepszy
   dystans dla każdego zapytania do tabeli:

| # | Zapytanie | Typ | Najlepszy dystans | Trafienie sensowne? |
|---|---|---|---|---|
| 1 | … | poz. | 0.43 | tak |
| … | … | neg. | 0.81 | — |

4. **Reguła wyboru progu:** największa wartość, przy której wszystkie
   negatywne dają „brak wspomnień", z marginesem 0.05 poniżej najlepszego
   negatywnego. Jeśli przedziały pozytywnych i negatywnych się przecinają —
   zgłoś to jako sygnał do zmiany modelu embeddingów (e5), nie do żonglowania
   progiem.
5. Wynik kalibracji (data, model, próg, tabela) dopisz do tego dokumentu.

## 9. Szacunki wydajności i pojemności

Rząd wielkości (2 wykłady/tydzień po 90 min + autonomia):

| Miara | Dziś | Po roku |
|---|---|---|
| chunki lecture_notes | ~40 (3 sesje testowe) | ~3 500 (100 wykładów × ~35) |
| sekcje research_notes | ~30 | ~2 000 |
| podsumowania sesji | ~20 | ~500 |
| wektory łącznie (384 wym., fp32) | < 1 MB | ~9 MB |
| baza na dysku (chroma sqlite+hnsw) | < 10 MB | 50–100 MB |

Czas embeddingu MiniLM-L12 (118M): pojedynczy chunk **< 5 ms na GPU**
(torch cu128 już jest), ~50 ms na CPU. Pełny backfill roku danych: sekundy na
GPU, < 5 min na CPU. Zapytanie `recall` (1 embedding + 4 × HNSW na tysiącach
wektorów): **< 100 ms** — pomijalne przy sekundach inferencji Gemmy.

**Wniosek:** skala jest trywialna dla domyślnego HNSW chromy; żadnego
tuningu indeksu, shardingu ani kwantyzacji nie projektujemy. Jedyny realny
koszt to jednorazowe pobranie modelu (~120 MB) i ~500 MB RAM na załadowany
model w procesie.

## 10. Macierz testów

Testy jednostkowe używają **fałszywego embeddera** (deterministyczny wektor
z sha256 tekstu, wymiar 16) — zero pobierania modeli i sieci w pytest;
baza chroma w katalogu tymczasowym (conftest już izoluje `PIORUN_*`).

| Test | Weryfikuje | Typ |
|---|---|---|
| `test_split_markdown_respects_max_len` | brak kawałka > max_len; cięcie po zdaniu | unit |
| `test_split_markdown_merges_crumbs` | scalanie okruchów < 300 zn. | unit |
| `test_split_markdown_edge_cases` | pusty tekst, sam nagłówek, ściana tekstu | unit |
| `test_split_note_sections_parses_blocks` | parsowanie `## HH:MM:SS \| tytuł` | unit |
| `test_upsert_lecture_idempotent` | 2× ten sam session_dir → count bez zmian | unit |
| `test_upsert_research_note_ids_stable` | deterministyczne ID sekcji | unit |
| `test_conversation_summary_single_doc` | upsert nadpisuje, 1 dok/sesję | unit |
| `test_recall_kind_filter` | `kind="lecture"` nie zwraca research | unit |
| `test_recall_distance_cutoff` | trafienia > max_distance odcięte | unit |
| `test_recall_empty_db_returns_empty` | pusta baza → `[]`, format → „Brak wspomnień…" | unit |
| `test_model_mismatch_raises` | kolekcja z innym `embedding_model` → wyjątek | unit |
| `test_recall_disabled_flag` | flaga off → `[]`, hooki no-op | unit |
| `test_recall_infra_error_returns_empty` | uszkodzony klient → `[]` + log, bez wyjątku | unit |
| `reindex --all` na realnych sesjach z repo | backfill end-to-end, liczniki > 0 | integracyjny (ręczny) |
| protokół kalibracji (sekcja 8) | jakość rankingu na realnych danych | manualny, jednorazowy |

## 11. Tryby awarii i degradacji

| Objaw | Zachowanie systemu | Naprawa |
|---|---|---|
| brak `sentence-transformers` | fallback na DefaultEmbeddingFunction + WARNING w logu i w `doctor` („jakość PL obniżona") | `pip install sentence-transformers` + `reindex --wipe --all` |
| brak GPU / CUDA | ST działa na CPU (wolniej: ~50 ms/chunk) — bez zmian funkcjonalnych | nic; opcjonalnie mniejszy model |
| pierwsza inicjalizacja bez internetu | pobranie modelu niemożliwe → fallback jak wyżej | jednorazowo online albo model z cache HF |
| kolekcja budowana innym modelem | `EmbeddingModelMismatch` przy starcie modułu — twardy, czytelny błąd | `reindex --wipe --all` |
| uszkodzona/skasowana `.memory_db` | `recall` → `[]` + log; rozmowa działa dalej | `reindex --all` (baza w 100% odtwarzalna) |
| błąd w hooku zapisu | warning w logu, notatka/podsumowanie zapisane normalnie | `reindex` dogania zaległości |
| wolny embedding w rozmowie | jednorazowy koszt ładowania modelu przy pierwszym recall (~2-5 s); kolejne < 100 ms | akceptowane; ewentualnie preload przy starcie CLI |

Zasada nadrzędna: **pamięć jest ulepszeniem, nie zależnością** — każda awaria
warstwy wektorowej degraduje system do stanu sprzed wdrożenia, nigdy niżej.

## 12. Prywatność i granice indeksowania

Do indeksu trafiają WYŁĄCZNIE treści, które już są trwałymi artefaktami
Pioruna w folderze roboczym: notatki wykładowe, notatki researchu autonomii,
podsumowania sesji. Świadomie POZA indeksem:

- **treść maili** czytanych przez `inbox_manager` (dane osób trzecich, ulotne);
- **credentials i pliki konfiguracyjne** (`agent_credentials.json`, `.env` —
  nigdy nie przechodzą przez ścieżki indeksujące);
- **surowa historia rozmów** (szum + potencjalnie wrażliwe wtręty; indeksujemy
  tylko destylowane podsumowania);
- **pliki spoza `PIORUN_WORKDIR`** — `index_file` (kolekcja `documents`)
  pozostaje narzędziem wywoływanym ręcznie i w trybie autonomicznym podlega
  `ToolPolicy._ensure_inside_root` jak dziś.

`recall` jest read-only i nie wykonuje żadnych akcji — dlatego może być
dozwolony w trybie autonomicznym bez rozszerzania `ToolPolicy` (analogicznie
do `search_global_history`). Baza żyje lokalnie w `.memory_db/`, nieśledzona
przez git (przy wdrożeniu dochodzi jawny wpis w `.gitignore`).

## 13. Integracje przyszłe (zaprojektowane, nie wdrażane teraz)

1. **Semantyczna deduplikacja plannera autonomii** — dziś
   `autonomy_supervisor` trzyma ~40 linii ręcznych słowników `_TOPIC_AI`,
   `_TOPIC_CYBER`, … do wykrywania powtórek tematów. Po wdrożeniu pamięci:
   `semantic_key` można zastąpić testem `recall(query, kind="research",
   max_distance=0.35)` — „czy mam już świeżą notatkę o tym samym?". Usuwa
   całą klasę problemów (nowy temat = nowy słownik). Wymaga okresu próbnego
   recall, żeby zaufać progom.
2. **Fiszki i quiz (4.2 / 4.5)** — generator fiszek pobiera materiał przez
   `recall(kind="lecture", top_k=10)` per temat egzaminacyjny zamiast czytać
   pliki wprost; quiz ocenia odpowiedź porównując ją wektorowo z fragmentem
   źródłowym (odległość jako miara trafności odpowiedzi).
3. **Time-decay w rankingu** — mnożnik `distance * (1 + λ·wiek_w_miesiącach)`
   dla `research_notes` (research się starzeje; notatki wykładowe NIE podlegają
   decay — wiedza egzaminacyjna nie traci ważności w semestrze).
4. **Panel www (5.1)** — zakładka „Pamięć": wyszukiwarka po bazie + statystyki
   kolekcji z `collection_stats()`.

## 14. Decyzje architektoniczne (mini-ADR)

**ADR-1: chromadb, nie FAISS/sqlite-vec/Qdrant.** Chroma już jest zależnością
projektu (zainstalowana, w `requirements.txt`), ma persystencję i metadane
out-of-the-box. FAISS = szybszy, ale goły (własna warstwa metadanych do
napisania); sqlite-vec = ładny minimalizm, ale kolejna młoda zależność;
Qdrant = serwer do utrzymywania. Przy skali < 10 k wektorów różnice wydajności
nie istnieją. → Zostajemy przy chromie; wymiana za rok jest tania, bo całość
przechodzi przez jeden moduł `vector_memory.py`.

**ADR-2: sentence-transformers, nie własny ONNX.** Torch z CUDA już jest na
maszynie, więc ST to lekka instalacja i natychmiastowe GPU. Własny pipeline
ONNX (tokenizer + sesja onnxruntime) oszczędziłby ~500 MB RAM, ale kosztuje
dzień pracy i utrzymanie. → ST; ONNX w backlogu, gdyby RAM zaczął boleć.

**ADR-3: podsumowania sesji, nie surowa historia.** Surowe wiadomości to szum
(pojedyncze „ok", komendy, wklejki) i ryzyko prywatności; podsumowania już są
utrzymywane przez `refresh_session_summary` i niosą destylat. → Indeksujemy
podsumowania; surowa historia zostaje w SQLite pod LIKE/FTS.

**ADR-4: indeks synchroniczny, nie kolejka.** Pojedynczy upsert to < 1 s;
najczęstszy producent (notatka autonomii) działa w tle i tak. Kolejka/wątek
dałaby złożoność bez zysku. → Synchronicznie, w try/except; przy większej skali
decyzję rewiduje pomiar, nie przeczucie.

## 15. Plan wdrożenia — 12 kroków

Kolejność zaprojektowana tak, by każdy krok był osobno testowalny i osobno
commitowalny; kroki 1-8 to ~2 wieczory, 9-12 to kalibracja i tydzień obserwacji.

| Krok | Co | Pliki | Rozmiar |
|---|---|---|---|
| 1 | `pip install sentence-transformers` + wpis w `requirements.txt`; `.memory_db/` jawnie do `.gitignore`; nowe pola w `core/config.py` i `.env.example` (sekcja 7) | requirements, .gitignore, config | S |
| 2 | `tools/vector_memory.py` — część 1: `_load_embedding_function` (ST + fallback + cache), `get_collection` (cosine, wersjonowanie, `EmbeddingModelMismatch`), `collection_stats` | nowy plik | S |
| 3 | część 2: czyste funkcje chunkowania `split_markdown_chunk`, `split_note_sections` (pseudokod z sekcji 4) | j.w. | S |
| 4 | część 3: `upsert_*` (deterministyczne ID z sekcji 2), `recall`, `format_recall_for_llm/human` | j.w. | M |
| 5 | Testy jednostkowe — pełna macierz z sekcji 10 (fałszywy embedder, tmp chroma) | `tests/test_vector_memory.py` | M |
| 6 | `scripts/reindex_memory.py` (backfill z licznikami, `--wipe`) + **przebieg na realnych danych** z repo (`sessions/`, `autonomy_notes/`) | nowy plik | S |
| 7 | Hooki zapisu (3 linie każdy, w try/except): `note_generator`, `autonomy_supervisor._append_note`, `memory.refresh_session_summary` | 3 istniejące pliki | S |
| 8 | Narzędzie `recall` w `core/brain.py` (ToolDefinition + handler, rejestracja tylko gdy flaga on) i komenda `/recall` w `piorun.py` | 2 istniejące pliki | S |
| 9 | **Kalibracja progu** wg protokołu z sekcji 8; wynik dopisany do tego dokumentu | ten dokument | S |
| 10 | `doctor` (gdy powstanie, zad. 3.2): `collection_stats` + zgodność modelu + obecność ST; wpisy w README i CHANGELOG | doki | S |
| 11 | **Rollback-check**: ustaw `PIORUN_MEMORY_RECALL_ENABLED=false` i potwierdź, że system działa identycznie jak przed wdrożeniem (test + ręcznie) | — | S |
| 12 | **Pomiar po tygodniu**: ile razy recall użyty w rozmowach (grep historii narzędzi), ile trafień vs „brak wspomnień"; decyzja o podpięciu plannera (sekcja 13.1) | — | S |

**Kryterium ukończenia:** (a) `reindex --all` przechodzi na istniejących danych
i raportuje > 0 dokumentów w 3 kolekcjach; (b) pytanie w rozmowie o temat
z kwietniowego wykładu zwraca właściwy fragment z metryczką źródła;
(c) pytanie o temat spoza notatek zwraca „brak wspomnień", nie halucynację;
(d) pytest zielony bez dostępu do sieci; (e) wyłączenie flagi przywraca
zachowanie sprzed wdrożenia.

## 16. Przykłady end-to-end

### 16.1 Recall w rozmowie

Mateusz: *„przypomnij mi co było na wykładzie o indeksach w bazach"*

Model wywołuje `recall(query="indeksy w bazach danych wykład", top_k=5)`.
Narzędzie zwraca (string, który widzi model):

```
[wykład | Bazy Danych | 2026-04-14 | 30:00-35:00]
## Indeksy B+ tree
**Indeks zgrupowany (clustered)**: dane tabeli fizycznie ułożone wg klucza...
**Fill factor**: współczynnik zapełnienia strony liścia...

[wykład | Bazy Danych | 2026-04-14 | 35:00-40:00]
## Indeksy nieklastrowane
...

[rozmowa | Pytania o grafy | 2026-05-02]
Temat sesji: Pytania o grafy. Ostatnie intencje: różnica między indeksem a...
```

Oczekiwana odpowiedź modelu: streszczenie Z CYTATEM źródła („na wykładzie
z 14.04, ok. 30 minuty…") — format `[źródło]` na wierzchu wymusza cytowanie.

### 16.2 `/recall` w CLI

```
Piorun [Nowa konwersacja] ⚡ > /recall drzewa B+

[PAMIĘĆ] 3 trafienia dla: drzewa B+
1. (0.31) wykład | Bazy Danych | 2026-04-14 | 30:00-35:00
   ## Indeksy B+ tree — **Indeks zgrupowany**: dane tabeli fizycznie...
   → notes/Bazy Danych/2026-04-14.html
2. (0.44) wykład | Algorytmy | 2026-04-21 | 15:00-20:00
   ...
3. (0.58) research | 2026-07-02 | Autonomy Research: struktury indeksowe
   ...
```

### 16.3 Zapytanie spoza bazy

`/recall przepis na bigos` → `[PAMIĘĆ] Brak wspomnień pasujących do zapytania.`
(wszystkie dystanse > próg; to jest poprawny, pożądany wynik — sekcja 8).

## 17. Ryzyka i decyzje odłożone

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
   nieprzewidywalna), własny pipeline ONNX (ADR-2).

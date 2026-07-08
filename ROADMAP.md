# Piorun ⚡ — Master Plan rozwoju (v2)

Stan na: 2026-07-06. Wersja szczegółowa — rozbicie na podzadania z plikami,
szacunkiem rozmiaru (S = do 1 h, M = wieczór, L = weekend), ryzykiem i sposobem
weryfikacji. Kolejność wykonania na końcu dokumentu.

---

## 1. Wizja: czym Piorun ma być za rok

**Lokalny, prywatny system operacyjny studenta informatyki.** Trzy obietnice:

1. **Żaden wykład nie ginie** — nagranie → transkrypcja → notatka z OCR slajdów
   → przeszukiwalna baza wiedzy → fiszki przed kolokwium. Zero ręcznej roboty.
2. **Autonomia oddaje więcej, niż kosztuje** — poranny research z prawdziwych
   źródeł, przypomnienia o terminach zanim będzie za późno, tygodniowe
   podsumowanie własnej pracy. Wszystko z hamulcami i kolejką akceptacji.
3. **Rdzeń w 100% na Twoim sprzęcie** — Gemma przez llama.cpp, Whisper na GPU,
   pamięć w SQLite/Chroma. Chmura tylko na styku ze światem (mail, kalendarz).

## 2. Zasady projektu (niezmienne)

1. **Local-first** — model, transkrypcja i pamięć lokalnie.
2. **Autonomia z hamulcami** — limity, cooldowny, dedup, kolejka akceptacji;
   akcje destrukcyjne i maile do osób trzecich zablokowane na stałe w `ToolPolicy`.
3. **Dowód przed „działa"** — nowa logika = test albo świeży przebieg. `pytest` zielony.
4. **Zmiany chirurgiczne** — małe commity, bez przepisywania działającego kodu.

## 3. Stan wyjściowy (Etap 0 — ukończony 2026-07-06)

Fundament niezawodności zamknięty i wypchnięty na GitHub (commity
`23d2d95`, `78ecab9`, `244dd5d`): naprawiona wyszukiwarka (ddgs), sensowne
notatki autonomii, planner z datą i terminami studiów, twarde nagrywanie
wykładów, retry LLM, wznawialny `/process`, deterministyczny raport poranny,
36 testów, requirements, changelog. Szczegóły: `CHANGELOG.md`.

**Fakty zweryfikowane pod ten plan** (nie założenia):
- `rapidocr-onnxruntime` instaluje się i importuje na tej maszynie (sprawdzone
  2026-07-06) → OCR slajdów (zad. 1.3) nie ma ryzyka zależności.
- Skrypty jednorazowe w `core/` i pliki `gemma_*` nie są nigdzie importowane
  (grep po całym repo) → reorganizacja (zad. 3.3) jest bezpieczna.
- W repo jest realna sesja testowa ze slajdami PNG
  (`sessions/2026-04-14_2031_Wyklad`) → materiał do weryfikacji OCR.

---

## 4. Etap 1 — Academic Mode PRO

**Cel:** od `/stop` do gotowej, przeszukiwalnej notatki bez ani jednej ręcznej
decyzji; pipeline odporny na wszystko poza brakiem prądu.

> **Status (2026-07-07): 1.1, 1.2, 1.3, 1.5, 1.6 ZREALIZOWANE.**
> Zostaje 1.4 (OCR slajdów — sprint B, `rapidocr` już zweryfikowany) i 1.7
> (podpowiedź języka transkrypcji).

| # | Zadanie | Pliki | Rozmiar | Ryzyko |
|---|---------|-------|---------|--------|
| 1.1 | Auto-process po `/stop`: pytanie „przetworzyć teraz? [T/n]", refaktor wspólnego `process_session()` używanego przez `/stop` i `/process` | `piorun.py` | S | niskie |
| 1.2 | Detekcja ciszy: RMS ramek (numpy), ostrzeżenie po 60 s ciszy (env `PIORUN_LECTURE_SILENCE_WARN_SECONDS`), statystyka max ciszy w podsumowaniu | `tools/lecture_recorder.py` | S | niskie |
| 1.3 | Fallback urządzenia: gdy loopback domyślnego wyjścia nie znaleziony — pierwszy dostępny loopback z ostrzeżeniem zamiast odmowy startu | `tools/lecture_recorder.py` | S | niskie |
| 1.4 | OCR slajdów (rapidocr, opcjonalny import z graceful fallback): `tools/slide_ocr.py`, cache `ocr_cache.json` per sesja, tekst slajdu w promptcie notatek `[TEKST ZE SLAJDU]` | nowy + `tools/note_generator.py` | M | średnie: jakość OCR na slajdach z kodem — zweryfikować na realnej sesji z repo |
| 1.5 | Eksport DOCX: nagłówki/listy/bold + osadzone slajdy, zapis obok HTML, flaga env `PIORUN_LECTURE_EXPORT_DOCX` | nowy `tools/docx_export.py`, `piorun.py` | M | niskie (python-docx już w projekcie) |
| 1.6 | Test integracyjny pipeline'u: fixture transcript.json + slajd → notatki (LLM zamockowany) → HTML → DOCX; bez Whispera i bez modelu | `tests/test_lecture_pipeline.py` | M | niskie |
| 1.7 | Podpowiedź języka transkrypcji (env `PIORUN_LECTURE_LANGUAGE`, domyślnie auto) — mniejsza szansa błędnej detekcji przy cichym początku | `tools/whisper_bridge.py` | S | niskie |

**Kryterium ukończenia:** świeże nagranie 2-minutowe przechodzi `/stop` → [T] →
otwarty HTML z tekstem ze slajdu w notatce; `pytest` zawiera test integracyjny.

## 5. Etap 2 — Autonomia, która realnie pomaga

**Cel:** autonomiczne akcje mają mierzalną wartość; system sam raportuje, co
zrobił, i sam sprząta po nieudanych próbach.

| # | Zadanie | Pliki | Rozmiar | Ryzyko |
|---|---------|-------|---------|--------|
| 2.1 | Akcja `send_reminder`: mail o terminie WYŁĄCZNIE do właściciela (istniejąca polityka), fingerprint+cooldown jak dla innych akcji, planner instruowany „tylko gdy termin <48 h i nie było przypomnienia" | `core/autonomy_supervisor.py` | M | średnie: spam — mitygacja przez cooldown 720 min i dedup po ID terminu |
| 2.2 | Tygodniowy digest: agregacja 7 dni (ticki, notatki, decyzje kolejki, terminy zamknięte/otwarte) → markdown do workdir + opcjonalny mail; czysto deterministyczny, bez LLM | nowy `tools/weekly_digest.py`, wpięcie w CLI | M | niskie |
| 2.3 | TTL kolejki: pozycje `execution_failed` starsze niż 7 dni wygasają automatycznie (env `PIORUN_AUTONOMY_FAILED_TTL_DAYS`) | `core/autonomy_supervisor.py` | S | niskie |
| 2.4 | Metryka jakości źródeł w notatkach research: liczba wyników, unikalne domeny, ile z bieżącego roku — stopka w notatce + wpis w decisions.jsonl | `core/autonomy_supervisor.py` | S | niskie |
| 2.5 | Pętla zwrotna plannera: digest czyta decyzje approve/reject i dopisuje do kontekstu plannera „czego właściciel nie chce" (ostatnie odrzucenia z powodami) | `core/autonomy_supervisor.py` | L | średnie: prompt rośnie — limit do 5 ostatnich odrzuceń |

**Kryterium ukończenia:** po tygodniu działania ≥80% notatek research ma źródła
z bieżącego roku, zero duplikatów tematów, kolejka nie zawiera pozycji
starszych niż 7 dni, przyszedł ≥1 sensowny digest.

## 6. Etap 3 — Jeden interfejs i operacje

**Cel:** koniec żonglowania czterema .bat; jedna komenda mówi, czy system jest
zdrowy.

| # | Zadanie | Pliki | Rozmiar | Ryzyko |
|---|---------|-------|---------|--------|
| 3.1 | Subkomendy: `python piorun.py [chat\|doctor\|digest\|autonomy ...]`; bez argumentów = chat (zgodność z istniejącymi .bat); `autonomy` deleguje do istniejącego `scripts/autonomy_ops.py` | `piorun.py` | M | niskie |
| 3.2 | `doctor`: LLM endpoint (jest `ops_runtime.check_llm_health`), model Whisper na dysku, import ddgs, credentials (istnienie, nie treść), bazy zapisywalne, urządzenie loopback, wolne miejsce na dysku workdir | nowy `core/doctor.py` | M | niskie |
| 3.3 | ✅ ZREALIZOWANE (2026-07-07): 4 pliki legacy → `scripts/legacy/`, 11 jednorazowych z `core/` → `scripts/maintenance/` (git mv, importy i pytest potwierdzone po przenosinach) | struktura repo | S | niskie |
| 3.4 | Retencja: rotacja `autonomy_logs/` i `decisions.jsonl` (archiwizacja > 90 dni do zip w backup_dir) | `core/ops_runtime.py` | S | niskie |
| 3.5 | Backup automatyczny: istnieje `ops_runtime.create_backup` — wpiąć w harmonogram (tygodniowo, przy digestcie) + przycinanie starych backupów do N=8 | `tools/weekly_digest.py` | S | niskie |

**Kryterium ukończenia:** świeży klon repo + `pip install -r requirements.txt` +
`python piorun.py doctor` daje czytelną diagnozę wszystkich zależności;
struktura repo bez śmieci na poziomie root/core.

## 7. Etap 4 — Wiedza i pamięć (nowy filar)

**Cel:** notatki przestają być plikami, stają się bazą wiedzy, która odpowiada
na pytania i przygotowuje do egzaminów.

| # | Zadanie | Pliki | Rozmiar | Ryzyko |
|---|---------|-------|---------|--------|
| 4.1 | Indeks pełnotekstowy: SQLite FTS5 nad `notes_structured.json` wszystkich sesji + komenda `/find <fraza>` (wyniki: przedmiot, data, fragment, link do HTML) | nowy `tools/knowledge_index.py`, `piorun.py` | M | niskie: FTS5 jest w stdlib sqlite |
| 4.2 | Fiszki z notatek: sekcje „Pytania kontrolne" już są generowane — parser zbiera je per przedmiot i eksportuje do formatu Anki (apkg przez `genanki` albo prosty TSV) + `/flashcards <przedmiot>` | nowy `tools/flashcards.py` | M | średnie: jakość pytań zależy od modelu — zacząć od TSV |
| 4.3 | Powiązanie notatek z terminami: `/study` pokazuje przy terminie liczbę notatek z przedmiotu i link do najnowszej | `tools/study_deadlines.py`, `piorun.py` | S | niskie |
| 4.4 | Pamięć wektorowa w rozmowie: narzędzie `recall` dla modelu — **pełny projekt: `docs/vector-memory-design.md`** (4 kolekcje, spec API, algorytmy chunkowania, hybryda z FTS, kalibracja, macierz testów, tryby awarii, ADR-y, wdrożenie w 12 krokach z rollbackiem) | wg projektu | L | zaadresowane w projekcie |
| 4.5 | Quiz przed kolokwium: `/quiz <przedmiot>` — model odpytuje z notatek (pętla pytanie→odpowiedź→ocena), wynik zapisywany, słabe obszary trafiają do fiszek | `piorun.py` + nowy `tools/quiz.py` | L | średnie: wymaga działającego LLM, projekt promptów |

**Kryterium ukończenia:** `/find` znajduje frazę z dowolnego wykładu w <1 s;
przed kolokwium da się wygenerować talię fiszek z całego przedmiotu jedną komendą.

## 8. Etap 5 — Interfejs graficzny i dostęp (dalszy horyzont)

**Cel:** rzeczy, które są niewygodne w terminalu, dostają lekki front — bez
przepisywania rdzenia.

| # | Zadanie | Rozmiar | Uwagi |
|---|---------|---------|-------|
| 5.1 | Panel www (FastAPI + jeden plik HTML): kolejka autonomii (approve/reject), digest, health — na bazie istniejącego `ops_api_server.py` | L | zamiast rozbudowy 40 KB tkinter GUI; localhost-only |
| 5.2 | Dashboard notatek 2.0: wyszukiwarka (FTS z 4.1), tagi przedmiotów, ostatnio otwierane | M | rozbudowa `core/html_builder.py` |
| 5.3 | Kanał mobilny (opcjonalny, do decyzji): powiadomienia przez istniejący mail; ewentualny bot (np. Telegram) tylko read-only + approve/reject kolejki | L | UWAGA: wejście z zewnątrz = nowa powierzchnia ataku; wymaga osobnej decyzji właściciela |

**Kryterium ukończenia (5.1–5.2):** kolejkę autonomii da się przejrzeć
i rozstrzygnąć z przeglądarki; notatki mają wyszukiwarkę.

## 9. Etap 6 — Jakość modelu i odpowiedzi

**Cel:** mierzyć i poprawiać to, co model generuje, zamiast wierzyć na słowo.

| # | Zadanie | Rozmiar | Uwagi |
|---|---------|---------|-------|
| 6.1 | Zestaw ewaluacyjny notatek: 3 transkrypty-fixture + rubryka (kompletność pojęć, poprawność, format) — uruchamiany ręcznie po zmianie promptu | M | pierwszy krok do świadomego strojenia promptów |
| 6.2 | Strumieniowanie odpowiedzi w CLI (`stream=True`) — odpowiedź pojawia się od razu, nie po 20 s | M | duża poprawa odczuwalnej szybkości |
| 6.3 | Wymienny backend LLM: profil konfiguracyjny (llama.cpp / LM Studio / dowolny endpoint OpenAI-compatible) + `doctor` pokazuje aktywny profil | S | `base_url` już jest w env — brakuje presetów i dokumentacji |
| 6.4 | Budżet kontekstu per zadanie: notatki dostają większe okno niż small-talk (dziś jeden limit globalny) | S | konfig w `core/config.py` |

## 10. Kolejność wykonania (sprinty)

Zależności: 1.1→1.6 (test używa refaktoru), 4.1→4.2/5.2 (indeks przed fiszkami
i wyszukiwarką), 2.2→2.5/3.5 (digest przed pętlą zwrotną i backupem), 3.1→3.2.

- **Sprint A — „Wykład bez rąk"** (najbliższy): 1.1, 1.2, 1.3, 1.5, 1.6 + 3.3
  (porządek repo przy okazji). Efekt widoczny na pierwszym nagraniu.
- **Sprint B — „OCR i doktor"**: 1.4 (weryfikacja na realnej sesji z repo),
  3.1, 3.2, 1.7. Efekt: notatki widzą slajdy, system sam się diagnozuje.
- **Sprint C — „Autonomia z raportem"**: 2.1, 2.2, 2.3, 2.4, 3.4, 3.5.
  Efekt: pierwszy tygodniowy digest + przypomnienia o terminach.
- **Sprint D — „Baza wiedzy"**: 4.1, 4.3, 4.2. Efekt: `/find` i fiszki.
- **Sprint E — „Szlif"**: 6.2, 6.3, 2.5, 5.2. Potem decyzje: 4.4/4.5/5.1/5.3.

Każdy sprint kończy się: pytest zielony → smoke-test na żywo → commit(y) na
main → push po Twoim OK.

## 11. Metryki sukcesu (globalne)

- **Academic:** 100% nagranych wykładów kończy jako HTML w bazie; 0 sesji
  utraconych przez błąd pipeline'u (błąd = sesja czeka, nie znika).
- **Autonomia:** ≥80% notatek research ze źródłami z bieżącego roku; 0 powtórek
  tematu w tygodniu; każde przypomnienie o terminie ≥24 h przed deadline'em.
- **Operacje:** `doctor` zielony po świeżej instalacji wg README; backup ≤7 dni.
- **Jakość kodu:** pytest zielony na main; każda nowa funkcja z testem logiki.

## 12. Backlog świadomie odłożony

- Chmurowe LLM jako rdzeń — sprzeczne z wizją local-first.
- Autonomiczne operacje na plikach poza `Desktop/Piorun` i maile do osób
  trzecich — na stałe zablokowane, nie „kiedyś".
- Rozbudowa tkinter GUI (`piorun_gui.py`, 40 KB) — zamrożona na rzecz panelu
  www (5.1); GUI zostaje jako działający artefakt.
- Nagrywanie kamery/mikrofonu (nie tylko loopback) — wróci, jeśli pojawią się
  wykłady stacjonarne bez Teams.
- Multi-user — Piorun jest jednoosobowy z definicji.

## 13. Ryzyka przekrojowe

1. **Lokalny LLM jest wąskim gardłem jakości** (Gemma 9B): dlatego wszystkie
   krytyczne ścieżki mają fallbacki deterministyczne (raport bez syntezy,
   notatki z surowych wyników), a 6.1 da narzędzie do mierzenia.
2. **DDG jako jedyne źródło wyszukiwania**: przy kolejnej awarii biblioteki
   dodać drugi backend (np. wyszukiwarka Brave API — wymaga klucza, decyzja
   właściciela); interfejs `_tool_web_search` już izoluje resztę systemu.
3. **Rozrost danych** (sesje audio, logi): adresowane w 3.4 (retencja) i przez
   istniejący cleanup audio po przetworzeniu.

# Changelog

## 2026-07-07 — Academic Mode PRO, sprint A (roadmap 1.1–1.3, 1.5–1.6)

### Dodane
- **Auto-process po `/stop`**: po zakończeniu nagrania Piorun proponuje
  natychmiastowe przetworzenie (`[T/n]`, domyślnie TAK) — od nagrania do
  otwartej notatki HTML bez ręcznej komendy. Wspólna funkcja `process_session()`
  używana przez `/stop` i `/process` (koniec zduplikowanej logiki).
- **Detekcja ciszy**: nagrywarka liczy RMS ramek i ostrzega po 60 s ciszy
  (env `PIORUN_LECTURE_SILENCE_WARN_SECONDS`) — wychwytuje wyciszony Teams albo
  zły kanał audio W TRAKCIE wykładu, nie po nim; statystyka max ciszy
  w podsumowaniu (`tools/lecture_recorder.py`).
- **Fallback urządzenia loopback**: gdy nie ma loopbacku pasującego do
  domyślnego wyjścia, nagrywarka bierze pierwszy dostępny (z ostrzeżeniem)
  zamiast odmawiać startu.
- **Eksport DOCX** (`tools/docx_export.py`, za flagą `PIORUN_LECTURE_EXPORT_DOCX`):
  notatki jako dokument Word z nagłówkami, listami, pogrubieniami i osadzonymi
  slajdami — obok wersji HTML.
- **Test integracyjny pipeline'u** (`tests/test_lecture_pipeline.py`):
  transcript → notatki → HTML → DOCX z zamockowanym LLM (bez Whispera, modelu
  i sieci); plus testy jednostkowe RMS, detekcji ciszy i wyboru urządzenia.
  Łącznie 61 testów pytest.

## 2026-07-07 — Pamięć wektorowa (roadmap 4.4)

### Dodane
- **`tools/vector_memory.py`**: cztery kolekcje chromadb (cosine) —
  `lecture_notes`, `research_notes`, `session_summaries`, `documents`;
  deterministyczne ID (idempotentne upserty), wielojęzyczne embeddingi
  (`paraphrase-multilingual-MiniLM-L12-v2`, GPU przez zainstalowanego torcha)
  z fallbackiem i wersjonowaniem modelu (`EmbeddingModelMismatch` zamiast
  cichego mieszania przestrzeni). Pełny projekt: `docs/vector-memory-design.md`.
- **Narzędzie `recall` dla modelu** (za flagą `PIORUN_MEMORY_RECALL_ENABLED`)
  i komenda **`/recall <fraza>`** w CLI — semantyczne wyszukiwanie w notatkach
  z wykładów, researchu autonomii i podsumowaniach rozmów, ze źródłem przy
  każdym trafieniu.
- **Hooki indeksujące** (nigdy nie blokują operacji głównej): notatki wykładowe
  po wygenerowaniu, notatki autonomii po dopisaniu, podsumowania sesji po
  odświeżeniu; **`scripts/reindex_memory.py`** do backfillu (`--all`, `--wipe`).
- **15 testów** warstwy pamięci z fałszywym embedderem (zero sieci i pobierania
  modeli w pytest); rollback-check flagi wyłączającej.

### Naprawione
- **`PersistentClient` chromy nigdy nie działał na tej maszynie**: równolegle
  zainstalowany pakiet `chromadb-client` (thin) wymuszał tryb http-only —
  dlatego `.memory_db` był zawsze pusty. Usunięty konflikt, ostrzeżenie
  w `requirements.txt`.

### Zweryfikowane
- Backfill na realnych danych: 39 sekcji researchu + 9 podsumowań rozmów;
  żywe zapytanie „nowe zagrożenia w cyberbezpieczeństwie" → trafienia
  z dystansem 0.29; kontrola negatywna („przepis na bigos") → poprawne
  „brak wspomnień". 51 testów pytest zielonych.

## 2026-07-06 — Fundament niezawodności (Etap 0)

### Naprawione
- **web_search zwracał 0 wyników**: porzucona biblioteka `duckduckgo_search`
  zastąpiona następcą `ddgs`; region `pl-pl`, 3 próby z odczekaniem, jawny
  komunikat błędu zamiast pustej listy (`core/brain.py`, `piorun.py`).
- **Notatki autonomii były zrzutem JSON**: teraz czytelny markdown
  (tytuł, opis, źródło) z opcjonalną syntezą przez lokalny LLM; puste
  wyszukiwanie nie liczy się jako wykonana akcja (`core/autonomy_supervisor.py`).
- **Planner proponował "trendy 2024" w 2026**: prompt plannera dostaje bieżącą
  datę oraz wymogi konkretności zapytań i samodzielności treści notatek.
- **Śmieciowe notatki "Autonomy heartbeat"**: usunięte — brak propozycji to
  poprawny, cichy wynik ticka.
- **Nagrywanie wykładu cicho zawodziło (audio.wav 0 B)**: sonda strumienia na
  starcie, licznik ramek/błędów, okresowy flush na dysk, raport i ostrzeżenie
  przy zatrzymaniu (`tools/lecture_recorder.py`).
- **Dobór slajdu do fragmentu notatek**: wybierany według środka fragmentu
  (wcześniej: koniec — często slajd z następnego tematu); poprawione granice
  chunków; odporny odczyt odpowiedzi modelu (`tools/note_generator.py`).
- **Jeden błąd 503 zabijał sesję agenta**: retry z backoffem (3 próby) na
  wywołania LLM + limit 24 iteracji pętli narzędzi (`core/agent_runtime.py`).

### Dodane
- **Testy**: katalog `tests/` — 36 testów pytest z pełną izolacją środowiska
  (testy nie dotykają prawdziwych baz ani folderu Desktop/Piorun); `pytest.ini`.
- **`requirements.txt`**: przypięte zależności top-level.
- **`/process` odporny i wznawialny**: pomija gotową transkrypcję po padzie,
  błąd jednej sesji nie przerywa batcha, podsumowanie sukcesów/porażek;
  sesje bez audio, ale z transkrypcją, są wznawiane (`piorun.py`).
- **Raport poranny — deterministyczny pipeline**: wyszukiwania wykonywane
  w kodzie per temat, LLM tylko syntetyzuje z materiałów, sekcja "Źródła",
  fallback bez LLM, kopia raportu w folderze Piorun (`tools/autonomous_engine.py`).
- **Planner zna terminy studenckie**: nadchodzące terminy z `/study` (7 dni)
  trafiają do kontekstu plannera z instrukcją preferowania akcji, które
  w nich pomagają.
- **Komenda `/autonomy` w CLI**: status | queue [limit] | tick | approve <id> |
  reject <id> [powód] — przegląd i decyzje bez odpalania osobnego ops CLI.
- **Limit kolejki autonomii**: maks. 100 pozycji (ochrona przed zapchaniem).
- **`ROADMAP.md`**: plan rozwoju z etapami i kryteriami ukończenia.

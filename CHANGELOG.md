# Changelog

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

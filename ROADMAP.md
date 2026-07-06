# Piorun ⚡ — Plan rozwoju (ROADMAP)

Stan na: 2026-07-06. Ten dokument to mapa rozwoju projektu: co jest zrobione,
co jest w toku i co ma sens jako następny krok. Każdy etap ma kryterium
ukończenia — bez spełnienia kryterium etap nie jest "done".

## Zasady projektu

1. **Local-first** — model językowy (Gemma przez llama.cpp), transkrypcja (Whisper)
   i pamięć działają lokalnie; chmura tylko tam, gdzie to konieczne (mail, kalendarz).
2. **Autonomia z hamulcami** — każda akcja autonomiczna przechodzi przez limity,
   cooldowny, deduplikację i (dla ryzykownych) kolejkę akceptacji.
3. **Dowód przed "działa"** — nowa logika wchodzi z testem albo ze świeżym
   przebiegiem na prawdziwym przypadku. `python -m pytest` musi być zielone.
4. **Zmiany chirurgiczne** — małe commity, bez przepisywania działającego kodu.

## Etap 0 — Fundament niezawodności ✅ (2026-07-06)

Cel: wyeliminować przyczyny, przez które projekt "działał słabo".

- [x] Wyszukiwarka: migracja `duckduckgo_search` → `ddgs`, region `pl-pl`,
      3 próby z odczekaniem, jawny sygnał porażki zamiast pustej listy.
- [x] Notatki autonomii: czytelny markdown ze źródłami zamiast zrzutu JSON;
      nieudane wyszukiwanie nie liczy się jako sukces.
- [x] Planner: zna bieżącą datę, nie powtarza tematów, nie pisze notatek-"heartbeat",
      widzi terminy studenckie z `/study`.
- [x] Nagrywanie wykładów: sonda strumienia na starcie, licznik ramek,
      okresowy flush, głośne ostrzeżenie przy pustym audio.
- [x] Runtime agenta: retry z backoffem na błędy LLM, limit iteracji pętli narzędzi.
- [x] `/process`: wznawialny (nie transkrybuje drugi raz), odporny na błąd
      pojedynczej sesji, raportuje sukcesy/porażki.
- [x] Raport poranny: deterministyczny pipeline (wyszukiwania w kodzie → synteza
      przez LLM → sekcja źródeł), fallback bez LLM, kopia raportu na dysku.
- [x] Testy: `tests/` (36 testów), izolowane środowisko, `requirements.txt`.

Kryterium ukończenia: pytest zielony + żywy przebieg wyszukiwarki i nagrywania. ✅

## Etap 1 — Academic Mode na pełnej mocy (najbliższe tygodnie)

Cel: z wykładu na Teams do gotowej notatki bez ani jednej ręcznej decyzji.

- [ ] `/process --auto` po `/stop`: pytanie "przetworzyć teraz?" z domyślnym TAK.
- [ ] Wykrywanie ciszy: ostrzeżenie w trakcie nagrywania, gdy przez >60 s
      audio jest ciszą (zły device, wyciszony Teams).
- [ ] OCR slajdów (lokalnie, np. RapidOCR): tekst ze slajdów dołączany do promptu
      notatek — model widzi wzory i definicje, nie tylko słyszy.
- [ ] Eksport notatek do PDF/docx (istnieje `docx_builder`) + spis treści.
- [ ] Test integracyjny pipeline'u na 30-sekundowym nagraniu-fixture.

Kryterium ukończenia: jedna komenda od `/stop` do otwartego HTML; test
integracyjny w CI lokalnym (pytest) przechodzi.

## Etap 2 — Autonomia, która realnie pomaga (1–2 miesiące)

Cel: autonomiczne akcje mają mierzalną wartość, nie tylko "aktywność".

- [ ] Akcja `study_reminder`: planner może zaproponować przypomnienie o terminie
      (mail przez istniejący mailer, tylko do właściciela).
- [ ] Tygodniowy raport zbiorczy: co autonomia zrobiła, które notatki otwarto,
      co odrzucono w kolejce — pętla zwrotna do strojenia plannera.
- [ ] Ocena jakości notatek researchowych: prosta heurystyka (liczba unikalnych
      domen w źródłach, świeżość dat) logowana per notatka.
- [ ] Kolejka: TTL dla pozycji `execution_failed` (auto-wygasanie po 7 dniach).

Kryterium ukończenia: po tygodniu działania autonomii ≥80% notatek zawiera
źródła z bieżącego roku i zero duplikatów tematów w tygodniu.

## Etap 3 — Jeden interfejs (dalej)

Cel: koniec żonglowania czterema plikami .bat.

- [ ] Jeden entrypoint `piorun.py` z podkomendami: `chat`, `ops`, `autonomy`,
      `lecture`, `serve` (zastępuje start_*.bat).
- [ ] Health-check na starcie: llama.cpp żyje? model whisper jest? credentials są?
      (istnieje `ops_runtime.check_llm_health` — spiąć w jedno).
- [ ] Uporządkowanie repo: jednorazowe skrypty diagnostyczne z `core/`
      (fix_db, final_cleanup, deep_diagnosis, …) → `scripts/maintenance/`.
- [ ] GUI: przegląd kolejki autonomii i notatek (dziś tylko CLI/ops API).

Kryterium ukończenia: świeża instalacja z README uruchamia się jedną komendą.

## Poza zakresem (świadomie)

- Chmurowe LLM jako rdzeń — projekt jest local-first.
- Autonomiczne akcje destrukcyjne (usuwanie plików, wysyłka maili do osób
  trzecich) — na stałe zablokowane w `ToolPolicy`.

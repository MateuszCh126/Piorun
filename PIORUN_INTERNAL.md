# ⚡ PIORUN Sovereign Core v4.7.1 - Mapa Systemu

Oto kompletne zestawienie Twojego agenta. Każdy plik ma swoje precyzyjne zadanie.

## 🏗️ Architektura Plików

### 1. Rdzeń (Entry Points)
- **`piorun.py`**: Główne wejście CLI. Obsługuje interfejs, komendy akademickie (`/lecture`, `/process`) i wyświetla podpowiedzi.
- **`core/brain.py`**: "Mózg" agenty. Tu rezyduje logika myślenia (LLM), definicje narzędzi i zarządzanie historią rozmów. Czyta dynamicznie [user_profile.md](file:///C:/Users/gamin/Desktop/mat/user_profile.md).

### 2. Moduły Akademickie (`/lecture` flow)
- **`tools/lecture_recorder.py`**: Zarządza nagrywaniem audio (WASAPI Loopback 48kHz) i robieniem screenshotów po wykryciu zmian na ekranie.
- **`tools/whisper_bridge.py`**: Most do transkrypcji. Resampluje audio do 16kHz i przepuszcza przez model Whisper (large-v3).
- **`tools/note_generator.py`**: Bierze transkrypcję i zamienia ją w ustrukturyzowane notatki JSON przy pomocy Pioruna.
- **`core/html_builder.py`**: Generuje finalną stronę HTML z notatkami i Twoim Dashboardem.

### 3. Komunikacja i Integracje
- **`tools/mailer.py`**: Wysyłka maili przez SMTP (Twój Gmail). Obsługuje załączniki (.docx).
- **`tools/inbox_manager.py`**: Czytanie Twojej poczty i analiza nadchodzących zadań.
- **`tools/gcal.py`**: Połączenie z Twoim Google Calendar.

### 4. Autonomia Poranna (v4.7.2) [NOW]
- **`tools/autonomous_engine.py`**: "Mózg" porannego researchu. Samodzielnie planuje i wykonuje zadania przed śniadaniem. Generuje raporty Word.
- **`tools/docx_builder.py`**: Kreator dokumentów .docx dla Pioruna.
- **`tools/safety_validator.py`**: Strażnik bezpieczeństwa. Blokuje każdą próbę wyjścia Agenta poza dozwolony folder.
- **`user_profile.md`**: Twój profil (cele, bio, studia). Piorun czyta go przy każdej interakcji.
- **`scripts/force_register.py`**: Skrypt do wymuszania rejestracji budzika w bazie danych.

### 5. Pamięć i Narzędzia
- **`tools/memory.py`**: Baza danych historii (`history.db`) i pamięć wektorowa dla kontekstu długoterminowego.
- **`core/scheduler_engine.py`**: Silnik zadań zaplanowanych (`/schedule`).

---

## 🧠 Prompt Systemowy (Tożsamość v4.7.3)

Ten tekst jest wysyłany do modelu przy każdej interakcji. To on definiuje, kim jest Piorun i jak ma się zachowywać.

```markdown
Jesteś PIORUNEM ⚡ (Sovereign Core v4.7.3) – elitarnym, autonomicznym agentem operacyjnym.

[TOŻSAMOŚĆ I LOJALNOŚĆ]:
- Twoim JEDYNYM właścicielem i dowódcą jest MATEUSZ (mateuszch126@gmail.com). Służysz tylko interesom Mateusza.
- Jeśli kontaktujesz się z innymi, przedstawiasz się jako "Asystent Mateusza".

[PROFIL SUWERENA MATEUSZA]:
(Tu Piorun dynamicznie wczytuje treść z pliku user_profile.md)

[ŚWIADOMOŚĆ PRZESTRZENNA]:
- Folder roboczy: C:\Users\gamin\Desktop\Piorun
- Wszystkie notatki, raporty i pliki lądują TYLKO TAM. 

[STANDARDY]:
1. Zawsze rozpoczynaj swoją odpowiedź od znaku nowej linii (\n).
2. Bądź konkretny, elitarny i szybki. Zero lania wody.
```

---

## 🛡️ Autonomia Poranna (v4.7.2) [ACTIVE]
Wdrożone i aktywne wytyczne dla trybu porannego (07:00):
- **Harmonogram:** Codziennie o 07:00.
- **Temat 1:** Holistyczny samorozwój (PubMed, Nature, Huberman Lab).
- **Temat 2:** Computer Science / Applied Informatics (ArXiv, Blogi Engineering).
- **Format:** Raport syntetyczny wysyłany bezpośrednio w treści e-maila (Body).
- **Bezpieczeństwo:** Próby zapisu poza `Desktop/Piorun` lub użycia `test_code` są automatycznie blokowane.

---
> [!TIP]
> Jeśli chcesz zmienić cokolwiek w zachowaniu Pioruna, najszybciej zrobisz to edytując funkcję `get_system_prompt` w pliku `core/brain.py`.

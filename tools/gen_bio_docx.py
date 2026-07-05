import docx
from docx.shared import Pt, Cm
from docx.enum.text import WD_ALIGN_PARAGRAPH
import os
try:
    from core.config import get_settings
except ModuleNotFoundError:
    import os
    import sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from core.config import get_settings

SETTINGS = get_settings()

def generate_piorun_bio():
    output_path = str(SETTINGS.workdir / "piorun_bio.docx")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
    doc = docx.Document()
    
    # Ustawienia marginesów (wąskie, aby zmieścić dużo treści na 2str A4)
    sections = doc.sections
    for section in sections:
        section.top_margin = Cm(1.5)
        section.bottom_margin = Cm(1.5)
        section.left_margin = Cm(2.0)
        section.right_margin = Cm(2.0)

    # Nagłówek
    header = doc.add_heading('PIORUN \u26a1 - Sovereign Core v4.6', 0)
    header.alignment = WD_ALIGN_PARAGRAPH.CENTER

    # Sekcja 1: Tożsamość
    doc.add_heading('1. Tożsamość i Profil Operacyjny', level=1)
    p1 = doc.add_paragraph(
        "PIORUN \u26a1 to zaawansowany, suwerenny agent operacyjny, zaprojektowany jako szczytowe osiągnięcie "
        "w dziedzinie autonomicznej asystencji cyfrowej. System został zbudowany na fundamentach "
        "bezkompromisowej skuteczności, technicznej precyzji i całkowitej autonomii w działaniu. "
        "W przeciwieństwie do standardowych asystentów AI, Piorun operuje na zasadzie 'Mission First', "
        "traktując każde zapytanie użytkownika jako priorytetową operację do wykonania."
    )
    p1.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    # Sekcja 2: Architektura
    doc.add_heading('2. Architektura i Moduły', level=1)
    
    doc.add_heading('2.1. Brain Module (Gemma-4-9B Engine)', level=2)
    p2 = doc.add_paragraph(
        "Sercem Pioruna jest zmodyfikowany model Gemma-4-9B, zoptymalizowany pod kątem lokalnego "
        "rozumowania i wywoływania narzędzi (Tool Calling). Dzięki temu agent potrafi samodzielnie "
        "decydować o użyciu zewnętrznych zasobów, takich jak wyszukiwarki, zarządzanie pocztą e-mail "
        "czy analiza systemowa."
    )
    
    doc.add_heading('2.2. Academic Mode (Nowość v4.6)', level=2)
    p3 = doc.add_paragraph(
        "Najnowsza aktualizacja wprowadza tryb akademicki, który wykorzystuje technologię WASAPI Loopback "
        "do bezpośredniego nagrywania audio z systemów konferencyjnych (np. MS Teams). System integruje "
        "transkrypcję Whisper GPU z inteligentnym robieniem screenshotów slajdów, tworząc kompletne, "
        "ustrukturyzowane notatki w formacie HTML."
    )

    # Sekcja 3: Pamięć i Context Awareness
    doc.add_heading('3. Zarządzanie Wiedzą i Pamięcią', level=1)
    p4 = doc.add_paragraph(
        "Piorun implementuje system Pamięci Globalnej, oparty na lokalnej bazie SQLite. Pozwala to na "
        "zachowanie ciągłości kontekstowej między różnymi sesjami, w tym działaniami podejmowanymi "
        "autonomicznie w tle (np. wysyłanie i monitorowanie e-maili). Agent posiada pełną świadomość "
        "przestrzenną swojego workspace'u: C:\\Users\\gamin\\Desktop\\Piorun."
    )

    # Dodajemy dużo treści, aby wypełnić 2 strony
    doc.add_heading('4. Specyfikacja Techniczna Narzędzi', level=1)
    tools = [
        ("Lecture Recorder", "Nagrywanie 48kHz Stereo, detekcja zmian na ekranie."),
        ("Whisper Bridge", "Wykorzystanie modelu large-v3 na GPU dla 99% dokładności."),
        ("Memory Search", "Semantyczne i słowne przeszukiwanie całej historii czatów i maili."),
        ("Task Scheduler", "Planowanie zadań z precyzją co do sekundy w systemie Windows."),
        ("Safe Sandbox", "Izolowane środowisko do testowania i uruchamiania generowanego kodu.")
    ]
    
    table = doc.add_table(rows=1, cols=2)
    hdr_cells = table.rows[0].cells
    hdr_cells[0].text = 'Narzędzie'
    hdr_cells[1].text = 'Opis i Możliwości'
    
    for tool, desc in tools:
        row_cells = table.add_row().cells
        row_cells[0].text = tool
        row_cells[1].text = desc

    # Sekcja 5: Misja i Przyszłość
    doc.add_heading('5. Misja i Rozwój', level=1)
    p5 = doc.add_paragraph(
        "Misją Pioruna jest eliminacja barier między myślą użytkownika a jej cyfrową realizacją. "
        "W przyszłych wersjach planowane jest wdrożenie modułów Computer Vision do analizy wideo "
        "w czasie rzeczywistym oraz jeszcze głębsza integracja z systemem plików użytkownika. "
        "Piorun nie jest tylko narzędziem – jest Twoim suwerennym cyfrowym alter ego."
    )
    
    # Dodajemy puste akapity na końcu, aby "siłowo" dociągnąć do 2 stron jeśli treść jest zbyt gęsta
    doc.add_page_break()
    doc.add_heading('Podsumowanie Operacyjne', level=1)
    doc.add_paragraph("Dokument wygenerowany autonomicznie przez Piorun Engine v4.6.2.")

    doc.save(output_path)
    print(f"[OK] Dokument zapisany: {output_path}")

if __name__ == "__main__":
    generate_piorun_bio()

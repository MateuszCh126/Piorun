from docx import Document
from docx.shared import Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
import os

def create_report(title, sections, output_path):
    """
    Tworzy profesjonalny raport .docx na podstawie słownika sekcji.
    sections: { "Nagłówek": "Treść punktowana lub tekstowa" }
    """
    doc = Document()
    
    # 1. Nagłówek główny (Tytuł)
    header = doc.add_heading(title, 0)
    header.alignment = WD_ALIGN_PARAGRAPH.CENTER
    
    # 2. Dodawanie sekcji
    for section_title, content in sections.items():
        # Nagłówek sekcji
        h = doc.add_heading(section_title, level=1)
        h_run = h.runs[0]
        h_run.font.color.rgb = RGBColor(0, 51, 102) # Ciemny niebieski (Tech)
        
        # Treść
        if isinstance(content, list):
            for item in content:
                doc.add_paragraph(item, style='List Bullet')
        else:
            p = doc.add_paragraph(content)
            p.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            
    # 3. Stopka z datą
    section = doc.sections[0]
    footer = section.footer
    p = footer.paragraphs[0]
    p.text = f"Wygenerowano przez PIORUN Sovereign Core | Data: {os.path.basename(output_path)}"
    p.alignment = WD_ALIGN_PARAGRAPH.RIGHT

    doc.save(output_path)
    return output_path

if __name__ == "__main__":
    # Test
    test_data = {
        "Computer Science": ["Analiza trendów AI", "Nowości w C++23"],
        "Samorozwój": "Skupienie na technice Pomodoro i biohackingu."
    }
    create_report("Testowy Raport Pioruna", test_data, "test.docx")

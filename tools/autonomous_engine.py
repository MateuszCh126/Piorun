import os
import sys
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.brain as brain
from core.autonomy_supervisor import _format_search_results

try:
    from core.config import get_settings
except ModuleNotFoundError:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from core.config import get_settings

TOPICS = [
    "Holistyczny samorozwoj (science-based, PubMed, bez pseudonauki)",
    "Applied Computer Science (trendy, publikacje, AI architecture)",
]

# Konkretne zapytania per temat - LLM nie musi sam wymyslac ani wywolywac narzedzi.
TOPIC_QUERIES = {
    TOPICS[0]: "nauka o zdrowiu sen trening nawyki badania",
    TOPICS[1]: "machine learning AI engineering nowe publikacje trendy",
}

SETTINGS = get_settings()
AUTONOMY_LOG = str(SETTINGS.autonomy_log)


def log_event(message):
    os.makedirs(os.path.dirname(AUTONOMY_LOG), exist_ok=True)
    with open(AUTONOMY_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")


def _gather_materials():
    """Wykonuje wyszukiwania per temat w kodzie (deterministycznie), zwraca sformatowane materialy."""
    materials = []
    year = datetime.now().year
    for topic in TOPICS:
        query = f"{TOPIC_QUERIES.get(topic, topic)} {year}"
        raw = brain.execute_tool_by_name("web_search", {"query": query}, mode="autonomous")
        formatted = _format_search_results(str(raw))
        if formatted:
            log_event(f"AKCJA OK: web_search ({query})")
        else:
            log_event(f"AKCJA PUSTA: web_search ({query})")
        materials.append({"topic": topic, "query": query, "results": formatted})
    return materials


def _materials_to_text(materials):
    sections = []
    for m in materials:
        body = m["results"] or "- Brak wynikow wyszukiwania dla tego tematu."
        sections.append(f"### {m['topic']}\n{body}")
    return "\n\n".join(sections)


def _synthesize_report(materials_text):
    """Jedna proba syntezy raportu przez lokalny LLM (bez narzedzi)."""
    prompt = f"""
Przygotuj poranny raport dla Mateusza na podstawie PONIZSZYCH materialow (nie zmyslaj faktow spoza nich).

STRUKTURA:
1. Informatyka i Tech - najwazniejsze fakty i wnioski.
2. Holistyczny Samorozwoj - najwazniejsze fakty i wnioski.
3. Wnioski i Rekomendacje - 2-3 konkretne, praktyczne kroki.
Na koncu sekcja "Zrodla" z adresami URL z materialow.

MATERIALY:
{materials_text}
"""
    response = brain.client.chat.completions.create(
        model=brain.MODEL_NAME,
        messages=[
            {"role": "system", "content": brain.get_system_prompt()},
            {"role": "user", "content": prompt},
        ],
        temperature=0.3,
        timeout=120,
    )
    msg = response.choices[0].message
    return (getattr(msg, "content", "") or "").strip()


def run_morning_routine():
    log_event("--- START SESJI PORANNEJ ---")

    materials = _gather_materials()
    materials_text = _materials_to_text(materials)
    any_results = any(m["results"] for m in materials)

    report = ""
    if any_results:
        try:
            report = _synthesize_report(materials_text)
        except Exception as e:
            log_event(f"BLAD LLM (fallback na surowe materialy): {e}")

    if len(report.strip()) < 300:
        # Fallback: raport z samych materialow - nadal wartosciowy, zawiera zrodla.
        header = "RAPORT PORANNY (tryb awaryjny - synteza LLM niedostepna)\n\n" if any_results else (
            "RAPORT PORANNY (uwaga: wyszukiwarka nie zwrocila wynikow)\n\n"
        )
        report = header + materials_text
        log_event(f"OSTRZEZENIE: raport w trybie fallback ({len(report)} znakow).")

    # Kopia raportu na dysku (folder roboczy Pioruna).
    date_tag = datetime.now().strftime("%Y%m%d")
    report_path = str(SETTINGS.workdir / f"Raport_poranny_{date_tag}.md")
    try:
        with open(report_path, "w", encoding="utf-8") as f:
            f.write(report)
        log_event(f"RAPORT ZAPISANY: {report_path}")
    except Exception as e:
        log_event(f"BLAD ZAPISU RAPORTU: {e}")

    subject = f"RAPORT PORANNY | {datetime.now().strftime('%d.%m.%Y')}"
    recipient = "mateuszch126@gmail.com"
    status = brain.mailer.send_email(to_email=recipient, subject=subject, body=report)
    log_event(f"RAPORT WYSLANY: {status}")
    log_event("--- KONIEC SESJI PORANNEJ ---")
    return f"Raport wyslany w tresci e-maila, kopia: {report_path}"


if __name__ == "__main__":
    run_morning_routine()

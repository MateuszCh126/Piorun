import os
import sys
from datetime import datetime

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.brain as brain

try:
    from core.config import get_settings
except ModuleNotFoundError:
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from core.config import get_settings

TOPICS = [
    "Holistyczny samorozwoj (science-based, PubMed, bez pseudonauki)",
    "Applied Computer Science (trendy, publikacje, AI architecture)",
]

SETTINGS = get_settings()
AUTONOMY_LOG = str(SETTINGS.autonomy_log)


def log_event(message):
    os.makedirs(os.path.dirname(AUTONOMY_LOG), exist_ok=True)
    with open(AUTONOMY_LOG, "a", encoding="utf-8") as f:
        f.write(f"[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] {message}\n")


def _extract_final_text(history):
    if not history:
        return ""

    last_msg = history[-1]
    if hasattr(last_msg, "content") and last_msg.content:
        return last_msg.content
    if isinstance(last_msg, dict) and last_msg.get("content"):
        return last_msg["content"]

    for msg in reversed(history):
        content = getattr(msg, "content", None) if not isinstance(msg, dict) else msg.get("content")
        if content:
            return content
    return ""


def run_morning_routine():
    log_event("--- START SESJI PORANNEJ ---")

    subjects = ", ".join(TOPICS)
    prompt = f"""
Jestes w trybie AUTONOMICZNYM. Przygotuj profesjonalny raport dla Mateusza.
TEMATY: {subjects}.

WYMAGANIA:
1. Przeszukaj siec (`web_search`) pod katem najnowszych i sprawdzonych informacji.
2. Raport musi miec sekcje:
   - Informatyka i Tech
   - Holistyczny Samorozwoj
   - Wnioski i Rekomendacje
3. Zakoncz gotowym raportem tekstowym do wysylki e-mail.
"""

    history = [
        {"role": "system", "content": brain.get_system_prompt()},
        {"role": "user", "content": prompt},
    ]
    session_id = f"AUTO_{datetime.now().strftime('%Y%m%d')}"
    topic = "Autonomous Morning"

    # Zapis user promptu, aby summary sesji mialo pelny kontekst.
    brain.save_message(session_id, topic, "user", prompt)

    try:
        history = brain.execute_brain_loop(
            history=history,
            session_id=session_id,
            topic=topic,
            mode="autonomous",
        )
    except Exception as e:
        log_event(f"BLAD LLM: {e}")
        return f"Blad sesji autonomicznej: {e}"

    final_text = _extract_final_text(history) or "Nie udalo sie zebrac tresci raportu."
    subject = f"RAPORT PORANNY | {datetime.now().strftime('%d.%m.%Y')}"

    recipient = "mateuszch126@gmail.com"
    status = brain.mailer.send_email(to_email=recipient, subject=subject, body=final_text)
    log_event(f"RAPORT WYSLANY: {status}")
    log_event("--- KONIEC SESJI PORANNEJ ---")
    return "Raport wyslany w tresci e-maila."


if __name__ == "__main__":
    run_morning_routine()

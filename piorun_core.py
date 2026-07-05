import json
import os
import socket
import threading
import time

import core.brain as brain
import core.autonomy_supervisor as autonomy
import core.db_schema as db_schema
import core.scheduler_engine as ste
from core.config import get_settings
import tools.inbox_manager as inbox
import tools.mailer as mailer

# Sciezki baz
SETTINGS = get_settings()
DB_PATH = str(SETTINGS.tasks_db)


def setup_db():
    try:
        db_schema.ensure_tasks_db(DB_PATH)
    except Exception as e:
        print(f"[!] Blad bazy: {e}")


def run_task_sync():
    """Petla synchronizacji zadan harmonogramu."""
    print("[*] Synchronizacja zadan aktywna (60s)...")
    while True:
        try:
            ste.sync_pending_tasks()
        except Exception as e:
            print(f"[!] Blad synchronizacji: {e}")
        time.sleep(60)


def _extract_assistant_text(history):
    if not history:
        return "Zadanie wykonane."

    last_msg = history[-1]
    if isinstance(last_msg, dict):
        role = last_msg.get("role")
        content = last_msg.get("content")
    else:
        role = getattr(last_msg, "role", None)
        content = getattr(last_msg, "content", None)

    if role == "assistant" and content:
        return content
    return "Zadanie wykonane."


def _load_default_recipient():
    try:
        with open(mailer.CREDENTIALS_PATH, "r", encoding="utf-8") as f:
            return json.load(f).get("recipient")
    except Exception:
        return None


def run_inbox_listener():
    """Petla nasluchu komend mailowych (co 5 minut)."""
    print("[*] Nasluch poczty aktywny (300s)...")
    while True:
        try:
            new_mails = inbox.fetch_unread_emails()
            for mail in new_mails:
                print(f"[+] Otrzymano zdalne polecenie: {mail['subject']}")

                session_id = f"email_{int(time.time())}"
                topic = f"Zdalne: {mail['subject']}"

                content = f"POLECENIE MAILOWE OD MATEUSZA:\nTresc: {mail['body']}"
                if mail["attachments"]:
                    files = ", ".join([os.path.basename(p) for p in mail["attachments"]])
                    content += f"\nZalaczniki pobrane do: {inbox.ATTACHMENTS_DIR}\nPliki: {files}"

                history = [
                    {"role": "system", "content": brain.get_system_prompt()},
                    {"role": "user", "content": content},
                ]

                brain.save_message(session_id, topic, "user", content)
                history = brain.execute_brain_loop(history, session_id, topic)

                final_res = _extract_assistant_text(history)
                recipient = _load_default_recipient()
                if recipient:
                    mailer.send_email(
                        recipient,
                        f"Re: {mail['subject']}",
                        f"Piorun \u26a1 POTWIERDZENIE:\n\n{final_res}",
                    )
                else:
                    print("[!] Brak recipient w agent_credentials.json - pomijam wysylke potwierdzenia.")

        except Exception as e:
            print(f"[!] Blad nasluchu poczty: {e}")
        time.sleep(300)


def run_service():
    setup_db()

    # Port do sprawdzania czy bije serce.
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(("127.0.0.1", 9999))
        s.listen(1)
    except Exception:
        print("[!] Serce juz bije w innym procesie.")
        return

    print("==============================================")
    print("   PIORUN Sovereign Service v4.5")
    print("==============================================")

    t1 = threading.Thread(target=run_task_sync, daemon=True)
    t2 = threading.Thread(target=run_inbox_listener, daemon=True)
    t3 = threading.Thread(target=autonomy.run_autonomy_loop, daemon=True)
    t1.start()
    t2.start()
    t3.start()

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        print("\n[*] Serce zatrzymane.")
    except Exception as e:
        print(f"[!] Blad krytyczny serwisu: {e}")


if __name__ == "__main__":
    run_service()

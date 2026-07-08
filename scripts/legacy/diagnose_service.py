import sqlite3
import socket
import os
from core.config import get_settings

SETTINGS = get_settings()
HIST_DB = str(SETTINGS.history_db)

def check_history():
    print("[*] Sprawdzanie history.db...")
    try:
        conn = sqlite3.connect(HIST_DB)
        cursor = conn.cursor()
        cursor.execute("SELECT session_id, topic, timestamp FROM history WHERE session_id LIKE 'email_%' ORDER BY timestamp DESC LIMIT 5")
        rows = cursor.fetchall()
        if not rows:
            print("[!] Nie znaleziono zadnych sesji emailowych w bazie.")
        else:
            print("[+] Znaleziono sesje emailowe:")
            for r in rows:
                print(f"  - ID: {r[0]}, Temat: {r[1]}, Czas: {r[2]}")
        conn.close()
    except Exception as e:
        print(f"[!] Blad odczytu bazy: {e}")

def check_port():
    print("[*] Sprawdzanie portu 9999 (Serce)...")
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.connect(('127.0.0.1', 9999))
        print("[+] Serwis bije (Port 9999 gotowy).")
        s.close()
    except:
        print("[!] Serwis NIE ODPOWIADA na porcie 9999.")

if __name__ == "__main__":
    check_history()
    check_port()

import sqlite3
import os

STARA_BAZA = "C:\\Users\\gamin\\Desktop\\mat\\data\\piorun.db"
NOWA_BAZA = "C:\\Users\\gamin\\.piorun\\piorun.db"

def check_db(path, label):
    print(f"\n--- {label} ({path}) ---")
    if not os.path.exists(path):
        print("[!] Baza nie istnieje.")
        return
    
    try:
        conn = sqlite3.connect(path)
        cursor = conn.cursor()
        
        # Sprawdzamy wszystkie zadania
        cursor.execute("SELECT id, name, schedule_time, status FROM tasks ORDER BY id DESC LIMIT 10")
        tasks = cursor.fetchall()
        
        if tasks:
            print("[INFO] Znalezione zadania (ostatnie 10):")
            for t in tasks:
                print(f" ID: {t[0]} | Nazwa: {t[1]} | Plan: {t[2]} | Status: {t[3]}")
        else:
            print("[INFO] Brak jakichkolwiek zadan w tabeli tasks.")
            
        # Sprawdzamy logi audytowe (ostatnie 10)
        print("\nOstatnie logi:")
        cursor.execute("SELECT event_type, description, timestamp FROM audit_logs ORDER BY timestamp DESC LIMIT 10")
        logs = cursor.fetchall()
        for l in logs:
            print(f" [{l[2]}] {l[0]}: {l[1]}")
            
        conn.close()
    except Exception as e:
        print(f"[ERROR]: {str(e)}")

if __name__ == "__main__":
    check_db(STARA_BAZA, "STARA BAZA")
    check_db(NOWA_BAZA, "NOWA BAZA")

import sqlite3
import os
try:
    from core.config import get_settings
except ModuleNotFoundError:
    import sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from core.config import get_settings

SETTINGS = get_settings()
DB_PATH = str(SETTINGS.tasks_db)

def check_db():
    if not os.path.exists(DB_PATH):
        print(f"Błąd: Nie znaleziono bazy w {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("\n--- ZAREJESTROWANE ZADANIA HARMONOGRAMU ---\n")
    cursor.execute("SELECT name, job_id, type, schedule_time FROM tasks")
    rows = cursor.fetchall()
    
    if not rows:
        print("[!] Brak zadań w bazie.")
    else:
        for r in rows:
            print(f"Nazwa: {r[0]}")
            print(f"ID:    {r[1]}")
            print(f"Typ:   {r[2]}")
            print(f"Cykl:  {r[3]}")
            print("-" * 30)
    
    conn.close()

if __name__ == "__main__":
    check_db()

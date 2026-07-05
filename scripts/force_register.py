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

def force_setup():
    print("[*] Wymuszanie rejestracji Autonomicznego Trybu Porannego...")
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # Usuwamy stare śmieci o tej samej nazwie jeśli są
    cursor.execute("DELETE FROM tasks WHERE name = 'Morning Autonomy' OR job_id = 'rec_morning_autonomy'")
    
    # Wpisujemy zadanie poranne (Cron: 7:00)
    cursor.execute("""
        INSERT INTO tasks (name, job_id, type, status, schedule_time, payload, retries_remaining) 
        VALUES (?, ?, ?, ?, ?, ?, ?)
    """, ("Morning Autonomy", "rec_morning_autonomy", "RECURRING", "PENDING", "0 7 * * *", "[]", 3))
    
    conn.commit()
    conn.close()
    print("[OK] Baza danych zaktualizowana. Piorun będzie budził się o 07:00.")

if __name__ == "__main__":
    force_setup()

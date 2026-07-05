import sqlite3
import json
from datetime import datetime

DB_PATH = "C:\\Users\\gamin\\Desktop\\mat\\data\\piorun.db"

def inject():
    conn = sqlite3.connect(DB_PATH, timeout=30)
    cursor = conn.cursor()
    
    # Dane zadania
    name = "Filozoficzna Refleksja Wieczorna"
    run_date = "2026-04-13 22:00:00"
    payload = json.dumps(["mateuszch126@gmail.com", "Odwaga i Determinacja", "Prawdziwa odwaga to dziaanie mimo strachu. - Piorun ⚡"])
    
    # Insert
    cursor.execute("INSERT INTO tasks (name, job_id, type, schedule_time, payload, status) VALUES (?, ?, ?, ?, ?, ?)",
                   (name, "EMERGENCY_JOB_001", "EMAIL", run_date, payload, "PENDING"))
    
    conn.commit()
    conn.close()
    print("[✔] Zadanie wstrzyknięte do bazy na 22:00.")

if __name__ == "__main__":
    inject()

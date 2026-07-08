import sqlite3
import os

DB_PATH = "C:\\Users\\gamin\\.piorun\\piorun.db"

def diagnose():
    if not os.path.exists(DB_PATH):
        print("Baza nie istnieje.")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    print("\n--- TABELA TASKS (Aplikacyjna) ---")
    cursor.execute("SELECT id, name, job_id, status, last_error FROM tasks")
    for row in cursor.fetchall():
        print(f"ID: {row[0]} | Name: {row[1]} | JobID: {row[2]} | Status: {row[3]} | Error: {row[4]}")

    print("\n--- TABELA APSCHEDULER_JOBS (Wewnetrzna) ---")
    try:
        cursor.execute("SELECT id, next_run_time FROM apscheduler_jobs")
        for row in cursor.fetchall():
            print(f"JobStore ID: {row[0]} | Next Run: {row[1]}")
    except Exception as e:
        print(f"Blad odczytu jobstore: {e}")

    print("\n--- OSTATNIE LOGI AUDYTOWE ---")
    cursor.execute("SELECT event_type, description, timestamp FROM audit_logs ORDER BY timestamp DESC LIMIT 10")
    for row in cursor.fetchall():
        print(f" [{row[2]}] {row[0]}: {row[1]}")

    conn.close()

if __name__ == "__main__":
    diagnose()

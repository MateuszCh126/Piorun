import sqlite3
import os

HIST_DB = "C:\\Users\\gamin\\.piorun\\history.db"
TSKS_DB = "C:\\Users\\gamin\\.piorun\\tasks.db"

def clean_history():
    print("[*] Czyszczenie history.db...")
    conn = sqlite3.connect(HIST_DB)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS tasks")
    cursor.execute("DROP TABLE IF EXISTS audit_logs")
    cursor.execute("DROP TABLE IF EXISTS apscheduler_jobs")
    conn.commit()
    conn.close()

def clean_tasks():
    print("[*] Czyszczenie tasks.db...")
    conn = sqlite3.connect(TSKS_DB)
    cursor = conn.cursor()
    cursor.execute("DROP TABLE IF EXISTS session_metadata")
    cursor.execute("DROP TABLE IF EXISTS history")
    conn.commit()
    conn.close()

if __name__ == "__main__":
    clean_history()
    clean_tasks()
    print("[✔] Bazy danych zostaly poprawnie rozdzielone i oczyszczone.")

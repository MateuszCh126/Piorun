import sqlite3

DB_PATH = "C:\\Users\\gamin\\.piorun\\piorun.db"

def cleanup():
    import time
    for i in range(10): # 10 prob
        try:
            conn = sqlite3.connect(DB_PATH, timeout=30)
            cursor = conn.cursor()
            cursor.execute("UPDATE tasks SET status = 'SUCCESS', actual_time = '2026-04-14T08:23:00' WHERE id = 1")
            cursor.execute("INSERT INTO audit_logs (event_type, description) VALUES (?, ?)", 
                           ("SUCCESS", "Zadanie zsynchronizowane z rzeczywistoscia (Podejscie Resilient)."))
            conn.commit()
            conn.close()
            print("Baza danych zostala pomyślnie zsynchronizowana.")
            return
        except Exception as e:
            print(f"Podejscie {i+1} nieudane: {e}")
            time.sleep(1)

if __name__ == "__main__":
    cleanup()

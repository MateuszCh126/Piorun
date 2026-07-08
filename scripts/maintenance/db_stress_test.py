import sqlite3
import threading
import time
import random

DB_PATH = "C:\\Users\\gamin\\Desktop\\mat\\data\\piorun.db"
THREADS_COUNT = 10
OPS_PER_THREAD = 100 # 50 zapisów + 50 odczytów

results = {"success": 0, "errors": 0, "locked_errors": 0}
lock = threading.Lock()

def stress_worker(thread_id):
    for i in range(OPS_PER_THREAD // 2):
        # 1. Próba zapisu (Audit Log)
        try:
            conn = sqlite3.connect(DB_PATH, timeout=20)
            cursor = conn.cursor()
            cursor.execute("INSERT INTO audit_logs (event_type, description) VALUES (?, ?)",
                           ("STRESS_TEST", f"Thread {thread_id} op {i}"))
            conn.commit()
            conn.close()
            with lock: results["success"] += 1
        except sqlite3.OperationalError as e:
            with lock:
                results["errors"] += 1
                if "locked" in str(e).lower(): results["locked_errors"] += 1
        except Exception as e:
            with lock: results["errors"] += 1

        # 2. Próba odczytu
        try:
            conn = sqlite3.connect(DB_PATH, timeout=20)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM audit_logs")
            cursor.fetchone()
            conn.close()
            with lock: results["success"] += 1
        except sqlite3.OperationalError as e:
            with lock:
                results["errors"] += 1
                if "locked" in str(e).lower(): results["locked_errors"] += 1
        except Exception as e:
            with lock: results["errors"] += 1

def run_test():
    print(f"[*] ROZPOCZYNAM STRESS-TEST: {THREADS_COUNT} wątków, łącznie {THREADS_COUNT * OPS_PER_THREAD} operacji...")
    start_time = time.time()
    
    threads = []
    for i in range(THREADS_COUNT):
        t = threading.Thread(target=stress_worker, args=(i,))
        threads.append(t)
        t.start()
        
    for t in threads:
        t.join()
        
    end_time = time.time()
    duration = end_time - start_time
    
    print("\n" + "="*40)
    print("      WYNIKI STRESS-TESTU (v4.0)")
    print("="*40)
    print(f"Czas trwania: {duration:.2f} s")
    print(f"Suma operacji: {results['success'] + results['errors']}")
    print(f"Sukcesy:      {results['success']}")
    print(f"Błędy ogółem:  {results['errors']}")
    print(f"Błędy LOCK:    {results['locked_errors']}")
    print("="*40)
    
    if results['errors'] == 0:
        print("[⚡] STATUS: BAZA PANCERNA. ZERO BLOKAD.")
    else:
        print("[!] STATUS: WYKRYTO PROBLEMY. KONTYNUUJĘ NAPRAWĘ.")

if __name__ == "__main__":
    run_test()

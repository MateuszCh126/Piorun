import sqlite3
import time
import os

DB_PATH = "C:\\Users\\gamin\\Desktop\\mat\\data\\piorun.db"

def force_wal():
    print(f"[*] Rozpoczynam forsowną migrację do trybu WAL dla: {DB_PATH}")
    print("[*] Będę oczekiwał na zwolnienie bazy przez 60 sekund...")
    
    try:
        # Otwieramy połączenie z długim timeoutem
        conn = sqlite3.connect(DB_PATH, timeout=60)
        
        # 1. Sprawdzenie integralności
        print("[*] Sprawdzam integralność (integrity_check)...")
        result = conn.execute("PRAGMA integrity_check;").fetchone()
        if result[0] != "ok":
            print(f"[!] BŁĄD INTEGRALNOŚCI: {result[0]}")
            return
        
        # 2. Wymuszenie WAL
        print("[*] Wymuszam tryb WAL...")
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        
        # 3. Weryfikacja
        mode = conn.execute("PRAGMA journal_mode;").fetchone()
        print(f"[+] Status po operacji: {mode[0]}")
        
        conn.commit()
        conn.close()
        
        if mode[0].upper() == "WAL":
            print("[SUCCESS] Baza danych została pomyślnie skonfigurowana do trybu wielodostępowego.")
        else:
            print("[FAILURE] Nie udało się zmienić trybu na WAL.")
            
    except Exception as e:
        print(f"[CRITICAL] Błąd krytyczny podczas operacji: {e}")

if __name__ == "__main__":
    force_wal()

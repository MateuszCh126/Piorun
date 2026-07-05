import sqlite3
import os

DB_PATH = "C:\\Users\\gamin\\Desktop\\mat\\data\\piorun.db"

def fix_concurrency():
    try:
        conn = sqlite3.connect(DB_PATH)
        # Włączamy tryb WAL (Write Ahead Logging)
        conn.execute("PRAGMA journal_mode=WAL;")
        # Ustalamy synchroniczność na NORMAL (bezpieczne przy WAL)
        conn.execute("PRAGMA synchronous=NORMAL;")
        conn.commit()
        conn.close()
        print("Pomyślnie włączono tryb WAL. Baza danych powinna działać płynnie.")
    except Exception as e:
        print(f"Błąd podczas naprawy bazy: {e}")

if __name__ == "__main__":
    fix_concurrency()

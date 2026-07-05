import sqlite3

DB_PATH = "C:\\Users\\gamin\\Desktop\\mat\\data\\piorun.db"

def check():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name, status, actual_time, last_error FROM tasks WHERE name LIKE '%Test%' ORDER BY id DESC LIMIT 1")
    row = cursor.fetchone()
    conn.close()
    
    if row:
        print("\n" + "="*40)
        print("      PIORUN ⚡ FINAL VERIFICATION")
        print("="*40)
        print(f"Zadanie:     {row[0]}")
        print(f"Status:      {row[1]}")
        print(f"Czas wyk.:   {row[2]}")
        if row[3]: print(f"Ostatni błąd: {row[3]}")
        print("="*40)
    else:
        print("\n[!] Nie znaleziono zadania w bazie danych.")

if __name__ == "__main__":
    check()

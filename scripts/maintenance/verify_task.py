import sqlite3

DB_PATH = "C:\\Users\\gamin\\Desktop\\mat\\data\\piorun.db"

def verify():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    cursor.execute("SELECT name, schedule_time, status FROM tasks WHERE schedule_time LIKE '%22:00%'")
    rows = cursor.fetchall()
    conn.close()
    
    if rows:
        print("\n[✔] ZADANIE ODNALEZIONE W BAZIE:")
        for r in rows:
            print(f"- Nazwa: {r[0]} | Czas: {r[1]} | Status: {r[2]}")
    else:
        print("\n[!] Nie znaleziono zadania na 22:00.")

if __name__ == "__main__":
    verify()

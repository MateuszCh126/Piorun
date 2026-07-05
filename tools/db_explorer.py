import sqlite3
import pandas as pd
import os

def query_database(db_path, sql, read_only=True):
    """Wykonuje zapytanie SQL na lokalnej bazie SQLite."""
    if not os.path.exists(db_path):
        return f"Błąd: Baza danych {db_path} nie istnieje."
    
    # Proste zabezpieczenie przed modyfikacją danych, jeśli wybrano tryb read_only
    if read_only:
        sql_lower = sql.lower().strip()
        forbidden = ["drop", "delete", "update", "insert", "alter", "truncate", "vacuum"]
        if any(cmd in sql_lower for cmd in forbidden):
            return "Błąd: W trybie Read-Only dozwolone są tylko zapytania SELECT."

    try:
        conn = sqlite3.connect(db_path)
        # Używamy pandas dla ładniejszego formatowania wyników
        df = pd.read_sql_query(sql, conn)
        conn.close()
        
        if df.empty:
            return "Zapytanie wykonane pomyślnie, ale nie zwrócono żadnych rekordów."
        
        return df.to_string(index=False)
    except Exception as e:
        return f"Błąd bazy danych: {str(e)}"

def list_tables(db_path):
    """Pomocnicze narzędzie do sprawdzania struktury bazy."""
    sql = "SELECT name FROM sqlite_master WHERE type='table';"
    return query_database(db_path, sql)

if __name__ == "__main__":
    # Test
    # print(list_tables("C:\\moje\\dane.db"))
    pass

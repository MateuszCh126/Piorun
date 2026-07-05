import sqlite3
import os
try:
    from core.config import get_settings
except ModuleNotFoundError:
    import os
    import sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from core.config import get_settings

SETTINGS = get_settings()
DB_PATH = str(SETTINGS.history_db)


def recover_last_emails(keyword: str | None = None, limit: int = 10):
    if not os.path.exists(DB_PATH):
        print(f"Błąd: Nie znaleziono bazy w {DB_PATH}")
        return

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Szukamy ostatnich wiadomości asystenta (opcjonalnie filtrowanych po słowie kluczowym)
    if keyword:
        cursor.execute(
            """
            SELECT role, content, timestamp
            FROM history
            WHERE content LIKE ?
            ORDER BY id DESC LIMIT ?
            """,
            (f"%{keyword}%", limit),
        )
    else:
        cursor.execute(
            """
            SELECT role, content, timestamp
            FROM history
            ORDER BY id DESC LIMIT ?
            """,
            (limit,),
        )

    rows = cursor.fetchall()
    import sys
    # Wymuszenie UTF-8 dla konsoli Windows
    sys.stdout.reconfigure(encoding='utf-8')

    print("\n--- OSTATNIE LOGI KOMUNIKACJI ---\n")
    for r in rows:
        print(f"[{r[2]}] {r[0]}:\n{r[1]}\n")
    conn.close()


if __name__ == "__main__":
    import sys
    kw = sys.argv[1] if len(sys.argv) > 1 else None
    recover_last_emails(kw)

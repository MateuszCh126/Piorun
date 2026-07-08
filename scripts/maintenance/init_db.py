import os
import sys

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.db_schema as db_schema
from core.config import get_settings

SETTINGS = get_settings()
HIST_DB = str(SETTINGS.history_db)
TSKS_DB = str(SETTINGS.tasks_db)


def init_db():
    db_schema.ensure_all(HIST_DB, TSKS_DB)
    print(f"Baza historii gotowa: {HIST_DB}")
    print(f"Baza zadan gotowa:   {TSKS_DB}")


if __name__ == "__main__":
    init_db()

"""Izolacja srodowiska testowego.

Musi wykonac sie PRZED importem core.config (get_settings jest cachowane),
dlatego zmienne ustawiamy na poziomie importu conftest, nie w fixture.
Wszystkie sciezki Pioruna kierujemy do katalogu tymczasowego - testy nigdy
nie dotykaja prawdziwych baz, notatek ani folderu Desktop/Piorun.
"""
import os
import sys
import tempfile
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

_TMP = Path(tempfile.mkdtemp(prefix="piorun_tests_"))

os.environ["PIORUN_RUNTIME_ROOT"] = str(_TMP / "runtime")
os.environ["PIORUN_WORKDIR"] = str(_TMP / "Piorun")
os.environ["PIORUN_ALLOWED_ROOT"] = str(_TMP / "Piorun")
os.environ["PIORUN_SESSIONS_ROOT"] = str(_TMP / "Piorun" / "sessions")
os.environ["PIORUN_NOTES_ROOT"] = str(_TMP / "Piorun" / "notes")
os.environ["PIORUN_AUTONOMY_LOG"] = str(_TMP / "Piorun" / "autonomous_log.md")
os.environ["PIORUN_AUTONOMY_STATE_DIR"] = str(_TMP / "autonomy")
os.environ["PIORUN_HISTORY_DB"] = str(_TMP / "runtime" / "history.db")
os.environ["PIORUN_TASKS_DB"] = str(_TMP / "runtime" / "tasks.db")
os.environ["PIORUN_MEMORY_VECTOR_DB"] = str(_TMP / "memory_db")
os.environ["PIORUN_SANDBOX_DIR"] = str(_TMP / "sandbox")
os.environ["PIORUN_BACKUP_DIR"] = str(_TMP / "backups")
os.environ["PIORUN_AGENT_CREDENTIALS_PATH"] = str(_TMP / "agent_credentials.json")
os.environ["PIORUN_AUTONOMY_ENABLED"] = "false"
# Hooki pamieci wektorowej jako no-op: zaden test nie moze pobierac
# prawdziwego modelu embeddingow. Testy pamieci wlaczaja flage lokalnie
# (fixture memory_enabled w test_vector_memory.py) z falszywym embedderem.
os.environ["PIORUN_MEMORY_RECALL_ENABLED"] = "false"

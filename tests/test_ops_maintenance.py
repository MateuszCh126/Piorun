import zipfile
from datetime import datetime, timedelta

import core.ops_runtime as ops
from core.config import get_settings

SETTINGS = get_settings()


def test_rotate_old_logs_archives_and_removes():
    logs_dir = SETTINGS.allowed_root / "autonomy_logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    old_name = (datetime.now() - timedelta(days=120)).strftime("%Y-%m-%d") + ".md"
    fresh_name = datetime.now().strftime("%Y-%m-%d") + ".md"
    (logs_dir / old_name).write_text("stary log", encoding="utf-8")
    (logs_dir / fresh_name).write_text("swiezy log", encoding="utf-8")

    result = ops.rotate_old_logs(retention_days=90)
    assert old_name in result["archived"]
    assert not (logs_dir / old_name).exists()   # stary przeniesiony
    assert (logs_dir / fresh_name).exists()      # swiezy zostaje
    with zipfile.ZipFile(result["zip"]) as zf:
        assert any(old_name in n for n in zf.namelist())


def test_rotate_old_logs_noop_when_all_fresh():
    logs_dir = SETTINGS.allowed_root / "autonomy_logs"
    logs_dir.mkdir(parents=True, exist_ok=True)
    for p in logs_dir.glob("*.md"):
        p.unlink()
    (logs_dir / (datetime.now().strftime("%Y-%m-%d") + ".md")).write_text("x", encoding="utf-8")
    assert ops.rotate_old_logs(retention_days=90)["archived"] == []


def test_prune_backups_keeps_newest_n():
    backup_dir = SETTINGS.backup_dir
    backup_dir.mkdir(parents=True, exist_ok=True)
    for p in backup_dir.glob("piorun_backup_*.zip"):
        p.unlink()
    # Utworz 10 backupow z rosnacym mtime.
    import os
    import time
    created = []
    for i in range(10):
        p = backup_dir / f"piorun_backup_2026010{i}_000000.zip"
        p.write_text("x", encoding="utf-8")
        os.utime(p, (time.time() + i, time.time() + i))
        created.append(p)

    removed = ops.prune_backups(keep=8)
    remaining = list(backup_dir.glob("piorun_backup_*.zip"))
    assert len(remaining) == 8
    assert len(removed) == 2
    # Najstarsze dwa (i=0,1) usuniete.
    names = {p.name for p in remaining}
    assert "piorun_backup_20260100_000000.zip" not in names

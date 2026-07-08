"""Health-check Pioruna: jedna komenda mowi, czy caly stack jest sprawny.

Uzycie: python piorun.py doctor
Sprawdza: endpoint LLM, model Whisper, wyszukiwarke, embeddingi, poswiadczenia
e-mail, wolne miejsce, urzadzenie loopback i zapisywalnosc baz. Zaden check nie
rzuca wyjatku - kazdy zwraca ok/detail, zeby raport zawsze sie wyswietlil.
"""
import importlib.util
import os
import shutil

from core.config import get_settings

SETTINGS = get_settings()


def _check(name, ok, detail=""):
    return {"name": name, "ok": bool(ok), "detail": str(detail)}


def check_llm():
    try:
        import core.ops_runtime as ops

        health = ops.check_llm_health()
        return _check("LLM endpoint", health["ok"],
                      health.get("endpoint", "") if health["ok"] else health.get("error", ""))
    except Exception as e:
        return _check("LLM endpoint", False, str(e))


def check_whisper_model():
    path = str(SETTINGS.whisper_model_path)
    model_bin = os.path.join(path, "model.bin")
    ok = os.path.isdir(path) and os.path.exists(model_bin)
    return _check("Model Whisper", ok, path if ok else f"brak model.bin w {path}")


def check_ddgs():
    ok = (importlib.util.find_spec("ddgs") is not None
          or importlib.util.find_spec("duckduckgo_search") is not None)
    return _check("Wyszukiwarka (ddgs)", ok, "dostepna" if ok else "pip install ddgs")


def check_embeddings():
    ok = importlib.util.find_spec("sentence_transformers") is not None
    return _check("Embeddingi (sentence-transformers)", ok,
                  "dostepne" if ok else "brak - pamiec uzyje fallbacku EN; pip install sentence-transformers")


def check_credentials():
    p = str(SETTINGS.agent_credentials_path)
    ok = os.path.exists(p)
    return _check("Poswiadczenia e-mail", ok, "obecne" if ok else f"brak {p} (wysylka maili wylaczona)")


def check_disk():
    try:
        usage = shutil.disk_usage(str(SETTINGS.workdir))
        free_gb = usage.free / (1024 ** 3)
        return _check("Wolne miejsce (workdir)", free_gb > 1.0, f"{free_gb:.1f} GB")
    except Exception as e:
        return _check("Wolne miejsce (workdir)", False, str(e))


def check_loopback():
    try:
        import pyaudiowpatch as pyaudio

        import tools.lecture_recorder as lr

        p = pyaudio.PyAudio()
        try:
            dev = lr.LectureRecorder("doctor").get_loopback_device(p)
        finally:
            p.terminate()
        ok = dev is not None
        return _check("Urzadzenie loopback", ok,
                      dev["name"] if ok else "brak (nagrywanie wykladu niedostepne)")
    except Exception as e:
        return _check("Urzadzenie loopback", False, str(e))


def check_databases():
    results = []
    for label, path in [("history.db", SETTINGS.history_db), ("tasks.db", SETTINGS.tasks_db)]:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            ok = os.access(str(path.parent), os.W_OK)
            results.append(_check(f"Baza {label}", ok, str(path)))
        except Exception as e:
            results.append(_check(f"Baza {label}", False, str(e)))
    return results


def run_checks():
    checks = [
        check_llm(),
        check_whisper_model(),
        check_ddgs(),
        check_embeddings(),
        check_credentials(),
        check_disk(),
        check_loopback(),
    ]
    checks.extend(check_databases())
    return checks


def print_report():
    checks = run_checks()
    print("\n=== PIORUN DOCTOR ===")
    for c in checks:
        mark = "OK" if c["ok"] else "!!"
        print(f"[{mark}] {c['name']}: {c['detail']}")
    failed = [c for c in checks if not c["ok"]]
    total = len(checks)
    if failed:
        print(f"\n{total - len(failed)}/{total} sprawnych. Problemy: {', '.join(c['name'] for c in failed)}")
    else:
        print(f"\n{total}/{total} - wszystko sprawne.")
    return len(failed) == 0


if __name__ == "__main__":
    import sys

    sys.exit(0 if print_report() else 1)

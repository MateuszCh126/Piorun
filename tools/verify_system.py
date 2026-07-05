"""
Skrypt weryfikacji systemu Piorun v4.6.2
Sprawdza: Audio, Pamiec, CLI Imports, DOCX
"""
import sys
import os
try:
    from core.config import get_settings
except ModuleNotFoundError:
    import os
    import sys
    sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))
    from core.config import get_settings

SETTINGS = get_settings()

# Upewnij sie, ze Python widzi moduły Pioruna
BASE_DIR = str(SETTINGS.workspace_root)
if BASE_DIR not in sys.path:
    sys.path.insert(0, BASE_DIR)

results = []

# ---- 1. Audio ----
print("[1/4] Test Audio (WASAPI Loopback Stereo)...")
try:
    import pyaudiowpatch as pyaudio
    p = pyaudio.PyAudio()
    wasapi = None
    for i in range(p.get_host_api_count()):
        api = p.get_host_api_info_by_index(i)
        if "WASAPI" in api["name"]:
            wasapi = api
            break
    if wasapi:
        default_out = p.get_device_info_by_index(wasapi["defaultOutputDevice"])
        for i in range(p.get_device_count()):
            dev = p.get_device_info_by_index(i)
            if dev["hostApi"] == wasapi["index"] and dev["isLoopbackDevice"]:
                if default_out["name"] in dev["name"]:
                    rate = int(dev["defaultSampleRate"])
                    stream = p.open(
                        format=pyaudio.paInt16,
                        channels=2,
                        rate=rate,
                        input=True,
                        input_device_index=dev["index"],
                        frames_per_buffer=1024
                    )
                    stream.close()
                    results.append(f"[OK] Audio: {dev['name']} | {rate} Hz | Stereo")
                    break
    p.terminate()
except Exception as e:
    results.append(f"[FAIL] Audio: {e}")

# ---- 2. Pamięć Globalna ----
print("[2/4] Test Pamięci Globalnej...")
try:
    from tools.memory import search_global_history
    res = search_global_history("test")
    if str(res).lower().startswith("błąd"):
        results.append(f"[FAIL] Pamięć: {res}")
    else:
        results.append(f"[OK] search_global_history działa (odpowiedź: {res[:40]}...)")
except Exception as e:
    results.append(f"[FAIL] Pamięć: {e}")

# ---- 3. Brain / Core ----
print("[3/4] Test importu core.brain...")
try:
    import core.brain as brain
    prompt = brain.get_system_prompt()
    if str(SETTINGS.workdir) in prompt:
        results.append("[OK] Brain: Swiadomosc Przestrzenna wgrana poprawnie")
    else:
        results.append("[WARN] Brain: Brak sciezki przestrzennej w prompcie!")
except Exception as e:
    results.append(f"[FAIL] Brain: {e}")

# ---- 4. DOCX ----
print("[4/4] Test pliku DOCX...")
docx_path = str(SETTINGS.workdir / "piorun_bio.docx")
if os.path.exists(docx_path):
    size_kb = os.path.getsize(docx_path) // 1024
    results.append(f"[OK] DOCX istnieje: {docx_path} ({size_kb} KB)")
else:
    results.append(f"[FAIL] DOCX nie istnieje: {docx_path}")

# ---- RAPORT KOŃCOWY ----
print("\n" + "="*55)
print("  RAPORT WERYFIKACJI: Piorun v4.6.2")
print("="*55)
for r in results:
    print(r)
print("="*55)

fail_count = sum(1 for r in results if "[FAIL]" in r)
if fail_count == 0:
    print("\n[SYSTEM GOTOWY] Mozesz uruchomic Pioruna.")
else:
    print(f"\n[UWAGA] Znaleziono {fail_count} problem(y). Sprawdz powyzej.")

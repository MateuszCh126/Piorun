import json
import os
import subprocess
import sys
import time
import urllib.request

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from core.config import get_settings

SETTINGS = get_settings()


def _http_get(url, timeout=5):
    req = urllib.request.Request(url=url, method="GET")
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def _http_post(url, payload, timeout=10):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(url=url, method="POST", data=data, headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    base = f"http://{SETTINGS.ops_api_host}:{SETTINGS.ops_api_port}"
    env = dict(os.environ)
    env.setdefault("PIORUN_LLM_HEALTH_TIMEOUT_SECONDS", "1")
    proc = subprocess.Popen([sys.executable, os.path.join("tools", "ops_api_server.py")], env=env)
    try:
        # Czekamy, aż serwer wystartuje.
        ready = False
        for _ in range(30):
            try:
                _http_get(f"{base}/health", timeout=5)
                ready = True
                break
            except Exception:
                time.sleep(0.2)
        if not ready:
            raise RuntimeError("Ops API nie uruchomilo sie w czasie oczekiwania.")

        health = _http_get(f"{base}/health")
        status = _http_get(f"{base}/status")
        sessions = _http_get(f"{base}/sessions/recent?limit=5")
        summaries = _http_get(f"{base}/summaries/recent?limit=5")
        tasks = _http_get(f"{base}/tasks/recent?limit=5")
        autonomy_state = _http_get(f"{base}/autonomy/state")
        autonomy_queue = _http_get(f"{base}/autonomy/queue?limit=5")
        try:
            tick = _http_post(f"{base}/autonomy/tick", {}, timeout=45)
        except Exception as e:
            tick = {"error": str(e)}
        backup = _http_post(f"{base}/backup", {"include_workdir": False})

        print("health_ok=", health.get("ok"))
        print("status_keys=", sorted(list(status.keys()))[:8])
        print("sessions_items=", len(sessions.get("items", [])))
        print("summaries_items=", len(summaries.get("items", [])))
        print("tasks_items=", len(tasks.get("items", [])))
        print("autonomy_enabled=", autonomy_state.get("enabled"))
        print("autonomy_queue_items=", len(autonomy_queue.get("items", [])))
        print("autonomy_tick_keys=", sorted(list(tick.keys()))[:6])
        print("backup_path=", backup.get("backup_path"))
    finally:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()


if __name__ == "__main__":
    main()

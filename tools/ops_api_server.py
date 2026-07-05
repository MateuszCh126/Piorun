import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

import core.ops_runtime as ops
from core.config import get_settings

SETTINGS = get_settings()


def _json_bytes(payload):
    return json.dumps(payload, ensure_ascii=False).encode("utf-8")


def _to_int(value, default):
    try:
        return int(value)
    except Exception:
        return int(default)


class OpsHandler(BaseHTTPRequestHandler):
    server_version = "PiorunOps/1.0"

    def _send_json(self, status, payload):
        body = _json_bytes(payload)
        try:
            self.send_response(status)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return True
        except OSError:
            return False

    def _read_json_body(self):
        length = _to_int(self.headers.get("Content-Length"), 0)
        if length <= 0:
            return {}
        raw = self.rfile.read(length).decode("utf-8")
        if not raw.strip():
            return {}
        try:
            return json.loads(raw)
        except Exception:
            return {}

    def do_GET(self):
        parsed = urlparse(self.path)
        query = parse_qs(parsed.query)
        path = parsed.path

        try:
            if path == "/health":
                return self._send_json(200, ops.get_runtime_health())
            if path == "/status":
                return self._send_json(200, ops.get_runtime_status())
            if path == "/sessions/recent":
                limit = _to_int((query.get("limit") or ["20"])[0], 20)
                return self._send_json(200, {"items": ops.list_recent_sessions(limit=limit)})
            if path == "/summaries/recent":
                limit = _to_int((query.get("limit") or ["20"])[0], 20)
                return self._send_json(200, {"items": ops.list_recent_summaries(limit=limit)})
            if path == "/tasks/recent":
                limit = _to_int((query.get("limit") or ["20"])[0], 20)
                return self._send_json(200, {"items": ops.list_recent_tasks(limit=limit)})
            if path == "/autonomy/state":
                return self._send_json(200, ops.get_autonomy_state())
            if path == "/autonomy/queue":
                limit = _to_int((query.get("limit") or ["50"])[0], 50)
                return self._send_json(200, {"items": ops.list_autonomy_queue(limit=limit)})

            return self._send_json(404, {"error": "Not found", "path": path})
        except Exception as e:
            self._send_json(500, {"error": str(e), "path": path})
            return

    def do_POST(self):
        parsed = urlparse(self.path)
        path = parsed.path

        try:
            if path == "/backup":
                payload = self._read_json_body()
                include_workdir = bool(payload.get("include_workdir", True))
                result = ops.create_backup(include_workdir=include_workdir)
                return self._send_json(200, result)
            if path == "/autonomy/tick":
                result = ops.run_autonomy_tick_now()
                return self._send_json(200, result)
            if path == "/autonomy/decision":
                payload = self._read_json_body()
                item_id = str(payload.get("id", "")).strip()
                decision = str(payload.get("decision", "")).strip().lower()
                reviewer = str(payload.get("reviewer", "ops_api")).strip() or "ops_api"
                reason = str(payload.get("reason", "")).strip()
                if not item_id:
                    return self._send_json(400, {"error": "missing_id"})
                if decision not in {"approve", "reject"}:
                    return self._send_json(400, {"error": "invalid_decision", "allowed": ["approve", "reject"]})
                result = ops.decide_autonomy_queue_item(item_id=item_id, decision=decision, reviewer=reviewer, reason=reason)
                status = 200 if result.get("ok") else 404
                return self._send_json(status, result)
            return self._send_json(404, {"error": "Not found", "path": path})
        except Exception as e:
            self._send_json(500, {"error": str(e), "path": path})
            return

    def log_message(self, format, *args):
        # Celowo cicho - serwer operacyjny ma zwracać czysty output.
        return


def run_ops_api_server(host=None, port=None):
    host = host or SETTINGS.ops_api_host
    port = _to_int(port or SETTINGS.ops_api_port, SETTINGS.ops_api_port)
    server = ThreadingHTTPServer((host, port), OpsHandler)
    print(f"[*] Ops API listening on http://{host}:{port}")
    print(
        "[*] Endpoints: "
        "/health, /status, /sessions/recent, /summaries/recent, /tasks/recent, "
        "/autonomy/state, /autonomy/queue, POST /backup, POST /autonomy/tick, POST /autonomy/decision"
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        print("[*] Ops API stopped.")


if __name__ == "__main__":
    run_ops_api_server()

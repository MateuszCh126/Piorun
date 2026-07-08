import hmac
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


def _panel_html():
    return """<!DOCTYPE html>
<html lang="pl"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Piorun ⚡ Panel</title>
<style>
:root{--bg:#0d1117;--surface:#161b22;--border:#30363d;--text:#c9d1d9;--accent:#f0c040;}
*{box-sizing:border-box;}
body{background:var(--bg);color:var(--text);font-family:'Segoe UI',system-ui,sans-serif;margin:0;padding:20px;line-height:1.5;}
h1{color:var(--accent);font-size:1.5em;}h2{color:#fff;border-bottom:1px solid var(--border);padding-bottom:6px;margin-top:28px;}
.card{background:var(--surface);border:1px solid var(--border);border-radius:10px;padding:16px;margin-bottom:12px;}
.stats{display:flex;flex-wrap:wrap;gap:20px;}
.stat b{color:var(--accent);font-size:1.5em;display:block;}
button{background:var(--border);color:var(--text);border:0;border-radius:8px;padding:12px 18px;margin:4px 6px 4px 0;cursor:pointer;font-size:1em;min-height:44px;}
button:active{opacity:0.7;}
button.approve{background:#238636;color:#fff;}button.reject{background:#8b2c2c;color:#fff;}button.primary{background:var(--accent);color:#000;}
.muted{opacity:0.6;font-size:0.85em;}
#tokenBar{margin-bottom:16px;}
#tokenBar input{padding:10px;border-radius:8px;border:1px solid var(--border);background:var(--surface);color:var(--text);font-size:1em;}
@media(max-width:600px){body{padding:14px;}button{width:100%;margin:6px 0;}.card button{width:auto;}}
</style></head><body>
<h1>Piorun ⚡ Panel operacyjny</h1>
<div id="tokenBar"></div>
<div id="state" class="card">Ładowanie…</div>
<button class="primary" onclick="tick()">Uruchom tick teraz</button>
<button onclick="refresh()">Odśwież</button>
<h2>Kolejka akceptacji</h2>
<div id="queue">Ładowanie…</div>
<script>
function getToken(){
  var u=new URLSearchParams(location.search).get('token');
  if(u){localStorage.setItem('piorun_token',u);history.replaceState({},'',location.pathname);return u;}
  return localStorage.getItem('piorun_token')||'';
}
function setToken(t){localStorage.setItem('piorun_token',t||'');}
function hdr(){var t=localStorage.getItem('piorun_token')||'';return t?{'X-Piorun-Token':t}:{};}
async function jget(u){const r=await fetch(u,{headers:hdr()});if(r.status===401){onUnauthorized();throw new Error('401');}return r.json();}
async function jpost(u,b){const r=await fetch(u,{method:'POST',headers:Object.assign({'Content-Type':'application/json'},hdr()),body:JSON.stringify(b||{})});if(r.status===401){onUnauthorized();throw new Error('401');}return r.json();}
function onUnauthorized(){
  document.getElementById('tokenBar').innerHTML=
    '<div class="muted">Wymagany token dostępu:</div>'+
    '<input id="tk" type="password" placeholder="token…"> <button onclick="saveToken()">Zapisz</button>';
}
function saveToken(){setToken(document.getElementById('tk').value.trim());document.getElementById('tokenBar').innerHTML='';refresh();}
async function refresh(){
  try{
    const s=await jget('/autonomy/state');
    document.getElementById('state').innerHTML='<div class="stats">'+
      `<span class="stat"><b>${s.enabled}</b>autonomia</span>`+
      `<span class="stat"><b>${s.queue_size}</b>w kolejce</span>`+
      `<span class="stat"><b>${s.ticks_count}</b>ticki</span>`+
      `<span class="stat"><b>${s.autoexec_count_this_hour}</b>akcje/h</span></div>`+
      `<div class="muted">Ostatni tick: ${s.last_tick_at||'—'}</div>`;
    const q=(await jget('/autonomy/queue?limit=50')).items||[];
    if(!q.length){document.getElementById('queue').innerHTML='<div class="muted">Kolejka pusta.</div>';return;}
    document.getElementById('queue').innerHTML=q.map(function(it){
      const a=it.action||{};
      return `<div class="card"><b>${(it.title||'').replace(/</g,'&lt;')}</b>`+
        `<div class="muted">akcja=${a.type||''} | conf=${it.confidence} | blokada=${it.reason_blocked||''}</div>`+
        `<button class="approve" onclick="decide('${it.id}','approve')">Zatwierdź</button>`+
        `<button class="reject" onclick="decide('${it.id}','reject')">Odrzuć</button></div>`;
    }).join('');
  }catch(e){/* 401 obsluzone w onUnauthorized */}
}
async function decide(id,d){try{await jpost('/autonomy/decision',{id:id,decision:d});refresh();}catch(e){}}
async function tick(){try{await jpost('/autonomy/tick',{});refresh();}catch(e){}}
getToken();refresh();
</script></body></html>"""


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

    def _send_html(self, status, html):
        body = html.encode("utf-8")
        try:
            self.send_response(status)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return True
        except OSError:
            return False

    def _authorized(self):
        """Bramka uwierzytelnienia. Gdy PIORUN_OPS_API_TOKEN pusty -> brak auth
        (zgodnosc z czysto-lokalnym uzyciem). Gdy ustawiony -> wymagany token
        w naglowku X-Piorun-Token albo w query ?token= (porownanie stalego czasu)."""
        token = SETTINGS.ops_api_token
        if not token:
            return True
        provided = self.headers.get("X-Piorun-Token", "")
        if not provided:
            provided = (parse_qs(urlparse(self.path).query).get("token") or [""])[0]
        return hmac.compare_digest(str(provided), str(token))

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
            # Powloka panelu jest publiczna (sama poprosi o token); dane wymagaja tokenu.
            if path in ("/", "/panel"):
                return self._send_html(200, _panel_html())
            if not self._authorized():
                return self._send_json(401, {"error": "unauthorized"})
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
            if not self._authorized():
                return self._send_json(401, {"error": "unauthorized"})
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

    is_loopback = host in ("127.0.0.1", "localhost", "::1")
    if not is_loopback and not SETTINGS.ops_api_token:
        print(
            "[!] OSTRZEZENIE: serwer nasluchuje poza localhostem "
            f"({host}) BEZ tokenu. Ustaw PIORUN_OPS_API_TOKEN, "
            "zanim wystawisz panel na siec (Tailscale) - inaczej kazdy w sieci "
            "moze zatwierdzac akcje autonomii."
        )
    if SETTINGS.ops_api_token:
        print("[*] Auth: token wymagany (PIORUN_OPS_API_TOKEN ustawiony).")

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

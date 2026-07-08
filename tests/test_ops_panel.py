import threading
import time
import urllib.error
import urllib.request

from http.server import ThreadingHTTPServer

import tools.ops_api_server as ops_srv


def _serve(port):
    server = ThreadingHTTPServer(("127.0.0.1", port), ops_srv.OpsHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.3)
    return server


def test_panel_html_has_core_elements():
    html = ops_srv._panel_html()
    assert "<!DOCTYPE html>" in html
    assert "Panel operacyjny" in html
    assert "/autonomy/queue" in html
    assert "/autonomy/decision" in html
    assert "/autonomy/tick" in html
    assert "X-Piorun-Token" in html  # obsluga tokenu w panelu


def test_panel_served_over_http():
    server = _serve(8793)
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:8793/", timeout=5)
        assert resp.status == 200
        body = resp.read().decode("utf-8")
        assert "Panel operacyjny" in body
        assert "text/html" in resp.headers.get("Content-Type", "")
    finally:
        server.shutdown()
        server.server_close()


def test_token_auth_enforced(monkeypatch):
    monkeypatch.setattr(
        ops_srv, "SETTINGS",
        ops_srv.SETTINGS.__class__(**{**ops_srv.SETTINGS.__dict__, "ops_api_token": "sekret123"}),
    )
    server = _serve(8795)
    try:
        # Powloka panelu (/) dostepna bez tokenu.
        assert urllib.request.urlopen("http://127.0.0.1:8795/", timeout=5).status == 200

        # Endpoint danych bez tokenu -> 401.
        try:
            urllib.request.urlopen("http://127.0.0.1:8795/autonomy/state", timeout=5)
            assert False, "spodziewane 401"
        except urllib.error.HTTPError as e:
            assert e.code == 401

        # Z tokenem w naglowku -> 200.
        req = urllib.request.Request("http://127.0.0.1:8795/autonomy/state",
                                     headers={"X-Piorun-Token": "sekret123"})
        assert urllib.request.urlopen(req, timeout=5).status == 200

        # Z tokenem w query -> 200.
        assert urllib.request.urlopen(
            "http://127.0.0.1:8795/autonomy/state?token=sekret123", timeout=5).status == 200

        # Zly token -> 401.
        req_bad = urllib.request.Request("http://127.0.0.1:8795/autonomy/state",
                                         headers={"X-Piorun-Token": "zle"})
        try:
            urllib.request.urlopen(req_bad, timeout=5)
            assert False, "spodziewane 401"
        except urllib.error.HTTPError as e:
            assert e.code == 401
    finally:
        server.shutdown()
        server.server_close()

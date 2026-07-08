import threading
import time
import urllib.request

from http.server import ThreadingHTTPServer

import tools.ops_api_server as ops_srv


def test_panel_html_has_core_elements():
    html = ops_srv._panel_html()
    assert "<!DOCTYPE html>" in html
    assert "Panel operacyjny" in html
    assert "/autonomy/queue" in html
    assert "/autonomy/decision" in html
    assert "/autonomy/tick" in html


def test_panel_served_over_http():
    server = ThreadingHTTPServer(("127.0.0.1", 8793), ops_srv.OpsHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    time.sleep(0.3)
    try:
        resp = urllib.request.urlopen("http://127.0.0.1:8793/", timeout=5)
        assert resp.status == 200
        body = resp.read().decode("utf-8")
        assert "Panel operacyjny" in body
        assert "text/html" in resp.headers.get("Content-Type", "")
    finally:
        server.shutdown()
        server.server_close()

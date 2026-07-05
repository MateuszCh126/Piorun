"""piorun_gui.py — Nowoczesny interfejs PIORUN (pywebview + HTML/CSS/JS)

Wymagania:
    pip install pywebview

Zastępuje stary piorun_chat_gui.py oparty na tkinter.
Uruchamiaj tak samo: python piorun_gui.py
"""

from __future__ import annotations

import json
import os
import socket
import sqlite3
import subprocess
import sys
import threading
from datetime import datetime


def _configure_qt_rendering() -> None:
    """
    Konfiguracja renderingu pywebview+Qt na Windows.

    Domyslnie (performance): zostawiamy hardware rendering.
    Opcjonalnie (stable): wymuszenie software renderingu i flag anty-flicker.

    Sterowanie:
    - PIORUN_GUI_RENDER_MODE=performance (default)
    - PIORUN_GUI_RENDER_MODE=stable
    - kompatybilnosc wsteczna: PIORUN_GUI_STABLE_RENDER=1 -> stable
    """
    if sys.platform != "win32":
        return

    mode = str(os.environ.get("PIORUN_GUI_RENDER_MODE", "performance")).strip().lower()
    legacy = os.environ.get("PIORUN_GUI_STABLE_RENDER")
    if legacy is not None:
        legacy_on = str(legacy).strip().lower() in {"1", "true", "yes", "y", "on"}
        if legacy_on:
            mode = "stable"

    existing = str(os.environ.get("QTWEBENGINE_CHROMIUM_FLAGS", "")).strip()
    flags = [f for f in existing.split(" ") if f]
    heavy_flags = [
        "--disable-gpu",
        "--disable-gpu-compositing",
        "--disable-gpu-vsync",
        "--disable-features=UseSkiaRenderer",
    ]

    if mode == "stable":
        # Najbardziej odporny na migniecia, ale wolniejszy.
        os.environ.setdefault("QT_OPENGL", "software")
        for flag in heavy_flags:
            if flag not in flags:
                flags.append(flag)
    else:
        # Tryb wydajnosci: usuwamy ciezkie flagi z procesu.
        flags = [f for f in flags if f not in heavy_flags]
        if os.environ.get("QT_OPENGL", "").strip().lower() == "software":
            # Nie wymuszamy software renderingu domyslnie.
            os.environ.pop("QT_OPENGL", None)

    os.environ["QTWEBENGINE_CHROMIUM_FLAGS"] = " ".join(flags)


_configure_qt_rendering()

import webview

import core.brain as brain
import core.db_schema as db_schema
from core.config import get_settings

SETTINGS   = get_settings()
HISTORY_DB = str(SETTINGS.history_db)


# ── utils ─────────────────────────────────────────────────────────────────────

def ensure_core_running() -> None:
    try:
        with socket.create_connection(("127.0.0.1", 9999), timeout=1):
            return
    except Exception:
        pass
    try:
        subprocess.Popen(
            [sys.executable, str(SETTINGS.workspace_root / "piorun_core.py")],
            creationflags=0x00000008,
            close_fds=True,
        )
    except Exception:
        pass


# ── Python ↔ JS bridge ────────────────────────────────────────────────────────

class PiorunAPI:
    """All public methods are callable from JS via window.pywebview.api.*"""

    def __init__(self) -> None:
        self._window: webview.Window | None = None
        self.session_id: str = ""
        self.topic:      str = ""
        self.history:    list[dict] = []
        self.busy:       bool = False

        db_schema.ensure_history_db(HISTORY_DB)
        ensure_core_running()
        self._reset_session()

    def set_window(self, w: webview.Window) -> None:
        self._window = w

    # ── internals ─────────────────────────────────────────────────────────────

    def _reset_session(self) -> None:
        self.session_id = f"SESS_{datetime.now().strftime('%Y%m%d_%H%M%S')}"
        self.topic   = "Nowa konwersacja"
        self.history = [{"role": "system", "content": brain.get_system_prompt()}]

    def _push(self, event_type: str, data) -> None:
        """Thread-safe push to JS event bus."""
        if self._window is None:
            return
        payload = json.dumps({"type": event_type, "data": data}, ensure_ascii=False)
        safe    = json.dumps(payload)          # produces a valid JS string literal
        self._window.evaluate_js(f"window.__piorun_event({safe})")

    def _update_topic_db(self) -> None:
        with sqlite3.connect(HISTORY_DB, timeout=20) as conn:
            conn.execute(
                "UPDATE history SET topic = ? WHERE session_id = ?",
                (self.topic, self.session_id),
            )

    # ── JS-callable ───────────────────────────────────────────────────────────

    def get_sessions(self) -> list[dict]:
        with sqlite3.connect(HISTORY_DB, timeout=20) as conn:
            rows = conn.execute(
                """
                SELECT session_id,
                       MAX(topic)     AS topic,
                       MAX(timestamp) AS last_ts,
                       COUNT(*)       AS msg_count
                FROM history
                GROUP BY session_id
                ORDER BY last_ts DESC
                LIMIT 80
                """
            ).fetchall()
        return [
            {
                "session_id": r[0],
                "topic":      (r[1] or "Brak tematu").strip(),
                "timestamp":  (r[2] or "").strip(),
                "count":      r[3],
            }
            for r in rows
        ]

    def new_session(self) -> bool:
        if self.busy:
            return False
        self._reset_session()
        return True

    def resume_session(self, session_id: str, topic: str) -> "dict | bool":
        if self.busy:
            return False
        with sqlite3.connect(HISTORY_DB, timeout=20) as conn:
            rows = conn.execute(
                "SELECT role, content FROM history WHERE session_id = ? ORDER BY id ASC",
                (session_id,),
            ).fetchall()
        messages = [{"role": r[0], "content": r[1]} for r in rows]
        self.session_id = session_id
        self.topic      = topic or "Wznowiona konwersacja"
        self.history    = [{"role": "system", "content": brain.get_system_prompt()}] + messages
        return {"messages": messages, "topic": self.topic}

    def send_message(self, text: str) -> "bool | dict":
        text = (text or "").strip()
        if self.busy or not text:
            return False
        if not brain.save_message(self.session_id, self.topic, "user", text):
            return {"error": "db_locked"}
        self.history.append({"role": "user", "content": text})
        if self.topic == "Nowa konwersacja":
            self.topic = text[:44] + ("\u2026" if len(text) > 44 else "")
            self._update_topic_db()
        self.busy = True
        threading.Thread(target=self._run_brain, daemon=True).start()
        return True

    # ── brain worker ──────────────────────────────────────────────────────────

    def _run_brain(self) -> None:
        def cb(content: str, is_status: bool = False) -> None:
            self._push("status_msg" if is_status else "assistant_msg", str(content))

        try:
            updated = brain.execute_brain_loop(
                self.history, self.session_id, self.topic, print_callback=cb
            )
            self.history = updated
            self._push("done", {"topic": self.topic})
        except Exception as exc:
            self._push("error_msg", str(exc))
        finally:
            self.busy = False
            self._push("idle", None)


# ── HTML / CSS / JS ───────────────────────────────────────────────────────────

HTML = r"""<!DOCTYPE html>
<html lang="pl">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>PIORUN</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Onest:wght@300;400;500;600;700&family=IBM+Plex+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
/* ── Design tokens ───────────────────────────────────────────── */
:root {
  --bg:             #05080f;
  --surface:        rgba(255,255,255,0.03);
  --surface-raised: rgba(255,255,255,0.055);
  --border:         rgba(255,255,255,0.07);
  --border-strong:  rgba(255,255,255,0.13);
  --text:           #dce8fa;
  --text-dim:       #6b87b8;
  --text-faint:     #3a527a;
  --accent:         #2de0c8;
  --accent-dim:     rgba(45,224,200,0.15);
  --accent-glow:    rgba(45,224,200,0.25);
  --user-grad:      linear-gradient(145deg, #1c6bff 0%, #0d44cc 100%);
  --user-glow:      rgba(28,107,255,0.22);
  --status-bg:      rgba(130,80,255,0.12);
  --status-border:  rgba(130,80,255,0.22);
  --status-text:    #b89bff;
  --danger:         #ff5060;
  --mono:           'IBM Plex Mono', monospace;
  --sans:           'Onest', system-ui, sans-serif;
  --radius-sm:  10px;
  --radius-md:  16px;
  --radius-lg:  22px;
  --radius-xl:  28px;
  --sidebar-w:  290px;
  --ease:       cubic-bezier(0.34, 1.56, 0.64, 1);
  --ease-smooth: cubic-bezier(0.4, 0, 0.2, 1);
}

/* ── Reset ───────────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { height: 100%; }
body {
  font-family: var(--sans);
  background: var(--bg);
  color: var(--text);
  height: 100vh;
  overflow: hidden;
  -webkit-font-smoothing: antialiased;
}

/* ── Ambient background ──────────────────────────────────────── */
.bg {
  position: fixed; inset: 0;
  pointer-events: none;
  z-index: 0;
  overflow: hidden;
}
.bg::before {
  content: '';
  position: absolute;
  width: 900px; height: 900px;
  background: radial-gradient(circle, rgba(28,107,255,0.1) 0%, transparent 70%);
  top: -300px; left: -200px;
  animation: drift-a 25s ease-in-out infinite alternate;
}
.bg::after {
  content: '';
  position: absolute;
  width: 700px; height: 700px;
  background: radial-gradient(circle, rgba(45,224,200,0.07) 0%, transparent 70%);
  bottom: -200px; right: -100px;
  animation: drift-b 30s ease-in-out infinite alternate;
}
.bg-mid {
  position: absolute;
  width: 500px; height: 500px;
  background: radial-gradient(circle, rgba(130,80,255,0.06) 0%, transparent 70%);
  top: 35%; left: 35%;
  animation: drift-c 20s ease-in-out infinite alternate;
}

@keyframes drift-a {
  from { transform: translate(0, 0) scale(1); }
  to   { transform: translate(60px, 40px) scale(1.08); }
}
@keyframes drift-b {
  from { transform: translate(0, 0) scale(1); }
  to   { transform: translate(-40px, -30px) scale(1.05); }
}
@keyframes drift-c {
  from { transform: translate(0, 0) scale(1); }
  to   { transform: translate(30px, -40px) scale(0.95); }
}

/* Noise overlay */
.bg-noise {
  position: absolute; inset: 0;
  opacity: 0.018;
  background-image: url("data:image/svg+xml,%3Csvg viewBox='0 0 256 256' xmlns='http://www.w3.org/2000/svg'%3E%3Cfilter id='n'%3E%3CfeTurbulence type='fractalNoise' baseFrequency='0.9' numOctaves='4' stitchTiles='stitch'/%3E%3C/filter%3E%3Crect width='100%25' height='100%25' filter='url(%23n)'/%3E%3C/svg%3E");
  background-size: 180px 180px;
}

/* ── Layout ──────────────────────────────────────────────────── */
.app {
  display: flex;
  height: 100vh;
  padding: 14px;
  gap: 14px;
  position: relative;
  z-index: 1;
}

/* Glass utility */
.glass {
  background: var(--surface);
  backdrop-filter: blur(28px) saturate(160%);
  -webkit-backdrop-filter: blur(28px) saturate(160%);
  border: 1px solid var(--border);
}

/* ── Sidebar ─────────────────────────────────────────────────── */
.sidebar {
  width: var(--sidebar-w);
  flex-shrink: 0;
  border-radius: var(--radius-xl);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.sidebar-head {
  padding: 22px 20px 18px;
  border-bottom: 1px solid var(--border);
}
.sidebar-eyebrow {
  font-family: var(--mono);
  font-size: 9px;
  font-weight: 500;
  letter-spacing: 3px;
  color: var(--accent);
  text-transform: uppercase;
  margin-bottom: 8px;
}
.sidebar-title {
  font-size: 22px;
  font-weight: 700;
  letter-spacing: -0.5px;
  color: var(--text);
}

.sessions-scroll {
  flex: 1;
  overflow-y: auto;
  padding: 10px 10px;
  display: flex;
  flex-direction: column;
  gap: 3px;
}
.sessions-scroll::-webkit-scrollbar { width: 3px; }
.sessions-scroll::-webkit-scrollbar-track { background: transparent; }
.sessions-scroll::-webkit-scrollbar-thumb {
  background: rgba(255,255,255,0.08);
  border-radius: 2px;
}
.sessions-scroll::-webkit-scrollbar-thumb:hover {
  background: rgba(255,255,255,0.16);
}

.session-empty {
  font-size: 12px;
  color: var(--text-faint);
  text-align: center;
  padding: 32px 16px;
  font-style: italic;
}

.session-item {
  padding: 10px 12px;
  border-radius: var(--radius-md);
  cursor: pointer;
  border: 1px solid transparent;
  transition: all 0.18s var(--ease-smooth);
  position: relative;
  overflow: hidden;
}
.session-item::before {
  content: '';
  position: absolute;
  left: 0; top: 0; bottom: 0;
  width: 2px;
  background: var(--accent);
  transform: scaleY(0);
  transition: transform 0.2s var(--ease-smooth);
  border-radius: 0 2px 2px 0;
}
.session-item:hover {
  background: rgba(255,255,255,0.05);
  border-color: var(--border);
  transform: translateX(3px);
}
.session-item:hover::before { transform: scaleY(1); }
.session-item.active {
  background: var(--accent-dim);
  border-color: rgba(45,224,200,0.18);
}
.session-item.active::before { transform: scaleY(1); }
.session-topic {
  font-size: 12.5px;
  font-weight: 500;
  color: var(--text);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.3;
}
.session-meta {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--text-faint);
  margin-top: 3px;
}

.sidebar-actions {
  padding: 12px;
  border-top: 1px solid var(--border);
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* ── Buttons ─────────────────────────────────────────────────── */
.btn {
  font-family: var(--sans);
  font-size: 13px;
  font-weight: 600;
  padding: 10px 16px;
  border-radius: var(--radius-sm);
  border: 1px solid var(--border);
  background: var(--surface-raised);
  color: var(--text-dim);
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 8px;
  transition: all 0.18s var(--ease-smooth);
  position: relative;
  overflow: hidden;
}
.btn::after {
  content: '';
  position: absolute;
  inset: 0;
  background: linear-gradient(135deg, rgba(255,255,255,0.06), transparent);
  opacity: 0;
  transition: opacity 0.18s;
}
.btn:hover {
  border-color: var(--border-strong);
  color: var(--text);
  transform: translateY(-1px);
  box-shadow: 0 6px 20px rgba(0,0,0,0.35);
}
.btn:hover::after { opacity: 1; }
.btn:active { transform: translateY(0); box-shadow: none; }

.btn-accent {
  background: linear-gradient(145deg, rgba(45,224,200,0.18), rgba(45,224,200,0.06));
  border-color: rgba(45,224,200,0.22);
  color: var(--accent);
}
.btn-accent:hover {
  background: linear-gradient(145deg, rgba(45,224,200,0.28), rgba(45,224,200,0.12));
  border-color: rgba(45,224,200,0.4);
  box-shadow: 0 6px 24px var(--accent-glow);
  color: var(--accent);
}

/* ── Main chat panel ──────────────────────────────────────────── */
.chat-panel {
  flex: 1;
  border-radius: var(--radius-xl);
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
}

/* Topbar */
.topbar {
  padding: 18px 24px;
  display: flex;
  align-items: center;
  gap: 14px;
  border-bottom: 1px solid var(--border);
  flex-shrink: 0;
}
.topbar-logo {
  font-family: var(--mono);
  font-size: 14px;
  font-weight: 500;
  letter-spacing: 4px;
  color: var(--accent);
}
.topbar-sep {
  width: 1px;
  height: 16px;
  background: var(--border);
}
.topbar-topic {
  flex: 1;
  font-size: 13px;
  font-weight: 400;
  color: var(--text-dim);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}
.status-pill {
  display: flex;
  align-items: center;
  gap: 7px;
  padding: 6px 14px;
  border-radius: 99px;
  border: 1px solid var(--border);
  background: var(--surface-raised);
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 500;
  color: var(--text-dim);
  transition: all 0.3s var(--ease-smooth);
  white-space: nowrap;
}
.status-dot {
  width: 5px; height: 5px;
  border-radius: 50%;
  background: #3ddc84;
  transition: all 0.3s var(--ease-smooth);
  flex-shrink: 0;
}
.status-pill.thinking {
  border-color: rgba(45,224,200,0.25);
  background: var(--accent-dim);
  color: var(--accent);
}
.status-pill.thinking .status-dot {
  background: var(--accent);
  animation: dot-pulse 1.1s ease-in-out infinite;
}

@keyframes dot-pulse {
  0%, 100% { transform: scale(1);   opacity: 1; }
  50%       { transform: scale(0.4); opacity: 0.3; }
}

/* Feed */
.feed {
  flex: 1;
  overflow-y: auto;
  padding: 24px 28px;
  display: flex;
  flex-direction: column;
  gap: 14px;
  scroll-behavior: smooth;
}
.feed::-webkit-scrollbar { width: 4px; }
.feed::-webkit-scrollbar-track { background: transparent; }
.feed::-webkit-scrollbar-thumb {
  background: rgba(255,255,255,0.07);
  border-radius: 2px;
}
.feed::-webkit-scrollbar-thumb:hover { background: rgba(255,255,255,0.14); }

/* Welcome */
.welcome {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  min-height: 70%;
  gap: 10px;
  user-select: none;
  animation: fade-up 0.6s var(--ease-smooth) both;
}
.welcome-glyph {
  font-family: var(--mono);
  font-size: 56px;
  font-weight: 500;
  letter-spacing: 6px;
  background: linear-gradient(135deg, var(--accent) 0%, #6b8fff 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
  margin-bottom: 6px;
  line-height: 1;
}
.welcome-sub {
  font-size: 14px;
  color: var(--text-faint);
  letter-spacing: 0.2px;
}
.welcome-hint {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text-faint);
  opacity: 0.6;
  margin-top: 4px;
}

@keyframes fade-up {
  from { opacity: 0; transform: translateY(16px); }
  to   { opacity: 1; transform: translateY(0); }
}

/* Bubble rows */
.row {
  display: flex;
  flex-direction: column;
}
.row.user      { align-items: flex-end;   animation: slide-right 0.28s var(--ease) both; }
.row.assistant { align-items: flex-start; animation: slide-left  0.28s var(--ease) both; }
.row.status    { align-items: center;     animation: fade-up 0.25s var(--ease-smooth) both; }
.row.user + .row.user,
.row.assistant + .row.assistant { margin-top: -6px; }

@keyframes slide-right {
  from { opacity: 0; transform: translateX(16px) scale(0.97); }
  to   { opacity: 1; transform: translateX(0)    scale(1); }
}
@keyframes slide-left {
  from { opacity: 0; transform: translateX(-16px) scale(0.97); }
  to   { opacity: 1; transform: translateX(0)     scale(1); }
}

.bubble-meta {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--text-faint);
  margin-bottom: 5px;
  padding: 0 4px;
}

.bubble {
  max-width: 72%;
  padding: 12px 17px;
  font-size: 14px;
  line-height: 1.65;
  white-space: pre-wrap;
  word-break: break-word;
}

.bubble.user {
  background: var(--user-grad);
  color: #fff;
  border-radius: var(--radius-lg) 5px var(--radius-lg) var(--radius-lg);
  box-shadow: 0 5px 24px var(--user-glow);
}

.bubble.assistant {
  background: var(--surface-raised);
  border: 1px solid var(--border);
  color: var(--text);
  border-radius: 5px var(--radius-lg) var(--radius-lg) var(--radius-lg);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
}

.bubble.status {
  background: var(--status-bg);
  border: 1px solid var(--status-border);
  color: var(--status-text);
  border-radius: 99px;
  font-size: 11.5px;
  font-family: var(--mono);
  padding: 7px 18px;
  text-align: center;
  max-width: 85%;
}

/* Typing dots */
.typing {
  display: none;
  align-items: center;
  gap: 5px;
  padding: 14px 18px;
  background: var(--surface-raised);
  border: 1px solid var(--border);
  border-radius: 5px var(--radius-lg) var(--radius-lg) var(--radius-lg);
  animation: slide-left 0.28s var(--ease) both;
  align-self: flex-start;
}
.typing.show { display: flex; }
.dot {
  width: 5px; height: 5px;
  border-radius: 50%;
  background: var(--text-dim);
  animation: bounce-dot 1.3s ease-in-out infinite;
}
.dot:nth-child(2) { animation-delay: 0.18s; }
.dot:nth-child(3) { animation-delay: 0.36s; }

@keyframes bounce-dot {
  0%, 60%, 100% { transform: translateY(0);   opacity: 0.35; }
  30%            { transform: translateY(-7px); opacity: 1; }
}

/* Composer */
.composer-wrap {
  border-top: 1px solid var(--border);
  padding: 16px 20px 14px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  flex-shrink: 0;
}

.composer {
  display: flex;
  align-items: flex-end;
  gap: 12px;
}

.input-shell {
  flex: 1;
  display: flex;
  align-items: flex-end;
  background: rgba(255,255,255,0.04);
  border: 1px solid var(--border);
  border-radius: var(--radius-lg);
  padding: 13px 16px;
  transition: all 0.2s var(--ease-smooth);
  gap: 10px;
  position: relative;
}
.input-shell:focus-within {
  border-color: rgba(45,224,200,0.35);
  background: rgba(255,255,255,0.06);
  box-shadow: 0 0 0 3px rgba(45,224,200,0.07), 0 8px 32px rgba(0,0,0,0.4);
}

#msg {
  flex: 1;
  background: transparent;
  border: none;
  outline: none;
  font-family: var(--sans);
  font-size: 14px;
  color: var(--text);
  line-height: 1.55;
  resize: none;
  min-height: 22px;
  max-height: 130px;
  overflow-y: auto;
}
#msg::placeholder { color: var(--text-faint); }
#msg::-webkit-scrollbar { width: 3px; }
#msg::-webkit-scrollbar-thumb { background: rgba(255,255,255,0.1); border-radius: 2px; }

.cmd-suggest {
  position: absolute;
  left: 12px;
  right: 12px;
  bottom: calc(100% + 8px);
  background: rgba(8, 16, 28, 0.98);
  border: 1px solid var(--border-strong);
  border-radius: 14px;
  box-shadow: 0 18px 48px rgba(0,0,0,0.5);
  backdrop-filter: blur(16px);
  -webkit-backdrop-filter: blur(16px);
  max-height: 220px;
  overflow-y: auto;
  z-index: 50;
}
.cmd-suggest.hidden { display: none; }
.cmd-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
  cursor: pointer;
  border-bottom: 1px solid rgba(255,255,255,0.05);
}
.cmd-item:last-child { border-bottom: none; }
.cmd-item:hover,
.cmd-item.active { background: rgba(45,224,200,0.14); }
.cmd-main {
  font-family: var(--mono);
  font-size: 12px;
  color: #d8fff9;
}
.cmd-desc {
  font-size: 11px;
  color: var(--text-faint);
  text-align: right;
}

.send {
  width: 44px; height: 44px;
  border-radius: var(--radius-sm);
  border: none;
  background: linear-gradient(145deg, #2de0c8, #1ab5a0);
  color: #032822;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  transition: all 0.18s var(--ease-smooth);
  box-shadow: 0 4px 18px var(--accent-glow);
}
.send:hover {
  transform: scale(1.07) translateY(-1px);
  box-shadow: 0 8px 28px rgba(45,224,200,0.4);
}
.send:active { transform: scale(0.95); }
.send svg { width: 17px; height: 17px; }

.composer-hint {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--text-faint);
  text-align: center;
  opacity: 0.55;
  letter-spacing: 0.3px;
}

/* ── Divider with accent gradient ────────────────────────────── */
.glow-sep {
  height: 1px;
  background: linear-gradient(90deg, transparent 0%, rgba(45,224,200,0.25) 40%, rgba(45,224,200,0.25) 60%, transparent 100%);
  flex-shrink: 0;
}
</style>
</head>
<body>

<div class="bg">
  <div class="bg-mid"></div>
  <div class="bg-noise"></div>
</div>

<div class="app">

  <!-- ── Sidebar ─────────────────────────────────────────── -->
  <aside class="sidebar glass">
    <div class="sidebar-head">
      <div class="sidebar-eyebrow">PIORUN AI</div>
      <div class="sidebar-title">Sesje</div>
    </div>

    <div class="sessions-scroll" id="sessions-list">
      <div class="session-empty">Ładowanie…</div>
    </div>

    <div class="sidebar-actions">
      <button class="btn btn-accent" onclick="newSession()">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round">
          <line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/>
        </svg>
        Nowa sesja
      </button>
      <button class="btn" onclick="refreshSessions()">
        <svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
          <polyline points="23 4 23 10 17 10"/><polyline points="1 20 1 14 7 14"/>
          <path d="M3.51 9a9 9 0 0114.85-3.36L23 10M1 14l4.64 4.36A9 9 0 0020.49 15"/>
        </svg>
        Odśwież
      </button>
    </div>
  </aside>

  <!-- ── Chat panel ──────────────────────────────────────── -->
  <main class="chat-panel glass">

    <!-- Topbar -->
    <div class="topbar">
      <div class="topbar-logo">PIORUN</div>
      <div class="topbar-sep"></div>
      <div class="topbar-topic" id="topic-label">Nowa konwersacja</div>
      <div class="status-pill" id="status-pill">
        <div class="status-dot"></div>
        <span id="status-text">Gotowy</span>
      </div>
    </div>
    <div class="glow-sep"></div>

    <!-- Message feed -->
    <div class="feed" id="feed">
      <div class="welcome" id="welcome">
        <div class="welcome-glyph">P I O R U N</div>
        <div class="welcome-sub">Twój asystent AI gotowy do działania</div>
        <div class="welcome-hint">// napisz wiadomość, aby zacząć</div>
      </div>
      <!-- Typing indicator always last before content -->
      <div class="typing" id="typing">
        <div class="dot"></div><div class="dot"></div><div class="dot"></div>
      </div>
    </div>

    <!-- Composer -->
    <div class="composer-wrap">
      <div class="composer">
        <div class="input-shell">
          <textarea id="msg" rows="1" placeholder="Napisz wiadomość…" maxlength="12000"></textarea>
          <div id="cmd-suggest" class="cmd-suggest hidden"></div>
        </div>
        <button class="send" onclick="sendMessage()" title="Wyślij (Enter)">
          <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5" stroke-linecap="round" stroke-linejoin="round">
            <line x1="22" y1="2" x2="11" y2="13"/>
            <polygon points="22 2 15 22 11 13 2 9 22 2"/>
          </svg>
        </button>
      </div>
      <div class="composer-hint">Enter: wyślij &nbsp;·&nbsp; Shift+Enter: nowa linia &nbsp;·&nbsp; /new &nbsp;·&nbsp; /clear &nbsp;·&nbsp; /help</div>
    </div>

  </main>
</div>

<script>
'use strict';

// ── DOM refs ─────────────────────────────────────────────────────────────────
const feed        = document.getElementById('feed');
const msgInput    = document.getElementById('msg');
const cmdSuggest  = document.getElementById('cmd-suggest');
const typing      = document.getElementById('typing');
const welcome     = document.getElementById('welcome');
const statusPill  = document.getElementById('status-pill');
const statusText  = document.getElementById('status-text');
const topicLabel  = document.getElementById('topic-label');
const sessionList = document.getElementById('sessions-list');

let sessions       = [];
let activeSessionId = null;
let cmdItems        = [];
let cmdFiltered     = [];
let cmdSelected     = -1;
let switchingSession = false;
let bulkRestoringSession = false;

const SLASH_COMMANDS = [
  { cmd: '/new', desc: 'Nowa sesja' },
  { cmd: '/clear', desc: 'Czysci okno czatu' },
  { cmd: '/help', desc: 'Pokazuje komendy' },
  { cmd: '/restart', desc: 'Alias dla /new' },
];

// ── Python → JS event bus ────────────────────────────────────────────────────
window.__piorun_event = function(jsonStr) {
  const ev = JSON.parse(jsonStr);
  switch (ev.type) {
    case 'assistant_msg':
      hideTyping();
      addBubble('assistant', ev.data);
      break;
    case 'status_msg':
      statusText.textContent = ev.data;
      addBubble('status', ev.data);
      break;
    case 'error_msg':
      hideTyping();
      addBubble('status', '⚠ ' + ev.data);
      setIdle();
      break;
    case 'done':
      hideTyping();
      if (ev.data?.topic) topicLabel.textContent = ev.data.topic;
      refreshSessions();
      break;
    case 'idle':
      setIdle();
      break;
  }
};

// ── Status helpers ────────────────────────────────────────────────────────────
function setThinking() {
  statusPill.classList.add('thinking');
  statusText.textContent = 'myśli…';
  showTyping();
}
function setIdle() {
  statusPill.classList.remove('thinking');
  statusText.textContent = 'Gotowy';
  hideTyping();
}
function showTyping() {
  feed.insertBefore(typing, null);   // move to very end
  typing.classList.add('show');
  scrollBottom();
}
function hideTyping() {
  typing.classList.remove('show');
}

// ── Feed helpers ──────────────────────────────────────────────────────────────
function ts() {
  return new Date().toLocaleTimeString('pl-PL', {hour:'2-digit', minute:'2-digit', second:'2-digit'});
}

function addBubble(source, text, options = {}) {
  if (!text?.trim()) return;
  if (welcome) welcome.style.display = 'none';

  const row = document.createElement('div');
  row.className = 'row ' + source;

  if (source === 'status') {
    const b = document.createElement('div');
    b.className = 'bubble status';
    b.textContent = ts() + '  ' + text;
    row.appendChild(b);
  } else {
    const meta = document.createElement('div');
    meta.className = 'bubble-meta';
    meta.textContent = source === 'user' ? `ty  ·  ${ts()}` : `piorun  ·  ${ts()}`;
    const b = document.createElement('div');
    b.className = 'bubble ' + source;
    b.textContent = text;
    row.appendChild(meta);
    row.appendChild(b);
  }

  feed.insertBefore(row, typing);
  if (!options.skipScroll) {
    scrollBottom(options.behavior || 'smooth');
  }
}

function clearFeed() {
  Array.from(feed.children).forEach(c => {
    if (c !== typing && c !== welcome) c.remove();
  });
  if (welcome) { welcome.style.display = ''; welcome.style.animation = 'none'; }
  scrollBottom('auto');
}

function scrollBottom(behavior = 'smooth') {
  requestAnimationFrame(() => feed.scrollTo({ top: feed.scrollHeight, behavior: behavior }));
}

// ── Slash command suggestions ──────────────────────────────────────────────────
function getSlashPrefix() {
  const text = msgInput.value || '';
  const compact = text.replace(/^\s+/, '').split('\n')[0];
  if (!compact.startsWith('/')) return '';
  return compact.split(/\s+/)[0];
}

function hideCommandSuggestions() {
  cmdSelected = -1;
  cmdItems = [];
  cmdFiltered = [];
  cmdSuggest.innerHTML = '';
  cmdSuggest.classList.add('hidden');
}

function renderCommandSuggestions() {
  cmdSuggest.innerHTML = '';
  cmdItems = [];
  cmdFiltered.forEach((item, idx) => {
    const row = document.createElement('div');
    row.className = 'cmd-item' + (idx === cmdSelected ? ' active' : '');
    row.dataset.index = String(idx);
    row.innerHTML = `<div class="cmd-main">${item.cmd}</div><div class="cmd-desc">${item.desc}</div>`;
    cmdSuggest.appendChild(row);
    cmdItems.push(row);
  });
  cmdSuggest.classList.remove('hidden');
}

function updateCommandSuggestions() {
  const prefix = getSlashPrefix().toLowerCase();
  if (!prefix) {
    hideCommandSuggestions();
    return;
  }
  cmdFiltered = SLASH_COMMANDS.filter(item => item.cmd.startsWith(prefix));
  if (!cmdFiltered.length) {
    hideCommandSuggestions();
    return;
  }
  if (cmdSelected < 0 || cmdSelected >= cmdFiltered.length) cmdSelected = 0;
  renderCommandSuggestions();
}

function applySelectedCommand(index = cmdSelected) {
  if (index < 0 || index >= cmdFiltered.length) return false;
  const selected = cmdFiltered[index].cmd;
  const leadingWhitespace = (msgInput.value.match(/^\s*/) || [''])[0];
  msgInput.value = `${leadingWhitespace}${selected} `;
  msgInput.focus();
  msgInput.dispatchEvent(new Event('input'));
  hideCommandSuggestions();
  return true;
}

// ── Textarea auto-resize ──────────────────────────────────────────────────────
msgInput.addEventListener('input', () => {
  msgInput.style.height = 'auto';
  msgInput.style.height = Math.min(msgInput.scrollHeight, 130) + 'px';
  updateCommandSuggestions();
});
msgInput.addEventListener('keydown', e => {
  const suggestionsVisible = !cmdSuggest.classList.contains('hidden');
  if (suggestionsVisible && e.key === 'ArrowDown') {
    e.preventDefault();
    cmdSelected = (cmdSelected + 1) % cmdFiltered.length;
    renderCommandSuggestions();
    return;
  }
  if (suggestionsVisible && e.key === 'ArrowUp') {
    e.preventDefault();
    cmdSelected = (cmdSelected - 1 + cmdFiltered.length) % cmdFiltered.length;
    renderCommandSuggestions();
    return;
  }
  if (suggestionsVisible && (e.key === 'Tab' || (e.key === 'Enter' && !e.shiftKey))) {
    e.preventDefault();
    applySelectedCommand();
    return;
  }
  if (suggestionsVisible && e.key === 'Escape') {
    e.preventDefault();
    hideCommandSuggestions();
    return;
  }
  if (e.key === 'Enter' && !e.shiftKey) { e.preventDefault(); sendMessage(); }
});
msgInput.addEventListener('blur', () => setTimeout(hideCommandSuggestions, 120));
msgInput.addEventListener('focus', updateCommandSuggestions);
cmdSuggest.addEventListener('mousedown', e => e.preventDefault());
cmdSuggest.addEventListener('click', e => {
  const row = e.target.closest('.cmd-item');
  if (!row) return;
  const idx = Number(row.dataset.index || '-1');
  applySelectedCommand(idx);
});

// ── Actions ───────────────────────────────────────────────────────────────────
async function sendMessage() {
  const text = msgInput.value.trim();
  if (!text) return;
  hideCommandSuggestions();

  if (text === '/clear') {
    msgInput.value = ''; msgInput.style.height = 'auto';
    clearFeed(); return;
  }
  if (text === '/help') {
    msgInput.value = ''; msgInput.style.height = 'auto';
    addBubble('status', 'Komendy: /new, /clear, /help, /restart');
    return;
  }
  if (text === '/new') {
    msgInput.value = ''; msgInput.style.height = 'auto';
    newSession(); return;
  }
  if (text === '/restart') {
    msgInput.value = ''; msgInput.style.height = 'auto';
    newSession(); return;
  }

  msgInput.value = ''; msgInput.style.height = 'auto';
  addBubble('user', text);
  setThinking();

  const result = await window.pywebview.api.send_message(text);
  if (result?.error === 'db_locked') {
    addBubble('status', '⚠ Baza historii jest chwilowo zablokowana.'); setIdle();
  } else if (result === false) {
    setIdle();
  }
}

async function newSession() {
  const ok = await window.pywebview.api.new_session();
  if (ok) {
    clearFeed();
    topicLabel.textContent = 'Nowa konwersacja';
    addBubble('status', 'Utworzono nową sesję.');
    activeSessionId = null;
    await refreshSessions();
  }
}

async function refreshSessions() {
  sessions = await window.pywebview.api.get_sessions();
  renderSessions();
}

function updateActiveSessionHighlight() {
  const sessionNodes = sessionList.querySelectorAll('.session-item');
  sessionNodes.forEach(node => {
    node.classList.toggle('active', node.dataset.sid === activeSessionId);
  });
}

async function resumeSession(sid, topic) {
  if (!sid || switchingSession) return;
  if (sid === activeSessionId) return;
  switchingSession = true;
  bulkRestoringSession = true;
  try {
    const result = await window.pywebview.api.resume_session(sid, topic);
    if (!result) return;
    activeSessionId = sid;
    updateActiveSessionHighlight();
    topicLabel.textContent = result.topic;
    clearFeed();
    addBubble('status', 'Wznowiono: ' + result.topic, { behavior: 'auto' });
    (result.messages || []).forEach(m => {
      if (m.role === 'user')      addBubble('user',      m.content, { skipScroll: true });
      else if (m.role === 'assistant') addBubble('assistant', m.content, { skipScroll: true });
    });
    scrollBottom('auto');
  } finally {
    bulkRestoringSession = false;
    switchingSession = false;
  }
}

// ── Render session list ───────────────────────────────────────────────────────
function renderSessions() {
  if (!sessions?.length) {
    sessionList.innerHTML = '<div class="session-empty">Brak sesji</div>';
    return;
  }
  sessionList.innerHTML = '';
  sessions.forEach(s => {
    const el   = document.createElement('div');
    el.dataset.sid = s.session_id;
    el.className = 'session-item' + (s.session_id === activeSessionId ? ' active' : '');

    const topicEl = document.createElement('div');
    topicEl.className = 'session-topic';
    topicEl.textContent = s.topic;

    const metaEl = document.createElement('div');
    metaEl.className = 'session-meta';
    metaEl.textContent = (s.timestamp.substring(0, 16) || '?') + '  ·  ' + s.count + ' wiad.';

    el.appendChild(topicEl);
    el.appendChild(metaEl);

    el.addEventListener('click', async () => {
      await resumeSession(s.session_id, s.topic);
    });

    sessionList.appendChild(el);
  });
}

// ── Init ──────────────────────────────────────────────────────────────────────
window.addEventListener('pywebviewready', async () => {
  await refreshSessions();
});
</script>
</body>
</html>
"""


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    api = PiorunAPI()

    w = webview.create_window(
        title="PIORUN",
        html=HTML,
        js_api=api,
        width=1380,
        height=880,
        min_size=(920, 620),
        background_color="#05080f",
        text_select=True,
    )
    api.set_window(w)
    # Wymuszamy backend Qt, zeby ominac pythonnet/winforms (problem na Python 3.14).
    webview.start(gui="qt", debug=False)


if __name__ == "__main__":
    main()

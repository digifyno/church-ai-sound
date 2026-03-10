"""
Church Sound Technician — Web Dashboard

  python3 app.py        → http://localhost:5050
"""

from dotenv import load_dotenv
load_dotenv()

import logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

from flask import Flask, render_template, jsonify, redirect
from flask_socketio import SocketIO
import threading
import time
import signal
import sys

from config import (WEB_PORT, CYCLE_SEC)
from x18 import X18Client
from mixer_engine import MixerEngine
from automix import auto_mix_step, save_backup, restore_backup

app = Flask(__name__)
import os, secrets as _secrets
_secret = os.environ.get("FLASK_SECRET_KEY", "")
if not _secret:
    _secret = _secrets.token_hex(32)
    log.warning("FLASK_SECRET_KEY not set — using a random key (sessions won't persist across restarts)")
app.config["SECRET_KEY"] = _secret
socketio = SocketIO(app, cors_allowed_origins="*", async_mode="threading")


@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self'; "
        "style-src 'self' 'unsafe-inline'; "
        "connect-src 'self' ws: wss:"
    )
    return response


_shutdown = threading.Event()

x18    = X18Client()
engine = MixerEngine(x18)


@app.route("/")
def index():
    return render_template("index.html")


@app.route("/favicon.ico")
def favicon():
    return redirect("/static/favicon.svg", code=301)


# ── Live mode state ──
_live_mode = False
_live_lock = threading.Lock()
_live_backup = None
_consecutive_raises: dict[int, int] = {}
_input_history: dict[int, list] = {}


def _automix_loop():
    """Background loop that applies fader changes when live mode is on."""
    global _live_mode
    while not _shutdown.is_set():
        if _live_mode and x18.connected:
            try:
                auto_mix_step(x18, _consecutive_raises, _input_history)
            except Exception:
                log.exception("automix_loop error")
        if _shutdown.wait(CYCLE_SEC):
            break


@app.route("/api/mode", methods=["GET"])
def get_mode():
    return jsonify({"live": _live_mode})


@app.route("/api/mode", methods=["POST"])
def toggle_mode():
    global _live_mode, _live_backup
    from flask import request
    data = request.get_json(silent=True) or {}
    want_live = data.get("live", not _live_mode)

    with _live_lock:
        if want_live and not _live_mode:
            if x18.connected:
                _live_backup = save_backup(x18)
                _consecutive_raises.clear()
                _input_history.clear()
                log.info("LIVE MODE ON — backup saved")
            else:
                return jsonify({"error": "Mixer not connected"}), 400
            _live_mode = True
        elif not want_live and _live_mode:
            _live_mode = False
            if _live_backup and x18.connected:
                restore_backup(x18)
                log.info("LIVE MODE OFF — backup restored")
            _live_backup = None

    return jsonify({"live": _live_mode})


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "mixer_connected": x18.connected,
    })


_slow_cache = {}

def _slow_loop():
    """Update slow-changing data (sim) every 500ms."""
    global _slow_cache
    while not _shutdown.is_set():
        try:
            _slow_cache = {
                "sim": engine.get_state(),
            }
        except Exception:
            log.exception("slow_loop error")
        if _shutdown.wait(0.5):
            break

def push_loop():
    """Broadcast meter state to all connected clients at ~20Hz."""
    while not _shutdown.is_set():
        try:
            payload = {
                "channels":   x18.get_snapshot(),
                "connected":  x18.connected,
                "live":       _live_mode,
                "time":       time.strftime("%H:%M:%S"),
            }
            payload.update(_slow_cache)
            socketio.emit("state", payload)
        except Exception:
            log.exception("push_loop error")
        if _shutdown.wait(0.05):
            break


def shutdown(*_):
    _shutdown.set()
    x18.stop()
    engine.stop()
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("Church Sound Technician")
    print(f"  Mixer   → {'ready' if x18.connected else 'connecting'}")
    print(f"  Web UI  → http://localhost:{WEB_PORT}")
    print()

    x18.start()
    engine.start()

    threading.Thread(target=_slow_loop, daemon=True).start()
    threading.Thread(target=push_loop, daemon=True).start()
    threading.Thread(target=_automix_loop, daemon=True).start()

    socketio.run(
        app,
        host="0.0.0.0",
        port=WEB_PORT,
        debug=False,
        allow_unsafe_werkzeug=True,
    )

"""
Church AI Sound Technician — Web Dashboard

  python3 app.py        → http://localhost:5050
  SIMULATION MODE       → proposes changes, never writes to the mixer.
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

from config import (WEB_PORT, SOCKETIO_CORS_ORIGINS, CHANNEL_ROLES, ROLE_TARGETS,
                    SILENCE_DB, MAX_STEP_DB, CYCLE_SEC, HOLD_ZONE, FADER_CEIL_DB,
                    MAX_CONSECUTIVE_RAISES, STALE_INPUT_WINDOW, STALE_INPUT_BAND_DB)

# Derive WebSocket origins from CORS origins for CSP connect-src
_WS_ORIGINS = " ".join(
    ("ws://" + o[7:]) if o.startswith("http://") else ("wss://" + o[8:])
    for o in SOCKETIO_CORS_ORIGINS
    if o.startswith(("http://", "https://"))
)
from x18 import X18Client
from room_mic import RoomMic
from mixer_engine import MixerEngine
from ai_engine import AIEngine
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
mic    = RoomMic()
engine = MixerEngine(x18)
ai     = AIEngine(
    get_channels=x18.get_snapshot,
    get_room=mic.get,
    get_sim=engine.get_state,
)


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
            # Entering live mode — save backup
            if x18.connected:
                _live_backup = save_backup(x18)
                _consecutive_raises.clear()
                _input_history.clear()
                log.info("LIVE MODE ON — backup saved")
            else:
                return jsonify({"error": "Mixer not connected"}), 400
            _live_mode = True
        elif not want_live and _live_mode:
            # Exiting live mode — restore backup
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
        "ai_active": ai.running,
    })


_slow_cache = {}

def _slow_loop():
    """Update slow-changing data (AI, sim, room) every 500ms."""
    global _slow_cache
    while not _shutdown.is_set():
        try:
            _slow_cache = {
                "room":       mic.get(),
                "suggestion": ai.get_suggestion(),
                "sim":        engine.get_state(),
                "ai_stats":   ai.get_stats(),
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
    mic.stop()
    engine.stop()
    ai.stop()
    sys.exit(0)


if __name__ == "__main__":
    signal.signal(signal.SIGINT, shutdown)
    signal.signal(signal.SIGTERM, shutdown)

    print("Church AI Sound Technician")
    print(f"  Mixer   → {'ready' if x18.connected else 'connecting'}")
    print(f"  Web UI  → http://localhost:{WEB_PORT}")
    print(f"  Mode    → SIMULATION (read only)")
    print()

    x18.start()
    mic.start()
    engine.start()
    ai.start()

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

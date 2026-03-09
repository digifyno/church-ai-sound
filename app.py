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

from config import WEB_PORT, SOCKETIO_CORS_ORIGINS
from x18 import X18Client
from room_mic import RoomMic
from mixer_engine import MixerEngine
from ai_engine import AIEngine

app = Flask(__name__)
import os, secrets as _secrets
_secret = os.environ.get("FLASK_SECRET_KEY", "")
if not _secret:
    _secret = _secrets.token_hex(32)
    log.warning("FLASK_SECRET_KEY not set — using a random key (sessions won't persist across restarts)")
app.config["SECRET_KEY"] = _secret
socketio = SocketIO(app, cors_allowed_origins=SOCKETIO_CORS_ORIGINS, async_mode="eventlet")


@app.after_request
def set_security_headers(response):
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; "
        "script-src 'self' 'unsafe-inline'; "
        "style-src 'self' 'unsafe-inline'; "
        "connect-src 'self' ws: wss:"
    )
    return response


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


@app.route("/health")
def health():
    return jsonify({
        "status": "ok",
        "mixer_connected": x18.connected,
        "ai_active": ai.running,
    })


def push_loop():
    """Broadcast state to all connected clients ~7 times/sec."""
    while True:
        try:
            channels   = x18.get_snapshot()
            room       = mic.get()
            suggestion = ai.get_suggestion()
            sim        = engine.get_state()

            socketio.emit("state", {
                "channels":   channels,
                "room":       room,
                "suggestion": suggestion,
                "sim":        sim,
                "ai_stats":   ai.get_stats(),
                "connected":  x18.connected,
                "time":       time.strftime("%H:%M:%S"),
            })
        except Exception:
            log.exception("push_loop error")
        time.sleep(0.15)


def shutdown(*_):
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

    threading.Thread(target=push_loop, daemon=True).start()

    socketio.run(
        app,
        host="0.0.0.0",
        port=WEB_PORT,
        debug=False,
    )

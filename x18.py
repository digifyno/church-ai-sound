"""
X-AIR X18 OSC client.

Provides:
 - Real-time meter subscription (/meters/0, /meters/1)
 - On-demand fader/name/mute reads
 - Connection-status tracking
 - Thread-safe snapshots for the rest of the app

Read-only by default.  Nothing is sent unless the caller explicitly
calls send().
"""

import logging
import socket
import threading
import time

log = logging.getLogger(__name__)

from config import MIXER_IP, MIXER_PORT
from osc import build_message, parse_message, parse_meter_blob, fader_to_db


class X18Client:
    def __init__(self):
        self._sock = None
        self._running = False
        self._thread = None
        self._lock = threading.Lock()

        # Meter data (dB, pre-fader)
        self._meters_0 = {}          # ch1-8  from /meters/0
        self._meters_1 = {}          # ch1-18 from /meters/1

        # Channel metadata (read once on connect, refreshed periodically)
        self._names  = {}            # ch -> str
        self._faders = {}            # ch -> float (0.0–1.0)
        self._mutes  = {}            # ch -> bool (True = signal flowing)

        self._connected = False
        self._last_rx   = 0.0        # last time we received anything

        self._meta_thread = None

    # ── lifecycle ──────────────────────────────────────────────────────

    def start(self):
        self._sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self._sock.bind(("", 0))     # OS picks a free port
        self._sock.settimeout(0.5)
        self._running = True
        self._thread = threading.Thread(target=self._run, daemon=True)
        self._thread.start()
        self._meta_thread = threading.Thread(target=self._meta_loop, daemon=True)
        self._meta_thread.start()

    def stop(self):
        self._running = False
        if self._sock:
            self._sock.close()

    # ── public queries ─────────────────────────────────────────────────

    @property
    def connected(self) -> bool:
        with self._lock:
            return self._connected

    # ── write commands ─────────────────────────────────────────────────

    def set_fader(self, ch: int, value: float):
        """Set fader position (0.0–1.0) for channel 1–16."""
        if not (1 <= ch <= 16):
            raise ValueError(f"Channel {ch} out of range 1-16")
        value = max(0.0, min(1.0, value))
        self._send(build_message(f"/ch/{ch:02d}/mix/fader", ("f", value)))
        with self._lock:
            self._faders[ch] = value

    def set_fader_db(self, ch: int, db: float):
        """Set fader by dB value (-90 to +10)."""
        if not (1 <= ch <= 16):
            raise ValueError(f"Channel {ch} out of range 1-16")
        from osc import db_to_fader
        self.set_fader(ch, db_to_fader(db))

    def set_mute(self, ch: int, on: bool):
        """Set channel on/off (True = signal flows, False = muted)."""
        if not (1 <= ch <= 16):
            raise ValueError(f"Channel {ch} out of range 1-16")
        self._send(build_message(f"/ch/{ch:02d}/mix/on", ("i", 1 if on else 0)))
        with self._lock:
            self._mutes[ch] = on

    def get_snapshot(self) -> dict:
        """Return {ch_number: {name, db, fader, fader_db, on, active}}."""
        with self._lock:
            channels = {}
            for ch in range(1, 19):
                # Best meter source: /meters/0 for 1-8, /meters/1 for 9-18
                if ch <= 8 and ch in self._meters_0:
                    db = self._meters_0[ch]
                elif ch in self._meters_1:
                    db = self._meters_1[ch]
                else:
                    db = -90.0

                fader_val = self._faders.get(ch, 0.0)
                channels[ch] = {
                    "name":     self._names.get(ch, f"CH{ch:02d}"),
                    "db":       round(db, 1),
                    "fader":    round(fader_val, 3),
                    "fader_db": round(fader_to_db(fader_val), 1),
                    "on":       self._mutes.get(ch, True),
                    "active":   db > -55,
                }
            return channels

    # ── internal ───────────────────────────────────────────────────────

    def _send(self, msg: bytes):
        self._sock.sendto(msg, (MIXER_IP, MIXER_PORT))

    def _query(self, sock: socket.socket, address: str, expected_type: str):
        """Send a query on *sock* and return the first value matching expected_type."""
        sock.sendto(build_message(address), (MIXER_IP, MIXER_PORT))
        try:
            data, _ = sock.recvfrom(1024)
            _, vals = parse_message(data)
            for t, v in vals:
                if t == expected_type:
                    return v
        except socket.timeout:
            pass
        return None

    def _read_channel_meta(self):
        """Read names, faders, and mutes for all 16 channels.

        Uses a dedicated ephemeral socket so that _run's recvfrom on
        self._sock is the sole consumer of meter blobs — no packet stealing.
        """
        q_sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        q_sock.bind(("", 0))
        q_sock.settimeout(0.5)
        try:
            names  = {}
            faders = {}
            mutes  = {}
            for ch in range(1, 17):
                prefix = f"/ch/{ch:02d}"
                n = self._query(q_sock, f"{prefix}/config/name", "s")
                if n is not None:
                    names[ch] = n
                f = self._query(q_sock, f"{prefix}/mix/fader", "f")
                if f is not None:
                    faders[ch] = f
                m = self._query(q_sock, f"{prefix}/mix/on", "i")
                if m is not None:
                    mutes[ch] = (m == 1)
                time.sleep(0.015)   # ~240ms total, gentle on the mixer
        finally:
            q_sock.close()
        with self._lock:
            self._names.update(names)
            self._faders.update(faders)
            self._mutes.update(mutes)

    def _subscribe_meters(self):
        for endpoint in ["/meters/0", "/meters/1"]:
            self._send(build_message(endpoint, ("s", endpoint)))

    def _meta_loop(self):
        """Refresh names/faders/mutes every 30s, independent of receive loop."""
        time.sleep(1)  # let socket settle
        while self._running:
            self._read_channel_meta()
            time.sleep(30)

    def _run(self):
        last_sub = 0.0

        while self._running:
            now = time.time()

            # Re-subscribe to meters every 5s (X-AIR requirement)
            if now - last_sub > 5:
                self._subscribe_meters()
                last_sub = now

            # Receive
            try:
                data, _ = self._sock.recvfrom(8192)
                self._last_rx = now
                addr, vals = parse_message(data)
                if not addr or not vals:
                    continue

                if vals[0][0] == "b":
                    blob   = vals[0][1]
                    levels = parse_meter_blob(blob)
                    with self._lock:
                        self._connected = True
                        if addr == "/meters/0":
                            for i, db in enumerate(levels[:8]):
                                self._meters_0[i+1] = db
                        elif addr == "/meters/1":
                            for i, db in enumerate(levels[:min(18, len(levels))]):
                                self._meters_1[i+1] = db
            except socket.timeout:
                with self._lock:
                    if now - self._last_rx > 8:
                        self._connected = False
            except Exception:
                log.exception("_run receive error")

"""
Auto-mix simulation engine — READ ONLY.

Reads the current mixer state from X18Client (meters + faders) and
calculates what an ideal mix would look like.  Nothing is sent.

The core logic:
  output_level = input_meter_db + fader_db
  error        = target_db - output_level
  proposed     = fader_db + clamp(error, ±MAX_STEP_DB)
"""

import logging
import threading
import time

log = logging.getLogger(__name__)

from config import CHANNEL_ROLES, ROLE_TARGETS, SILENCE_DB, MAX_STEP_DB, FADER_CEIL_DB, HOLD_ZONE
from osc import fader_to_db, db_to_fader, compute_adjustment


class MixerEngine:
    def __init__(self, x18_client):
        self._x18 = x18_client
        self._lock = threading.Lock()
        self._running = False
        self._thread = None

        self._proposals  = {}
        self._scene      = "Standby"
        self._mix_health = 100

    def start(self):
        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    def get_state(self) -> dict:
        with self._lock:
            return {
                "proposals":  dict(self._proposals),
                "scene":      self._scene,
                "mix_health": self._mix_health,
            }

    # ── scene detection ───────────────────────────────────────────────

    @staticmethod
    def _detect_scene(snapshot: dict) -> str:
        def role_active(role):
            return any(
                snapshot.get(ch, {}).get("active", False)
                for ch, r in CHANNEL_ROLES.items() if r == role
            )

        vocals      = role_active("vocal") or role_active("backup")
        guitars     = role_active("guitar")
        keys        = role_active("keys")
        playback    = role_active("playback")
        instruments = sum([guitars, keys, playback])

        if vocals and instruments >= 2:
            return "Worship"
        if vocals and instruments <= 1:
            return "Sermon / Talk"
        if playback and not vocals:
            return "Intro / Music Only"
        return "Standby"

    # ── simulation ────────────────────────────────────────────────────

    @staticmethod
    def _simulate(snapshot: dict) -> dict:
        proposals = {}

        for ch, info in snapshot.items():
            if not info["active"] or not info["on"]:
                continue

            role       = CHANNEL_ROLES.get(ch, "unknown")
            target_db  = ROLE_TARGETS[role]
            input_db   = info["db"]
            fader_db   = info["fader_db"]

            output_db, capped, action = compute_adjustment(
                input_db, fader_db, target_db, hold_zone=HOLD_ZONE
            )

            proposed_fader_db = max(-90.0, min(FADER_CEIL_DB, fader_db + capped))

            proposals[ch] = {
                "name":              info["name"],
                "role":              role,
                "input_db":          round(input_db, 1),
                "output_db":         round(output_db, 1),
                "target_db":         target_db,
                "current_fader_db":  round(fader_db, 1),
                "proposed_fader_db": round(proposed_fader_db, 1),
                "delta_db":          round(capped, 1),
                "action":            action,
            }

        return proposals

    # ── health score ──────────────────────────────────────────────────

    @staticmethod
    def _calc_health(proposals: dict) -> int:
        if not proposals:
            return 100
        errors = [abs(p["output_db"] - p["target_db"]) for p in proposals.values()]
        avg_error = sum(errors) / len(errors)
        # 0 dB error = 100%, 10+ dB error = 0%
        return max(0, min(100, int(100 - avg_error * 10)))

    # ── main loop ─────────────────────────────────────────────────────

    def _loop(self):
        while self._running:
            try:
                snapshot  = self._x18.get_snapshot()
                proposals = self._simulate(snapshot)
                scene     = self._detect_scene(snapshot)
                health    = self._calc_health(proposals)

                with self._lock:
                    self._proposals  = proposals
                    self._scene      = scene
                    self._mix_health = health
            except Exception:
                log.exception("simulation loop error")

            time.sleep(2.0)

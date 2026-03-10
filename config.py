"""
Central configuration for Church Sound.
"""

import os as _os
import urllib.parse as _urlparse

MIXER_IP   = _os.environ.get("MIXER_IP",   "192.168.8.18")
MIXER_PORT = int(_os.environ.get("MIXER_PORT", "10024"))
WEB_PORT   = 5050

# Channel roles — determines target levels and scene detection.
# "vocal"    = lead vocals, wireless mics (target -18 dBFS post-fader)
# "backup"   = secondary vocal mics       (target -24 dBFS)
# "guitar"   = acoustic/electric guitars   (target -22 dBFS)
# "keys"     = piano, keyboards            (target -22 dBFS)
# "playback" = PC return, backing tracks   (target -26 dBFS)
CHANNEL_ROLES = {
    1:  "vocal",      # 58A
    2:  "backup",     # SM58
    3:  "vocal",      # WL2 (wireless)
    4:  "vocal",      # WL1 (wireless)
    5:  "guitar",     # Guitar1
    6:  "guitar",     # Guitar2
    7:  "keys",       # Piano L
    8:  "keys",       # Piano R
    15: "playback",   # PC Return L
    16: "playback",   # PC Return R
}

ROLE_TARGETS = {
    "vocal":    -18.0,
    "backup":   -24.0,
    "keys":     -22.0,
    "guitar":   -22.0,
    "playback": -26.0,
    "unknown":  -20.0,
}

SILENCE_DB   = -55.0   # below this = effectively silent
MAX_STEP_DB  = 2.0     # max fader adjustment per simulation cycle

MAX_CONSECUTIVE_RAISES = 5    # halt raises after this many cycles without input improvement
STALE_INPUT_WINDOW     = 5    # cycles to look back for stale-input detection
STALE_INPUT_BAND_DB    = 1.0  # input must vary more than this (dB) to not be considered stale

# Auto-mix
CYCLE_SEC  = 2.0   # seconds per auto-mix cycle
HOLD_ZONE  = 1.0   # ±dB: close enough, don't adjust

# WebSocket CORS — defaults to localhost only; set CORS_ORIGINS env var for LAN access
# e.g. CORS_ORIGINS=http://192.168.8.100:5050
def _valid_origin(o: str) -> bool:
    try:
        p = _urlparse.urlparse(o)
        return p.scheme in ('http', 'https') and bool(p.netloc)
    except Exception:
        return False

_cors_raw = _os.environ.get("CORS_ORIGINS", "http://localhost:5050,http://127.0.0.1:5050")
_cors_candidates = [o.strip() for o in _cors_raw.split(",") if o.strip()]
SOCKETIO_CORS_ORIGINS = [o for o in _cors_candidates if _valid_origin(o)]

if len(SOCKETIO_CORS_ORIGINS) != len(_cors_candidates):
    import logging as _logging
    _logging.getLogger(__name__).warning(
        "CORS_ORIGINS: %d invalid origin(s) dropped: %s",
        len(_cors_candidates) - len(SOCKETIO_CORS_ORIGINS),
        [o for o in _cors_candidates if not _valid_origin(o)],
    )

AUTOMIX_LOG_FILE    = _os.path.join(_os.path.dirname(_os.path.abspath(__file__)), "automix_log.jsonl")

# Auto-mix safety
FADER_CEIL_DB    = 0.0    # never push a fader above 0 dB

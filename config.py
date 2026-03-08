"""
Central configuration for Church AI Sound.
"""

MIXER_IP   = "192.168.8.18"
MIXER_PORT = 10024
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

MIC_DEVICE   = None     # None = system default mic
SAMPLE_RATE  = 48000

# AI analysis
ANALYSIS_INTERVAL = 15   # seconds between Claude queries

# Auto-mix
CYCLE_SEC  = 2.0   # seconds per auto-mix cycle
HOLD_ZONE  = 1.0   # ±dB: close enough, don't adjust

# Room mic
BLOCK_SIZE = 4096  # audio capture block size (~85ms at 48 kHz)

# AI cost accounting (Haiku 4.5 pricing, per million tokens)
AI_LOG_FILE      = "ai_log.jsonl"
AI_PRICE_INPUT   = 0.80   # $0.80 / 1M input tokens
AI_PRICE_OUTPUT  = 4.00   # $4.00 / 1M output tokens

# Auto-mix safety
FADER_CEIL_DB    = 0.0    # never push a fader above 0 dB

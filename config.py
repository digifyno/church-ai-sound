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

MIC_DEVICE   = None     # None = system default mic
SAMPLE_RATE  = 48000

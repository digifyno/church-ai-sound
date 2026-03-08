"""
Shared OSC encoding/decoding for X-AIR protocol.
Used by both x18.py and mixer_engine.py.
"""

import struct


def encode_str(s: str) -> bytes:
    """Encode a string with null-terminator padded to 4-byte boundary."""
    b = s.encode("utf-8") + b"\x00"
    return b + b"\x00" * ((4 - len(b) % 4) % 4)


def build_message(address: str, *args: tuple) -> bytes:
    """Build an OSC message.  args are (type_char, value) tuples."""
    msg = encode_str(address)
    if args:
        tags = "," + "".join(a[0] for a in args)
        msg += encode_str(tags)
        for t, v in args:
            if   t == "f": msg += struct.pack(">f", v)
            elif t == "i": msg += struct.pack(">i", v)
            elif t == "s": msg += encode_str(v)
    else:
        msg += encode_str(",")
    return msg


def parse_message(data: bytes):
    """Parse an OSC message.  Returns (address, [(type, value), ...])."""
    def read_str(d, o):
        end = d.index(b"\x00", o)
        s = d[o:end].decode("utf-8", errors="replace")
        padded = end + 1
        return s, padded + (4 - padded % 4) % 4

    try:
        addr, o = read_str(data, 0)
        tags, o = read_str(data, o)
        vals = []
        for t in tags.lstrip(","):
            if t == "f":
                vals.append(("f", struct.unpack(">f", data[o:o+4])[0])); o += 4
            elif t == "i":
                vals.append(("i", struct.unpack(">i", data[o:o+4])[0])); o += 4
            elif t == "s":
                v, o = read_str(data, o); vals.append(("s", v))
            elif t == "b":
                size = struct.unpack(">i", data[o:o+4])[0]; o += 4
                vals.append(("b", data[o:o+size]))
                o += size + (4 - size % 4) % 4
        return addr, vals
    except Exception:
        return None, []


def parse_meter_blob(blob: bytes) -> list[float]:
    """Parse an X-AIR meter blob into a list of dB values."""
    count = struct.unpack("<i", blob[:4])[0]
    return [struct.unpack("<h", blob[4+i*2:6+i*2])[0] / 256.0 for i in range(count)]


# ── X-AIR fader taper ────────────────────────────────────────────────
#
# The X-AIR fader float (0.0–1.0) maps to dB using a 4-segment
# piecewise linear taper.  Measured from the X32/X-AIR protocol docs:
#
#   float   dB
#   0.0    -inf  (treated as -90)
#   0.0625 -60
#   0.25   -30
#   0.50   -10
#   0.75    0
#   1.0   +10
#
_TAPER = [
    # (fader_lo, fader_hi, db_lo, db_hi)
    (0.0,    0.0625, -90.0, -60.0),
    (0.0625, 0.25,   -60.0, -30.0),
    (0.25,   0.50,   -30.0, -10.0),
    (0.50,   0.75,   -10.0,   0.0),
    (0.75,   1.0,      0.0,  10.0),
]

def fader_to_db(f: float) -> float:
    """Convert X-AIR fader float (0.0–1.0) to dB."""
    if f <= 0.0:
        return -90.0
    for flo, fhi, dlo, dhi in _TAPER:
        if f <= fhi:
            t = (f - flo) / (fhi - flo) if fhi > flo else 0.0
            return dlo + t * (dhi - dlo)
    return 10.0


def db_to_fader(db: float) -> float:
    """Convert dB to X-AIR fader float (0.0–1.0)."""
    db = max(-90.0, min(10.0, db))
    for flo, fhi, dlo, dhi in _TAPER:
        if db <= dhi:
            t = (db - dlo) / (dhi - dlo) if dhi > dlo else 0.0
            return flo + t * (fhi - flo)
    return 1.0

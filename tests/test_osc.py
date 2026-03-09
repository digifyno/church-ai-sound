import struct

import pytest
from osc import build_message, compute_adjustment, db_to_fader, fader_to_db, parse_message, parse_meter_blob


# ── fader_to_db ──

def test_fader_to_db_zero():
    assert fader_to_db(0.0) == -90.0


def test_fader_to_db_unity():  # 0.75 = 0 dB (unity gain)
    assert abs(fader_to_db(0.75) - 0.0) < 0.1


def test_fader_to_db_max():
    assert fader_to_db(1.0) == pytest.approx(10.0, abs=0.1)


def test_fader_to_db_taper_segments():
    # -30 dB at 0.25, -10 dB at 0.50 (taper breakpoints)
    assert abs(fader_to_db(0.25) - (-30.0)) < 0.5
    assert abs(fader_to_db(0.50) - (-10.0)) < 0.5


# ── db_to_fader (roundtrip) ──

@pytest.mark.parametrize("db", [-90, -60, -30, -20, -10, 0, 10])
def test_db_fader_roundtrip(db):
    assert abs(fader_to_db(db_to_fader(db)) - db) < 0.5


def test_db_to_fader_ceiling():
    # Clamps at +10 dB → 1.0
    assert db_to_fader(15.0) == pytest.approx(1.0, abs=0.01)


def test_db_to_fader_floor():
    # Clamps at -90 dB → 0.0
    assert db_to_fader(-200.0) == pytest.approx(0.0, abs=0.01)


# ── compute_adjustment ──

def test_compute_adjustment_hold_zone():
    _, delta, action = compute_adjustment(-30.0, -10.0, -40.0, hold_zone=1.0)
    # output=-40, target=-40 → hold
    assert action == "hold"
    assert delta == 0.0


def test_compute_adjustment_raise():
    _, delta, action = compute_adjustment(-30.0, -5.0, -18.0, hold_zone=1.0, max_step=2.0)
    # output=-35, target=-18, error=+17 → capped raise
    assert action == "raise"
    assert delta == pytest.approx(2.0)


def test_compute_adjustment_lower():
    _, delta, action = compute_adjustment(-10.0, 0.0, -18.0, hold_zone=1.0, max_step=2.0)
    # output=-10, target=-18, error=-8 → capped lower
    assert action == "lower"
    assert delta == pytest.approx(-2.0)


def test_compute_adjustment_max_step_capped():
    _, delta, _ = compute_adjustment(-20.0, 0.0, -40.0, hold_zone=1.0, max_step=2.0)
    assert abs(delta) <= 2.0  # never exceeds max_step


# ── build_message / parse_message ──

def test_build_and_parse_float():
    msg = build_message("/ch/01/mix/fader", ("f", 0.75))
    addr, vals = parse_message(msg)
    assert addr == "/ch/01/mix/fader"
    assert vals == [("f", pytest.approx(0.75, abs=1e-5))]


def test_build_no_args_query():
    msg = build_message("/ch/01/mix/fader")
    addr, vals = parse_message(msg)
    assert addr == "/ch/01/mix/fader"
    assert vals == []


def test_build_and_parse_int():
    msg = build_message("/some/addr", ("i", 42))
    addr, vals = parse_message(msg)
    assert addr == "/some/addr"
    assert vals == [("i", 42)]


# ── parse_meter_blob ──

def test_parse_meter_blob_length():
    blob = struct.pack("<i", 18) + b"\x00" * 36
    levels = parse_meter_blob(blob)
    assert len(levels) == 18
    assert all(isinstance(v, float) for v in levels)


def test_parse_meter_blob_values():
    # int16 value of 256 → 256 / 256.0 = 1.0 dB
    blob = struct.pack("<i", 1) + struct.pack("<h", 256)
    levels = parse_meter_blob(blob)
    assert levels == [pytest.approx(1.0)]


# ── parse_meter_blob bounds validation ──

def test_parse_meter_blob_empty_blob():
    assert parse_meter_blob(b"") == []


def test_parse_meter_blob_inflated_count():
    # count=256 but 0 bytes of meter data — must return [] not raise
    blob = struct.pack("<i", 256)
    assert parse_meter_blob(blob) == []


def test_parse_meter_blob_partial_data():
    # count=5 but only 2 channels worth of data — clamp to 2
    blob = struct.pack("<i", 5) + struct.pack("<hh", 256, 512)
    levels = parse_meter_blob(blob)
    assert len(levels) == 2
    assert levels[0] == pytest.approx(1.0)
    assert levels[1] == pytest.approx(2.0)


# ── blob size cap (security) ──

def test_parse_message_blob_oversized_returns_none():
    # Craft a message with blob size field = 10_000_000 to trigger OOM guard
    addr = b"/meters\x00"  # 8 bytes (aligned)
    tags = b",b\x00\x00"   # 4 bytes (aligned)
    blob_size = struct.pack(">i", 10_000_000)
    data = addr + tags + blob_size
    addr_out, vals = parse_message(data)
    assert addr_out is None
    assert vals == []


def test_parse_message_blob_negative_size_returns_none():
    addr = b"/meters\x00"
    tags = b",b\x00\x00"
    blob_size = struct.pack(">i", -1)
    data = addr + tags + blob_size
    addr_out, vals = parse_message(data)
    assert addr_out is None
    assert vals == []

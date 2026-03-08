import pytest
from osc import fader_to_db, db_to_fader, compute_adjustment


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

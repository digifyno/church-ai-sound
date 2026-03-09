import pytest
from mixer_engine import MixerEngine


# ── _detect_scene ──

def _snap(active_channels):
    return {ch: {"active": ch in active_channels, "on": True} for ch in range(1, 19)}


def test_detect_scene_worship():
    # vocal (ch1) + guitar (ch5) + keys (ch7) → 2 instrument groups → Worship
    assert MixerEngine._detect_scene(_snap((1, 5, 7))) == "Worship"


def test_detect_scene_sermon():
    # vocal only → 0 instrument groups → Sermon / Talk
    assert MixerEngine._detect_scene(_snap((1,))) == "Sermon / Talk"


def test_detect_scene_standby():
    # nothing active → Standby
    assert MixerEngine._detect_scene(_snap(())) == "Standby"


def test_detect_scene_music_only():
    # playback only (ch15, ch16), no vocals → Intro / Music Only
    assert MixerEngine._detect_scene(_snap((15, 16))) == "Intro / Music Only"


def test_detect_scene_vocal_plus_one_instrument():
    # vocal + one instrument group = instruments=1 → Sermon / Talk
    assert MixerEngine._detect_scene(_snap((1, 5))) == "Sermon / Talk"


def test_detect_scene_worship_three_groups():
    # vocal + guitar + keys + playback → instruments=3 → Worship
    assert MixerEngine._detect_scene(_snap((1, 5, 7, 15))) == "Worship"


# ── _calc_health ──

def test_calc_health_perfect():
    assert MixerEngine._calc_health({}) == 100


def test_calc_health_zero_error():
    props = {1: {"output_db": -18.0, "target_db": -18.0}}
    assert MixerEngine._calc_health(props) == 100


def test_calc_health_ten_db_error():
    props = {1: {"output_db": -28.0, "target_db": -18.0}}
    assert MixerEngine._calc_health(props) == 0


def test_calc_health_five_db_error():
    props = {1: {"output_db": -23.0, "target_db": -18.0}}
    assert MixerEngine._calc_health(props) == 50


def test_calc_health_clamps_below_zero():
    # error > 10 dB must still return 0, not negative
    props = {1: {"output_db": -38.0, "target_db": -18.0}}
    assert MixerEngine._calc_health(props) == 0


def test_calc_health_averages_multiple_channels():
    # ch1: 0 dB error, ch2: 10 dB error → avg=5 → 50%
    props = {
        1: {"output_db": -18.0, "target_db": -18.0},
        2: {"output_db": -34.0, "target_db": -24.0},
    }
    assert MixerEngine._calc_health(props) == 50


# ── _simulate ──

def test_simulate_skips_inactive():
    snap = {1: {"active": False, "on": True, "db": -20, "fader_db": 0, "name": "vocal"}}
    assert MixerEngine._simulate(snap) == {}


def test_simulate_skips_muted():
    snap = {1: {"active": True, "on": False, "db": -20, "fader_db": 0, "name": "vocal"}}
    assert MixerEngine._simulate(snap) == {}


def test_simulate_produces_proposal_for_active_channel():
    snap = {1: {"active": True, "on": True, "db": -30, "fader_db": 0.0, "name": "vocal"}}
    result = MixerEngine._simulate(snap)
    assert 1 in result
    p = result[1]
    assert p["role"] == "vocal"
    assert p["target_db"] == -18.0
    assert "output_db" in p
    assert "proposed_fader_db" in p


def test_simulate_excludes_unmapped_channel():
    # Channels 9-14 are not in CHANNEL_ROLES; they must never appear in proposals
    snap = {10: {"active": True, "on": True, "db": -20, "fader_db": 0.0, "name": "aux10"}}
    assert MixerEngine._simulate(snap) == {}


def test_simulate_excludes_ch17_ch18():
    # Channels 17-18 are aux/bus and not in CHANNEL_ROLES; they must never appear in proposals
    snap = {
        17: {"active": True, "on": True, "db": -20, "fader_db": 0.0, "name": "aux17"},
        18: {"active": True, "on": True, "db": -20, "fader_db": 0.0, "name": "aux18"},
    }
    assert MixerEngine._simulate(snap) == {}

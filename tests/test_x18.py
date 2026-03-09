"""
Unit tests for X18Client — no real mixer/network required.

All tests use mocks/stubs to avoid UDP socket access.
"""

import threading
from unittest.mock import MagicMock, patch

import pytest

from x18 import X18Client


# ── Channel bounds validation ─────────────────────────────────────────────────

def test_set_fader_rejects_channel_zero():
    client = X18Client()
    with pytest.raises(ValueError):
        client.set_fader(0, 0.5)


def test_set_fader_rejects_channel_above_16():
    client = X18Client()
    with pytest.raises(ValueError):
        client.set_fader(17, 0.5)


def test_set_mute_rejects_channel_zero():
    client = X18Client()
    with pytest.raises(ValueError):
        client.set_mute(0, True)


def test_set_mute_rejects_channel_above_16():
    client = X18Client()
    with pytest.raises(ValueError):
        client.set_mute(17, True)


# ── Fader value clamping ──────────────────────────────────────────────────────

def test_set_fader_clamps_above_one():
    client = X18Client()
    with patch.object(client, '_send'):
        client.set_fader(1, 1.5)
    assert client._faders[1] == 1.0


def test_set_fader_clamps_below_zero():
    client = X18Client()
    with patch.object(client, '_send'):
        client.set_fader(1, -0.5)
    assert client._faders[1] == 0.0


def test_set_fader_accepts_valid_range():
    client = X18Client()
    with patch.object(client, '_send'):
        client.set_fader(1, 0.75)
    assert client._faders[1] == pytest.approx(0.75)


# ── get_snapshot: fallbacks and structure ─────────────────────────────────────

def test_get_snapshot_returns_all_18_channels():
    client = X18Client()
    snap = client.get_snapshot()
    assert set(snap.keys()) == set(range(1, 19))


def test_get_snapshot_falls_back_to_minus90_when_no_meter_data():
    client = X18Client()
    snap = client.get_snapshot()
    assert snap[9]["db"] == -90.0


def test_get_snapshot_active_false_at_minus90():
    client = X18Client()
    snap = client.get_snapshot()
    assert snap[9]["active"] is False


def test_get_snapshot_prefers_meters0_for_ch1_to_8():
    client = X18Client()
    with client._lock:
        client._meters_0[1] = -20.0
        client._meters_1[1] = -30.0
    snap = client.get_snapshot()
    assert snap[1]["db"] == -20.0


def test_get_snapshot_uses_meters1_for_ch9_to_18():
    client = X18Client()
    with client._lock:
        client._meters_1[9] = -25.0
    snap = client.get_snapshot()
    assert snap[9]["db"] == -25.0


def test_get_snapshot_active_true_above_silence():
    client = X18Client()
    with client._lock:
        client._meters_0[1] = -30.0
    snap = client.get_snapshot()
    assert snap[1]["active"] is True


def test_get_snapshot_channel_keys():
    client = X18Client()
    snap = client.get_snapshot()
    for ch in range(1, 19):
        assert "db" in snap[ch]
        assert "fader" in snap[ch]
        assert "fader_db" in snap[ch]
        assert "on" in snap[ch]
        assert "active" in snap[ch]
        assert "name" in snap[ch]


# ── Connection state ──────────────────────────────────────────────────────────

def test_connected_false_before_start():
    client = X18Client()
    assert client.connected is False

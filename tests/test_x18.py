"""
Unit tests for X18Client — no real mixer/network required.

All tests use mocks/stubs to avoid UDP socket access.
"""

import threading
from unittest.mock import MagicMock, patch

import pytest

from x18 import X18Client, _sanitize_name


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


# ── _query: address verification ─────────────────────────────────────────────

def test_query_returns_none_on_address_mismatch():
    """Response from a different OSC address must be silently discarded."""
    from osc import build_message
    client = X18Client()
    sock = MagicMock()
    # Response address is /ch/02/mix/fader but we queried /ch/01/mix/fader
    sock.recvfrom.return_value = (
        build_message("/ch/02/mix/fader", ("f", 0.75)),
        ("192.168.8.18", 10024),
    )
    result = client._query(sock, "/ch/01/mix/fader", "f")
    assert result is None


def test_query_returns_value_on_address_match():
    """Correct address response must return the expected value."""
    from osc import build_message
    client = X18Client()
    sock = MagicMock()
    sock.recvfrom.return_value = (
        build_message("/ch/01/mix/fader", ("f", 0.75)),
        ("192.168.8.18", 10024),
    )
    result = client._query(sock, "/ch/01/mix/fader", "f")
    assert result == pytest.approx(0.75, abs=1e-5)


def test_query_returns_none_on_timeout():
    """Socket timeout must result in None."""
    import socket
    client = X18Client()
    sock = MagicMock()
    sock.recvfrom.side_effect = socket.timeout
    result = client._query(sock, "/ch/01/mix/fader", "f")
    assert result is None


# ── Connection state ──────────────────────────────────────────────────────────

def test_connected_false_before_start():
    client = X18Client()
    assert client.connected is False


# ── _sanitize_name ────────────────────────────────────────────────────────────

def test_sanitize_name_normal():
    assert _sanitize_name("Vocal 1") == "Vocal 1"


def test_sanitize_name_strips_ansi_escape():
    # ESC (\x1b) is a Cc control char and is stripped; the remaining printable
    # ASCII chars are kept — this is sufficient to prevent terminal injection.
    assert _sanitize_name("\x1b[31mVocal\x1b[0m") == "[31mVocal[0m"


def test_sanitize_name_strips_nul_bytes():
    assert _sanitize_name("CH\x0001") == "CH01"


def test_sanitize_name_strips_other_control_chars():
    # tab (\t = \x09), newline (\n), carriage return (\r) are all Cc
    assert _sanitize_name("Na\tme\nHere\r") == "NameHere"


def test_sanitize_name_truncates_long_name():
    long_name = "A" * 100
    result = _sanitize_name(long_name)
    assert len(result) == 32
    assert result == "A" * 32


def test_sanitize_name_default_fallback_unchanged():
    assert _sanitize_name("CH01") == "CH01"

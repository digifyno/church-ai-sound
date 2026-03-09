import pytest
from unittest.mock import MagicMock, patch
from automix import auto_mix_step, save_backup, restore_backup
from config import MAX_CONSECUTIVE_RAISES, STALE_INPUT_WINDOW, STALE_INPUT_BAND_DB


class FakeClient:
    """Minimal X18Client stub for automix testing."""
    def __init__(self, snapshot):
        self._snap = snapshot
        self.fader_calls = []  # (ch, new_db) records

    def get_snapshot(self):
        return dict(self._snap)

    def set_fader_db(self, ch, db):
        self.fader_calls.append((ch, db))
        self._snap[ch]['fader_db'] = db


def _ch(input_db=-30.0, fader_db=0.0, active=True, on=True, name="Vocal"):
    """Helper: minimal channel dict understood by auto_mix_step."""
    return {
        "db": input_db, "fader_db": fader_db,
        "active": active, "on": on, "name": name,
    }


def test_runaway_protection_halts_raises():
    """
    After MAX_CONSECUTIVE_RAISES raises without input improvement,
    auto_mix_step must stop raising even if output is still below target.
    Input decreases slightly each cycle (band > STALE_INPUT_BAND_DB so the
    stale guard doesn't fire), but never improves, so the runaway counter
    accumulates until it exceeds MAX_CONSECUTIVE_RAISES.
    """
    client = FakeClient({1: _ch(input_db=-20.0, fader_db=-20.0)})
    consecutive = {}
    history = {}
    for i in range(MAX_CONSECUTIVE_RAISES + 2):
        # Slowly decreasing input: keeps the band > STALE_INPUT_BAND_DB
        # so the stale guard doesn't fire, but never improves so the
        # runaway counter keeps incrementing.
        client._snap[1]['db'] = -20.0 - i * 0.5
        auto_mix_step(client, consecutive, history)
    assert consecutive.get(1, 0) > MAX_CONSECUTIVE_RAISES
    # Total fader raises should be capped at MAX_CONSECUTIVE_RAISES
    raises = sum(1 for (ch, db) in client.fader_calls if ch == 1)
    assert raises <= MAX_CONSECUTIVE_RAISES + 1


def test_stale_input_guard_halts_raises():
    """
    When input_db is stuck within STALE_INPUT_BAND_DB over STALE_INPUT_WINDOW
    cycles, raises must be suppressed.
    """
    client = FakeClient({1: _ch(input_db=-30.0, fader_db=-10.0)})
    consecutive = {}
    history = {1: [-30.0] * STALE_INPUT_WINDOW}  # pre-populate stale history
    fader_calls_before = len(client.fader_calls)
    auto_mix_step(client, consecutive, history)
    # Fader should NOT have been changed
    assert len(client.fader_calls) == fader_calls_before


def test_runaway_counter_resets_on_vocal_return():
    """
    When input_db improves by more than STALE_INPUT_BAND_DB,
    the consecutive raise counter resets.
    """
    consecutive = {1: MAX_CONSECUTIVE_RAISES + 1}  # pre-set to halted state
    history = {1: [-30.0] * STALE_INPUT_WINDOW}   # history ends at -30
    client = FakeClient({1: _ch(input_db=-20.0, fader_db=-10.0)})  # vocal returned
    # auto_mix_step will append -20 to history, making history[-1]=-20 vs
    # history[-2]=-30, a 10 dB improvement > STALE_INPUT_BAND_DB → reset
    auto_mix_step(client, consecutive, history)
    assert consecutive.get(1, 0) == 0 or consecutive.get(1, 0) <= 1


def test_inactive_channel_skipped():
    client = FakeClient({1: _ch(active=False)})
    consecutive = {}
    history = {}
    auto_mix_step(client, consecutive, history)
    assert client.fader_calls == []


def test_fader_ceiling_never_exceeded():
    """
    Even when output is far below target, fader must never be set above 0 dB.
    """
    client = FakeClient({1: _ch(input_db=-30.0, fader_db=-1.0)})  # just under ceiling
    consecutive = {}
    history = {}
    auto_mix_step(client, consecutive, history)
    for ch, db in client.fader_calls:
        assert db <= 0.0, f"Fader pushed above 0 dB: {db}"


def test_unmapped_channel_is_skipped():
    """Channels not in CHANNEL_ROLES must never have their fader adjusted."""
    client = FakeClient({9: _ch(input_db=-30.0, fader_db=0.0), 1: _ch(input_db=-30.0, fader_db=-10.0)})
    consecutive = {}
    history = {}
    auto_mix_step(client, consecutive, history)
    adjusted_channels = [ch for ch, _ in client.fader_calls]
    assert 9 not in adjusted_channels, "Unmapped channel 9 must not be adjusted"


# ── save_backup / restore_backup ──

def test_save_and_restore_backup(tmp_path):
    client = MagicMock()
    client.get_snapshot.return_value = {
        1: {"name": "VOC", "fader": 0.75, "fader_db": -5.0, "on": True}
    }
    path = tmp_path / "backup.json"
    with patch("time.sleep"):
        save_backup(client, path=str(path))
        assert path.exists()
        restore_backup(client, path=str(path))
    client.set_fader.assert_called_once_with(1, 0.75)


def test_restore_backup_corrupted_file(tmp_path):
    path = tmp_path / "backup.json"
    path.write_text("{ not valid json")
    client = MagicMock()
    restore_backup(client, path=str(path))  # should not raise
    client.set_fader.assert_not_called()

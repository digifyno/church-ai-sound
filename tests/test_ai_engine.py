import datetime
from unittest.mock import patch

from ai_engine import AIEngine


def _make_engine():
    return AIEngine(
        get_channels=lambda: {},
        get_room=lambda: {},
        get_sim=lambda: {},
    )


def test_budget_resets_on_new_day():
    engine = _make_engine()
    engine._total_cost = 1.50
    engine._budget_date = datetime.date(2026, 3, 8)  # "yesterday"

    tomorrow = datetime.date(2026, 3, 10)

    def stop_after_sleep(s):
        engine._running = False

    with patch("ai_engine.date") as mock_date, \
         patch("time.sleep", side_effect=stop_after_sleep):
        mock_date.today.return_value = tomorrow
        engine._running = True
        engine._loop()

    assert engine._total_cost == 0.0
    assert engine._budget_date == tomorrow


def test_silence_message_when_all_channels_inactive():
    inactive_channels = {
        "1": {"active": False, "db": -60, "name": "CH1", "fader_db": 0},
        "2": {"active": False, "db": -60, "name": "CH2", "fader_db": 0},
    }
    engine = AIEngine(
        get_channels=lambda: inactive_channels,
        get_room=lambda: {},
        get_sim=lambda: {},
    )

    def stop_after_sleep(s):
        engine._running = False

    with patch("ai_engine.date") as mock_date, \
         patch("time.sleep", side_effect=stop_after_sleep):
        mock_date.today.return_value = datetime.date(2026, 3, 9)
        engine._running = True
        engine._loop()

    assert engine.get_suggestion() == "No active channels — mix is silent."


def test_budget_not_reset_same_day():
    engine = _make_engine()
    engine._total_cost = 0.75
    today = datetime.date(2026, 3, 9)
    engine._budget_date = today

    def stop_after_sleep(s):
        engine._running = False

    with patch("ai_engine.date") as mock_date, \
         patch("time.sleep", side_effect=stop_after_sleep):
        mock_date.today.return_value = today
        engine._running = True
        engine._loop()

    assert engine._total_cost == 0.75
    assert engine._budget_date == today

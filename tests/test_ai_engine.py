import datetime
import json
from unittest.mock import patch, MagicMock

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

    with patch("ai_engine.date") as mock_date:
        mock_date.today.return_value = tomorrow
        engine._running = True
        engine._stop_event.set()  # return True from wait() immediately
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

    with patch("ai_engine.date") as mock_date:
        mock_date.today.return_value = datetime.date(2026, 3, 9)
        engine._running = True
        engine._stop_event.set()  # return True from wait() immediately
        engine._loop()

    assert engine.get_suggestion() == "No active channels — mix is silent."


def test_budget_not_reset_same_day():
    engine = _make_engine()
    engine._total_cost = 0.75
    today = datetime.date(2026, 3, 9)
    engine._budget_date = today

    with patch("ai_engine.date") as mock_date:
        mock_date.today.return_value = today
        engine._running = True
        engine._stop_event.set()  # return True from wait() immediately
        engine._loop()

    assert engine._total_cost == 0.75
    assert engine._budget_date == today


# ---------------------------------------------------------------------------
# _analyze() tests
# ---------------------------------------------------------------------------

def _make_mock_response(text="Lower piano by 2 dB", input_tokens=100, output_tokens=50):
    resp = MagicMock()
    resp.content = [MagicMock(text=text)]
    resp.usage.input_tokens = input_tokens
    resp.usage.output_tokens = output_tokens
    return resp


def _minimal_channels():
    return {
        "1": {"active": True, "db": -20.0, "name": "Vocals", "fader_db": 0.0},
    }


def _minimal_sim():
    return {
        "scene": "Worship",
        "mix_health": 85,
        "proposals": {
            "1": {
                "role": "lead_vocal",
                "output_db": -20.0,
                "target_db": -18.0,
                "action": "hold",
                "delta_db": 0.0,
                "name": "Vocals",
            }
        },
    }


def test_analyze_returns_ai_text_on_success(tmp_path):
    engine = _make_engine()
    engine._client = MagicMock()
    engine._client.messages.create.return_value = _make_mock_response("Lower piano by 2 dB")

    with patch("ai_engine.AI_LOG_FILE", str(tmp_path / "ai_log.jsonl")):
        result = engine._analyze(_minimal_channels(), {}, _minimal_sim())

    assert result == "Lower piano by 2 dB"


def test_analyze_increments_cost_counters(tmp_path):
    engine = _make_engine()
    engine._client = MagicMock()
    engine._client.messages.create.return_value = _make_mock_response(
        input_tokens=100, output_tokens=50
    )

    with patch("ai_engine.AI_LOG_FILE", str(tmp_path / "ai_log.jsonl")):
        engine._analyze(_minimal_channels(), {}, _minimal_sim())

    assert engine._total_requests == 1
    assert engine._total_input_tokens == 100
    assert engine._total_output_tokens == 50
    assert engine._total_cost > 0


def test_analyze_writes_log_entry(tmp_path):
    log_file = tmp_path / "ai_log.jsonl"
    engine = _make_engine()
    engine._client = MagicMock()
    engine._client.messages.create.return_value = _make_mock_response()

    with patch("ai_engine.AI_LOG_FILE", str(log_file)):
        engine._analyze(_minimal_channels(), {}, _minimal_sim())

    assert log_file.exists()
    lines = log_file.read_text().strip().splitlines()
    assert len(lines) == 1
    entry = json.loads(lines[0])
    for key in ("ts", "model", "cost_usd", "prompt", "response"):
        assert key in entry, f"Missing key: {key}"


def test_analyze_returns_fallback_on_api_error(tmp_path):
    engine = _make_engine()
    engine._client = MagicMock()
    engine._client.messages.create.side_effect = Exception("timeout")

    with patch("ai_engine.AI_LOG_FILE", str(tmp_path / "ai_log.jsonl")):
        result = engine._analyze(_minimal_channels(), {}, _minimal_sim())

    assert result == "AI analysis temporarily unavailable."


def test_analyze_includes_room_mic_when_available(tmp_path):
    log_file = tmp_path / "ai_log.jsonl"
    engine = _make_engine()
    engine._client = MagicMock()
    engine._client.messages.create.return_value = _make_mock_response()

    room = {
        "available": True,
        "db": -30.0,
        "peak_db": -25.0,
        "speech_detected": True,
        "dominant_freqs": [250, 500],
    }

    with patch("ai_engine.AI_LOG_FILE", str(log_file)):
        engine._analyze(_minimal_channels(), room, _minimal_sim())

    entry = json.loads(log_file.read_text().strip())
    assert "ROOM MIC" in entry["prompt"]

"""
AI analysis engine — periodically asks Claude to assess the mix
and provide one actionable suggestion.  Logs every request with cost.
"""

import logging
import os
import time
import threading
import json
from datetime import datetime, date

from config import ANALYSIS_INTERVAL, ANALYSIS_TIMEOUT_SEC, AI_LOG_FILE, AI_MODEL, AI_PRICE_INPUT, AI_PRICE_OUTPUT, MAX_DAILY_COST_USD

log = logging.getLogger(__name__)


class AIEngine:
    def __init__(self, get_channels, get_room, get_sim):
        self._get_channels = get_channels
        self._get_room     = get_room
        self._get_sim      = get_sim
        self._suggestion   = "Waiting for first analysis..."
        self._lock         = threading.Lock()
        self._running      = False
        self._thread       = None
        self._client       = None

        # Cumulative stats
        self._total_requests     = 0
        self._total_input_tokens = 0
        self._total_output_tokens = 0
        self._total_cost         = 0.0
        self._budget_date        = date.today()

    def _load_today_cost(self) -> float:
        """Read ai_log.jsonl and sum costs logged today."""
        today_str = date.today().isoformat()[:10]  # "2026-03-09"
        total = 0.0
        try:
            with open(AI_LOG_FILE) as f:
                for line in f:
                    try:
                        entry = json.loads(line)
                        if entry.get("ts", "").startswith(today_str):
                            total += entry.get("cost_usd", 0.0)
                    except (json.JSONDecodeError, KeyError):
                        continue
        except FileNotFoundError:
            pass  # no log yet — first run
        except Exception:
            log.warning("Could not read AI log for cost recovery", exc_info=True)
        return total

    def start(self):
        api_key = os.environ.get("ANTHROPIC_API_KEY", "")
        if not api_key:
            with self._lock:
                self._suggestion = "Set ANTHROPIC_API_KEY to enable AI suggestions."
            return

        import anthropic
        self._client = anthropic.Anthropic(api_key=api_key)

        with self._lock:
            self._total_cost = self._load_today_cost()
            if self._total_cost > 0:
                log.info("Recovered today's AI cost from log: $%.4f", self._total_cost)

        self._running = True
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._running = False

    @property
    def running(self) -> bool:
        """True if the AI analysis loop is active."""
        with self._lock:
            return self._running

    def get_suggestion(self) -> str:
        with self._lock:
            return self._suggestion

    def get_stats(self) -> dict:
        with self._lock:
            return {
                "requests":      self._total_requests,
                "input_tokens":  self._total_input_tokens,
                "output_tokens": self._total_output_tokens,
                "total_cost":    round(self._total_cost, 6),
            }

    def _log(self, entry: dict):
        try:
            import os
            fd = os.open(AI_LOG_FILE, os.O_WRONLY | os.O_CREAT | os.O_APPEND, 0o600)
            with os.fdopen(fd, "a") as f:
                f.write(json.dumps(entry) + "\n")
        except Exception:
            log.warning("Failed to write AI log entry", exc_info=True)

    def _analyze(self, channels: dict, room: dict, sim: dict) -> str:
        active  = [(ch, i) for ch, i in channels.items() if i["active"]]
        silent  = [(ch, i) for ch, i in channels.items() if not i["active"]]
        props   = sim.get("proposals", {})

        prompt = []
        prompt.append(
            "You are an expert AI church sound technician. "
            "Analyze the live mixer state below and give ONE short, practical "
            "suggestion (max 2 sentences). Be specific with channel names and dB values. "
            "Consider the room microphone level when assessing overall volume."
        )
        prompt.append("")
        prompt.append(f"DETECTED SCENE: {sim.get('scene', 'Unknown')}")
        prompt.append(f"MIX HEALTH: {sim.get('mix_health', '?')}%")
        prompt.append("")

        prompt.append("ACTIVE CHANNELS:")
        for ch, i in active:
            fader_info = f"fader={i['fader_db']}dB"
            role = props.get(ch, {}).get("role", "?")
            output = props.get(ch, {}).get("output_db", "?")
            target = props.get(ch, {}).get("target_db", "?")
            prompt.append(
                f"  CH{ch} {i['name']} [{role}]: "
                f"input={i['db']}dB  {fader_info}  "
                f"output~{output}dB  target={target}dB"
            )

        prompt.append("")
        prompt.append("SILENT CHANNELS:")
        for ch, i in silent:
            prompt.append(f"  CH{ch} {i['name']}")

        if room.get('available', False):
            prompt.append("")
            prompt.append(
                f"ROOM MIC: {room['db']} dB  "
                f"Peak: {room['peak_db']} dB  "
                f"Speech: {room['speech_detected']}"
            )
            if room.get("dominant_freqs"):
                prompt.append(f"Room dominant freqs: {room['dominant_freqs']} Hz")

        if props:
            adjustments = [
                f"  {p['name']}: {p['action']} {p['delta_db']:+.1f} dB"
                for p in props.values() if p["action"] != "hold"
            ]
            if adjustments:
                prompt.append("")
                prompt.append("PROPOSED ADJUSTMENTS (simulation):")
                prompt.extend(adjustments)

        prompt_text = "\n".join(prompt)

        try:
            t0 = time.time()
            resp = self._client.messages.create(
                model=AI_MODEL,
                max_tokens=150,
                messages=[{"role": "user", "content": prompt_text}],
                timeout=ANALYSIS_TIMEOUT_SEC,
            )
            elapsed = time.time() - t0

            answer       = resp.content[0].text.strip()
            input_tokens = resp.usage.input_tokens
            output_tokens = resp.usage.output_tokens
            cost = (input_tokens * AI_PRICE_INPUT + output_tokens * AI_PRICE_OUTPUT) / 1_000_000

            with self._lock:
                self._total_requests      += 1
                self._total_input_tokens  += input_tokens
                self._total_output_tokens += output_tokens
                self._total_cost          += cost

            self._log({
                "ts":             datetime.now().isoformat(),
                "model":          AI_MODEL,
                "input_tokens":   input_tokens,
                "output_tokens":  output_tokens,
                "cost_usd":       round(cost, 6),
                "cumulative_usd": round(self._total_cost, 6),
                "elapsed_s":      round(elapsed, 2),
                "prompt":         prompt_text,
                "response":       answer,
                "scene":          sim.get("scene", ""),
            })

            return answer

        except Exception as e:
            log.exception("AI analysis failed")
            self._log({
                "ts":    datetime.now().isoformat(),
                "error": str(e),
            })
            return "AI analysis temporarily unavailable."

    def _loop(self):
        while self._running:
            try:
                today = date.today()
                with self._lock:
                    if today != self._budget_date:
                        log.info(
                            "New day — resetting AI cost accumulator (was $%.4f)",
                            self._total_cost,
                        )
                        self._total_cost = 0.0
                        self._budget_date = today

                channels = self._get_channels()
                room     = self._get_room()
                sim      = self._get_sim()

                active_count = sum(1 for c in channels.values() if c.get('active', False))
                if active_count == 0:
                    with self._lock:
                        self._suggestion = "No active channels — mix is silent."
                    time.sleep(ANALYSIS_INTERVAL)
                    continue

                with self._lock:
                    over_budget = self._total_cost >= MAX_DAILY_COST_USD
                if over_budget:
                    log.warning(
                        "AI cost budget exceeded ($%.4f >= $%.2f) — analysis paused",
                        self._total_cost, MAX_DAILY_COST_USD,
                    )
                    time.sleep(ANALYSIS_INTERVAL)
                    continue

                text = self._analyze(channels, room, sim)
                with self._lock:
                    self._suggestion = text
            except Exception:
                log.exception("AIEngine analysis loop error")
                with self._lock:
                    self._suggestion = "AI analysis temporarily unavailable."
            time.sleep(ANALYSIS_INTERVAL)

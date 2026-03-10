# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

AI-powered sound technician for church services using a Behringer X-AIR X18 mixer.
Communicates via OSC (Open Sound Control) over UDP. Monitors levels, analyzes the
mix with Claude AI, and can auto-adjust faders.

## Running

```bash
# Web dashboard (simulation, read-only)
python3 app.py                  # → http://localhost:5050

# Live auto-mix (writes faders, Ctrl+C restores backup)
python3 automix.py

# Diagnostics
python3 read_x18.py             # Query mixer info (channel summary table)
# python3 monitor.py            # Terminal meter display (TODO: not yet implemented)
```

## Testing

```bash
pytest tests/          # run all unit tests
pytest tests/ -v       # verbose output
```

Coverage:
- `tests/test_osc.py` — fader taper math, OSC message roundtrips, `compute_adjustment`
- `tests/test_mixer_engine.py` — scene detection, health score, simulation proposals

Safety-critical paths tested: fader ceiling enforcement, hold-zone logic, runaway detection.

Requires `.env` with `ANTHROPIC_API_KEY` and `FLASK_SECRET_KEY` (see `.env.example`). Optional env vars: `MIXER_IP` (default `192.168.8.18`), `MIXER_PORT` (default `10024`), `CORS_ORIGINS`. Install deps:
```bash
pip3 install -r requirements.txt
```

## Architecture

All components are **thread-safe** (lock-protected shared state) and communicate
through snapshot reads — no blocking, no shared mutable references. All engine
classes (`X18Client`, `MixerEngine`, `AIEngine`) use a `threading.Event`
(`_stop_event`) alongside a `_running` bool for clean, fast shutdown — loop
sleeps use `_stop_event.wait(interval)` so they exit immediately on stop.

**Data flow:**
```
X18 mixer (UDP 10024) ←→ x18.py (meters + faders)
                              ↓ get_snapshot()
Room mic → room_mic.py ──→ app.py (push_loop, 7Hz SocketIO) → browser
                              ↑ get_state() / get_suggestion()
              mixer_engine.py (simulation) ← x18 snapshot
              ai_engine.py (Claude Haiku, 15s cycle) ← all snapshots
```

**Key modules:**
- `osc.py` — Shared OSC encode/decode + fader taper math. All OSC code goes here.
- `x18.py` — X18Client: meter subscription, fader/name/mute reads, write commands.
- `config.py` — All hardcoded values (mixer IP, channel roles, target levels).
- `mixer_engine.py` — Computes `output = input_meter + fader_db`, compares to role targets.
- `ai_engine.py` — Claude API calls with full cost logging to `ai_log.jsonl` (created mode 0o600).

## OSC Protocol Gotchas

- **Meter subscriptions expire after ~10s.** Must re-subscribe every 5s. Forgetting
  this causes silent data loss.
- **Byte order is mixed:** OSC message structure is big-endian, but meter blob
  int16 values are **little-endian**. Use `<h` not `>h` for `struct.unpack`.
- **Fader taper is piecewise, not linear.** Use `osc.fader_to_db()` and
  `osc.db_to_fader()` — never do raw math on fader floats.
- **All float params are 0.0–1.0 normalized.** EQ freq, gain, Q, compressor
  threshold, etc. See `docs/X18_OSC_REFERENCE.md` for real-world mappings.
- **Query = send address with no args.** Set = send address with value arg.
- **`_query()` verifies response address.** The helper discards any response
  whose address doesn't match the queried address, preventing stale or
  mismatched packets from being silently accepted as valid replies.
- **Log files use restricted permissions.** `ai_log.jsonl` and
  `automix_log.jsonl` are created via `os.open(..., 0o600)` so they are
  owner-readable only — never world-readable.

## Simulation vs Live

`app.py` is read-only (simulation). `automix.py` writes faders. The simulation
engine (`mixer_engine.py`) computes proposals but never sends OSC.

When writing live fader changes:
1. Always save backup first (`save_backup(client)` in automix.py)
2. Cap adjustments at ±2 dB per cycle (`MAX_STEP_DB` in config)
3. Never push faders above 0 dB
4. Restore on exit (signal handler)
5. Halt raises after `MAX_CONSECUTIVE_RAISES` cycles without input improvement (runaway protection)
6. Halt raises when input level is stuck in a narrow band (`STALE_INPUT_BAND_DB`) over `STALE_INPUT_WINDOW` cycles (stale-input guard)

## Adding New OSC Parameters

1. Add the float-to-real-world mapping to `docs/X18_OSC_REFERENCE.md`
2. Add read/write methods to `X18Client` in `x18.py`
3. Use `osc.build_message()` and `osc.parse_message()` — don't duplicate OSC code
4. All mixer communication goes through `x18.py`, not directly from other modules

## Channel Roles

Defined in `config.py`. Each role has a target output level used by the simulation
engine. The mapping is: `output_db = input_meter_db + fader_db`, compared against
`ROLE_TARGETS[role]`. Active = above `SILENCE_DB` (-55 dB).

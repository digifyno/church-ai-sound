# Church AI Sound — Architecture

## Overview

An AI-powered sound technician for church services using a Behringer X-AIR X18
mixer. The system monitors audio levels, analyzes the mix, and can automatically
adjust faders to maintain optimal sound.

## System Diagram

```
┌──────────────┐         UDP/OSC          ┌──────────────────┐
│  X-AIR X18   │◄────────────────────────►│   x18.py         │
│  (mixer)     │   port 10024             │   OSC client      │
└──────────────┘                          └────────┬─────────┘
                                                   │
┌──────────────┐                          ┌────────┴─────────┐
│  Room Mic    │──── sounddevice ────────►│  room_mic.py     │
│  (MacBook)   │   48kHz PCM              │  FFT analyzer     │
└──────────────┘                          └────────┬─────────┘
                                                   │
                                          ┌────────┴─────────┐
                                          │  mixer_engine.py  │
                                          │  auto-mix logic   │
                                          └────────┬─────────┘
                                                   │
┌──────────────┐    Claude API            ┌────────┴─────────┐
│  Anthropic   │◄────────────────────────►│  ai_engine.py    │
│  (Haiku 4.5) │   every 15s              │  analysis + log   │
└──────────────┘                          └────────┬─────────┘
                                                   │
                                          ┌────────┴─────────┐
│  Browser     │◄──── SocketIO ──────────►│  app.py          │
│  (dashboard) │   7 Hz updates           │  Flask server     │
└──────────────┘                          └──────────────────┘
```

## File Structure

```
.
├── app.py              # Flask + SocketIO web server
├── x18.py              # X-AIR X18 OSC client (meters, faders, read/write)
├── osc.py              # Shared OSC encode/decode + fader taper curves
├── config.py           # Centralized configuration
├── room_mic.py         # Room microphone FFT analyzer
├── mixer_engine.py     # Auto-mix simulation engine
├── ai_engine.py        # Claude AI analysis with cost logging
├── automix.py          # Standalone auto-mix script (live mode)
├── templates/
│   └── index.html      # Web dashboard UI
├── docs/
│   ├── ARCHITECTURE.md # This file
│   └── X18_OSC_REFERENCE.md  # OSC protocol reference
├── .env                # API keys (gitignored)
├── .gitignore
├── fader_backup.json   # Auto-saved fader backup (gitignored)
└── ai_log.jsonl        # AI request/cost log (gitignored)
```

## Components

### x18.py — X18Client
- Connects to the mixer via UDP/OSC on port 10024
- Subscribes to `/meters/0` and `/meters/1` for real-time levels
- Reads channel names, fader positions, and mute states periodically
- Provides `set_fader()`, `set_fader_db()`, `set_mute()` for writes
- Thread-safe snapshots via `get_snapshot()`

### osc.py — OSC Protocol
- Encodes/decodes OSC messages (strings, floats, ints, blobs)
- Parses X-AIR meter blobs (int16 LE, divide by 256 = dB)
- Accurate 5-segment fader taper conversion (fader ↔ dB)

### room_mic.py — RoomMic
- Captures audio from the system microphone via sounddevice
- Computes RMS level in dB
- FFT peak detection for dominant frequencies (feedback candidates)
- Speech detection via zero-crossing rate heuristic
- Time-based peak decay (12 dB/sec, like professional VU meters)

### mixer_engine.py — MixerEngine
- Reads meter + fader data from X18Client
- Computes: `output_level = input_meter + fader_gain`
- Compares output to role-based targets (vocal=-18dB, guitar=-22dB, etc.)
- Proposes gradual adjustments (max ±2 dB per 2-second cycle)
- Detects scene: Worship, Sermon/Talk, Intro/Music, Standby
- Calculates mix health score (0–100%)

### ai_engine.py — AIEngine
- Calls Claude Haiku 4.5 every 15 seconds
- Sends full mixer state (active channels, levels, room mic, proposals)
- Logs every request to `ai_log.jsonl` with token counts and cost
- Tracks cumulative cost (~$0.24 per 2-hour service)

### automix.py — Live Auto-Mixer
- Standalone script for real fader adjustments
- Saves backup before any changes
- Ctrl+C restores backup immediately
- Gradual adjustments: max ±2 dB/cycle, fader ceiling at 0 dB

### app.py — Web Dashboard
- Flask + SocketIO, serves at http://localhost:5050
- Broadcasts state at 7 Hz to all connected browsers
- Shows: channel meters, fader positions, room mic, AI suggestions,
  simulation proposals, scene detection, mix health, AI cost stats

## Safety

- **Simulation by default** — the web dashboard is read-only
- **automix.py** saves a backup before making any changes
- **Ctrl+C restore** — automix immediately restores fader backup
- **Gradual adjustments** — max ±2 dB per 2-second cycle
- **Fader ceiling** — never pushes faders above 0 dB
- **No API keys in git** — .env is gitignored

## Channel Roles (configurable in config.py)

| Channel | Name       | Role     | Target (dBFS) |
|---------|------------|----------|---------------|
| 1       | 58A        | vocal    | -18           |
| 2       | SM58       | backup   | -24           |
| 3       | WL2        | vocal    | -18           |
| 4       | WL1        | vocal    | -18           |
| 5       | Guitar1    | guitar   | -22           |
| 6       | Guitar2    | guitar   | -22           |
| 7       | Piano L    | keys     | -22           |
| 8       | Piano R    | keys     | -22           |
| 15      | PC Ret L   | playback | -26           |
| 16      | PC Ret R   | playback | -26           |

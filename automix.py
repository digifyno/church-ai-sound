#!/usr/bin/env python3
"""
Church AI Auto-Mixer — LIVE MODE.

Continuously reads meter levels and adjusts faders to hit role-based
targets.  Adjustments are gradual (max ±2 dB per cycle, 2-second cycle).

Safety:
 - Backup saved to fader_backup.json before any changes.
 - Ctrl+C restores the backup immediately.
 - Only adjusts channels that have real signal (above SILENCE_DB).
 - Faders are never pushed above 0 dB.

Usage:
    python3 automix.py              # run auto-mix
    python3 automix.py --restore    # restore backup
"""

import json
import signal
import sys
import time

from config import CHANNEL_ROLES, ROLE_TARGETS, SILENCE_DB, MAX_STEP_DB
from osc import fader_to_db, db_to_fader
from x18 import X18Client

CYCLE_SEC   = 2.0
FADER_CEIL  = 0.0     # never push a fader above 0 dB
HOLD_ZONE   = 1.0     # ±1 dB = close enough, don't adjust


def save_backup(client: X18Client, path="fader_backup.json"):
    snap = client.get_snapshot()
    backup = {}
    for ch, c in snap.items():
        backup[str(ch)] = {
            "name": c["name"], "fader": c["fader"],
            "fader_db": c["fader_db"], "on": c["on"],
        }
    with open(path, "w") as f:
        json.dump(backup, f, indent=2)
    return backup


def restore_backup(client: X18Client, path="fader_backup.json"):
    with open(path) as f:
        backup = json.load(f)
    for ch_str, info in backup.items():
        ch = int(ch_str)
        if ch < 1 or ch > 16:
            continue
        client.set_fader(ch, info["fader"])
        time.sleep(0.02)
    print("Faders restored from backup.")


def auto_mix_step(client: X18Client) -> list[str]:
    """One cycle: read state, compute deltas, apply.  Returns log lines."""
    snap = client.get_snapshot()
    actions = []

    for ch, info in snap.items():
        if ch > 16:
            continue
        if not info["active"] or not info["on"]:
            continue

        role      = CHANNEL_ROLES.get(ch, "unknown")
        target_db = ROLE_TARGETS[role]
        input_db  = info["db"]
        fader_db  = info["fader_db"]

        # Estimated output level
        output_db = input_db + fader_db
        error     = target_db - output_db

        if abs(error) < HOLD_ZONE:
            continue

        # Gradual: cap to ±MAX_STEP_DB per cycle
        delta = max(-MAX_STEP_DB, min(MAX_STEP_DB, error))
        new_fader_db = fader_db + delta

        # Safety ceiling
        new_fader_db = min(new_fader_db, FADER_CEIL)
        new_fader_db = max(new_fader_db, -90.0)

        # Skip if no meaningful change
        if abs(new_fader_db - fader_db) < 0.1:
            continue

        client.set_fader_db(ch, new_fader_db)
        direction = "↑" if delta > 0 else "↓"
        actions.append(
            f"  CH{ch:<2} {info['name']:<12} "
            f"in={input_db:>6.1f}  fader {fader_db:>6.1f} → {new_fader_db:>6.1f} dB  "
            f"{direction} {delta:+.1f}  (target={target_db})"
        )

    return actions


def main():
    if "--restore" in sys.argv:
        x = X18Client()
        x.start()
        time.sleep(2)
        restore_backup(x)
        x.stop()
        return

    x = X18Client()
    x.start()
    time.sleep(3)

    print("Church AI Auto-Mixer — LIVE")
    print(f"  Mixer: {x.connected and 'connected' or 'offline'}")
    print(f"  Cycle: {CYCLE_SEC}s   Max step: ±{MAX_STEP_DB} dB")
    print(f"  Fader ceiling: {FADER_CEIL} dB")
    print()

    # Save backup before any changes
    backup = save_backup(x)
    print(f"Backup saved ({len(backup)} channels)")
    print("Press Ctrl+C to stop and restore.\n")

    def on_exit(*_):
        print("\nStopping — restoring backup...")
        restore_backup(x)
        x.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, on_exit)
    signal.signal(signal.SIGTERM, on_exit)

    cycle = 0
    while True:
        cycle += 1
        actions = auto_mix_step(x)
        ts = time.strftime("%H:%M:%S")
        if actions:
            print(f"[{ts}] Cycle {cycle} — {len(actions)} adjustment(s):")
            for a in actions:
                print(a)
        else:
            if cycle % 10 == 1:
                print(f"[{ts}] Cycle {cycle} — all channels on target")
        time.sleep(CYCLE_SEC)


if __name__ == "__main__":
    main()

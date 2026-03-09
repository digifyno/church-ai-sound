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
import logging
import os
import signal
import sys
import time

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

_SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))

from config import (CHANNEL_ROLES, ROLE_TARGETS, SILENCE_DB, MAX_STEP_DB,
                    MAX_CONSECUTIVE_RAISES, STALE_INPUT_WINDOW, STALE_INPUT_BAND_DB,
                    CYCLE_SEC, HOLD_ZONE, FADER_CEIL_DB)
from osc import fader_to_db, db_to_fader, compute_adjustment
from x18 import X18Client


def save_backup(client: X18Client, path=None):
    if path is None:
        path = os.path.join(_SCRIPT_DIR, "fader_backup.json")
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


def restore_backup(client: X18Client, path=None):
    if path is None:
        path = os.path.join(_SCRIPT_DIR, "fader_backup.json")
    if not os.path.exists(path):
        print(f"No backup found at {path}. Nothing to restore.")
        return
    try:
        with open(path) as f:
            backup = json.load(f)
    except (json.JSONDecodeError, OSError) as e:
        log.error("Cannot read backup file %s: %s", path, e)
        log.error("Faders NOT restored — manual recovery required.")
        return
    for ch_str, info in backup.items():
        ch = int(ch_str)
        if ch < 1 or ch > 16:
            continue
        client.set_fader(ch, info["fader"])
        time.sleep(0.02)
    print("Faders restored from backup.")


def auto_mix_step(client: X18Client, consecutive_raises: dict, input_history: dict) -> list[str]:
    """One cycle: read state, compute deltas, apply.  Returns log lines."""
    snap = client.get_snapshot()
    actions = []

    for ch, info in snap.items():
        if ch > 16:
            continue
        if not info["active"] or not info["on"]:
            consecutive_raises.pop(ch, None)
            input_history.pop(ch, None)
            continue

        role      = CHANNEL_ROLES.get(ch, "unknown")
        target_db = ROLE_TARGETS[role]
        input_db  = info["db"]
        fader_db  = info["fader_db"]

        # Track input history for stale-input detection
        history = input_history.get(ch, [])
        history.append(input_db)
        if len(history) > STALE_INPUT_WINDOW:
            history = history[-STALE_INPUT_WINDOW:]
        input_history[ch] = history

        # Reset raise counter if input has improved significantly (vocalist returned)
        if len(history) >= 2 and history[-1] > history[-2] + STALE_INPUT_BAND_DB:
            consecutive_raises[ch] = 0

        output_db, delta, action = compute_adjustment(
            input_db, fader_db, target_db, hold_zone=HOLD_ZONE, max_step=MAX_STEP_DB
        )

        if action == "hold":
            consecutive_raises[ch] = 0
            continue

        new_fader_db = fader_db + delta

        # Safety ceiling
        new_fader_db = min(new_fader_db, FADER_CEIL_DB)
        new_fader_db = max(new_fader_db, -90.0)

        # Skip if no meaningful change
        if abs(new_fader_db - fader_db) < 0.1:
            consecutive_raises[ch] = 0
            continue

        if action == "raise":  # raising the fader
            # Stale-input guard: input stuck in narrow band indicates mic issue
            if len(history) >= STALE_INPUT_WINDOW:
                band = max(history) - min(history)
                if band <= STALE_INPUT_BAND_DB:
                    actions.append(
                        f"  CH{ch:<2} {info['name']:<12} HOLD (stale input: "
                        f"range={band:.1f} dB over {STALE_INPUT_WINDOW} cycles)"
                    )
                    continue

            # Consecutive-raise guard: halt if fader keeps rising without improvement
            consecutive_raises[ch] = consecutive_raises.get(ch, 0) + 1
            if consecutive_raises[ch] > MAX_CONSECUTIVE_RAISES:
                actions.append(
                    f"  CH{ch:<2} {info['name']:<12} HOLD (runaway protection: "
                    f"{consecutive_raises[ch]} consecutive raises)"
                )
                continue
        else:
            consecutive_raises[ch] = 0  # reset on lower

        client.set_fader_db(ch, new_fader_db)
        direction = "↑" if action == "raise" else "↓"
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

    # Register safety handler before any blocking sleep so Ctrl+C during
    # startup doesn't kill the process without a chance to clean up.
    backup_taken = [False]

    def on_exit(*_):
        print("\nStopping — restoring backup...")
        if backup_taken[0]:
            restore_backup(x)
        x.stop()
        sys.exit(0)

    signal.signal(signal.SIGINT, on_exit)
    signal.signal(signal.SIGTERM, on_exit)

    time.sleep(3)  # wait for OSC connection to settle

    print("Church AI Auto-Mixer — LIVE")
    print(f"  Mixer: {x.connected and 'connected' or 'offline'}")
    print(f"  Cycle: {CYCLE_SEC}s   Max step: ±{MAX_STEP_DB} dB")
    print(f"  Fader ceiling: {FADER_CEIL_DB} dB")
    print()

    # Save backup before any changes
    backup = save_backup(x)
    backup_taken[0] = True
    print(f"Backup saved ({len(backup)} channels)")
    print("Press Ctrl+C to stop and restore.\n")

    cycle = 0
    consecutive_raises: dict[int, int] = {}
    input_history: dict[int, list] = {}
    was_connected = x.connected
    while True:
        cycle += 1

        now_connected = x.connected
        if not now_connected:
            if cycle % 5 == 1:  # log every 5 cycles to avoid log spam
                log.warning("Mixer offline — pausing adjustments")
            was_connected = False
            time.sleep(CYCLE_SEC)
            continue

        if not was_connected:
            # Mixer just reconnected — clear stale counters
            consecutive_raises.clear()
            input_history.clear()
            log.info("Mixer reconnected — counters reset")
        was_connected = True

        try:
            actions = auto_mix_step(x, consecutive_raises, input_history)
        except Exception:
            log.exception("auto_mix_step failed — skipping cycle %d", cycle)
            time.sleep(CYCLE_SEC)
            continue

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

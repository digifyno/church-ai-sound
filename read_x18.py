#!/usr/bin/env python3
"""
Diagnostic: query X18 mixer state and print channel summary.
Usage: python3 read_x18.py
"""
from dotenv import load_dotenv
load_dotenv()

import time
from x18 import X18Client
from osc import fader_to_db
from config import CHANNEL_ROLES, ROLE_TARGETS, SILENCE_DB

client = X18Client()
client.start()
print("Connecting to mixer...")
time.sleep(3)  # wait for initial subscription + metadata

if not client.connected:
    print("ERROR: Mixer not responding. Check MIXER_IP and network.")
    client.stop()
    exit(1)

snap = client.get_snapshot()
print(f"{'CH':<4} {'Name':<14} {'Role':<10} {'Input dB':>9} {'Fader dB':>9} {'Output dB':>10} {'Active':<7} {'Muted':<7}")
print("-" * 80)
for ch, info in sorted(snap.items()):
    role = CHANNEL_ROLES.get(ch, "-")
    output_db = info['db'] + info['fader_db']
    active = "YES" if info['active'] else "no"
    muted = "YES" if not info['on'] else "no"
    print(f"{ch:<4} {info['name']:<14} {role:<10} {info['db']:>9.1f} {info['fader_db']:>9.1f} {output_db:>10.1f} {active:<7} {muted:<7}")

client.stop()

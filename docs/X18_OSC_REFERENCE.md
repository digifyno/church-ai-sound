# Behringer X-AIR X18/XR18 — OSC Protocol Reference

This document covers the OSC (Open Sound Control) protocol used to communicate
with Behringer X-AIR X18/XR18 mixers over UDP port **10024**.

Sources:
- [Behringer World Wiki — X-Air OSC](https://behringer.world/wiki/doku.php?id=x-air_osc)
- [Behringer Wiki — OSC Remote Protocol](https://behringerwiki.musictribe.com/index.php?title=OSC_Remote_Protocol)
- [Unofficial X32/M32 OSC Protocol PDF](https://wiki.munichmakerlab.de/images/1/17/UNOFFICIAL_X32_OSC_REMOTE_PROTOCOL_(1).pdf)
- [xair-remote (GitHub)](https://github.com/peterdikant/xair-remote)

---

## Connection

| Setting       | Value          |
|---------------|----------------|
| Protocol      | UDP            |
| Mixer port    | 10024          |
| Message format| OSC 1.0        |
| Byte order    | Big-endian (network byte order) for OSC, little-endian for meter blobs |

The mixer does **not** maintain a persistent connection. You must:
1. Send commands/queries as UDP datagrams to `<mixer_ip>:10024`
2. Receive responses on the same socket
3. Re-subscribe to meters every ~5 seconds (they auto-expire after ~10s)

---

## Value Encoding

All OSC messages follow the standard format:
```
[address string, null-padded to 4 bytes]
[type tag string ",..." null-padded to 4 bytes]
[arguments]
```

Supported types:
- `f` — float32 (big-endian)
- `i` — int32 (big-endian)
- `s` — null-terminated string (padded to 4 bytes)
- `b` — blob (4-byte length prefix + data, padded to 4 bytes)

---

## Normalized Float Parameters

Most parameters use a **normalized 0.0–1.0 float** that maps to a real-world range.
The mapping is linear unless otherwise noted.

---

## Channel Addresses

Channels 1–16: `/ch/01` through `/ch/16`
(X18 also has AUX/USB return channels)

### Config

| Parameter      | Address                    | Type  | Values              |
|----------------|----------------------------|-------|---------------------|
| Name           | `/ch/XX/config/name`       | s     | Up to 12 chars      |
| Color          | `/ch/XX/config/color`      | i     | 0–15 (color index)  |
| Icon           | `/ch/XX/config/icon`       | i     | 0–74                |
| Source         | `/ch/XX/config/source`     | i     | Input routing       |

### Preamp / Headamp

| Parameter      | Address                    | Type  | Range    | Real-world         |
|----------------|----------------------------|-------|----------|--------------------|
| Gain           | `/headamp/XXX/gain`        | f     | 0.0–1.0  | 0 to +60 dB       |
| Phantom 48V    | `/headamp/XXX/phantom`     | i     | 0/1      | Off/On             |
| Phase invert   | `/ch/XX/preamp/invert`     | i     | 0/1      | Normal/Inverted    |
| HPF on         | `/ch/XX/preamp/hpon`       | i     | 0/1      | Off/On             |
| HPF frequency  | `/ch/XX/preamp/hpf`        | f     | 0.0–1.0  | 20–400 Hz          |

Headamp index: `(channel - 1) * 2` for left, `(channel - 1) * 2 + 1` for right.

---

## EQ (4-Band Parametric per Channel)

Each channel has 4 EQ bands: `/ch/XX/eq/1` through `/ch/XX/eq/4`

| Parameter | Address              | Type  | Range   | Real-world          |
|-----------|----------------------|-------|---------|---------------------|
| On/Off    | `/ch/XX/eq/on`       | i     | 0/1     | Bypass/Active       |
| Type      | `/ch/XX/eq/N/type`   | i     | 0–5     | See below           |
| Frequency | `/ch/XX/eq/N/f`      | f     | 0.0–1.0 | 20–20,000 Hz        |
| Gain      | `/ch/XX/eq/N/g`      | f     | 0.0–1.0 | -15.0 to +15.0 dB   |
| Q (width) | `/ch/XX/eq/N/q`      | f     | 0.0–1.0 | 0.3–10.0            |

### EQ Types

| Value | Type   | Description              |
|-------|--------|--------------------------|
| 0     | LCut   | Low cut (high-pass)      |
| 1     | LShv   | Low shelf                |
| 2     | PEQ    | Parametric EQ (bell)     |
| 3     | VEQ    | Vintage EQ               |
| 4     | HShv   | High shelf               |
| 5     | HCut   | High cut (low-pass)      |

### Frequency Float-to-Hz Mapping

The frequency mapping is **logarithmic** from 20 Hz to 20,000 Hz:
```
Hz = 20 * (1000 ^ float_value)
float_value = log10(Hz / 20) / 3
```

Examples:
| Float | Frequency |
|-------|-----------|
| 0.0   | 20 Hz     |
| 0.25  | 112 Hz    |
| 0.33  | 200 Hz    |
| 0.50  | 632 Hz    |
| 0.66  | 2,000 Hz  |
| 0.75  | 3,560 Hz  |
| 1.0   | 20,000 Hz |

### Gain Float-to-dB Mapping

Linear: `dB = (float * 30) - 15`
```
0.0 = -15 dB
0.5 =   0 dB (flat)
1.0 = +15 dB
```

### Q Float Mapping

Logarithmic: `Q = 10 ^ (float * 1.523 - 0.523)`
```
0.0   = 0.3  (very wide)
0.465 = 3.2  (medium)
1.0   = 10.0 (very narrow)
```

---

## Dynamics / Compressor

Address prefix: `/ch/XX/dyn/`

| Parameter    | Address     | Type  | Range    | Real-world               |
|-------------|-------------|-------|----------|--------------------------|
| On/Off      | `dyn/on`    | i     | 0/1      |                          |
| Mode        | `dyn/mode`  | i     | 0/1      | 0=Compressor, 1=Expander |
| Detection   | `dyn/det`   | i     | 0/1      | 0=Peak, 1=RMS            |
| Envelope    | `dyn/env`   | i     | 0/1      | 0=Linear, 1=Logarithmic  |
| Threshold   | `dyn/thr`   | f     | 0.0–1.0  | -60 to 0 dB              |
| Ratio       | `dyn/ratio` | i     | 0–11     | See table                |
| Knee        | `dyn/knee`  | f     | 0.0–1.0  | 0–5 dB                   |
| Makeup gain | `dyn/mgain` | f     | 0.0–1.0  | 0–24 dB                  |
| Attack      | `dyn/attack`| f     | 0.0–1.0  | 0–120 ms                 |
| Hold        | `dyn/hold`  | f     | 0.0–1.0  | 0.02–2000 ms             |
| Release     | `dyn/release`| f    | 0.0–1.0  | 5–4000 ms                |
| Mix         | `dyn/mix`   | f     | 0.0–1.0  | 0–100% (parallel comp.)  |
| Key source  | `dyn/keysrc`| i     | 0–22     | Sidechain source         |
| Auto makeup | `dyn/auto`  | i     | 0/1      |                          |
| Filter on   | `dyn/filter/on`  | i | 0/1     | Sidechain filter         |
| Filter type | `dyn/filter/type`| i | 0–8     | Filter shape             |
| Filter freq | `dyn/filter/f`   | f | 0.0–1.0 | 20–20,000 Hz             |

### Compression Ratios

| Value | Ratio |
|-------|-------|
| 0     | 1.1:1 |
| 1     | 1.3:1 |
| 2     | 1.5:1 |
| 3     | 2.0:1 |
| 4     | 2.5:1 |
| 5     | 3.0:1 |
| 6     | 4.0:1 |
| 7     | 5.0:1 |
| 8     | 7.0:1 |
| 9     | 10:1  |
| 10    | 20:1  |
| 11    | 100:1 (limiter) |

---

## Gate

Address prefix: `/ch/XX/gate/`

| Parameter    | Address        | Type  | Range    | Real-world          |
|-------------|----------------|-------|----------|---------------------|
| On/Off      | `gate/on`      | i     | 0/1      |                     |
| Mode        | `gate/mode`    | i     | 0–4      | See table           |
| Threshold   | `gate/thr`     | f     | 0.0–1.0  | -80 to 0 dB        |
| Range       | `gate/range`   | f     | 0.0–1.0  | 3–60 dB             |
| Attack      | `gate/attack`  | f     | 0.0–1.0  | 0–120 ms            |
| Hold        | `gate/hold`    | f     | 0.0–1.0  | 0.02–2000 ms        |
| Release     | `gate/release` | f     | 0.0–1.0  | 5–4000 ms           |
| Key source  | `gate/keysrc`  | i     | 0–22     | Sidechain source    |
| Filter on   | `gate/filter/on`  | i  | 0/1      |                     |
| Filter type | `gate/filter/type`| i  | 0–8      | Filter shape        |
| Filter freq | `gate/filter/f`   | f  | 0.0–1.0  | 20–20,000 Hz       |

### Gate Modes

| Value | Mode | Description                          |
|-------|------|--------------------------------------|
| 0     | GATE | Standard gate (full attenuation)     |
| 1     | EXP2 | Expander, 2:1 ratio                  |
| 2     | EXP3 | Expander, 3:1 ratio                  |
| 3     | EXP4 | Expander, 4:1 ratio                  |
| 4     | DUCK | Ducker (inverted gate)               |

---

## Mix / Fader / Mute

| Parameter    | Address                | Type  | Range    | Real-world      |
|-------------|------------------------|-------|----------|-----------------|
| Fader       | `/ch/XX/mix/fader`     | f     | 0.0–1.0  | See taper below |
| On/mute     | `/ch/XX/mix/on`        | i     | 0/1      | Muted/On        |
| Pan         | `/ch/XX/mix/pan`       | f     | 0.0–1.0  | L100–R100       |
| Main LR on  | `/ch/XX/mix/lr`        | i     | 0/1      |                 |

### Bus Sends

| Parameter    | Address                    | Type  | Range   |
|-------------|----------------------------|-------|---------|
| Send level  | `/ch/XX/mix/NN/level`      | f     | 0.0–1.0 |
| Send on     | `/ch/XX/mix/NN/on`         | i     | 0/1     |
| Send pre/post| `/ch/XX/mix/NN/grpon`     | i     | 0/1     |

Where NN = 01–06 for bus sends, 11–14 for FX sends.

### Fader Taper (float → dB)

The fader uses a **5-segment piecewise linear** taper:

| Float  | dB     |
|--------|--------|
| 0.0    | -inf   |
| 0.0625 | -60 dB |
| 0.25   | -30 dB |
| 0.50   | -10 dB |
| 0.75   |   0 dB |
| 1.0    | +10 dB |

---

## Meters

Meter data is received by subscribing with a string argument:

```
Send:    /meters  ,s  /meters/0
Receive: /meters/0  ,b  <blob>
```

### Blob Format

```
[4 bytes]  int32 little-endian  — count of int16 values
[count × 2 bytes]  int16 little-endian values
```

Each int16 value: `dB = raw_value / 256.0`

### Meter Endpoints

| Endpoint    | Slots | Description                              |
|-------------|-------|------------------------------------------|
| /meters/0   | 8     | Input channels 1–8 (pre-fader)           |
| /meters/1   | 40    | All channels + buses (pre/post-fader)    |
| /meters/2   | 36    | Bus outputs                              |
| /meters/3   | 56    | Main/matrix outputs                      |

Subscriptions expire after ~10 seconds — re-subscribe every 5s.

---

## Main LR

| Parameter    | Address                  | Type  | Range   |
|-------------|--------------------------|-------|---------|
| Fader       | `/main/st/mix/fader`     | f     | 0.0–1.0 |
| On/mute     | `/main/st/mix/on`        | i     | 0/1     |

---

## FX Slots

The X18 has 4 FX slots.

| Parameter    | Address           | Type  | Description           |
|-------------|-------------------|-------|-----------------------|
| FX type     | `/fx/N/type`      | i     | Effect type (see app) |
| FX params   | `/fx/N/par/NN`    | f/i   | Effect-specific       |

---

## Info / Status

| Address    | Description                                |
|------------|--------------------------------------------|
| `/info`    | Returns server version, name, firmware, model |
| `/xinfo`   | Returns IP, name, model, firmware           |
| `/status`  | Returns connection status                   |

---

## Scenes / Snapshots

| Address               | Description                    |
|-----------------------|--------------------------------|
| `/-snap/name`         | Get/set snapshot name          |
| `/-snap/index`        | Get/set current snapshot index |
| `/-snap/N/name`       | Name of snapshot N             |

---

## Tips

- All queries are "ask and receive": send the address with no arguments to read the current value.
- To set a value, send the address with the new value as an argument.
- Multiple commands can be sent rapidly — the mixer handles them sequentially.
- Use `/xremote` keepalive every 8–10s if not using meters (meters act as keepalive).

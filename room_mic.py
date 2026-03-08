"""
Room microphone analyzer.

Captures ambient audio via the system mic and extracts:
 - RMS level (dB)
 - Peak level with ballistic decay
 - Dominant frequency peaks (feedback candidates)
 - Speech detection heuristic
"""

import logging
import numpy as np
import sounddevice as sd
import threading
import time

from config import MIC_DEVICE, SAMPLE_RATE

log = logging.getLogger(__name__)

BLOCK_SIZE = 4096   # ~85 ms at 48 kHz


class RoomMic:
    def __init__(self):
        self._stream    = None
        self._available = False
        self._lock = threading.Lock()
        self._state = {
            "db":              -90.0,
            "peak_db":         -90.0,
            "dominant_freqs":  [],
            "speech_detected": False,
            "available":       False,
        }
        self._peak_db   = -90.0
        self._last_time = time.time()

    def start(self):
        try:
            self._stream = sd.InputStream(
                device=MIC_DEVICE,
                channels=1,
                samplerate=SAMPLE_RATE,
                blocksize=BLOCK_SIZE,
                callback=self._callback,
            )
            self._stream.start()
            self._available = True
            with self._lock:
                self._state['available'] = True
        except Exception as e:
            log.warning("Room mic unavailable: %s", e)
            self._available = False
            with self._lock:
                self._state['error'] = str(e)

    def stop(self):
        if self._stream:
            self._stream.stop()
            self._stream.close()

    def get(self) -> dict:
        with self._lock:
            return dict(self._state)

    def _callback(self, indata, frames, time_info, status):
        samples = indata[:, 0].astype(np.float32)

        # ── RMS level ──
        rms = float(np.sqrt(np.mean(samples ** 2)))
        db  = float(20 * np.log10(rms + 1e-9))

        # ── Peak with time-based ballistic decay ──
        now = time.time()
        dt  = now - self._last_time
        self._last_time = now
        # Decay ~12 dB/sec (professional VU-style)
        decay = 12.0 * dt
        self._peak_db = max(db, self._peak_db - decay)

        # ── FFT dominant frequencies ──
        window  = samples * np.hanning(len(samples))
        fft_mag = np.abs(np.fft.rfft(window))
        freqs   = np.fft.rfftfreq(len(samples), 1.0 / SAMPLE_RATE)

        # Peaks above noise floor in the 80–8000 Hz range
        noise_floor = float(np.mean(fft_mag))
        mask = (freqs > 80) & (freqs < 8000) & (fft_mag > noise_floor * 6)
        peak_freqs = freqs[mask]
        peak_mags  = fft_mag[mask]

        if len(peak_mags) > 0:
            order = np.argsort(peak_mags)[::-1][:4]
            dominant = [int(round(float(peak_freqs[i]))) for i in order]
        else:
            dominant = []

        # ── Speech detection (energy + zero-crossing rate) ──
        zcr = float(np.mean(np.diff(np.sign(samples)) != 0))
        speech = bool(db > -40 and 0.02 < zcr < 0.35)

        with self._lock:
            self._state = {
                "db":              round(db, 1),
                "peak_db":         round(self._peak_db, 1),
                "dominant_freqs":  dominant,
                "speech_detected": speech,
            }

# utils/metrics.py
from __future__ import annotations
import time, threading

class _Metrics:
    def __init__(self):
        self._lock = threading.Lock()
        self._counters = {
            "requests_total": 0,
            "success": 0,
            "errors_total": 0,
            "duplicates": 0,
            "rate_limited": 0,
            "auth_failed": 0,
            "sheet_errors": 0,
        }
        self._latency_ema_ms = 0.0
        self._ema_alpha = 0.2
        self._last_signal_ts = 0

    def bump(self, key: str):
        with self._lock:
            self._counters[key] = self._counters.get(key, 0) + 1

    def observe_latency_ms(self, ms: float):
        with self._lock:
            if self._latency_ema_ms == 0.0:
                self._latency_ema_ms = float(ms)
            else:
                a = self._ema_alpha
                self._latency_ema_ms = a * float(ms) + (1 - a) * self._latency_ema_ms

    def set_last_signal_now(self):
        with self._lock:
            self._last_signal_ts = int(time.time())

    def snapshot(self):
        with self._lock:
            return {
                "counters": dict(self._counters),
                "latency_ema_ms": round(self._latency_ema_ms, 2),
                "last_signal_ts": self._last_signal_ts,
            }

METRICS = _Metrics()

def snapshot_metrics():
    return METRICS.snapshot()

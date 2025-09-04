from __future__ import annotations
import time, threading

class _Metrics:
    """
    Thread-safe in-proc metrics store with:
    - integer counters
    - simple EMA latency (ms)
    - last_signal_ts (epoch seconds)
    """
    def __init__(self):
        self._lock = threading.Lock()
        self._counters = {
            # intake / general
            "requests_total": 0,
            "success": 0,
            "errors_total": 0,
            "duplicates": 0,
            "rate_limited": 0,
            "auth_failed": 0,
            "sheet_errors": 0,
            # policy events (P2)
            "policy_weekend_on": 0,
            "policy_weekend_off": 0,
            "holiday_halt_on": 0,
            "holiday_halt_off": 0,
            "news_freeze_on": 0,
            "news_freeze_off": 0,
            # lease/handovers (P3)
            "lease_active": 0,
            "passive_drop": 0,
        }
        self._latency_ema_ms: float = 0.0
        self._ema_alpha: float = 0.2
        self._last_signal_ts: int = 0

    # ---- counters ----
    def bump(self, key: str):
        with self._lock:
            self._counters[key] = self._counters.get(key, 0) + 1

    # ---- latency ----
    def observe_latency_ms(self, ms: float):
        with self._lock:
            ms = float(ms)
            if self._latency_ema_ms == 0.0:
                self._latency_ema_ms = ms
            else:
                a = self._ema_alpha
                self._latency_ema_ms = a * ms + (1.0 - a) * self._latency_ema_ms

    # ---- signal marker ----
    def set_last_signal_now(self):
        with self._lock:
            self._last_signal_ts = int(time.time())

    # ---- snapshot ----
    def snapshot(self) -> dict:
        with self._lock:
            return {
                "counters": dict(self._counters),
                "latency_ema_ms": round(self._latency_ema_ms, 2),
                "last_signal_ts": self._last_signal_ts,
            }

# global singleton
METRICS = _Metrics()

def snapshot_metrics() -> dict:
    return METRICS.snapshot()

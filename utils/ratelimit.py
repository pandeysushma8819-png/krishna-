from __future__ import annotations
import time, random
from collections import deque

class GlobalRateLimiter:
    def __init__(self, max_per_sec: int = 10):
        self.max = max(1, int(max_per_sec))
        self.win = deque()

    def allow(self) -> bool:
        now = time.monotonic()
        while self.win and now - self.win[0] > 1.0:
            self.win.popleft()
        if len(self.win) < self.max:
            self.win.append(now)
            return True
        return False

    def rand(self) -> float:
        return random.random()

class TokenBucket:
    """
    Simple per-key token bucket (rate per minute by default).
    """
    def __init__(self, capacity: int = 20, refill_secs: float = 60.0):
        self.capacity = max(1, int(capacity))
        self.refill = float(refill_secs)
        self._last: dict[str, float] = {}
        self._tokens: dict[str, float] = {}

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        tokens = self._tokens.get(key, self.capacity)
        last = self._last.get(key, now)
        # refill
        delta = now - last
        tokens = min(self.capacity, tokens + (delta * self.capacity / self.refill))
        if tokens >= 1.0:
            tokens -= 1.0
            self._tokens[key] = tokens
            self._last[key] = now
            return True
        else:
            self._tokens[key] = tokens
            self._last[key] = now
            return False

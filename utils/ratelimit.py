# utils/ratelimit.py
from __future__ import annotations
import time, random
from collections import deque

class GlobalRateLimiter:
    def __init__(self, max_per_sec: int = 10):
        self.max = max(1, int(max_per_sec))
        self.win = deque()

    def allow(self) -> bool:
        now = time.monotonic()
        # drop older than 1s
        while self.win and now - self.win[0] > 1.0:
            self.win.popleft()
        if len(self.win) < self.max:
            self.win.append(now)
            return True
        return False

    def rand(self) -> float:
        return random.random()

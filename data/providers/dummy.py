# data/providers/dummy.py
from __future__ import annotations
from typing import List, Dict, Any
import time, random

from .base import BaseDataProvider

class DummyProvider(BaseDataProvider):
    name = "dummy"

    def __init__(self, seed: int = 7):
        self.seed = seed

    def is_available(self) -> bool:
        return True

    def get_bars(self, symbol: str, tf_sec: int, limit: int = 200) -> List[Dict[str, Any]]:
        random.seed(self.seed + hash(symbol) % 1000 + int(tf_sec))
        now = int(time.time() // tf_sec * tf_sec)
        px = 100.0
        out: List[Dict[str, Any]] = []
        for i in range(limit, 0, -1):
            ts = now - i * tf_sec
            drift = random.uniform(-0.2, 0.25) / 100.0
            close = max(10.0, px * (1 + drift))
            high = max(close, px) + random.uniform(0.0, 0.3)
            low  = min(close, px) - random.uniform(0.0, 0.3)
            open_ = px
            vol = 800 + int(random.random() * 1200)
            out.append({"ts": ts, "open": round(open_,4), "high": round(high,4),
                        "low": round(low,4), "close": round(close,4), "volume": vol})
            px = close
        return out

PROVIDER = DummyProvider()

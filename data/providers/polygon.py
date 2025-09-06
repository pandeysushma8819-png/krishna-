# data/providers/polygon.py
from __future__ import annotations
from typing import List, Dict, Any
import os, time, requests, math, datetime as dt

from .base import BaseDataProvider

class PolygonProvider(BaseDataProvider):
    name = "polygon"

    def __init__(self, timeout: int = 10):
        self.timeout = timeout
        self.api_key = os.environ.get("POLYGON_API_KEY", "").strip()

    def is_available(self) -> bool:
        return bool(self.api_key)

    @staticmethod
    def _timespan(tf_sec: int) -> (int, str):
        # map to (multiplier, timespan)
        mapping = {
            60: (1, "minute"), 120: (2, "minute"), 300: (5, "minute"),
            900: (15, "minute"), 1800: (30, "minute"),
            3600: (1, "hour"), 86400: (1, "day")
        }
        return mapping.get(int(tf_sec), (15, "minute"))

    def get_bars(self, symbol: str, tf_sec: int, limit: int = 200) -> List[Dict[str, Any]]:
        if not self.api_key:
            raise RuntimeError("POLYGON_API_KEY missing")
        mult, span = self._timespan(tf_sec)
        now = int(time.time())
        start = now - int(limit) * int(tf_sec) * 2  # buffer
        fr = dt.datetime.utcfromtimestamp(start).strftime("%Y-%m-%d")
        to = dt.datetime.utcfromtimestamp(now).strftime("%Y-%m-%d")
        url = f"https://api.polygon.io/v2/aggs/ticker/{symbol.upper()}/range/{mult}/{span}/{fr}/{to}"
        params = {"adjusted": "true", "sort": "asc", "limit": 50000, "apiKey": self.api_key}
        r = requests.get(url, params=params, timeout=self.timeout)
        r.raise_for_status()
        jj = r.json()
        results = jj.get("results") or []
        out: List[Dict[str, Any]] = []
        for a in results[-limit:]:
            ts = int(a["t"] // 1000)
            out.append({
                "ts": ts,
                "open": float(a["o"]), "high": float(a["h"]), "low": float(a["l"]), "close": float(a["c"]),
                "volume": float(a.get("v", 0.0)),
            })
        return out

PROVIDER = PolygonProvider()

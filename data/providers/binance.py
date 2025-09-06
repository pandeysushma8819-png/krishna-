# data/providers/binance.py
from __future__ import annotations
from typing import List, Dict, Any
import requests, math

from .base import BaseDataProvider

class BinanceProvider(BaseDataProvider):
    name = "binance"

    BASE = "https://api.binance.com/api/v3"

    def __init__(self, timeout: int = 10):
        self.timeout = timeout

    def is_available(self) -> bool:
        # public klines don't require key; quick ping
        try:
            r = requests.get(self.BASE + "/ping", timeout=self.timeout)
            return r.status_code == 200
        except Exception:
            return False

    @staticmethod
    def _interval(tf_sec: int) -> str:
        m = {60:"1m",120:"2m",180:"3m",300:"5m",600:"10m",900:"15m",1800:"30m",
             3600:"1h",7200:"2h",14400:"4h",21600:"6h",43200:"12h",86400:"1d"}
        return m.get(int(tf_sec), "15m")

    def get_bars(self, symbol: str, tf_sec: int, limit: int = 200) -> List[Dict[str, Any]]:
        # NOTE: works for crypto symbols like BTCUSDT. NSE symbols won't be available.
        interval = self._interval(tf_sec)
        url = f"{self.BASE}/klines"
        params = {"symbol": symbol.upper(), "interval": interval, "limit": max(1, min(1000, int(limit)))}
        r = requests.get(url, params=params, timeout=self.timeout)
        r.raise_for_status()
        data = r.json()  # [[openTime, open, high, low, close, volume, closeTime, ...], ...]
        out: List[Dict[str, Any]] = []
        for k in data:
            ot = int(k[0] // 1000)
            out.append({
                "ts": ot,
                "open": float(k[1]), "high": float(k[2]), "low": float(k[3]), "close": float(k[4]),
                "volume": float(k[5]),
            })
        return out

PROVIDER = BinanceProvider()

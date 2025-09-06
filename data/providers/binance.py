# data/providers/binance.py
from __future__ import annotations
from typing import List, Dict, Any
import requests

from .base import BaseDataProvider


class BinanceProvider(BaseDataProvider):
    """
    Lightweight public-klines reader for Binance spot markets.

    Notes
    -----
    • No API key required for /api/v3/klines (public).
    • Some hosts block /api/v3/ping — we therefore make `is_available()` always True
      and let `get_bars()` decide. If the network call fails, the router will
      fall back to the next provider (e.g., Polygon, Dummy).
    • Works for symbols like BTCUSDT, ETHUSDT, etc. (Not NSE symbols.)
    """
    name = "binance"
    BASE = "https://api.binance.com"
    KLINES = "/api/v3/klines"

    def __init__(self, timeout: int = 10):
        self.timeout = int(timeout)
        self._session = requests.Session()

    # Avoid preflight ping (can be blocked on some hosts). Let get_bars handle errors.
    def is_available(self) -> bool:  # pragma: no cover
        return True

    @staticmethod
    def _interval(tf_sec: int) -> str:
        """Map seconds to Binance interval strings."""
        tf = int(tf_sec)
        mapping = {
            60: "1m",
            120: "2m",
            180: "3m",
            300: "5m",
            600: "10m",
            900: "15m",
            1800: "30m",
            3600: "1h",
            7200: "2h",
            14400: "4h",
            21600: "6h",
            43200: "12h",
            86400: "1d",
        }
        return mapping.get(tf, "15m")

    def get_bars(self, symbol: str, tf_sec: int, limit: int = 200) -> List[Dict[str, Any]]:
        """
        Fetch OHLCV bars from Binance.

        Parameters
        ----------
        symbol : str
            e.g., "BTCUSDT"
        tf_sec : int
            timeframe in seconds (mapped to Binance intervals)
        limit : int
            number of bars to return (1..1000)

        Returns
        -------
        List[Dict[str, Any]]  oldest → newest
            Each row = {"ts", "open", "high", "low", "close", "volume"}
        """
        if not symbol:
            raise ValueError("symbol required")

        interval = self._interval(tf_sec)
        lim = max(1, min(1000, int(limit)))

        url = f"{self.BASE}{self.KLINES}"
        params = {"symbol": symbol.upper(), "interval": interval, "limit": lim}

        r = self._session.get(url, params=params, timeout=self.timeout)
        # Raise explicit error to allow router fallback
        try:
            r.raise_for_status()
        except requests.HTTPError as e:
            # Include short body snippet for diagnostics
            snippet = ""
            try:
                snippet = r.text[:200]
            except Exception:
                pass
            raise RuntimeError(f"HTTP {r.status_code}: {e} {snippet}") from None

        data = r.json()
        if not isinstance(data, list) or not data:
            raise RuntimeError("empty/invalid klines payload")

        out: List[Dict[str, Any]] = []
        for k in data:
            # kline format:
            # [ openTime, open, high, low, close, volume, closeTime, quoteAssetVol,
            #   numberOfTrades, takerBuyBaseVol, takerBuyQuoteVol, ignore ]
            try:
                ts = int(k[0] // 1000)
                out.append(
                    {
                        "ts": ts,
                        "open": float(k[1]),
                        "high": float(k[2]),
                        "low": float(k[3]),
                        "close": float(k[4]),
                        "volume": float(k[5]),
                    }
                )
            except Exception as e:
                # Skip malformed row but keep going
                continue

        if not out:
            raise RuntimeError("no parsable bars")

        # Ensure ascending by timestamp
        out.sort(key=lambda r: r["ts"])
        # Trim to requested limit (should already be <= limit, but be safe)
        if len(out) > lim:
            out = out[-lim:]

        return out


PROVIDER = BinanceProvider()

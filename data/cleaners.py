from __future__ import annotations
from typing import List, Iterable
from data.schemas import BarDict

def sort_bars(bars: Iterable[BarDict]) -> List[BarDict]:
    return sorted((dict(b) for b in bars), key=lambda x: int(x["ts"]))

def dedupe_bars(bars: Iterable[BarDict]) -> List[BarDict]:
    """Keep the last bar for each ts."""
    out = {}
    for b in bars:
        out[int(b["ts"])] = dict(b)
    return sort_bars(out.values())

def fill_missing_bars(bars: Iterable[BarDict], tf_sec: int, method: str = "ffill") -> List[BarDict]:
    """
    Inserts missing bars at fixed tf_sec cadence.
    method: "ffill" (carry last close into OHLC; vol=0) or "drop" (skip)
    """
    sb = sort_bars(bars)
    if not sb:
        return []
    if method == "drop":
        return sb
    out: List[BarDict] = []
    last = sb[0]
    out.append(last)
    for b in sb[1:]:
        prev_ts = int(last["ts"])
        cur_ts  = int(b["ts"])
        t = prev_ts + tf_sec
        while t < cur_ts:
            # fill one gap bar
            fill = {
                "ts": t,
                "open": last["close"],
                "high": last["close"],
                "low": last["close"],
                "close": last["close"],
                "volume": 0.0,
            }
            out.append(fill)
            last = fill
            t += tf_sec
        out.append(b)
        last = b
    return out

def clamp_spikes(bars: Iterable[BarDict], max_pct: float = 0.15) -> List[BarDict]:
    """
    Clamp intrabar extremes if (high/low vs prev_close) deviates > max_pct (e.g., 0.15=15%).
    Returns a new list; does not mutate input.
    """
    sb = sort_bars(bars)
    if not sb:
        return []
    out: List[BarDict] = []
    prev_close = sb[0]["close"]
    out.append(dict(sb[0]))
    for b in sb[1:]:
        o, h, l, c = b["open"], b["high"], b["low"], b["close"]
        # bounds vs prev_close
        upper = prev_close * (1.0 + max_pct)
        lower = prev_close * (1.0 - max_pct)
        h2 = min(h, upper)
        l2 = max(l, lower)
        # ensure O and C within [l2,h2]
        o2 = min(max(o, l2), h2)
        c2 = min(max(c, l2), h2)
        out.append({"ts": int(b["ts"]), "open": o2, "high": max(h2, o2, c2), "low": min(l2, o2, c2), "close": c2, "volume": b.get("volume", 0.0)})
        prev_close = c2
    return out

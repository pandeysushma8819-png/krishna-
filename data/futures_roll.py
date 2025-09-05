from __future__ import annotations
from typing import Dict, List
from data.schemas import BarDict

def make_continuous_ratio(contracts: Dict[str, List[BarDict]], roll_days: int = 3) -> List[BarDict]:
    """
    Simple ratio-adjusted continuous series.
    contracts: { "YYYYMM": [bars...] } sorted keys ascending (old -> new).
    At each roll boundary (last roll_days of old contract), compute ratio of closes and rescale history.
    """
    if not contracts:
        return []
    # Ensure chronological order
    keys = sorted(contracts.keys())
    # Start with earliest as base
    series = [dict(b) for b in sorted(contracts[keys[0]], key=lambda x: int(x["ts"]))]
    for k in keys[1:]:
        prev = series
        nxt  = sorted(contracts[k], key=lambda x: int(x["ts"]))
        if not prev or not nxt:
            continue
        # pick overlap window: last N of prev vs first N of next
        w_prev = prev[-roll_days:]
        w_next = nxt[:roll_days]
        if not w_prev or not w_next:
            continue
        p = sum(b["close"] for b in w_prev) / len(w_prev)
        n = sum(b["close"] for b in w_next) / len(w_next)
        if p <= 0 or n <= 0:
            ratio = 1.0
        else:
            ratio = n / p
        # Rescale entire history so that end of prev matches start of next
        for b in prev:
            b["open"]  *= ratio
            b["high"]  *= ratio
            b["low"]   *= ratio
            b["close"] *= ratio
        # Merge with next
        series = prev + nxt
    return series

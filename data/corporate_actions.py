from __future__ import annotations
from typing import List
from data.schemas import BarDict, CorporateAction

def apply_corporate_actions(bars: List[BarDict], actions: List[CorporateAction], adjust_volume: bool = True, total_return: bool = True) -> List[BarDict]:
    """
    Adjust OHLC (and optionally volume) for splits and dividends.
    - Splits: price /= ratio going forward (i.e., adjust the history BEFORE the split)
    - Dividends (total_return=True): price_backfilled -= dividend (simple back-adjust)
    """
    if not bars:
        return []
    # Sort
    bars = sorted((dict(b) for b in bars), key=lambda x: int(x["ts"]))
    actions = sorted(actions, key=lambda a: int(a.ts))
    # Build cumulative adjustment factors going backward
    # We'll compute a factor map at each action point and apply to all bars with ts < action.ts
    price_adj = 1.0
    vol_adj   = 1.0
    out = [dict(b) for b in bars]
    for act in actions:
        if act.type == "split":
            # e.g., 1:2 split -> value=2.0; historical prices / 2; volumes * 2
            r = float(act.value) if act.value else 1.0
            if r <= 0: 
                continue
            price_adj *= 1.0 / r
            vol_adj   *= r
            for b in out:
                if int(b["ts"]) < act.ts:
                    b["open"]  *= 1.0 / r
                    b["high"]  *= 1.0 / r
                    b["low"]   *= 1.0 / r
                    b["close"] *= 1.0 / r
                    if adjust_volume:
                        b["volume"] = float(b.get("volume", 0.0)) * r
        elif act.type == "dividend" and total_return:
            d = float(act.value) if act.value else 0.0
            if d == 0.0:
                continue
            # Back-adjust: subtract dividend from all prior prices, keeping ratios
            for b in out:
                if int(b["ts"]) < act.ts:
                    b["open"]  = max(0.0, b["open"]  - d)
                    b["high"]  = max(0.0, b["high"]  - d)
                    b["low"]   = max(0.0, b["low"]   - d)
                    b["close"] = max(0.0, b["close"] - d)
    return out

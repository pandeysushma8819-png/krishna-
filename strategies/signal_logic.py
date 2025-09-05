from __future__ import annotations
from typing import Dict, List
from strategies.spec import StrategySpec
from strategies.indicators import ema, rsi

def build_target_positions(bars: List[dict], spec: StrategySpec) -> Dict[int, int]:
    sid = spec.strategy_id.lower()
    if sid == "ema_cross":
        fast = int(spec.params.get("fast", 10))
        slow = int(spec.params.get("slow", 30))
        closes = [b["close"] for b in bars]
        e_fast = ema(closes, fast)
        e_slow = ema(closes, slow)
        out: Dict[int, int] = {}
        last_pos = 0
        for i, b in enumerate(bars):
            if i == 0:
                out[int(b["ts"])] = 0
                continue
            if e_fast[i-1] > e_slow[i-1] and last_pos <= 0:
                last_pos = 1
            elif e_fast[i-1] < e_slow[i-1] and last_pos >= 0:
                last_pos = 0
            out[int(b["ts"])] = last_pos
        return out

    if sid == "rsi_reversion":
        period = int(spec.params.get("period", 14))
        buy_th = float(spec.params.get("buy_th", 30.0))
        sell_th = float(spec.params.get("sell_th", 55.0))
        closes = [b["close"] for b in bars]
        r = rsi(closes, period)
        out: Dict[int, int] = {}
        pos = 0
        for i, b in enumerate(bars):
            if r[i-1] <= buy_th and pos == 0:
                pos = 1
            elif r[i-1] >= sell_th and pos == 1:
                pos = 0
            out[int(b["ts"])] = pos
        return out

    return {int(b["ts"]): 0 for b in bars}

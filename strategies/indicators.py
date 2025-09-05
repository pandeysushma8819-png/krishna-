from __future__ import annotations
from typing import List

def ema(values: List[float], period: int) -> List[float]:
    if period <= 1 or not values:
        return values[:]
    k = 2.0 / (period + 1.0)
    out = [values[0]]
    for v in values[1:]:
        out.append(out[-1] + k * (v - out[-1]))
    return out

def rsi(values: List[float], period: int) -> List[float]:
    if period <= 0 or len(values) < period + 1:
        return [50.0] * len(values)
    gains, losses = [], []
    for i in range(1, len(values)):
        ch = values[i] - values[i-1]
        gains.append(max(ch, 0.0))
        losses.append(max(-ch, 0.0))
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    rsis = [50.0] * (period)
    for i in range(period, len(gains)):
        avg_gain = (avg_gain * (period - 1) + gains[i]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i]) / period
        rs = (avg_gain / avg_loss) if avg_loss > 0 else 9999.0
        r = 100.0 - (100.0 / (1.0 + rs))
        rsis.append(r)
    return [50.0] + rsis

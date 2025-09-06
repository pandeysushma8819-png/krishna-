# risk/utils.py
from __future__ import annotations
from typing import List, Tuple
import math

def ema(series: List[float], length: int) -> List[float]:
    if length <= 1 or len(series) <= 1:
        return series[:]
    a = 2.0 / (length + 1.0)
    out = []
    s = None
    for x in series:
        s = x if s is None else (a * x + (1 - a) * s)
        out.append(s)
    return out

def atr_last(bars: List[dict], length: int = 14) -> float:
    if len(bars) < 2:
        return 0.0
    trs = []
    prev_c = float(bars[0]["close"])
    for b in bars[1:]:
        h, l, c = float(b["high"]), float(b["low"]), float(b["close"])
        tr = max(h - l, abs(h - prev_c), abs(l - prev_c))
        trs.append(tr)
        prev_c = c
    if not trs:
        return 0.0
    return ema(trs, max(2, length))[-1]

def pct_returns(closes: List[float]) -> List[float]:
    out = [0.0]
    for i in range(1, len(closes)):
        p0 = closes[i - 1] or 1e-9
        out.append((closes[i] - closes[i - 1]) / p0)
    return out

def closes_from_bars(bars: List[dict]) -> List[float]:
    return [float(b["close"]) for b in bars]

def pearson_corr(a: List[float], b: List[float]) -> float:
    n = min(len(a), len(b))
    if n < 3:
        return 0.0
    a, b = a[-n:], b[-n:]
    ma = sum(a) / n
    mb = sum(b) / n
    va = sum((x - ma) ** 2 for x in a)
    vb = sum((y - mb) ** 2 for y in b)
    if va <= 0 or vb <= 0:
        return 0.0
    cov = sum((a[i] - ma) * (b[i] - mb) for i in range(n))
    return max(-1.0, min(1.0, cov / math.sqrt(va * vb)))

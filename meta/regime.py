from __future__ import annotations
from typing import List, Dict, Tuple
import math, statistics, time

# ---------- small helpers (no numpy) ----------

def ema(series: List[float], length: int) -> List[float]:
    if length <= 1: return series[:]
    alpha = 2.0 / (length + 1.0)
    out, s = [], None
    for x in series:
        s = x if s is None else (alpha * x + (1 - alpha) * s)
        out.append(s)
    return out

def atr(bars: List[dict], length: int = 14) -> List[float]:
    """ Wilder-ish ATR using EMA of TR """
    tr = []
    prev_close = None
    for b in bars:
        h, l, c = float(b["high"]), float(b["low"]), float(b["close"])
        if prev_close is None:
            tr.append(h - l)
        else:
            tr.append(max(h - l, abs(h - prev_close), abs(l - prev_close)))
        prev_close = c
    return ema(tr, max(2, length))

def pct_returns(closes: List[float]) -> List[float]:
    out = [0.0]
    for i in range(1, len(closes)):
        prev = max(1e-9, closes[i-1])
        out.append((closes[i] / prev) - 1.0)
    return out

def zscore(x: List[float], lookback: int) -> List[float]:
    out = [0.0] * len(x)
    for i in range(len(x)):
        j0 = max(0, i - lookback + 1)
        w = x[j0:i+1]
        if len(w) < 2:
            out[i] = 0.0
        else:
            m = statistics.fmean(w)
            sd = statistics.pstdev(w) or 1e-9
            out[i] = (x[i] - m) / sd
    return out

# ---------- regime features & classifier ----------

def compute_features(bars: List[dict],
                     tf_sec: int,
                     fast: int = 12,
                     slow: int = 26,
                     atr_len: int = 14,
                     vol_len: int = 20) -> Dict[str, List[float]]:
    closes = [float(b["close"]) for b in bars]
    highs  = [float(b["high"])  for b in bars]
    lows   = [float(b["low"])   for b in bars]

    efast = ema(closes, max(2, fast))
    eslow = ema(closes, max(3, slow))
    delta = [efast[i] - eslow[i] for i in range(len(bars))]
    atrs  = atr(bars, atr_len)

    # normalized trend-strength proxy: |ema_fast - ema_slow| / (ATR + eps)
    trend_strength = [abs(delta[i]) / max(1e-9, atrs[i]) for i in range(len(bars))]

    # volatility proxy: rolling std of pct returns
    rets = pct_returns(closes)
    volz = zscore(rets, vol_len)              # z-scored returns
    vol_abs = [abs(v) for v in volz]          # magnitude of z

    # persistence proxy: fraction of last K returns with same sign
    K = 8
    persist = []
    for i in range(len(bars)):
        j0 = max(0, i - K + 1)
        w = rets[j0:i+1]
        pos = sum(1 for r in w if r > 0)
        neg = sum(1 for r in w if r < 0)
        tot = max(1, len(w))
        persist.append(abs(pos - neg) / tot)  # 0..1 (higher => directional)
    return {
        "efast": efast, "eslow": eslow, "delta": delta,
        "atr": atrs, "trend_strength": trend_strength,
        "volz": volz, "vol_abs": vol_abs, "persist": persist
    }

def classify_regime(bars: List[dict],
                    tf_sec: int,
                    fast: int = 12,
                    slow: int = 26,
                    atr_len: int = 14,
                    vol_len: int = 20,
                    thr_trend: float = 0.7,
                    thr_highvol: float = 2.2) -> List[str]:
    """
    Returns regime tag per bar:
      'trend'      : strong trend_strength AND persistence
      'high_vol'   : volatility z magnitude very high
      'mean'       : weak trend_strength, moderate vol, frequent sign flips
      'sideways'   : low trend_strength and low vol
    """
    F = compute_features(bars, tf_sec, fast, slow, atr_len, vol_len)
    ts, va, ps = F["trend_strength"], F["vol_abs"], F["persist"]
    tags = []
    for i in range(len(bars)):
        if va[i] >= thr_highvol:
            tags.append("high_vol")
        elif ts[i] >= thr_trend and ps[i] >= 0.6:
            tags.append("trend")
        elif ts[i] <= 0.25 and va[i] <= 0.8:
            tags.append("sideways")
        else:
            tags.append("mean")
    return tags

def classify_latest(bars: List[dict], tf_sec: int) -> Tuple[str, Dict[str, float]]:
    """Return last regime + small scores snapshot"""
    F = compute_features(bars, tf_sec)
    tags = classify_regime(bars, tf_sec)
    i = len(bars) - 1
    snap = {
        "trend_strength": round(F["trend_strength"][i], 3),
        "vol_abs": round(F["vol_abs"][i], 3),
        "persist": round(F["persist"][i], 3),
    }
    return tags[-1], snap

def ts_to_ist_str(ts: int) -> str:
    # Asia/Kolkata is UTC+5:30 (no DST). Keep it simple.
    return time.strftime("%Y-%m-%d %H:%M:%S IST", time.gmtime(ts + 19800))

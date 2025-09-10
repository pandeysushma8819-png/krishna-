from __future__ import annotations
from typing import List, Dict, Any, Tuple
import math
from statistics import fmean

# --------- small utils (no deps) ---------
def sma(vals: List[float], n: int) -> List[float]:
    out=[]; s=0.0; q=[]
    for v in vals:
        q.append(v); s+=v
        if len(q)>n: s-=q.pop(0)
        out.append(s/len(q))
    return out

def ema(vals: List[float], n: int) -> List[float]:
    if n<=1: return vals[:]
    a=2.0/(n+1.0); s=None; out=[]
    for v in vals:
        s=v if s is None else a*v+(1-a)*s
        out.append(s)
    return out

def bucket(ts:int, size:int)->int:  # floor to frame
    return ts - (ts % size)

def resample_ohlcv(bars: List[dict], frame:int) -> List[dict]:
    """group by frame seconds; ts = last bar ts in the bucket"""
    if not bars: return []
    groups: Dict[int, List[dict]] = {}
    for b in bars:
        groups.setdefault(bucket(int(b["ts"]), frame), []).append(b)
    out=[]
    for k in sorted(groups.keys()):
        g=groups[k]
        o=g[0]["open"]; h=max(x["high"] for x in g)
        l=min(x["low"]  for x in g); c=g[-1]["close"]
        v=sum(float(x.get("volume",0)) for x in g)
        out.append({"ts":g[-1]["ts"], "open":o, "high":h, "low":l, "close":c, "volume":v, "bucket":k})
    return out

def rsi(cl: List[float], n:int=14) -> List[float]:
    gains=[0.0]; losses=[0.0]
    for i in range(1,len(cl)):
        ch=cl[i]-cl[i-1]
        gains.append(ch if ch>0 else 0.0)
        losses.append(-ch if ch<0 else 0.0)
    rsis=[]; avg_g=avg_l=None
    for i in range(len(cl)):
        if i<n: rsis.append(50.0); continue
        if i==n:
            avg_g=fmean(gains[1:n+1]); avg_l=fmean(losses[1:n+1])
        else:
            avg_g=(avg_g*(n-1)+gains[i])/n
            avg_l=(avg_l*(n-1)+losses[i])/n
        rs = avg_g / (avg_l if avg_l>1e-12 else 1e-12)
        rsis.append(100.0 - 100.0/(1.0+rs))
    return rsis

# --------- core helpers for the rules ---------
def prepare_frames(bars15: List[dict], tf15:int=900):
    H1=3600; D1=86400
    h1 = resample_ohlcv(bars15, H1)
    d1 = resample_ohlcv(bars15, D1)
    # 1H MA50 (close)
    h_cl = [float(b["close"]) for b in h1]
    h_ma50 = sma(h_cl, 50)
    # 1H vol avg20 + peak window
    h_vol = [float(b.get("volume",0.0)) for b in h1]
    h_vol_avg20 = sma(h_vol, 20)
    # Daily MA9 (close) for trend mode
    d_cl = [float(b["close"]) for b in d1]
    d_ma9 = sma(d_cl, 9)
    # index maps for quick lookup by bucket
    h_map = {b["bucket"]: i for i,b in enumerate(h1)}
    d_map = {b["bucket"]: i for i,b in enumerate(d1)}
    return h1, h_ma50, h_vol, h_vol_avg20, h_map, d1, d_ma9, d_map

def vol_strong(i:int, vol:list, vol_avg20:list, mode:str="soft", k:float=1.2, peakN:int=10)->bool:
    v = vol[i]; avg = vol_avg20[i] if i < len(vol_avg20) else None
    if avg is None: return False
    if mode == "strict":
        back = vol[max(0, i-peakN):i] or [0.0]
        return (v > avg) and (v > max(back))
    else:  # soft
        return v > (avg * k)

# --------- main strategy (edit params only) ---------
def compute_positions(bars: List[dict], params: Dict[str, Any]) -> Dict[str, int]:
    """
    Returns mapping ts(str) -> position {-1,0,+1}
    Implements:
      • Daily 9MA filter (auto mode)
      • 1H 'valid candle' level selection (BuyLevel/SellLevel)
      • 15m entry confirmation (cross + alignment to H1 MA50 with epsilon)
      • SL/TP from entry 15m candle (no pyramiding; re-entry allowed while level active)
      • MA50 recycle invalidation of levels with delta buffer
    """
    # ---- params (tune freely) ----
    tf15          = int(params.get("tf_sec", 900))   # input bars TF (15m default)
    daily_filter  = bool(params.get("daily_filter", True))
    mode          = str(params.get("mode", "auto"))  # "auto" | "buy_only" | "sell_only" | "both"
    eps           = float(params.get("align_eps", 0.001))  # 0.1% default
    delta         = float(params.get("ma_recycle_delta", 0.0))
    vol_mode      = str(params.get("vol_mode", "soft"))    # "soft" | "strict"
    vol_k         = float(params.get("vol_k", 1.2))
    vol_peakN     = int(params.get("vol_peakN", 10))
    target_pts    = float(params.get("target_pts", 50.0))
    require_green = bool(params.get("require_green_entry", False))
    require_red   = bool(params.get("require_red_entry", False))  # for sell optional
    allow_short   = True  # short side enabled per spec

    if not bars: return {}
    bars = sorted(bars, key=lambda b: int(b["ts"]))

    # frames
    h1, h_ma50, h_vol, h_vol_avg20, h_map, d1, d_ma9, d_map = prepare_frames(bars, tf15)

    # daily bull/bear lookup by bucket
    def daily_bias(ts:int) -> str:
        if not d1: return "both"
        db = bucket(ts, 86400)
        di = d_map.get(db)
        if di is None or di >= len(d1): return "both"
        if di < 9: return "both"  # not enough history
        return "bull" if d1[di]["close"] > d_ma9[di] else "bear"

    # state that evolves as we walk 15m bars
    buy_level: float | None = None
    sell_level: float | None = None
    pos = 0
    entry_px = None
    sl = tp = None

    out: Dict[str,int] = {}

    # helper to check/update 1H levels at the *close* of each 1H bar
    def update_levels(h_idx:int, bias:str):
        nonlocal buy_level, sell_level
        if h_idx is None or h_idx <= 0: return
        # invalidation first (MA50 recycle)
        b = h1[h_idx]
        ma = h_ma50[h_idx]
        if ma is None: return
        # BUY invalidate if 1H close > MA50*(1+δ) OR min(o, c) > MA50*(1+δ)
        if buy_level is not None:
            if (b["close"] > ma*(1+delta)) or (min(b["open"], b["close"]) > ma*(1+delta)):
                buy_level = None
        # SELL invalidate if 1H close < MA50*(1-δ) OR max(o, c) < MA50*(1-δ)
        if sell_level is not None:
            if (b["close"] < ma*(1-delta)) or (max(b["open"], b["close"]) < ma*(1-delta)):
                sell_level = None

        # Now detect new valid candle (overwrite)
        # BUY valid: red, both open&close strictly BELOW MA50, volume strong, daily bull (if enabled)
        if h_idx >= 50:  # need MA50 history
            if vol_strong(h_idx, h_vol, h_vol_avg20, vol_mode, vol_k, vol_peakN):
                if b["close"] < b["open"]:  # red
                    if (b["open"] < ma) and (b["close"] < ma):  # no touching
                        if (not daily_filter) or bias == "bull":
                            buy_level = float(b["high"])
                if b["close"] > b["open"]:  # green
                    if (b["open"] > ma) and (b["close"] > ma):
                        if (not daily_filter) or bias == "bear":
                            sell_level = float(b["low"])

    # walk 15m bars
    prev_close = None
    for i, m15 in enumerate(bars):
        ts = int(m15["ts"]); o=float(m15["open"]); c=float(m15["close"])
        h_bucket = bucket(ts, 3600)
        h_idx = h_map.get(h_bucket, None)
        ma50 = None if h_idx is None else h_ma50[h_idx]
        if h_idx is not None:
            bias = daily_bias(ts) if daily_filter or mode=="auto" else "both"
            update_levels(h_idx, bias)
        else:
            bias = "both"

        # decide which side allowed by 'mode' + daily bias
        allow_buy = allow_sell = True
        if mode == "buy_only": allow_sell = False
        elif mode == "sell_only": allow_buy = False
        elif mode == "auto":
            allow_buy  = (bias in ("both","bull"))
            allow_sell = (bias in ("both","bear"))

        # manage open position exits (SL/TP) using current 15m bar range
        if pos != 0 and entry_px is not None and sl is not None and tp is not None:
            hi = float(m15["high"]); lo = float(m15["low"])
            # conservative ordering: SL first if both hit in same bar
            if pos == 1:
                if lo <= sl: pos = 0; entry_px = sl = tp = None
                elif hi >= tp: pos = 0; entry_px = sl = tp = None
            elif pos == -1:
                if hi >= sl: pos = 0; entry_px = sl = tp = None
                elif lo <= tp: pos = 0; entry_px = sl = tp = None

        # new entries only if flat
        if pos == 0 and ma50 is not None and prev_close is not None:
            # BUY entry
            if allow_buy and (buy_level is not None):
                cross_up = (prev_close <= buy_level) and (c > buy_level)
                align_ok = (c <= ma50*(1+eps))
                green_ok = (not require_green) or (c > o)
                if cross_up and align_ok and green_ok:
                    pos = 1
                    entry_px = c
                    sl = float(m15["low"])
                    tp = entry_px + target_pts

            # SELL entry
            if pos == 0 and allow_short and allow_sell and (sell_level is not None):
                cross_dn = (prev_close >= sell_level) and (c < sell_level)
                align_ok = (c >= ma50*(1-eps))
                red_ok   = (not require_red) or (c < o)
                if cross_dn and align_ok and red_ok:
                    pos = -1
                    entry_px = c
                    sl = float(m15["high"])
                    tp = entry_px - target_pts

        out[str(ts)] = int(pos)
        prev_close = c

    return out

# strategies/my_strategy.py
# -*- coding: utf-8 -*-
"""
MASTER 15m v1.1 — BUY+SELL (Python port, long-only engine friendly)

- BUY/SELL दोनों rules मौजूद हैं.
- Engine long-only होने के कारण SELL अभी shorts नहीं खोलता, लेकिन
  valid SELL आने पर नए BUY entries रोक देता है (और चाहें तो flatten भी कर सकते हैं).
- Per-symbol target:
    * BTC*: fixed 1500 points
    * XAUUSD / XAGUSD / EURUSD / USDJPY (+ common aliases): RR = 1:5
"""

from __future__ import annotations
from typing import List, Dict, Any, Tuple
import math

# ---------- utils ----------
def sma(seq: List[float], n: int) -> List[float]:
    out, s, q = [], 0.0, []
    for x in seq:
        q.append(x); s += x
        if len(q) > n:
            s -= q.pop(0)
        out.append(s / len(q) if q else float("nan"))
    return out

def highest_prev(seq: List[float], i: int, width: int) -> float:
    if width <= 0 or i <= 0:
        return float("-inf")
    j0 = max(0, i - width)
    if j0 >= i:
        return float("-inf")
    return max(seq[j0:i])

def day_key(ts: int) -> int:
    return (ts // 86400) * 86400

def build_daily_prev_state(bars: List[dict]) -> Dict[int, Tuple[float, float]]:
    by_day: Dict[int, List[dict]] = {}
    for b in bars:
        by_day.setdefault(day_key(int(b["ts"])), []).append(b)
    days = sorted(by_day.keys())
    day_end_close = {d: float(by_day[d][-1]["close"]) for d in days}
    day_prev: Dict[int, Tuple[float, float]] = {}
    hist: List[float] = []
    for d in days:
        prev_c = hist[-1] if hist else float("nan")
        prev_s = (sum(hist[-9:]) / len(hist[-9:])) if hist else float("nan")
        day_prev[d] = (prev_c, prev_s)
        hist.append(day_end_close[d])
    return day_prev

def pick_side_locks(side_mode: str, use_daily9: bool, dPrevC: float, dPrevS9: float) -> Tuple[bool, bool]:
    sm = (side_mode or "auto").strip().lower()
    if sm in ("manual buy", "manual_buy", "buy_only", "buy"):
        return True, False
    if sm in ("manual sell", "manual_sell", "sell_only", "sell"):
        return False, True
    if sm in ("off", "none"):
        return True, True
    # auto (daily-sticky)
    if not use_daily9 or (math.isnan(dPrevC) or math.isnan(dPrevS9)):
        return True, True
    bullish = dPrevC > dPrevS9
    bearish = dPrevC < dPrevS9
    return bullish, bearish

# ---------- per-symbol TP policy ----------
FX_METALS = {"XAUUSD","XAGUSD","GOLD","SILVER","EURUSD","USDJPY"}
def _is_btc(sym: str) -> bool:
    s = (sym or "").upper()
    return "BTC" in s

def _is_fx_metals(sym: str) -> bool:
    s = (sym or "").upper()
    return any(tag in s for tag in FX_METALS)

def _resolve_target_policy(symbol: str, P: Dict[str, Any]) -> Dict[str, Any]:
    """Return dict with keys: target_mode in {"fixed_pts","rr"}, target_pts, rr_multiple."""
    # explicit params override auto
    if "target_mode" in P:
        mode = str(P["target_mode"]).lower()
        return {
            "target_mode": mode,
            "target_pts": float(P.get("target_pts", 50.0)),
            "rr_multiple": float(P.get("rr_multiple", 5.0))
        }
    # auto by symbol
    if _is_btc(symbol):
        return {"target_mode":"fixed_pts", "target_pts":1500.0, "rr_multiple":5.0}
    if _is_fx_metals(symbol):
        return {"target_mode":"rr", "target_pts":50.0, "rr_multiple":5.0}
    # default
    return {"target_mode":"fixed_pts", "target_pts":50.0, "rr_multiple":5.0}

def _compute_tp(entry: float, sl: float, side: str, policy: Dict[str, Any]) -> float:
    mode = policy["target_mode"]
    if mode == "fixed_pts":
        pts = float(policy["target_pts"])
        return entry + pts if side == "long" else entry - pts
    # rr mode
    rr = float(policy["rr_multiple"])
    risk = abs(entry - sl)
    gain = rr * risk
    return entry + gain if side == "long" else entry - gain

# ---------- params ----------
def _coerce_params(params: Dict[str, Any]) -> Dict[str, Any]:
    p = dict(params or {})
    # legacy
    if "volN" not in p and "vol_peakN" in p: p["volN"] = p["vol_peakN"]
    if "volK" not in p and "vol_k" in p: p["volK"] = p["vol_k"]
    if "target_pts" not in p and "tp_pts" in p: p["target_pts"] = p["tp_pts"]
    if "side_mode" not in p and "mode" in p:
        m = str(p["mode"]).lower()
        p["side_mode"] = {"auto":"auto","buy_only":"manual_buy","sell_only":"manual_sell","off":"off"}.get(m, "auto")
    if "use_daily9" not in p and "daily_filter" in p: p["use_daily9"] = bool(p["daily_filter"])
    if "need_color" not in p and "require_green_entry" in p: p["need_color"] = bool(p["require_green_entry"])
    # eps
    if "align_eps" in p: eps = float(p["align_eps"])
    elif "eps_pct" in p: eps = float(p["eps_pct"]) * 0.01
    else: eps = 0.003
    p["align_eps"] = eps
    # defaults
    p.setdefault("tf_sec", 900)
    p.setdefault("side_mode", "auto")
    p.setdefault("use_daily9", True)
    p.setdefault("vol_mode", "SMA*k")
    p.setdefault("volN", 20)
    p.setdefault("volK", 1.10)
    p.setdefault("need_color", False)
    p.setdefault("entry_mode", "Strict")
    p.setdefault("target_pts", 50.0)
    p.setdefault("rr_multiple", 5.0)
    p.setdefault("long_only", True)
    p.setdefault("symbol", "")
    return p

# ---------- main (long-only series 0/1) ----------
def make_target(bars: List[dict], params: Dict[str, Any]) -> Dict[str, int]:
    """
    Returns {ts: 0/1} for LONG position (engine long-only).
    BUY rules open long; SELL rules block new buys (and can flatten if desired).
    """
    P = _coerce_params(params)
    tf = int(P["tf_sec"])
    assert tf == 900, f"Expected 15m bars (tf_sec=900), got {tf}"
    symbol = str(P.get("symbol", ""))

    n = len(bars)
    if n == 0: return {}

    O = [float(b["open"])  for b in bars]
    H = [float(b["high"])  for b in bars]
    L = [float(b["low"])   for b in bars]
    C = [float(b["close"]) for b in bars]
    V = [float(b["volume"]) for b in bars]
    TS= [int(b["ts"]) for b in bars]

    m50 = sma(C, 50)
    vS  = sma(V, 20)
    day_prev_map = build_daily_prev_state(bars)

    # states
    buyLvl, bSrcL = math.nan, math.nan
    sellLvl, sSrcH = math.nan, math.nan
    pos, sl, tp = 0, math.nan, math.nan

    # params
    side_mode  = str(P["side_mode"])
    use_daily9 = bool(P["use_daily9"])
    vol_mode   = str(P["vol_mode"]).lower()
    volN       = int(P["volN"])
    volK       = float(P["volK"])
    need_color = bool(P["need_color"])
    entry_mode = str(P["entry_mode"]).lower()
    eps        = float(P["align_eps"])
    long_only  = bool(P["long_only"])

    policy = _resolve_target_policy(symbol, P)

    out: Dict[str, int] = {}

    for i in range(n):
        ts = TS[i]
        c, o, h, l = C[i], O[i], H[i], L[i]
        prev_c = C[i-1] if i > 0 else c

        # daily lock
        dPrevC, dPrevS9 = day_prev_map.get(day_key(ts), (float("nan"), float("nan")))
        buyAllowed, sellAllowed = pick_side_locks(side_mode, use_daily9, dPrevC, dPrevS9)
        if side_mode.lower() == "off":
            buyAllowed = True; sellAllowed = True

        m50_i = m50[i]; have_m50 = not math.isnan(m50_i)

        # recycle invalidate
        recycleB = have_m50 and ((c > m50_i) or (min(o, c) > m50_i))
        recycleS = have_m50 and ((c < m50_i) or (max(o, c) < m50_i))
        if recycleB: buyLvl, bSrcL = math.nan, math.nan
        if recycleS: sellLvl, sSrcH = math.nan, math.nan

        # 15m valid BUY
        isRed = c < o
        bodyBelow = have_m50 and (max(o, c) < m50_i)
        volStrictB = (V[i] > vS[i]) and (V[i] > highest_prev(V, i, volN))
        volSoftB   = (V[i] > vS[i] * volK)
        volPassB   = volStrictB if (vol_mode == "highestn") else volSoftB
        buyValid   = buyAllowed and isRed and have_m50 and (c < m50_i) and bodyBelow and volPassB

        # 15m valid SELL
        isGreen = c > o
        bodyAbove = have_m50 and (min(o, c) > m50_i)
        volStrictS = (V[i] > vS[i]) and (V[i] > highest_prev(V, i, volN))
        volSoftS   = (V[i] > vS[i] * volK)
        volPassS   = volStrictS if (vol_mode == "highestn") else volSoftS
        sellValid  = sellAllowed and isGreen and have_m50 and (c > m50_i) and bodyAbove and volPassS

        # lifecycle
        if buyValid:
            buyLvl = h
            bSrcL  = l
        if sellValid:
            sellLvl = l
            sSrcH   = h

        # gates
        alignB = have_m50 and (c <= m50_i * (1.0 + eps))
        alignS = have_m50 and (c >= m50_i * (1.0 - eps))
        colorB = (not need_color) or (c > o)      # green
        colorS = (not need_color) or (c < o)      # red

        # break Strict/Crossover
        breakBS = (not math.isnan(buyLvl))  and (c > buyLvl)  and (prev_c <= buyLvl)
        breakBC = (not math.isnan(buyLvl))  and (prev_c <= buyLvl < c)
        breakB  = breakBS if (entry_mode == "strict") else breakBC

        breakSS = (not math.isnan(sellLvl)) and (c < sellLvl) and (prev_c >= sellLvl)
        breakSC = (not math.isnan(sellLvl)) and (c < sellLvl <= prev_c)
        breakS  = breakSS if (entry_mode == "strict") else breakSC

        # exits for existing long
        if pos == 1:
            if l <= sl:  # stop first
                pos = 0; sl = tp = math.nan
            elif h >= tp:  # then target
                pos = 0; sl = tp = math.nan

        # entries only if flat
        if pos == 0:
            doBuy  = buyAllowed  and breakB and alignB and colorB
            doSell = sellAllowed and breakS and alignS and colorS
            if doBuy:
                pos = 1
                # SL = entry-candle low, TP per policy
                sl  = bSrcL if not math.isnan(bSrcL) else l
                tp  = _compute_tp(entry=c, sl=sl, side="long", policy=policy)
            elif doSell:
                # long-only: SELL नया long रोकेगा (optional: flatten करें तो यहाँ pos=0 ही है)
                pass

        out[str(ts)] = 1 if pos == 1 else 0

    return out

# aliases
def generate_target(bars: List[dict], params: Dict[str, Any]) -> Dict[str, int]:
    return make_target(bars, params)

# strategies/my_strategy.py
from __future__ import annotations
from typing import List, Dict, Any, Optional
from collections import deque
import math
import datetime as dt

# -----------------------------
# Helpers
# -----------------------------
def rolling_sma(vals: List[float], n: int) -> List[Optional[float]]:
    out: List[Optional[float]] = [None]*len(vals)
    if n <= 1:
        return [float(x) for x in vals]
    s = 0.0
    q = deque()
    for i, x in enumerate(vals):
        q.append(x)
        s += x
        if len(q) > n:
            s -= q.popleft()
        if len(q) == n:
            out[i] = s / n
    return out

def highest_prev(vals: List[float], i: int, lookback: int) -> float:
    """highest of previous N (exclude current i)"""
    j0 = max(0, i - lookback)
    j1 = max(0, i - 1)
    if j1 < j0:
        return float("-inf")
    return max(vals[j0:j1+1]) if j1 >= j0 else float("-inf")

def day_key(ts_sec: int) -> dt.date:
    # UTC date bucket
    return dt.datetime.utcfromtimestamp(ts_sec).date()

def resample_daily_close(bars: List[dict]) -> List[tuple[dt.date, float]]:
    if not bars:
        return []
    by_day: Dict[dt.date, float] = {}
    last_day = None
    last_close = None
    for b in bars:
        d = day_key(int(b["ts"]))
        c = float(b["close"])
        # overwrite till end of day -> last close of that day
        by_day[d] = c
        last_day = d
        last_close = c
    items = sorted(by_day.items(), key=lambda kv: kv[0])
    return items  # [(date, close)]

def daily_lock_flags_for_today(bars: List[dict]) -> tuple[bool, bool]:
    """
    Pine logic used previous day close vs 9MA[1].
    We'll build daily closes, SMA9, then compare prev-day close to prev-day SMA9.
    Returns (dBullish, dBearish); if not enough history, both True (don't block).
    """
    daily = resample_daily_close(bars)
    if len(daily) < 2:  # need prev-day at least
        return True, True
    closes = [c for _, c in daily]
    sma9 = rolling_sma(closes, 9)
    # index for prev day
    i_prev = len(closes) - 2
    if sma9[i_prev] is None:
        return True, True
    d_close_prev = closes[i_prev]
    d_sma9_prev = sma9[i_prev]
    d_bull = d_close_prev > d_sma9_prev
    d_bear = d_close_prev < d_sma9_prev
    return d_bull, d_bear

def is_btc(symbol: str) -> bool:
    s = (symbol or "").upper()
    return "BTC" in s or "XBT" in s

def is_rr_15_symbol(symbol: str) -> bool:
    s = (symbol or "").upper()
    return any(t in s for t in ["XAU", "GOLD", "XAG", "SILVER", "EURUSD", "USDJPY"])

# -----------------------------
# CORE: compute_positions
# -----------------------------
def compute_positions(bars: List[dict], params: Dict[str, Any]) -> Dict[str, int]:
    """
    Returns a sparse mapping { "ts": side } where side in { -1, 0, +1 },
    emitted only when state changes. Engine opens/closes from these transitions.

    Strategy = 15m valid level + 15m entry (Strict/Crossover)
      - Volume filter: "SMA*k" (default) or "HighestN"
      - Lock: Auto (Daily 9MA sticky), Manual BUY/SELL, or Off
      - Align with 15m MA50 within epsilon
      - Entry color optional
      - Recycle when MA50 crosses (invalidate stored level)
      - Exits (for 0-state): emulate SL/TP using close vs entry bar's high/low
         * BTCUSDT: fixed TP = 1500 (price units)
         * XAU/XAG/EURUSD/USDJPY: TP = 5 * risk (risk = entryC - entryBarLow for long; entryBarHigh - entryC for short)
    """
    if not bars:
        return {}

    # -------- params --------
    symbol: str = params.get("symbol", "")
    tf_sec: int = int(params.get("tf_sec", 900))
    side_mode: str = (params.get("side_mode") or "auto").lower()  # 'auto','manual buy','manual sell','off'
    use_daily9: bool = bool(params.get("use_daily9", True))
    vol_mode: str = (params.get("vol_mode") or "SMA*k").lower()   # 'sma*k' or 'highestn'
    vol_k: float = float(params.get("vol_k", 1.10))
    volN: int = int(params.get("volN", 20))
    align_eps: float = float(params.get("align_eps", 0.003))      # 0.3% = 0.003
    need_color: bool = bool(params.get("need_color", False))
    entry_mode: str = (params.get("entry_mode") or "Strict").lower()  # 'strict' or 'crossover'
    long_only: bool = bool(params.get("long_only", False))

    # -------- arrays --------
    O = [float(b["open"])  for b in bars]
    H = [float(b["high"])  for b in bars]
    L = [float(b["low"])   for b in bars]
    C = [float(b["close"]) for b in bars]
    V = [float(b.get("volume", 0.0)) for b in bars]
    TS= [int(b["ts"]) for b in bars]

    # 15m MA50 (close) and VolSMA20
    ma50 = rolling_sma(C, 50)
    volS = rolling_sma(V, 20)

    # daily lock (sticky for the whole current day, using prev-day info)
    dBull, dBear = daily_lock_flags_for_today(bars)

    def side_locks():
        # allowed sides wrt side_mode + daily
        if side_mode.startswith("manual buy"):
            buy_allowed, sell_allowed = True, False
        elif side_mode.startswith("manual sell"):
            buy_allowed, sell_allowed = False, True
        elif side_mode in ("off", "none"):
            buy_allowed, sell_allowed = True, True
        else:
            # auto
            if not use_daily9:
                buy_allowed, sell_allowed = True, True
            else:
                buy_allowed, sell_allowed = dBull, dBear
        return buy_allowed, sell_allowed

    buy_allowed, sell_allowed = side_locks()

    # state for levels
    buyLvl: Optional[float] = None
    bSrcIdx: Optional[int] = None  # index of valid bar
    sellLvl: Optional[float] = None
    sSrcIdx: Optional[int] = None

    # position state
    pos = 0               # -1/0/+1
    last_emitted = None   # last emitted state in result
    out: Dict[str, int] = {}

    # entry detail for TP/SL emulation
    entry_i = None
    entry_price = None
    entry_bar_low = None
    entry_bar_high = None

    # TP policy
    def compute_tp_sl_for_long(i_entry: int, entry_close: float) -> tuple[float, float]:
        # SL = entry bar low; TP either fixed 1500 for BTC or 5*risk otherwise
        sl = L[i_entry]
        risk = max(1e-9, entry_close - sl)
        if is_btc(symbol):
            tp = entry_close + 1500.0
        elif is_rr_15_symbol(symbol):
            tp = entry_close + 5.0 * risk
        else:
            # default: also RR 1:5
            tp = entry_close + 5.0 * risk
        return tp, sl

    def compute_tp_sl_for_short(i_entry: int, entry_close: float) -> tuple[float, float]:
        # SL = entry bar high; TP either fixed 1500 for BTC or 5*risk otherwise
        sl = H[i_entry]
        risk = max(1e-9, sl - entry_close)
        if is_btc(symbol):
            tp = entry_close - 1500.0
        elif is_rr_15_symbol(symbol):
            tp = entry_close - 5.0 * risk
        else:
            tp = entry_close - 5.0 * risk
        return tp, sl

    def emit(i: int, new_pos: int):
        nonlocal last_emitted, pos
        pos = new_pos
        if last_emitted != pos:
            out[str(TS[i])] = pos
            last_emitted = pos

    # iterate bars
    for i in range(len(bars)):
        c = C[i]; o = O[i]; h = H[i]; l = L[i]
        c_prev = C[i-1] if i > 0 else c
        m50 = ma50[i]
        v = V[i]
        vS = volS[i]

        # not enough warmup?
        if m50 is None or vS is None:
            if i == 0:
                emit(i, 0)
            # still flat until warm
            continue

        # volume pass
        if vol_mode == "highestn":
            vTop = highest_prev(V, i, volN)
            vol_pass_buy  = (v > vS) and (v > vTop)
            vol_pass_sell = (v > vS) and (v > vTop)
        else:
            # SMA*k
            vol_pass_buy  = v > vS * vol_k
            vol_pass_sell = v > vS * vol_k

        # valid candles
        is_red = c < o
        is_green = c > o
        body_below = max(o, c) < m50   # touch invalid
        body_above = min(o, c) > m50

        buy_valid  = is_red   and (c < m50) and body_below and vol_pass_buy  and buy_allowed
        sell_valid = is_green and (c > m50) and body_above and vol_pass_sell and sell_allowed

        # recycle invalidate (MA50 cross style)
        recycleB = (c > m50) or (min(o, c) > m50)
        recycleS = (c < m50) or (max(o, c) < m50)
        if recycleB:
            buyLvl = None
            bSrcIdx = None
        if recycleS:
            sellLvl = None
            sSrcIdx = None

        # set/overwrite levels on valid bars
        if buy_valid:
            buyLvl = h
            bSrcIdx = i
        if sell_valid:
            sellLvl = l
            sSrcIdx = i

        # Entries (only if flat)
        if pos == 0:
            eps = align_eps
            # BUY gates
            alignB = c <= m50 * (1.0 + eps)
            colorB = (not need_color) or (c > o)
            if buyLvl is not None:
                if entry_mode == "strict":
                    breakB = (c > buyLvl) and (c_prev <= buyLvl)
                else:
                    # crossover
                    breakB = (c_prev <= buyLvl) and (c > buyLvl)
            else:
                breakB = False
            doBuy = buy_allowed and (not long_only or long_only) and breakB and alignB and colorB  # long_only doesn't block buy
            if doBuy:
                # enter long
                emit(i, +1)
                entry_i = i
                entry_price = c
                entry_bar_low = l
                entry_bar_high = h
                continue

            # SELL gates (only if not long_only)
            if not long_only:
                alignS = c >= m50 * (1.0 - eps)
                colorS = (not need_color) or (c < o)
                if sellLvl is not None:
                    if entry_mode == "strict":
                        breakS = (c < sellLvl) and (c_prev >= sellLvl)
                    else:
                        breakS = (c_prev >= sellLvl) and (c < sellLvl)
                else:
                    breakS = False
                doSell = sell_allowed and breakS and alignS and colorS
                if doSell:
                    emit(i, -1)
                    entry_i = i
                    entry_price = c
                    entry_bar_low = l
                    entry_bar_high = h
                    continue

        # Exits (SL/TP emulation with close)
        else:
            # LONG
            if pos == +1 and entry_i is not None and entry_price is not None:
                tp, sl = compute_tp_sl_for_long(entry_i, entry_price)
                # SL -> close <= sl ;  TP -> close >= tp
                if c <= sl or c >= tp:
                    emit(i, 0)
                    entry_i = entry_price = entry_bar_low = entry_bar_high = None
                    # do not auto-flip same bar; next bar may re-enter
                    continue

            # SHORT
            if pos == -1 and entry_i is not None and entry_price is not None:
                tp, sl = compute_tp_sl_for_short(entry_i, entry_price)
                # SL -> close >= sl ;  TP -> close <= tp
                if c >= sl or c <= tp:
                    emit(i, 0)
                    entry_i = entry_price = entry_bar_low = entry_bar_high = None
                    continue

        # Ensure we start with an initial state at first bar
        if i == 0 and last_emitted is None:
            emit(i, 0)

    # End: if still in some position, emit flat at last bar to realize PnL in engine
    if pos != 0:
        emit(len(bars)-1, 0)

    return out

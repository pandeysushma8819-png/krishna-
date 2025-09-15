# scripts/btc_backtest_cli.py
# BTC Auto-Shift BUY backtest (4H CSV), no pandas/numpy
# Usage:
#   python scripts/btc_backtest_cli.py --csv data/BTCUSDT_4H.csv --out out/btc
# CSV columns (header required):
#   ts OR timestamp, open, high, low, close, volume
# Notes:
#   - Active TF: Monthly > Weekly > Daily > 4H (highest ON wins), regime ON = close < MA50 (strict)
#   - Valid BUY on ACTIVE TF close: RED (close<open) + High-Volume (vol > VolSMA20 & > prev vol)
#   - Re-entry gate: ECR 10% (next HV candle range overlap ≤ 10% of previous entry candle's range)
#   - Per-TF window quota: 4 entries per discount window (OFF→ON ... ON→OFF)
#   - Exit: target-only; EXIT ALL when close - avg_entry ≥ 1000 * open_entries (configurable)

from __future__ import annotations
import argparse, csv, os, json
from dataclasses import dataclass
from typing import List, Optional, Dict, Tuple
from datetime import datetime, timezone

# --------- helpers ---------
def parse_ts(s: str) -> datetime:
    s = s.strip()
    # Try a few common formats
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M"):
        try:
            dt = datetime.strptime(s, fmt)
            return dt.replace(tzinfo=None)
        except ValueError:
            continue
    # Last resort: fromisoformat (may handle Z-less ISO)
    try:
        return datetime.fromisoformat(s.replace("Z","")).replace(tzinfo=None)
    except Exception:
        raise ValueError(f"Unrecognized timestamp format: {s}")

def week_key(dt: datetime) -> Tuple[int,int]:
    # ISO week (Mon-start), ok for BTC; consistent is what matters
    iso = dt.isocalendar()
    return (iso.year, iso.week)

def month_key(dt: datetime) -> Tuple[int,int]:
    return (dt.year, dt.month)

def day_key(dt: datetime) -> Tuple[int,int,int]:
    return (dt.year, dt.month, dt.day)

def sma(vals: List[float], n: int) -> Optional[float]:
    if len(vals) < n: return None
    return sum(vals[-n:]) / float(n)

def overlap_len(low1: float, high1: float, low2: float, high2: float) -> float:
    lo = max(low1, low2); hi = min(high1, high2)
    return max(0.0, hi - lo)

# --------- params ---------
@dataclass
class Params:
    target_per_entry: float = 1000.0
    ma_len: int = 50
    vol_len: int = 20
    ecr_overlap_pct: float = 10.0
    max_entries_per_window: int = 4
    tol: float = 1e-6

# --------- data types ---------
@dataclass
class Bar:
    ts: datetime
    o: float; h: float; l: float; c: float; v: float

@dataclass
class TFStates:
    # rolling history for SMA
    closes: List[float]
    vols: List[float]
    # current window state
    window_on: bool
    entries_used: int
    # forward-filled regime at latest 4H bar
    reg_on_ff: bool
    # last finalized TF candle OHLCV at its close time (for HV/RED/ECR checks)
    last_tf_ts: Optional[datetime]
    last_o: float; last_h: float; last_l: float; last_c: float; last_v: float
    last_vsma: Optional[float]
    last_prev_v: Optional[float]

def new_tf_state() -> TFStates:
    return TFStates(
        closes=[], vols=[], window_on=False, entries_used=0, reg_on_ff=False,
        last_tf_ts=None, last_o=0.0, last_h=0.0, last_l=0.0, last_c=0.0, last_v=0.0,
        last_vsma=None, last_prev_v=None
    )

# --------- engine ---------
class AutoShiftBTCNoDeps:
    def __init__(self, bars4h: List[Bar], p: Params):
        self.bars = sorted(bars4h, key=lambda b: b.ts)
        self.p = p
        # TF states
        self.tf = {
            "4H": new_tf_state(),
            "D":  new_tf_state(),
            "W":  new_tf_state(),
            "M":  new_tf_state(),
        }
        # Aggregators for D/W/M (progress within current period)
        self.cur_day_key: Optional[Tuple[int,int,int]] = None
        self.cur_week_key: Optional[Tuple[int,int]] = None
        self.cur_month_key: Optional[Tuple[int,int]] = None
        self.agg_D = None  # (o,h,l,c,v)
        self.agg_W = None
        self.agg_M = None

        # positions/ECR/trades
        self.open_entries: List[Dict] = []   # [{ts, px, tf}]
        self.trades: List[Dict] = []         # closed entries

        # 4H SMA trackers
        self.closes_4h: List[float] = []
        self.vols_4h: List[float] = []
        self.prev_vol_4h: Optional[float] = None

    # ---- aggregation helpers ----
    @staticmethod
    def _agg_start(bar: Bar) -> Tuple[float,float,float,float,float]:
        return (bar.o, bar.h, bar.l, bar.c, bar.v)
    @staticmethod
    def _agg_add(agg: Tuple[float,float,float,float,float], bar: Bar) -> Tuple[float,float,float,float,float]:
        o,h,l,c,v = agg
        return (o, max(h, bar.h), min(l, bar.l), bar.c, v + bar.v)

    # ---- TF close finalizers (update SMA, regime, last-TF-candle snapshot, window transitions) ----
    def _finalize_tf(self, name: str, ts_close: datetime, o: float, h: float, l: float, c: float, v: float):
        st = self.tf[name]
        # update rolling histories
        st.closes.append(c); st.vols.append(v)
        ma = sma(st.closes, self.p.ma_len)
        vsma = sma(st.vols, self.p.vol_len)
        reg_on = (ma is not None) and (c < ma - self.p.tol)
        # window transitions happen only at TF closes
        if reg_on and not st.window_on:
            st.window_on = True
            st.entries_used = 0
        elif (not reg_on) and st.window_on:
            st.window_on = False
        # forward-fillable regime state
        st.reg_on_ff = reg_on
        # snapshot last TF candle (for HV/RED/ECR at its close)
        st.last_prev_v = st.vols[-2] if len(st.vols) >= 2 else None
        st.last_vsma = vsma
        st.last_tf_ts = ts_close
        st.last_o, st.last_h, st.last_l, st.last_c, st.last_v = o,h,l,c,v

    # ---- active TF at this 4H bar ----
    def _active_tf(self) -> Optional[str]:
        # Highest ON wins: M > W > D > 4H
        order = ("M","W","D","4H")
        for name in order:
            if self.tf[name].reg_on_ff:
                return name
        return None

    # ---- valid BUY on active TF close ----
    def _valid_buy_on_active_close(self, active: str, now_ts: datetime, close_px_4h: float) -> Tuple[bool,float,float,float]:
        st = self.tf[active]
        # Entry only at TF's close timestamp
        if active != "4H":
            if st.last_tf_ts is None or st.last_tf_ts != now_ts:
                return (False, 0.0, 0.0, 0.0)
        # 4H closes every bar; align to 4H close price for execution
        if active == "4H":
            o,h,l,c,v = self.tf["4H"].last_o, self.tf["4H"].last_h, self.tf["4H"].last_l, self.tf["4H"].last_c, self.tf["4H"].last_v
            # For 4H we set last_* each bar below (before calling this)
        else:
            o,h,l,c,v = st.last_o, st.last_h, st.last_l, st.last_c, st.last_v

        is_red = c < o - self.p.tol
        hv_sma = (st.last_vsma is not None) and (v > st.last_vsma + self.p.tol)
        hv_prev= (st.last_prev_v is not None) and (v > st.last_prev_v + self.p.tol)
        valid = is_red and hv_sma and hv_prev
        return (valid, close_px_4h, l, h)

    # ---- exit check (target-only) ----
    def _try_exit(self, now_ts: datetime, close_px_4h: float):
        if not self.open_entries:
            return
        avg_entry = sum(e["px"] for e in self.open_entries) / float(len(self.open_entries))
        need = self.p.target_per_entry * len(self.open_entries)
        if (close_px_4h - avg_entry) >= (need - self.p.tol):
            for e in self.open_entries:
                self.trades.append({
                    "side": "BUY", "tf": e["tf"],
                    "entry_ts": e["ts"].isoformat(sep=" "),
                    "entry_px": e["px"],
                    "exit_ts": now_ts.isoformat(sep=" "),
                    "exit_px": close_px_4h,
                    "status": "tp",
                    "pnl": close_px_4h - e["px"],
                })
            self.open_entries.clear()
            # reset ECR when flat
            self.ecr_low = None; self.ecr_high = None

    # ---- main run ----
    def run(self):
        if not self.bars:
            return []
        # init period keys from first bar
        self.cur_day_key = day_key(self.bars[0].ts)
        self.cur_week_key = week_key(self.bars[0].ts)
        self.cur_month_key = month_key(self.bars[0].ts)
        self.agg_D = self._agg_start(self.bars[0])
        self.agg_W = self._agg_start(self.bars[0])
        self.agg_M = self._agg_start(self.bars[0])

        # ECR
        self.ecr_low: Optional[float] = None
        self.ecr_high: Optional[float] = None

        n = len(self.bars)
        for i, bar in enumerate(self.bars):
            # ---- 4H rolling SMA / regime (close every bar) ----
            self.closes_4h.append(bar.c)
            self.vols_4h.append(bar.v)
            ma4 = sma(self.closes_4h, self.p.ma_len)
            vsma4 = sma(self.vols_4h, self.p.vol_len)
            reg4 = (ma4 is not None) and (bar.c < ma4 - self.p.tol)
            self.tf["4H"].reg_on_ff = reg4
            # snapshot last 4H candle (for ECR calc if active=4H)
            self.tf["4H"].last_tf_ts = bar.ts
            self.tf["4H"].last_o, self.tf["4H"].last_h, self.tf["4H"].last_l, self.tf["4H"].last_c, self.tf["4H"].last_v = bar.o, bar.h, bar.l, bar.c, bar.v
            self.tf["4H"].last_vsma = vsma4
            self.tf["4H"].last_prev_v = self.vols_4h[-2] if len(self.vols_4h) >= 2 else None

            # ---- build D/W/M aggregations ----
            # Append 4H into current period aggs
            self.agg_D = self._agg_add(self.agg_D, bar)
            self.agg_W = self._agg_add(self.agg_W, bar)
            self.agg_M = self._agg_add(self.agg_M, bar)

            # Lookahead keys to see if current bar is period close
            next_bar = self.bars[i+1] if i+1 < n else None
            day_close = (next_bar is None) or (day_key(next_bar.ts) != self.cur_day_key)
            week_close= (next_bar is None) or (week_key(next_bar.ts) != self.cur_week_key)
            month_close=(next_bar is None) or (month_key(next_bar.ts) != self.cur_month_key)

            # Finalize D/W/M at their closes
            if day_close:
                o,h,l,c,v = self.agg_D
                self._finalize_tf("D", bar.ts, o,h,l,c,v)
                # reset next day
                if next_bar:
                    self.cur_day_key = day_key(next_bar.ts)
                    self.agg_D = self._agg_start(next_bar)
            if week_close:
                o,h,l,c,v = self.agg_W
                self._finalize_tf("W", bar.ts, o,h,l,c,v)
                if next_bar:
                    self.cur_week_key = week_key(next_bar.ts)
                    self.agg_W = self._agg_start(next_bar)
            if month_close:
                o,h,l,c,v = self.agg_M
                self._finalize_tf("M", bar.ts, o,h,l,c,v)
                if next_bar:
                    self.cur_month_key = month_key(next_bar.ts)
                    self.agg_M = self._agg_start(next_bar)

            # ---- EXIT first (target-only) on 4H close ----
            self._try_exit(bar.ts, bar.c)

            # ---- ACTIVE TF selection ----
            active = self._active_tf()
            if active is None:
                continue

            # Require that TF actually closed now (for D/W/M)
            if active != "4H":
                st = self.tf[active]
                if st.last_tf_ts is None or st.last_tf_ts != bar.ts:
                    continue

            # Window/quota checks
            st = self.tf[active]
            if not st.window_on:
                continue
            if st.entries_used >= self.p.max_entries_per_window:
                continue

            # Valid BUY on active TF close
            ok, close_px, tf_low, tf_high = self._valid_buy_on_active_close(active, bar.ts, bar.c)
            if not ok:
                continue

            # ECR 10% re-entry gate
            if (self.ecr_low is not None) and (self.ecr_high is not None):
                R = max(0.0, self.ecr_high - self.ecr_low)
                if R > self.p.tol:
                    ov = overlap_len(self.ecr_low, self.ecr_high, tf_low, tf_high)
                    if ov > (R * (self.p.ecr_overlap_pct / 100.0) + self.p.tol):
                        continue

            # TAKE ENTRY @ 4H close price, ECR from ACTIVE TF candle
            self.open_entries.append({"ts": bar.ts, "px": close_px, "tf": active})
            st.entries_used += 1
            self.ecr_low, self.ecr_high = tf_low, tf_high

        return self.trades

# --------- CSV IO ---------
def load_4h_csv(path: str) -> List[Bar]:
    bars: List[Bar] = []
    with open(path, "r", newline="", encoding="utf-8") as f:
        rd = csv.DictReader(f)
        cols = {k.lower(): k for k in rd.fieldnames or []}
        # map ts/timestamp
        ts_key = "ts" if "ts" in cols else ("timestamp" if "timestamp" in cols else None)
        need = [ts_key, "open", "high", "low", "close", "volume"]
        if ts_key is None or any(c not in cols for c in need):
            raise ValueError(f"CSV must have headers: ts(or timestamp), open, high, low, close, volume; got {rd.fieldnames}")
        for row in rd:
            ts = parse_ts(row[cols[ts_key]])
            o = float(row[cols["open"]]); h=float(row[cols["high"]]); l=float(row[cols["low"]]); c=float(row[cols["close"]]); v=float(row[cols["volume"]])
            bars.append(Bar(ts,o,h,l,c,v))
    bars.sort(key=lambda b: b.ts)
    return bars

# --------- main ---------
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="Path to BTC 4H CSV (ts/timestamp,open,high,low,close,volume)")
    ap.add_argument("--out", default="out/btc", help="Output dir")
    ap.add_argument("--target", type=float, default=1000.0, help="Target per entry (points)")
    ap.add_argument("--ecr_pct", type=float, default=10.0, help="ECR overlap % (re-entry gate)")
    ap.add_argument("--ma_len", type=int, default=50, help="MA length (all TFs)")
    ap.add_argument("--vol_len", type=int, default=20, help="Volume SMA length (all TFs)")
    ap.add_argument("--max_entries", type=int, default=4, help="Per-TF window quota")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    bars = load_4h_csv(args.csv)
    p = Params(
        target_per_entry=args.target,
        ecr_overlap_pct=args.ecr_pct,
        ma_len=args.ma_len,
        vol_len=args.vol_len,
        max_entries_per_window=args.max_entries,
    )
    eng = AutoShiftBTCNoDeps(bars, p)
    trades = eng.run()

    # Save outputs
    trades_csv = os.path.join(args.out, "trades.csv")
    trades_json = os.path.join(args.out, "trades.json")
    with open(trades_csv, "w", newline="", encoding="utf-8") as f:
        wr = csv.writer(f)
        wr.writerow(["side","tf","entry_ts","entry_px","exit_ts","exit_px","status","pnl"])
        for t in trades:
            wr.writerow([t["side"],t["tf"],t["entry_ts"],t["entry_px"],t["exit_ts"],t["exit_px"],t["status"],t["pnl"]])
    with open(trades_json, "w", encoding="utf-8") as f:
        json.dump({"version":1,"trades":trades}, f, ensure_ascii=False)

    # Summary
    total = len(trades)
    total_pnl = sum(t["pnl"] for t in trades)
    avg_pnl = (total_pnl/total) if total>0 else 0.0
    by_tf: Dict[str,int] = {}
    for t in trades:
        by_tf[t["tf"]] = by_tf.get(t["tf"], 0) + 1

    print("==== BTC Backtest Summary ====")
    print(f"trades_closed: {total}")
    print(f"pnl_total: {total_pnl:.2f}")
    print(f"pnl_avg_per_trade: {avg_pnl:.2f}")
    print(f"trades_by_tf: {by_tf}")
    print(f"saved: {trades_csv}")
    print(f"saved: {trades_json}")

if __name__ == "__main__":
    main()

# strategies/auto_shift_buy.py
# KTW v3 — Auto-Shift BUY System (HTF only: 4H/D/W/M)
# BUY-only, target-only exit (no SL), Active TF = highest TF with discount (close < MA50).
# Valid BUY = RED + High Volume (Vol > SMA20 AND > prev bar vol) on ACTIVE TF close.
# Re-entry gate = ECR 10% overlap. Per-TF window quota = 4. Global cap = NONE (entries don't stop across TFs).
# Exit = EXIT ALL when (close - avg_entry) >= 1000 * (#open entries), checked each 4H close.
#
# I/O (project style):
#   - generate_trades(df4h, params) -> List[Dict] each with: entry_ts, exit_ts, entry_px, exit_px, tf, pnl, status
#   - to_target_json(trades) -> {"version":1, "trades":[...]}
#
# CSV helper (optional):
#   python strategies/auto_shift_buy.py data_4h.csv '{"target_per_entry":1000}'

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Optional, Tuple
import numpy as np
import pandas as pd


@dataclass
class Params:
    target_per_entry: float = 1000.0   # cumulative TP per open entry
    ma_len: int = 50                   # MA50 for all TFs
    vol_sma_len: int = 20              # Vol SMA for HV check
    ecr_overlap_pct: float = 10.0      # max allowed overlap (% of prior ECR range)
    max_entries_per_window: int = 4    # PER TF window quota
    tol: float = 1e-6                  # tiny tolerance


# ---------- utils ----------
def _as_dt_index(df: pd.DataFrame) -> pd.DataFrame:
    need = ["ts", "open", "high", "low", "close", "volume"]
    miss = [c for c in need if c not in df.columns]
    if miss:
        raise ValueError(f"Missing columns: {miss}")
    out = df.copy()
    if not np.issubdtype(out["ts"].dtype, np.datetime64):
        out["ts"] = pd.to_datetime(out["ts"], utc=True, errors="coerce")
    return out.set_index("ts").sort_index()

def _sma(s: pd.Series, n: int) -> pd.Series:
    return s.rolling(n, min_periods=n).mean()

def _resample(df: pd.DataFrame, rule: str) -> pd.DataFrame:
    agg = {"open":"first","high":"max","low":"min","close":"last","volume":"sum"}
    return df.resample(rule).agg(agg).dropna(how="any")

def _align_close_flags(base_idx: pd.DatetimeIndex, tf_idx: pd.DatetimeIndex) -> pd.Series:
    s = pd.Series(False, index=base_idx)
    if len(tf_idx):
        s.loc[s.index.isin(tf_idx)] = True
    return s

def _overlap_len(l1: float, h1: float, l2: float, h2: float) -> float:
    lo = max(l1, l2); hi = min(h1, h2)
    return max(0.0, hi - lo)

def _choose_active(reg4: bool, regD: bool, regW: bool, regM: bool) -> Optional[str]:
    # Highest ON wins — Monthly > Weekly > Daily > 4H
    if regM: return "M"
    if regW: return "W"
    if regD: return "D"
    if reg4: return "4H"
    return None


# ---------- engine ----------
class AutoShiftBuy:
    def __init__(self, df4h: pd.DataFrame, p: Params):
        self.p = p
        self.base = _as_dt_index(df4h)  # 4H base grid
        # 4H indicators
        self.base["ma"] = _sma(self.base["close"], p.ma_len)
        self.base["vsma"] = _sma(self.base["volume"], p.vol_sma_len)
        self.base["prev_vol"] = self.base["volume"].shift(1)
        self.base["reg"] = self.base["close"] < self.base["ma"]

        # Resample to HTFs
        D = _resample(self.base, "1D")
        W = _resample(self.base, "1W")
        M = _resample(self.base, "1M")
        for tdf in (D, W, M):
            tdf["ma"] = _sma(tdf["close"], p.ma_len)
            tdf["vsma"] = _sma(tdf["volume"], p.vol_sma_len)
            tdf["prev_vol"] = tdf["volume"].shift(1)
            tdf["reg"] = tdf["close"] < tdf["ma"]

        # forward-fill fields to 4H grid + TF-close flags
        self.tf = {
            "4H": {
                "df": self.base[["open","high","low","close","volume"]],
                "ma": self.base["ma"], "vsma": self.base["vsma"],
                "prev_vol": self.base["prev_vol"], "reg": self.base["reg"],
                "closed": pd.Series(True, index=self.base.index),
            },
            "D":  self._pack_tf(D),
            "W":  self._pack_tf(W),
            "M":  self._pack_tf(M),
        }

        # per-TF window state
        self.win_on = {k: False for k in self.tf}
        self.ents = {k: 0 for k in self.tf}  # entries used in current window
        self.prev_reg = {k: False for k in self.tf}

        # ECR & positions
        self.ecr_low: Optional[float] = None
        self.ecr_high: Optional[float] = None
        self.open_entries: List[Dict] = []     # [{ts, px, tf}]
        self.trades: List[Dict] = []           # per-entry closed trades

    def _pack_tf(self, tdf: pd.DataFrame) -> Dict[str, pd.Series | pd.DataFrame]:
        f = {
            "df": tdf[["open","high","low","close","volume"]],
            "ma": tdf["ma"],
            "vsma": tdf["vsma"],
            "prev_vol": tdf["prev_vol"],
            "reg": tdf["reg"],
            "closed": _align_close_flags(self.base.index, tdf.index),
        }
        # forward-fill series onto base grid
        for k in ("ma","vsma","prev_vol","reg"):
            f[k] = f[k].reindex(self.base.index, method="ffill")
        return f

    # ---- helpers ----
    def _update_windows(self, t: pd.Timestamp, i: int):
        for tf in ("4H","D","W","M"):
            closed = bool(self.tf[tf]["closed"].iat[i])
            if not closed:
                continue
            reg_now = bool(self.tf[tf]["reg"].iat[i])
            if reg_now and not self.prev_reg[tf]:
                self.win_on[tf] = True
                self.ents[tf] = 0
            elif (not reg_now) and self.win_on[tf]:
                self.win_on[tf] = False
            self.prev_reg[tf] = reg_now

    def _active_tf(self, i: int) -> Optional[str]:
        return _choose_active(bool(self.tf["4H"]["reg"].iat[i]),
                              bool(self.tf["D"]["reg"].iat[i]),
                              bool(self.tf["W"]["reg"].iat[i]),
                              bool(self.tf["M"]["reg"].iat[i]))

    def _valid_buy_on(self, tf: str, t: pd.Timestamp, i: int) -> Tuple[bool, float, float, float]:
        # (valid?, close_px, tf_low, tf_high)
        if tf == "4H":
            close_px = float(self.base["close"].iat[i])
            open_px  = float(self.base["open"].iat[i])
            vol      = float(self.base["volume"].iat[i])
            vsma     = float(self.tf["4H"]["vsma"].iat[i])
            vprev    = float(self.tf["4H"]["prev_vol"].iat[i])
            lo       = float(self.base["low"].iat[i]); hi = float(self.base["high"].iat[i])
        else:
            # must be exact TF close at t
            if not bool(self.tf[tf]["closed"].iat[i]):
                return (False, np.nan, np.nan, np.nan)
            if t not in self.tf[tf]["df"].index:
                return (False, np.nan, np.nan, np.nan)
            row = self.tf[tf]["df"].loc[t]
            close_px, open_px, lo, hi = float(row["close"]), float(row["open"]), float(row["low"]), float(row["high"])
            vsma = float(self.tf[tf]["vsma"].iat[i])
            # previous TF vol (aligned by TF index)
            tf_idx = self.tf[tf]["df"].index.get_loc(t)
            if tf_idx == 0:
                return (False, np.nan, np.nan, np.nan)
            vprev = float(self.tf[tf]["df"]["volume"].iloc[tf_idx-1])
            vol   = float(row["volume"])

        is_red = close_px < (open_px - self.p.tol)
        hv_sma = vol > (vsma + self.p.tol) if not np.isnan(vsma) else False
        hv_prev= vol > (vprev + self.p.tol) if not np.isnan(vprev) else False
        valid  = is_red and hv_sma and hv_prev
        return (valid, close_px, lo, hi)

    def _try_exit(self, i: int, t: pd.Timestamp):
        if not self.open_entries:
            return
        close_px = float(self.base["close"].iat[i])
        avg_entry = float(np.mean([e["px"] for e in self.open_entries]))
        need_pts = self.p.target_per_entry * len(self.open_entries)
        if (close_px - avg_entry) >= (need_pts - self.p.tol):
            # EXIT ALL — emit per-entry trade rows
            for e in self.open_entries:
                self.trades.append({
                    "side": "BUY",
                    "tf": e["tf"],
                    "entry_ts": e["ts"],
                    "entry_px": e["px"],
                    "exit_ts": t,
                    "exit_px": close_px,
                    "status": "tp",
                    "pnl": close_px - float(e["px"]),
                })
            self.open_entries = []
            self.ecr_low = self.ecr_high = None

    # ---- main run ----
    def run(self) -> List[Dict]:
        idx = self.base.index
        for i, t in enumerate(idx):
            # 1) windows update at TF closes
            self._update_windows(t, i)

            # 2) target-only exit (4H close)
            self._try_exit(i, t)

            # 3) select active TF; require that TF bar CLOSED now (for HTFs)
            active = self._active_tf(i)
            if active is None:
                continue
            if active != "4H" and not bool(self.tf[active]["closed"].iat[i]):
                continue
            if not self.win_on.get(active, False):
                continue
            if self.ents[active] >= self.p.max_entries_per_window:
                continue

            # 4) validate BUY on active TF
            ok, close_px, tf_low, tf_high = self._valid_buy_on(active, t, i)
            if not ok:
                continue

            # 5) ECR 10% re-entry gate
            if (self.ecr_low is not None) and (self.ecr_high is not None):
                R = max(0.0, self.ecr_high - self.ecr_low)
                if R > self.p.tol:
                    cur_low = float(self.base["low"].iat[i]); cur_high = float(self.base["high"].iat[i])
                    ov = _overlap_len(self.ecr_low, self.ecr_high, cur_low, cur_high)
                    if ov > (R * (self.p.ecr_overlap_pct / 100.0) + self.p.tol):
                        continue

            # 6) take entry @ base close price; set ECR from ACTIVE TF candle
            self.open_entries.append({"ts": t, "px": close_px, "tf": active})
            self.ents[active] += 1
            self.ecr_low, self.ecr_high = float(tf_low), float(tf_high)

        # no forced exit at end (spec)
        return self.trades


# ---------- public API ----------
def generate_trades(df4h: pd.DataFrame, params: Dict | Params) -> List[Dict]:
    p = Params(**params) if isinstance(params, dict) else params
    eng = AutoShiftBuy(df4h, p)
    return eng.run()

def to_target_json(trades: List[Dict]) -> Dict:
    return {"version": 1, "trades": trades}

def run_from_csv(csv_path: str, params: Dict | Params) -> Dict:
    df = pd.read_csv(csv_path)
    # normalize expected columns to project format
    if "ts" not in df.columns and "timestamp" in df.columns:
        df = df.rename(columns={"timestamp":"ts"})
    trades = generate_trades(df, params)
    return to_target_json(trades)


if __name__ == "__main__":
    import sys, json
    if len(sys.argv) < 3:
        print("Usage: python strategies/auto_shift_buy.py <csv_4h_path> '<params_json>'")
        sys.exit(1)
    csv_path = sys.argv[1]
    params = json.loads(sys.argv[2])
    out = run_from_csv(csv_path, params)
    # preview
    import json as _json
    print(_json.dumps(out)[:2000])

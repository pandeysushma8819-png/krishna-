# strategies/auto_shift_buy.py
# Krishna Trade Worker (v3) — Auto-Shift BUY System plugin
# BUY-only, target-only exit, auto-shift 4H→D→W→M (highest active TF wins),
# RED + High-Volume entry, ECR 10% re-entry gate, per-window quota ≤ 4,
# pyramiding cap ≤ 4, bar-close-only evaluation, no SL (target-only).

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Dict, Optional
import numpy as np
import pandas as pd


@dataclass
class Params:
    target_per_entry: float = 1000.0   # Target points per open entry
    ma_len: int = 50                   # MA50 for all TFs
    vol_sma_len: int = 20              # Vol SMA for HV check
    overlap_pct: float = 10.0          # ECR re-entry overlap max (% of prior ECR range)
    pyramiding_cap: int = 4            # Max total open entries
    tol: float = 1e-6                  # Tiny tolerance for comparisons


TF_RULE = {
    "4H": "4H",
    "D" : "1D",
    "W" : "1W",
    "M" : "1M",
}


def _as_dt_index(df: pd.DataFrame) -> pd.DataFrame:
    if "ts" not in df.columns:
        raise ValueError("Input DataFrame must have column 'ts'")
    req = ["open", "high", "low", "close", "volume"]
    for c in req:
        if c not in df.columns:
            raise ValueError(f"Missing required column: {c}")
    df = df.copy()
    if not np.issubdtype(df["ts"].dtype, np.datetime64):
        df["ts"] = pd.to_datetime(df["ts"], utc=True, errors="coerce")
    return df.set_index("ts").sort_index()


def _resample(df15: pd.DataFrame, rule: str, ma_len: int, vol_len: int) -> pd.DataFrame:
    # Standard OHLCV resample with volume sum, then MA50 & VolSMA
    agg = {"open": "first", "high": "max", "low": "min", "close": "last", "volume": "sum"}
    out = df15.resample(rule).agg(agg).dropna(how="any")
    out["ma"] = out["close"].rolling(ma_len, min_periods=ma_len).mean()
    out["vsma"] = out["volume"].rolling(vol_len, min_periods=vol_len).mean()
    out["prev_vol"] = out["volume"].shift(1)
    # Strict discount regime: close < MA (equal = OFF)
    out["reg_on"] = out["close"] < out["ma"]
    return out


def _ffill_to_15m(tf_df: pd.DataFrame, idx15: pd.DatetimeIndex, col: str) -> pd.Series:
    return tf_df[col].reindex(idx15, method="ffill")


def _flags_tf_closed(idx15: pd.DatetimeIndex, tf_idx: pd.DatetimeIndex) -> pd.Series:
    """True on 15m bars that coincide with TF close."""
    flag = pd.Series(False, index=idx15)
    common = idx15.intersection(tf_idx)
    if len(common):
        flag.loc[common] = True
    return flag


def _choose_active(reg4h: bool, regD: bool, regW: bool, regM: bool) -> Optional[str]:
    # Highest TF takes priority: M > W > D > 4H
    if regM: return "M"
    if regW: return "W"
    if regD: return "D"
    if reg4h: return "4H"
    return None


def _overlap_len(low1: float, high1: float, low2: float, high2: float) -> float:
    intr_low = max(low1, low2)
    intr_high = min(high1, high2)
    return max(0.0, intr_high - intr_low)


def generate_trades(df15: pd.DataFrame, params: Dict | Params) -> List[Dict]:
    """
    Input df15: 15m OHLCV with columns [ts, open, high, low, close, volume]
    Returns: list of closed trades with entry/exit details.
    """
    p = Params(**params) if isinstance(params, dict) else params
    if df15.empty:
        return []

    base = _as_dt_index(df15)

    # Build TF resamples
    tf_frames = {tf: _resample(base, TF_RULE[tf], p.ma_len, p.vol_sma_len) for tf in TF_RULE}

    # Forward-fill regimes to 15m timeline
    reg_ff = {tf: _ffill_to_15m(tf_frames[tf], base.index, "reg_on").fillna(False) for tf in TF_RULE}
    # Mark TF close instants on 15m grid
    tf_closed = {tf: _flags_tf_closed(base.index, tf_frames[tf].index) for tf in TF_RULE}

    # Precompute forward-filled fields (open/high/low/close/volume/vsma/prev_vol/ma/reg_on)
    ffields: Dict[str, Dict[str, pd.Series]] = {}
    for tf, fr in tf_frames.items():
        fields = {}
        for col in ["open", "high", "low", "close", "volume", "vsma", "prev_vol", "ma", "reg_on"]:
            fields[col] = fr[col].reindex(base.index, method="ffill")
        ffields[tf] = fields

    # Per-TF windows & entry counters
    win_on = {tf: False for tf in TF_RULE}   # ON between OFF→ON and ON→OFF
    ents = {tf: 0 for tf in TF_RULE}         # entries taken in current window
    prev_reg = {tf: False for tf in TF_RULE} # to detect transitions at TF closes

    # ECR (Entry Candle Range) from last entry candle (active TF)
    ecr_low: Optional[float] = None
    ecr_high: Optional[float] = None

    # Positions and trade log
    open_entries: List[Dict] = []  # [{ "ts": ts, "px": price, "tf": tf }]
    trades: List[Dict] = []        # closed trades on EXIT ALL

    closes = base["close"].values
    idx = base.index

    for i, ts in enumerate(idx):
        # Update windows at TF closes only
        for tf in ("4H", "D", "W", "M"):
            if tf_closed[tf].iat[i]:
                reg_now = bool(ffields[tf]["reg_on"].iat[i])
                if reg_now and not prev_reg[tf]:
                    # OFF -> ON
                    win_on[tf] = True
                    ents[tf] = 0
                elif (not reg_now) and prev_reg[tf]:
                    # ON -> OFF
                    win_on[tf] = False
                prev_reg[tf] = reg_now

        # Exit check: target-only on every 15m close
        if open_entries:
            avg_entry = float(np.mean([e["px"] for e in open_entries]))
            need_pts = p.target_per_entry * len(open_entries)
            unreal = float(closes[i] - avg_entry)
            if unreal >= (need_pts - p.tol):
                # EXIT ALL at 15m close
                exit_px = float(closes[i])
                for e in open_entries:
                    trades.append({
                        "side": "BUY",
                        "entry_ts": e["ts"],
                        "entry_px": e["px"],
                        "exit_ts": ts,
                        "exit_px": exit_px,
                        "status": "tp",
                        "reason": f"target_hit_{need_pts:.1f}",
                        "tf": e["tf"],
                        "pnl": exit_px - float(e["px"]),
                    })
                open_entries = []
                ecr_low = ecr_high = None
                # After exit, do not enter again on the same bar
                continue

        # Choose active TF (highest priority)
        active = _choose_active(bool(reg_ff["4H"].iat[i]),
                                bool(reg_ff["D"].iat[i]),
                                bool(reg_ff["W"].iat[i]),
                                bool(reg_ff["M"].iat[i]))
        # Entry only if an active TF exists and that TF bar has just CLOSED
        if active is None or not tf_closed[active].iat[i]:
            continue

        # Active TF OHLCV (forward-filled to this ts)
        f = ffields[active]
        act_open = float(f["open"].iat[i])
        act_high = float(f["high"].iat[i])
        act_low  = float(f["low"].iat[i])
        act_close= float(f["close"].iat[i])
        act_vol  = float(f["volume"].iat[i])
        act_vsma = float(f["vsma"].iat[i]) if not np.isnan(f["vsma"].iat[i]) else np.nan
        act_prev = float(f["prev_vol"].iat[i]) if not np.isnan(f["prev_vol"].iat[i]) else np.nan

        # Valid BUY candle: RED + High-Volume (Vol > SMA20 and > prev)
        is_red = act_close < (act_open - p.tol)
        hv_sma = (not np.isnan(act_vsma)) and (act_vol > (act_vsma + p.tol))
        hv_prev = (not np.isnan(act_prev)) and (act_vol > (act_prev + p.tol))
        valid = is_red and hv_sma and hv_prev

        # Quotas & caps
        if not win_on.get(active, False):
            continue
        if ents[active] >= 4:
            continue
        if len(open_entries) >= p.pyramiding_cap:
            continue

        # ECR 10% overlap re-entry gate
        ecr_ok = True
        if ecr_low is not None and ecr_high is not None:
            ecr_range = max(0.0, ecr_high - ecr_low)
            if ecr_range > p.tol:
                intr = _overlap_len(ecr_low, ecr_high, act_low, act_high)
                ecr_ok = intr <= (ecr_range * (p.overlap_pct / 100.0) + p.tol)
            else:
                ecr_ok = True  # degenerate prior ECR; allow refresh

        # Take entry at active TF close
        if valid and ecr_ok:
            open_entries.append({"ts": ts, "px": act_close, "tf": active})
            ents[active] += 1
            # Reset ECR from current entry candle
            ecr_low = act_low
            ecr_high = act_high

    # Spec: no forced exit at end; open entries can remain open
    return trades


def to_target_json(trades: List[Dict]) -> Dict:
    return {"version": 1, "trades": trades}


def run_from_csv(csv_path: str, params: Dict | Params) -> Dict:
    df = pd.read_csv(csv_path)
    trades = generate_trades(df, params)
    return to_target_json(trades)


if __name__ == "__main__":
    import sys, json
    if len(sys.argv) < 3:
        print("Usage: python strategies/auto_shift_buy.py <csv_15m_path> '<params_json>'")
        sys.exit(1)
    csv_path = sys.argv[1]
    params = json.loads(sys.argv[2])
    print(json.dumps(run_from_csv(csv_path, params))[:2000])

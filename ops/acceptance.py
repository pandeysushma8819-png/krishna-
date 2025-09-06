# ops/acceptance.py
from __future__ import annotations
from typing import Dict, Any, List, Tuple
import os, json, time, math, statistics
import gspread
from google.oauth2.service_account import Credentials

def _now_utc() -> int: return int(time.time())
def _ist_to_utc(ts_utc: int) -> int: return ts_utc  # windowing is UTC-based here
def _from_env_f(name: str, default: float) -> float:
    try: return float(os.environ.get(name, default))
    except Exception: return float(default)

def _gc():
    info = os.environ.get("GOOGLE_SA_JSON", "").strip()
    if not info: raise RuntimeError("GOOGLE_SA_JSON missing")
    creds = Credentials.from_service_account_info(
        json.loads(info),
        scopes=[
            "https://www.googleapis.com/auth/spreadsheets",
            "https://www.googleapis.com/auth/drive",
        ],
    )
    return gspread.authorize(creds)

def _open_ss(gc):
    sid = os.environ.get("GSHEET_SPREADSHEET_ID", "").strip()
    if not sid: raise RuntimeError("GSHEET_SPREADSHEET_ID missing")
    return gc.open_by_key(sid)

def _read_trades_window(days: int) -> List[Dict[str, Any]]:
    gc = _gc(); ss = _open_ss(gc)
    try:
        ws = ss.worksheet("Trades")
    except Exception:
        return []
    vals = ws.get_all_values()
    if not vals: return []
    hdr = [h.strip().lower() for h in vals[0]]
    rows = []
    now = _now_utc()
    since = now - days*86400
    # Expected headers: ts, symbol, side, qty, price, pnl, fees, slippage, strategy_id ...
    for r in vals[1:]:
        rec = {hdr[i]: r[i] if i < len(r) else "" for i in range(len(hdr))}
        try:
            ts = int(float(rec.get("ts","0")) or 0)
        except Exception:
            ts = 0
        if ts < since:  # window filter
            continue
        try:
            pnl = float(rec.get("pnl","0") or 0)
        except Exception:
            pnl = 0.0
        rows.append({
            "ts": ts,
            "symbol": rec.get("symbol",""),
            "side": rec.get("side",""),
            "qty": float(rec.get("qty","0") or 0),
            "price": float(rec.get("price","0") or 0),
            "pnl": pnl,
            "fees": float(rec.get("fees","0") or 0),
            "slippage": float(rec.get("slippage","0") or 0),
            "strategy_id": rec.get("strategy_id",""),
        })
    rows.sort(key=lambda x: x["ts"])
    return rows

def _equity_curve(trades: List[Dict[str,Any]], initial: float) -> List[Tuple[int, float]]:
    eq = initial
    curve = []
    for t in trades:
        eq += t["pnl"]
        curve.append((t["ts"], eq))
    return curve

def _max_dd_pct(curve: List[Tuple[int,float]]) -> float:
    if not curve: return 0.0
    peak = curve[0][1]; mdd = 0.0
    for _, v in curve:
        peak = max(peak, v)
        dd = 0.0 if peak <= 0 else (peak - v) / peak
        if dd > mdd: mdd = dd
    return round(mdd*100, 2)

def compute_kpis(period: str="daily") -> Dict[str, Any]:
    days = 1 if period=="daily" else 7
    init_equity = _from_env_f("INITIAL_EQUITY", 1_000_000.0)
    trades = _read_trades_window(days)
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] < 0]
    sum_win = sum(t["pnl"] for t in wins)
    sum_loss_abs = abs(sum(t["pnl"] for t in losses))
    trades_n = len(trades)
    win_rate = (len(wins)/trades_n*100.0) if trades_n else 0.0
    pf = (sum_win / sum_loss_abs) if sum_loss_abs > 0 else (float("inf") if sum_win>0 else 0.0)
    curve = _equity_curve(trades, init_equity)
    mdd_pct = _max_dd_pct(curve)
    ret_pct = ((curve[-1][1]-init_equity)/init_equity*100.0) if curve else 0.0
    return {
        "period": period,
        "stats": {
            "trades": trades_n,
            "wins": len(wins),
            "losses": len(losses),
            "ret_pct": round(ret_pct, 2),
            "mdd_pct": mdd_pct,
            "win_rate_pct": round(win_rate, 2),
            "profit_factor": (round(pf,3) if math.isfinite(pf) else "inf"),
            "final_equity": (curve[-1][1] if curve else init_equity)
        }
    }

def acceptance_check(period: str="daily") -> Dict[str, Any]:
    k = compute_kpis(period)
    # Thresholds (tweak via env)
    wr_min = _from_env_f("ACCEPT_WIN_RATE_MIN", 45.0)      # %
    pf_min = _from_env_f("ACCEPT_PF_MIN", 1.2)
    dd_max = _from_env_f("ACCEPT_MAXDD_MAX", 10.0)         # % (absolute)
    s = k["stats"]
    pass_wr = s["win_rate_pct"] >= wr_min
    pass_pf = (s["profit_factor"]=="inf") or (float(s["profit_factor"]) >= pf_min)
    pass_dd = s["mdd_pct"] <= dd_max
    ok = bool(pass_wr and pass_pf and pass_dd)
    return {
        "ok": ok,
        "period": period,
        "thresholds": {"win_rate_min": wr_min, "pf_min": pf_min, "maxdd_max": dd_max},
        "stats": s,
        "checks": {"win_rate": pass_wr, "profit_factor": pass_pf, "maxdd": pass_dd}
    }

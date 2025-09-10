# ops/acceptance.py
from __future__ import annotations

import os
import time
import math
from dataclasses import dataclass
from typing import Any, Dict, List, Tuple, Optional

# ---- Config ----

START_EQUITY = float(os.getenv("REPORT_START_EQUITY", "1000000"))  # same base as reports

# Threshold envs (defaults mirror earlier behavior)
DEF_WIN_RATE_MIN = float(os.getenv("ACCEPT_WIN_RATE_MIN", "45"))
DEF_PF_MIN = float(os.getenv("ACCEPT_PF_MIN", "1.2"))
DEF_MAXDD_MAX = float(os.getenv("ACCEPT_MAXDD_MAX", "10"))

DEF_MIN_TRADES_DAILY = int(os.getenv("ACCEPT_MIN_TRADES_DAILY", "12"))
DEF_MIN_TRADES_WEEKLY = int(os.getenv("ACCEPT_MIN_TRADES_WEEKLY", "40"))

APP_BASE_URL = os.getenv("APP_BASE_URL", "").rstrip("/")


# ---- Helpers ----

def _window(period: str) -> Tuple[int, int]:
    now = int(time.time())
    if period == "weekly":
        return now - 7 * 86400, now
    # default: daily (last 24h)
    return now - 86400, now


def _safe_float(x: Any, default: float = 0.0) -> float:
    try:
        if isinstance(x, str) and x.strip() == "":
            return default
        return float(x)
    except Exception:
        return default


def _pf_ok(pf_value: Any, pf_min: float) -> bool:
    """
    pf_value could be 'inf' (string) or a float.
    """
    if pf_value == "inf" or pf_value == float("inf"):
        return True
    return _safe_float(pf_value) >= pf_min


def _max_drawdown_pct(equity: List[float]) -> float:
    """Percent max drawdown from an equity curve list."""
    if not equity:
        return 0.0
    peak = equity[0]
    max_dd = 0.0
    for v in equity:
        peak = max(peak, v)
        dd = (peak - v) / peak if peak > 0 else 0.0
        max_dd = max(max_dd, dd)
    return round(max_dd * 100.0, 2)


# ---- Data sources: prefer Sheets; fallback to /report/{period} if available ----

def _load_trades_from_sheets(from_ts: int, to_ts: int) -> List[Dict[str, Any]]:
    """
    Read 'Trades' tab using service account envs.
    Expected headers include: ts, pnl, fees, slippage, symbol, side, qty, price, strategy_id
    """
    # Lazy import to avoid hard dep if not installed
    import json
    import gspread
    from google.oauth2.service_account import Credentials

    sa_json = os.getenv("GOOGLE_SA_JSON", "")
    sheet_id = os.getenv("GSHEET_SPREADSHEET_ID", "")
    if not sa_json or not sheet_id:
        return []

    info = json.loads(sa_json)
    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    creds = Credentials.from_service_account_info(info, scopes=scopes)
    gc = gspread.authorize(creds)
    ss = gc.open_by_key(sheet_id)
    try:
        ws = ss.worksheet("Trades")
    except Exception:
        return []

    rows = ws.get_all_records(head=1)  # list of dicts
    out: List[Dict[str, Any]] = []
    for r in rows:
        ts = int(_safe_float(r.get("ts", 0), 0))
        if ts < from_ts or ts > to_ts:
            continue
        out.append(r)
    return out


def _stats_from_trades(trades: List[Dict[str, Any]]) -> Dict[str, Any]:
    """
    Build stats compatible with /report outputs.
    """
    equity = START_EQUITY
    eq_curve = [equity]

    pos_sum = 0.0
    neg_sum = 0.0
    wins = 0
    losses = 0

    for t in trades:
        pnl = _safe_float(t.get("pnl", 0.0), 0.0)
        fees = _safe_float(t.get("fees", 0.0), 0.0)
        slip = _safe_float(t.get("slippage", 0.0), 0.0)
        net = pnl - fees - slip
        equity += net
        eq_curve.append(equity)
        if net > 0:
            wins += 1
            pos_sum += net
        elif net < 0:
            losses += 1
            neg_sum += -net

    trades_n = len(trades)
    win_rate = round((wins / trades_n) * 100.0, 2) if trades_n > 0 else 0.0
    if neg_sum == 0 and pos_sum > 0:
        pf: Any = "inf"
    else:
        pf = round(pos_sum / neg_sum, 3) if neg_sum > 0 else 0.0

    ret_pct = round(((equity - START_EQUITY) / START_EQUITY) * 100.0, 2)
    mdd_pct = _max_drawdown_pct(eq_curve)

    return {
        "trades": trades_n,
        "wins": wins,
        "losses": losses,
        "ret_pct": ret_pct,
        "mdd_pct": mdd_pct,
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": pf,
        "final_equity": round(equity, 2),
    }


def _stats_via_http(period: str) -> Optional[Dict[str, Any]]:
    """
    Fallback path: call /report/{period} if APP_BASE_URL is set and reachable.
    """
    if not APP_BASE_URL:
        return None
    import json
    import urllib.request

    url = f"{APP_BASE_URL}/report/{period}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read().decode("utf-8"))
        if not data.get("ok"):
            return None
        return data.get("stats")
    except Exception:
        return None


# ---- Public API ----

def acceptance_check(period: str = "daily") -> Dict[str, Any]:
    """
    Compute acceptance & gates:
      - win_rate >= ACCEPT_WIN_RATE_MIN
      - profit_factor >= ACCEPT_PF_MIN  (or inf => pass)
      - mdd_pct <= ACCEPT_MAXDD_MAX
      - trades >= ACCEPT_MIN_TRADES_{DAILY|WEEKLY}
    """
    period = "weekly" if period.lower().startswith("week") else "daily"
    frm, to = _window(period)

    # Try Sheets first
    stats: Optional[Dict[str, Any]] = None
    try:
        trades = _load_trades_from_sheets(frm, to)
        stats = _stats_from_trades(trades)
    except Exception:
        stats = None

    # Fallback: HTTP /report endpoint
    if stats is None:
        stats = _stats_via_http(period) or {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "ret_pct": 0.0,
            "mdd_pct": 0.0,
            "win_rate_pct": 0.0,
            "profit_factor": 0.0,
            "final_equity": START_EQUITY,
        }

    # Thresholds
    win_rate_min = DEF_WIN_RATE_MIN
    pf_min = DEF_PF_MIN
    maxdd_max = DEF_MAXDD_MAX
    min_trades = DEF_MIN_TRADES_WEEKLY if period == "weekly" else DEF_MIN_TRADES_DAILY

    # Checks
    checks = {
        "win_rate": _safe_float(stats.get("win_rate_pct", 0.0)) >= win_rate_min,
        "profit_factor": _pf_ok(stats.get("profit_factor"), pf_min),
        "maxdd": _safe_float(stats.get("mdd_pct", 100.0)) <= maxdd_max,
        "min_trades": int(_safe_float(stats.get("trades", 0))) >= min_trades,
    }
    ok = all(checks.values())

    thresholds = {
        "win_rate_min": win_rate_min,
        "pf_min": pf_min,
        "maxdd_max": maxdd_max,
        "min_trades": min_trades,
    }

    return {"ok": ok, "period": period, "thresholds": thresholds, "stats": stats, "checks": checks}

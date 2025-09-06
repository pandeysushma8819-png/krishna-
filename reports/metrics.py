# reports/metrics.py
from __future__ import annotations
from typing import List, Dict, Tuple
import math, time

def _to_float(x) -> float:
    try: return float(x)
    except Exception: return 0.0

def _to_int(x) -> int:
    try: return int(x)
    except Exception: return 0

def pick_window(trades: List[Dict], ts_from: int, ts_to: int) -> List[Dict]:
    out = []
    for t in trades:
        ts = _to_int(t.get("ts") or t.get("timestamp") or t.get("time") or 0)
        if ts_from <= ts <= ts_to:
            out.append(t | {"ts": ts})
    return sorted(out, key=lambda r: r["ts"])

def equity_curve(trades: List[Dict], start_equity: float = 1_000_000.0) -> Tuple[List[Tuple[int, float]], Dict[str, float]]:
    """
    trades records should contain pnl (profit minus loss). fees/slip optional.
    """
    eq = start_equity
    peak = eq
    curve: List[Tuple[int, float]] = []
    wins = losses = 0
    gross_win = gross_loss = 0.0

    for t in trades:
        ts = _to_int(t.get("ts") or 0)
        pnl = _to_float(t.get("pnl") or t.get("pl") or 0.0)
        fees = _to_float(t.get("fees") or 0.0)
        slip = _to_float(t.get("slippage") or 0.0)
        net = pnl - fees - slip
        eq += net
        peak = max(peak, eq)
        dd = (peak - eq) / peak if peak > 0 else 0.0
        curve.append((ts, round(eq, 2)))
        if net > 0:
            wins += 1; gross_win += net
        elif net < 0:
            losses += 1; gross_loss += -net

    trades_n = wins + losses
    win_rate = (wins / trades_n * 100.0) if trades_n > 0 else 0.0
    profit_factor = (gross_win / gross_loss) if gross_loss > 1e-9 else (gross_win > 0 and float("inf") or 0.0)
    ret_pct = ((eq - start_equity) / start_equity * 100.0) if start_equity > 0 else 0.0
    # compute MDD from curve:
    mdd = 0.0
    if curve:
        p = curve[0][1]
        for _, v in curve:
            p = max(p, v)
            mdd = max(mdd, (p - v) / p if p > 0 else 0.0)

    stats = {
        "trades": trades_n,
        "wins": wins,
        "losses": losses,
        "win_rate_pct": round(win_rate, 2),
        "profit_factor": (round(profit_factor, 3) if math.isfinite(profit_factor) else "inf"),
        "ret_pct": round(ret_pct, 2),
        "mdd_pct": round(mdd * 100.0, 2),
        "final_equity": round(eq, 2),
    }
    return curve, stats

def group_pnl_by(trades: List[Dict], key: str) -> List[Tuple[str, float]]:
    agg: Dict[str, float] = {}
    for t in trades:
        k = str(t.get(key) or "")
        pnl = _to_float(t.get("pnl") or t.get("pl") or 0.0)
        fees = _to_float(t.get("fees") or 0.0)
        slip = _to_float(t.get("slippage") or 0.0)
        agg[k] = agg.get(k, 0.0) + (pnl - fees - slip)
    items = [(k, v) for k, v in agg.items()]
    items.sort(key=lambda kv: kv[1], reverse=True)
    return items

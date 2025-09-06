# routes/report.py
from __future__ import annotations
from typing import Any, Dict, List, Tuple
import time, json
from flask import Blueprint, request, jsonify

from reports.io import connect_spreadsheet, get_ws
from reports.metrics import pick_window, equity_curve, group_pnl_by

report_bp = Blueprint("report", __name__)

def _ist_now() -> int:
    return int(time.time() + 19800)  # UTC + 5:30

def _win(period: str) -> Tuple[int, int, str]:
    """
    Returns (ts_from, ts_to, label) in UTC epoch seconds
    """
    now_utc = int(time.time())
    if period == "weekly":
        span = 7 * 24 * 3600
        label = "weekly"
    else:
        span = 24 * 3600
        label = "daily"
    return now_utc - span, now_utc, label

def _sheet_url(sheet_id: str) -> str:
    return f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit"

def _load_trades(ss, ts_from: int, ts_to: int) -> List[Dict]:
    # prefer "Trades" sheet if exists; else empty list
    ws = get_ws(ss, "Trades")
    if not ws:
        return []
    try:
        rows = ws.get_all_records()  # list[dict]
        # expect headers: ts, ist, symbol, side, qty, price, pnl, fees, slippage, strategy_id
        trades = pick_window(rows, ts_from, ts_to)
        return trades
    except Exception:
        return []

def _snapshot_to_sheets(title: str, obj: Dict[str, Any]) -> bool:
    try:
        from integrations.sheets import append_snapshot
        return append_snapshot(title, obj)
    except Exception:
        return False

@report_bp.get("/report/ping")
def ping() -> Any:
    return jsonify(ok=True, msg="report alive")

@report_bp.get("/report")
@report_bp.get("/report/<period>")
def report(period: str | None = None) -> Any:
    period = (period or request.args.get("period") or "daily").lower()
    if period not in ("daily", "weekly"):
        return jsonify(ok=False, error="period must be daily|weekly"), 400

    ts_from, ts_to, label = _win(period)
    ss, sheet_id, err = connect_spreadsheet()
    if err:
        return jsonify(ok=False, error=f"sheets: {err}"), 500

    trades = _load_trades(ss, ts_from, ts_to)
    start_equity = 1_000_000.0

    curve, stats = equity_curve(trades, start_equity=start_equity)
    top_syms = group_pnl_by(trades, "symbol")[:5]
    worst_syms = group_pnl_by(trades, "symbol")[-5:]
    top_syms = [(k, round(v,2)) for k,v in top_syms]
    worst_syms = [(k, round(v,2)) for k,v in worst_syms]

    top_strat = group_pnl_by(trades, "strategy_id")[:5]
    worst_strat = group_pnl_by(trades, "strategy_id")[-5:]
    top_strat = [(k, round(v,2)) for k,v in top_strat]
    worst_strat = [(k, round(v,2)) for k,v in worst_strat]

    payload = {
        "ok": True,
        "period": label,
        "window_utc": {"from": ts_from, "to": ts_to},
        "window_ist": {
            "from": time.strftime("%Y-%m-%d %H:%M:%S IST", time.gmtime(ts_from + 19800)),
            "to": time.strftime("%Y-%m-%d %H:%M:%S IST", time.gmtime(ts_to + 19800)),
        },
        "stats": stats,
        "equity": curve,  # [ [ts,equity], ... ]
        "top": {"symbols": top_syms, "strategies": top_strat},
        "worst": {"symbols": worst_syms, "strategies": worst_strat},
        "sheet_url": _sheet_url(sheet_id or ""),
    }

    # Snapshot in Sheets for audit / dashboard references
    _snapshot_to_sheets(f"report-{label}-{int(time.time())}", payload)

    return jsonify(payload), 200

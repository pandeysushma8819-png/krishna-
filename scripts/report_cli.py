# scripts/report_cli.py
from __future__ import annotations
import argparse, json, time
from reports.io import connect_spreadsheet
from routes.report import _win, _load_trades
from reports.metrics import equity_curve, group_pnl_by

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", choices=["daily","weekly"], default="daily")
    ap.add_argument("--out", default="report_out.json")
    args = ap.parse_args()

    ts_from, ts_to, label = _win(args.period)
    ss, sheet_id, err = connect_spreadsheet()
    if err:
        raise SystemExit(f"sheets error: {err}")

    trades = _load_trades(ss, ts_from, ts_to)
    curve, stats = equity_curve(trades, start_equity=1_000_000.0)
    top_syms = group_pnl_by(trades, "symbol")[:5]
    worst_syms = group_pnl_by(trades, "symbol")[-5:]
    top_strat = group_pnl_by(trades, "strategy_id")[:5]
    worst_strat = group_pnl_by(trades, "strategy_id")[-5:]

    payload = {
        "period": label,
        "window_utc": {"from": ts_from, "to": ts_to},
        "window_ist": {
            "from": time.strftime("%Y-%m-%d %H:%M:%S IST", time.gmtime(ts_from + 19800)),
            "to": time.strftime("%Y-%m-%d %H:%M:%S IST", time.gmtime(ts_to + 19800)),
        },
        "stats": stats,
        "equity": curve,
        "top": {"symbols": top_syms, "strategies": top_strat},
        "worst": {"symbols": worst_syms, "strategies": worst_strat},
        "sheet_url": f"https://docs.google.com/spreadsheets/d/{sheet_id}/edit",
    }
    with open(args.out, "w") as f:
        json.dump(payload, f, indent=2)
    print(f"OK: wrote {args.out}")

if __name__ == "__main__":
    main()

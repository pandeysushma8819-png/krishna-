from __future__ import annotations
import json, argparse
from backtesting.engine import BacktestConfig, run_backtest
from data.cleaners import dedupe_bars, fill_missing_bars, clamp_spikes
from data.corporate_actions import apply_corporate_actions, CorporateAction

def main():
    ap = argparse.ArgumentParser("KTW Backtest CLI")
    ap.add_argument("--bars-json", required=True, help="Path to JSON list of OHLCV bars")
    ap.add_argument("--tf-sec", type=int, default=900)
    ap.add_argument("--target-json", required=True, help="Path to JSON dict {ts: -1|0|1}")
    ap.add_argument("--allow-short", action="store_true")
    ap.add_argument("--market", default="NSE")
    ap.add_argument("--product", default="equity_intraday")
    ap.add_argument("--plan", default="INDIA_DISCOUNT")
    ap.add_argument("--lot-size", type=int, default=1)
    ap.add_argument("--slip-bps", type=float, default=1.0)
    ap.add_argument("--spread-bps", type=float, default=0.0)
    args = ap.parse_args()

    with open(args.bars_json,"r") as f:
        bars = json.load(f)
    with open(args.target_json,"r") as f:
        target = {int(k): int(v) for k,v in json.load(f).items()}

    bars = dedupe_bars(bars)
    bars = fill_missing_bars(bars, tf_sec=args.tf_sec, method="ffill")
    bars = clamp_spikes(bars, max_pct=0.15)

    cfg = BacktestConfig(
        market=args.market, product=args.product, plan=args.plan,
        lot_size=args.lot_size, slippage_bps=args.slip_bps, spread_bps=args.spread_bps,
        allow_short=args.allow_short
    )

    res = run_backtest(bars, target, cfg)
    print(json.dumps({"stats": res.stats, "trades": [t.__dict__ for t in res.trades], "equity": res.equity}, indent=2))

if __name__ == "__main__":
    main()

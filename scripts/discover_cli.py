from __future__ import annotations
import json, argparse
from discovery.pipeline import discover_and_backtest

def main():
    ap = argparse.ArgumentParser("KTW Discovery CLI (P6)")
    ap.add_argument("--bars-json", required=True, help="Path to OHLCV JSON (list of bars)")
    ap.add_argument("--tf-sec", type=int, required=True, help="Cadence seconds (e.g., 900 for 15m)")
    ap.add_argument("--market", default="NSE")
    ap.add_argument("--product", default="equity_intraday")
    ap.add_argument("--lot-size", type=int, default=1)
    ap.add_argument("--slip-bps", type=float, default=1.5)
    ap.add_argument("--spread-bps", type=float, default=0.5)
    ap.add_argument("--candidates", type=int, default=20)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--window", default="")
    ap.add_argument("--out", default="discover_out.json")
    args = ap.parse_args()

    with open(args.bars_json, "r") as f:
        bars = json.load(f)

    res = discover_and_backtest(
        bars=bars,
        tf_sec=args.tf_sec,
        total=args.candidates,
        market=args.market,
        product=args.product,
        lot_size=args.lot_size,
        slip_bps=args.slip_bps,
        spread_bps=args.spread_bps,
        seed=args.seed,
        window=args.window
    )

    with open(args.out, "w") as f:
        json.dump(res, f, indent=2)

    print(f"OK: wrote {args.out}. Leader: {res.get('leader') and res['leader']['strategy_id']} {res.get('leader') and res['leader']['version']}")

if __name__ == "__main__":
    main()

# scripts/risk_cli.py
from __future__ import annotations
import json, argparse, time
from risk.position import quote_position, OpenPos, RiskConfig

def load_json(p: str):
    with open(p, "r") as f: return json.load(f)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--bars-json", required=True)
    ap.add_argument("--equity", type=float, default=1_000_000)
    ap.add_argument("--price", type=float, default=100.0)
    ap.add_argument("--side", type=str, default="buy")
    ap.add_argument("--risk-scale", type=float, default=1.0)
    ap.add_argument("--ref-price", type=float, default=None)
    ap.add_argument("--open-json", default=None, help="optional open positions json")
    args = ap.parse_args()

    bars = load_json(args.bars_json)
    open_positions = []
    if args.open_json:
        raw = load_json(args.open_json)
        for p in raw:
            open_positions.append(OpenPos(
                symbol=p["symbol"], side=p.get("side","buy"),
                qty=int(p.get("qty",0)), entry=float(p.get("entry",0.0)),
                sl=float(p.get("sl",0.0)), bars=p.get("bars")
            ))

    out = quote_position(
        symbol="DEMO", side=args.side, price=args.price, equity=args.equity,
        bars=bars, open_positions=open_positions, risk_scale=args.risk_scale,
        ref_price=args.ref_price, cfg=None
    )
    print(json.dumps(out, indent=2))

if __name__ == "__main__":
    main()

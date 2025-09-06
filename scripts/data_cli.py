# scripts/data_cli.py
from __future__ import annotations
import json, argparse
from data.router import get_bars

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--symbol", required=True)
    ap.add_argument("--tf-sec", type=int, default=900)
    ap.add_argument("--limit", type=int, default=200)
    ap.add_argument("--out", default="")
    args = ap.parse_args()
    bars = get_bars(args.symbol, args.tf_sec, args.limit)
    js = json.dumps(bars, indent=2)
    if args.out:
        open(args.out, "w", encoding="utf-8").write(js)
        print("OK:", args.out, len(bars))
    else:
        print(js)

if __name__ == "__main__":
    main()

# scripts/ops_cli.py
from __future__ import annotations
import argparse, json
from ops.acceptance import acceptance_check

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", choices=["daily","weekly"], default="daily")
    args = ap.parse_args()
    out = acceptance_check(args.period)
    print(json.dumps(out, indent=2))

if __name__ == "__main__":
    main()

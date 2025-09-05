from __future__ import annotations
import json, argparse, pathlib
from typing import Any, Dict, List
from learning.ga import run_ga, GAConfig
from learning.cem import run_cem, CEMConfig

def load_bars(path: str) -> List[dict]:
    return json.load(open(path, "r"))

def main():
    ap = argparse.ArgumentParser("KTW Learning Engine (P8)")
    ap.add_argument("--algo", choices=["ga","cem"], default="ga")
    ap.add_argument("--strategy", choices=["ema_cross","rsi_reversion"], default="ema_cross")
    ap.add_argument("--bars-json", required=True)
    ap.add_argument("--tf-sec", type=int, required=True)
    ap.add_argument("--market", default="NSE")
    ap.add_argument("--product", default="equity_intraday")
    ap.add_argument("--lot-size", type=int, default=1)
    ap.add_argument("--slip-bps", type=float, default=1.5)
    ap.add_argument("--spread-bps", type=float, default=0.5)
    # GA params
    ap.add_argument("--pop", type=int, default=20)
    ap.add_argument("--gens", type=int, default=10)
    ap.add_argument("--elites", type=int, default=4)
    ap.add_argument("--mut-prob", type=float, default=0.35)
    ap.add_argument("--seed", type=int, default=42)
    # CEM params
    ap.add_argument("--iters", type=int, default=10)
    ap.add_argument("--elite-frac", type=float, default=0.25)
    ap.add_argument("--out", default="learn_out.json")
    args = ap.parse_args()

    bars = load_bars(args.bars_json)

    if args.algo == "ga":
        cfg = GAConfig(pop_size=args.pop, elites=args.elites, gens=args.gens, mut_prob=args.mut_prob, seed=args.seed)
        res = run_ga(bars, args.tf_sec, args.strategy, args.market, args.product, args.lot_size, args.slip_bps, args.spread_bps, cfg)
    else:
        cfg = CEMConfig(iters=args.iters, pop=args.pop, elite_frac=args.elite_frac, seed=args.seed)
        res = run_cem(bars, args.tf_sec, args.strategy, args.market, args.product, args.lot_size, args.slip_bps, args.spread_bps, cfg)

    pathlib.Path(args.out).write_text(json.dumps(res, indent=2), encoding="utf-8")
    best = res.get("best")
    print(f"OK: {args.algo} best params: {best and best['params']} reward={best and best['reward']} -> wrote {args.out}")

if __name__ == "__main__":
    main()

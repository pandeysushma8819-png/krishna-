from __future__ import annotations
from typing import Dict, Any, List, Tuple
import random
from learning.search_space import random_params, mutate, crossover, clamp_params
from learning.evaluate import evaluate_params

class GAConfig:
    def __init__(self, pop_size=20, elites=4, gens=12, mut_prob=0.35, seed=42):
        self.pop_size=pop_size; self.elites=elites; self.gens=gens
        self.mut_prob=mut_prob; self.seed=seed

def run_ga(bars: List[dict], tf_sec: int, strategy_id: str,
           market="NSE", product="equity_intraday",
           lot_size=1, slip_bps=1.5, spread_bps=0.5,
           cfg: GAConfig = GAConfig()) -> Dict[str, Any]:
    rng = random.Random(cfg.seed)
    # init pop
    pop = [random_params(strategy_id, rng) for _ in range(cfg.pop_size)]
    hist = []
    best = None
    for g in range(cfg.gens):
        scored = []
        for p in pop:
            ev = evaluate_params(bars, tf_sec, strategy_id, p, market, product, lot_size, slip_bps, spread_bps)
            scored.append(ev)
        scored.sort(key=lambda e: e["reward"], reverse=True)
        best = scored[0] if (best is None or scored[0]["reward"] > best["reward"]) else best
        hist.append({"gen": g, "best_reward": scored[0]["reward"], "best_params": scored[0]["params"]})

        # next generation via elitism + crossover + mutation
        elites = [e["params"] for e in scored[:cfg.elites]]
        next_pop = elites[:]
        while len(next_pop) < cfg.pop_size:
            a, b = rng.sample(elites, 2) if len(elites)>=2 else (elites[0], elites[0])
            child = crossover(strategy_id, a, b, rng)
            if rng.random() < cfg.mut_prob:
                child = mutate(strategy_id, child, rng)
            next_pop.append(child)
        pop = [clamp_params(strategy_id, p) for p in next_pop]
    return {"algo": "ga", "strategy_id": strategy_id, "best": best, "history": hist}

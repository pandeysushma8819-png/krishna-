from __future__ import annotations
import random
from typing import Dict, Tuple

Bounds = Dict[str, Tuple[int, int]]

EMA_BOUNDS: Bounds = {"fast": (5, 40), "slow": (20, 100)}
RSI_BOUNDS: Bounds = {"period": (8, 30), "buy_th": (20, 40), "sell_th": (50, 80)}

def random_params(strategy_id: str, rng: random.Random) -> Dict[str, int | float]:
    sid = strategy_id.lower()
    if sid == "ema_cross":
        fmin,fmax = EMA_BOUNDS["fast"]
        smin,smax = EMA_BOUNDS["slow"]
        fast = rng.randint(fmin, fmax)
        slow = rng.randint(max(fast+1, smin), smax)
        return {"fast": fast, "slow": slow}
    if sid == "rsi_reversion":
        pmin,pmax = RSI_BOUNDS["period"]
        bmin,bmax = RSI_BOUNDS["buy_th"]
        smin,smax = RSI_BOUNDS["sell_th"]
        period = rng.randint(pmin, pmax)
        buy    = round(rng.uniform(bmin, bmax), 1)
        sell   = max(round(rng.uniform(buy+5, smax), 1), 50.0)
        return {"period": period, "buy_th": buy, "sell_th": sell}
    return {}

def clamp_params(strategy_id: str, params: Dict[str, int | float]) -> Dict[str, int | float]:
    sid = strategy_id.lower()
    if sid == "ema_cross":
        fmin,fmax = EMA_BOUNDS["fast"]
        smin,smax = EMA_BOUNDS["slow"]
        fast = int(max(fmin, min(fmax, int(params.get("fast", 10)))))
        slow = int(max(max(fast+1, smin), min(smax, int(params.get("slow", 30)))))
        return {"fast": fast, "slow": slow}
    if sid == "rsi_reversion":
        pmin,pmax = RSI_BOUNDS["period"]
        period = int(max(pmin, min(pmax, int(params.get("period", 14)))))
        buy = float(params.get("buy_th", 30.0))
        sell = float(params.get("sell_th", 55.0))
        buy = max(10.0, min(50.0, buy))
        sell = max(buy+1.0, min(90.0, sell))
        return {"period": period, "buy_th": round(buy,1), "sell_th": round(sell,1)}
    return params

def mutate(strategy_id: str, params: Dict[str,int|float], rng: random.Random, p: float=0.3) -> Dict[str,int|float]:
    out = dict(params)
    if strategy_id.lower() == "ema_cross":
        if rng.random() < p: out["fast"] = out["fast"] + rng.choice([-3,-2,-1,1,2,3])
        if rng.random() < p: out["slow"] = out["slow"] + rng.choice([-5,-3,-1,1,3,5])
    else:
        if rng.random() < p: out["period"] = out["period"] + rng.choice([-2,-1,1,2])
        if rng.random() < p: out["buy_th"] = out["buy_th"] + rng.choice([-2.0,-1.0,1.0,2.0])
        if rng.random() < p: out["sell_th"] = out["sell_th"] + rng.choice([-2.0,-1.0,1.0,2.0])
    return clamp_params(strategy_id, out)

def crossover(strategy_id: str, a: Dict[str,int|float], b: Dict[str,int|float], rng: random.Random) -> Dict[str,int|float]:
    out = {}
    for k in a.keys():
        out[k] = rng.choice([a[k], b.get(k, a[k])])
    return clamp_params(strategy_id, out)

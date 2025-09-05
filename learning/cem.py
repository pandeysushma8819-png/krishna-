from __future__ import annotations
from typing import Dict, Any, List
import random, math
from learning.search_space import EMA_BOUNDS, RSI_BOUNDS, clamp_params
from learning.evaluate import evaluate_params

class CEMConfig:
    def __init__(self, iters=10, pop=20, elite_frac=0.25, seed=123):
        self.iters=iters; self.pop=pop; self.elite_frac=elite_frac; self.seed=seed

def _sample_int(mu: float, sigma: float, low: int, high: int, rng: random.Random) -> int:
    x = int(round(rng.gauss(mu, max(1.0, sigma))))
    return max(low, min(high, x))

def _sample_float(mu: float, sigma: float, low: float, high: float, rng: random.Random) -> float:
    x = rng.gauss(mu, max(0.5, sigma))
    return max(low, min(high, x))

def run_cem(bars: List[dict], tf_sec: int, strategy_id: str,
            market="NSE", product="equity_intraday",
            lot_size=1, slip_bps=1.5, spread_bps=0.5,
            cfg: CEMConfig = CEMConfig()) -> Dict[str, Any]:
    rng = random.Random(cfg.seed)
    if strategy_id.lower()=="ema_cross":
        f_low,f_high = EMA_BOUNDS["fast"]; s_low,s_high = EMA_BOUNDS["slow"]
        mu_f, sd_f = ( (f_low+f_high)/2.0, (f_high-f_low)/6.0 )
        mu_s, sd_s = ( (s_low+s_high)/2.0, (s_high-s_low)/6.0 )
    else:
        p_low,p_high = RSI_BOUNDS["period"]; b_low,b_high=RSI_BOUNDS["buy_th"]; s_low,s_high=RSI_BOUNDS["sell_th"]
        mu_p, sd_p = ( (p_low+p_high)/2.0, (p_high-p_low)/6.0 )
        mu_b, sd_b = ( (b_low+b_high)/2.0, (b_high-b_low)/6.0 )
        mu_s, sd_s = ( (s_low+s_high)/2.0, (s_high-s_low)/6.0 )

    history=[]; best=None
    for it in range(cfg.iters):
        pop=[]
        for _ in range(cfg.pop):
            if strategy_id.lower()=="ema_cross":
                fast = _sample_int(mu_f, sd_f, f_low, f_high, rng)
                slow = _sample_int(mu_s, sd_s, max(s_low, fast+1), s_high, rng)
                params = {"fast": fast, "slow": slow}
            else:
                period = _sample_int(mu_p, sd_p, p_low, p_high, rng)
                buy    = _sample_float(mu_b, sd_b, b_low, b_high, rng)
                sell   = max(buy + 1.0, _sample_float(mu_s, sd_s, s_low, s_high, rng))
                params = {"period": period, "buy_th": round(buy,1), "sell_th": round(sell,1)}
            params = clamp_params(strategy_id, params)
            ev = evaluate_params(bars, tf_sec, strategy_id, params, market, product, lot_size, slip_bps, spread_bps)
            pop.append(ev)
        pop.sort(key=lambda e: e["reward"], reverse=True)
        best = pop[0] if (best is None or pop[0]["reward"] > best["reward"]) else best
        history.append({"iter": it, "best_reward": pop[0]["reward"], "best_params": pop[0]["params"]})
        # update distributions from elites
        k = max(1, int(cfg.elite_frac * cfg.pop))
        elites = pop[:k]
        if strategy_id.lower()=="ema_cross":
            fs = [e["params"]["fast"] for e in elites]
            ss = [e["params"]["slow"] for e in elites]
            mu_f, sd_f = (sum(fs)/len(fs), max(1.0, (max(fs)-min(fs))/3.0))
            mu_s, sd_s = (sum(ss)/len(ss), max(1.0, (max(ss)-min(ss))/3.0))
        else:
            ps = [e["params"]["period"] for e in elites]
            bs = [e["params"]["buy_th"] for e in elites]
            ss = [e["params"]["sell_th"] for e in elites]
            mu_p, sd_p = (sum(ps)/len(ps), max(1.0, (max(ps)-min(ps))/3.0))
            mu_b, sd_b = (sum(bs)/len(bs), max(0.5, (max(bs)-min(bs))/3.0))
            mu_s, sd_s = (sum(ss)/len(ss), max(0.5, (max(ss)-min(ss))/3.0))
    return {"algo": "cem", "strategy_id": strategy_id, "best": best, "history": history}

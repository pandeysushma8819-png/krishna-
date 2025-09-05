from __future__ import annotations
from typing import Dict, Any, List, Tuple
import math, random, statistics
from strategies.signal_logic import build_target_positions
from strategies.spec import StrategySpec
from data.cleaners import dedupe_bars, fill_missing_bars, clamp_spikes
from backtesting.engine import BacktestConfig, run_backtest
from learning.reward import compute_reward

def _res_stats(res: Any) -> Dict[str, float]:
    if hasattr(res, "stats"): return res.stats  # dataclass-like
    if isinstance(res, dict): return res.get("stats", {})
    return {}

def _equity_curve(res: Any) -> List[Tuple[int,float]]:
    if hasattr(res, "equity"): return res.equity
    if isinstance(res, dict): return res.get("equity", [])
    return []

def _mc_bootstrap_p5(equity: List[Tuple[int,float]], R: int = 300) -> float:
    if not equity or len(equity) < 3:
        return 0.0
    # convert to returns series
    rets = []
    for i in range(1, len(equity)):
        prev = max(1e-9, float(equity[i-1][1]))
        cur  = max(1e-9, float(equity[i][1]))
        rets.append(math.log(cur/prev))
    if not rets: return 0.0
    rng = random.Random(42)
    n = len(rets)
    samples = []
    for _ in range(R):
        s = 0.0
        for _ in range(n):
            s += rets[rng.randrange(n)]
        samples.append(100.0*(math.exp(s)-1.0))  # percent return
    samples.sort()
    idx = max(0, int(0.05*len(samples))-1)
    return samples[idx]

def evaluate_params(bars: List[dict],
                    tf_sec: int,
                    strategy_id: str,
                    params: Dict[str,int|float],
                    market: str = "NSE",
                    product: str = "equity_intraday",
                    lot_size: int = 1,
                    slip_bps: float = 1.5,
                    spread_bps: float = 0.5) -> Dict[str, Any]:
    # hygiene
    bars2 = clamp_spikes(fill_missing_bars(dedupe_bars(bars), tf_sec=tf_sec), max_pct=0.15)
    # target positions
    spec = StrategySpec(strategy_id=strategy_id, params=params).materialize()
    target = build_target_positions(bars2, spec)
    # backtest
    cfg = BacktestConfig(market=market, product=product, lot_size=lot_size,
                         slippage_bps=slip_bps, spread_bps=spread_bps)
    res = run_backtest(bars2, target, cfg)
    stats = _res_stats(res)
    equity = _equity_curve(res)
    mc_p5 = _mc_bootstrap_p5(equity)
    reward = compute_reward(stats, mc_p5_ret=mc_p5, trades=stats.get("trades",0),
                            n_bars=len(bars2))
    return {"spec": spec, "params": params, "stats": stats, "reward": reward, "mc_p5_ret": mc_p5}

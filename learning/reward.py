from __future__ import annotations
from typing import Dict

def compute_reward(stats: Dict[str, float],
                   mc_p5_ret: float | None = None,
                   trades: int | None = None,
                   n_bars: int | None = None,
                   w_ret: float = 1.0,
                   w_mdd: float = 0.7,
                   w_pf: float = 5.0,
                   w_turn: float = 3.0,
                   min_trades: int = 5,
                   min_pf: float = 1.0) -> float:
    """Reward: ret - w_mdd*mdd + w_pf*(pf-1) - w_turn*turnover - penalties.
       If mc_p5_ret present, add 0.5*mc_p5_ret to reward (robustness bonus)."""
    ret = float(stats.get("ret_pct", 0.0))
    mdd = float(stats.get("mdd_pct", 0.0))
    pf  = float(stats.get("profit_factor", 0.0))
    T   = int(trades or stats.get("trades", 0))
    N   = int(n_bars or 0)

    # crude turnover proxy in [0,1]: entries per bar (two sides ≈ one trade)
    turnover = (T / max(1, N)) if N else 0.0

    reward = w_ret*ret - w_mdd*mdd + w_pf*max(0.0, pf - 1.0) - w_turn*turnover

    # robustness bonus (5th percentile bootstrapped return)
    if mc_p5_ret is not None:
        reward += 0.5 * mc_p5_ret

    # hard guards
    if T < min_trades:    reward -= 999.0
    if pf < min_pf:       reward -= 999.0
    return round(reward, 6)

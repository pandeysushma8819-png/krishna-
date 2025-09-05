from __future__ import annotations
from typing import List, Dict, Any
import random, time, json

from strategies.spec import StrategySpec
from strategies.signal_logic import build_target_positions
from backtesting.engine import BacktestConfig, run_backtest
from data.cleaners import dedupe_bars, fill_missing_bars, clamp_spikes
from integrations.sheets import SheetsClient

def _gen_ema_candidates(n: int, seed: int) -> List[StrategySpec]:
    rng = random.Random(seed)
    cands: List[StrategySpec] = []
    for _ in range(n):
        fast = rng.randint(5, 30)
        slow = rng.randint(max(fast+5, 20), 80)
        cands.append(StrategySpec("ema_cross", {"fast": fast, "slow": slow}, seed=rng.randrange(10**6)).materialize())
    return cands

def _gen_rsi_candidates(n: int, seed: int) -> List[StrategySpec]:
    rng = random.Random(seed)
    cands: List[StrategySpec] = []
    for _ in range(n):
        period = rng.randint(8, 20)
        buy = rng.uniform(20.0, 35.0)
        sell = max(buy + rng.uniform(10.0, 30.0), 50.0)
        cands.append(StrategySpec("rsi_reversion", {"period": period, "buy_th": round(buy,1), "sell_th": round(sell,1)}, seed=rng.randrange(10**6)).materialize())
    return cands

def generate_candidates(total: int, seed: int = 42) -> List[StrategySpec]:
    # half-half
    n1 = total // 2
    n2 = total - n1
    return _gen_ema_candidates(n1, seed) + _gen_rsi_candidates(n2, seed+1)

def _score(res_stats: Dict[str, float]) -> float:
    # Simple composite: reward return, penalize drawdown, encourage PF>1
    ret = float(res_stats.get("ret_pct", 0.0))
    mdd = float(res_stats.get("mdd_pct", 0.0))
    pf  = float(res_stats.get("profit_factor", 0.0))
    trades = int(res_stats.get("trades", 0))
    if trades < 5:           # prune very low-activity
        return -999
    if pf < 1.0:             # losing / fragile
        return -999
    return ret - 0.7*mdd + 5.0*(pf-1.0)  # tweakable

def discover_and_backtest(bars: List[dict], tf_sec: int, total: int = 20, market: str = "NSE", product: str = "equity_intraday", lot_size: int = 1, slip_bps: float = 1.5, spread_bps: float = 0.5, seed: int = 42, window: str = "") -> Dict[str, Any]:
    # Prep data
    bars = clamp_spikes(fill_missing_bars(dedupe_bars(bars), tf_sec=tf_sec), max_pct=0.15)

    specs = generate_candidates(total=total, seed=seed)
    for s in specs:
        s.window = window

    cfg = BacktestConfig(market=market, product=product, lot_size=lot_size, slippage_bps=slip_bps, spread_bps=spread_bps)
    rows = []
    sheets = SheetsClient()

    for spec in specs:
        target = build_target_positions(bars, spec)
        res = run_backtest(bars, target, cfg)
        score = _score(res.stats)
        row = {
            "strategy_id": spec.strategy_id,
            "version": spec.version,
            "seed": spec.seed,
            "window": spec.window,
            "params": spec.params,
            "stats": res.stats,
            "score": round(score, 3),
        }
        rows.append(row)

        # archive spec+metrics to Snapshots (best-effort)
        try:
            sheets.snapshot_spec(spec, res.stats, tag="P6")
        except Exception:
            pass

    # rank & pick champion/challengers
    ranked = sorted(rows, key=lambda r: r["score"], reverse=True)
    short = [r for r in ranked if r["score"] > 0][:5]  # positive score shortlist

    # write leaderboard (best-effort)
    try:
        for r in short:
            sheets.append_leaderboard(r)
    except Exception:
        pass

    return {
        "total": len(rows),
        "shortlist": short,
        "leader": short[0] if short else None,
        "all": ranked
    }

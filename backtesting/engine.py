from __future__ import annotations
from typing import List, Dict, Literal, Optional, Tuple
from dataclasses import dataclass, asdict
from data.schemas import BarDict
from costs.model_generic import estimate_trade_costs, apply_slippage_spread

Side = Literal["long","short","flat"]

@dataclass
class BacktestConfig:
    market: str = "NSE"
    product: str = "equity_intraday"   # equity_delivery | equity_intraday | futures | options
    plan: str = "INDIA_DISCOUNT"
    lot_size: int = 1
    slippage_bps: float = 1.0
    spread_bps: float = 0.0
    allow_short: bool = False
    initial_cash: float = 1_000_000.0  # INR
    trade_on: str = "next_open"        # next_open | next_close

@dataclass
class Trade:
    ts: int
    side: str         # "buy"/"sell"
    price: float
    qty: int
    costs: float

@dataclass
class Result:
    equity: List[Tuple[int, float]]
    trades: List[Trade]
    pnl_total: float
    return_pct: float
    max_dd_pct: float
    win_rate: float
    profit_factor: float
    stats: Dict[str, float]

def _fill_price(b: BarDict, side: str, trade_on: str, slippage_bps: float, spread_bps: float) -> float:
    px = b["open"] if trade_on == "next_open" else b["close"]
    return apply_slippage_spread(px, side=side, slippage_bps=slippage_bps, spread_bps=spread_bps)

def _max_drawdown(equity: List[Tuple[int,float]]) -> float:
    peak = -1e18
    mdd = 0.0
    for _, v in equity:
        peak = max(peak, v)
        mdd = max(mdd, (peak - v) / peak if peak > 0 else 0.0)
    return mdd

def run_backtest(bars: List[BarDict], target_pos: Dict[int, int], cfg: BacktestConfig) -> Result:
    """
    bars: sorted list of bars (ts ascending). Each bar dict has: ts, open, high, low, close, volume.
    target_pos: { ts: -1|0|1 } desired position (per bar close). Execution happens on *next* bar (no look-ahead).
    - Position notionally means quantity = target * lot_size (1x leverage for simplicity).
    """
    if not bars:
        return Result([], [], 0.0, 0.0, 0.0, 0.0, 0.0, {})
    # Sort bars
    bars = sorted((dict(b) for b in bars), key=lambda x: int(x["ts"]))
    # Current state
    cash = float(cfg.initial_cash)
    pos  = 0  # in lots: +1 long, -1 short
    qty_per_pos = int(cfg.lot_size)
    trades: List[Trade] = []
    equity: List[Tuple[int,float]] = []
    wins = 0
    losses = 0
    gross_win = 0.0
    gross_loss = 0.0
    last_entry_px = 0.0

    # Walk bars; on each bar, execute change from previous target at NEXT bar
    # So we pre-read target for bar i (desired close), execute at bar i+1 open/close.
    for i in range(len(bars)-1):
        cur = bars[i]
        nxt = bars[i+1]
        ts  = int(cur["ts"])
        nxt_ts = int(nxt["ts"])
        desired = int(target_pos.get(ts, pos))  # default stay
        if desired not in (-1,0,1):
            desired = 0
        if desired == -1 and not cfg.allow_short:
            desired = 0

        # mark-to-market equity at current close
        mtm = pos * qty_per_pos * cur["close"]
        equity_val = cash + mtm
        equity.append((ts, equity_val))

        # determine delta at next bar (execution)
        delta = desired - pos
        if delta != 0:
            if delta > 0:
                # need to buy delta lots
                leg_side = "buy"
                fill_px = _fill_price(nxt, leg_side, cfg.trade_on, cfg.slippage_bps, cfg.spread_bps)
                qty = abs(delta) * qty_per_pos
                notional = fill_px * qty
                cost, brk = estimate_trade_costs(notional, side=leg_side, market=cfg.market, product=cfg.product, plan=cfg.plan)
                cash -= notional
                cash -= cost
                trades.append(Trade(ts=nxt_ts, side=leg_side, price=fill_px, qty=qty, costs=cost))
                if pos == 0:
                    last_entry_px = fill_px
                pos = desired
            else:
                # need to sell |delta| lots
                leg_side = "sell"
                fill_px = _fill_price(nxt, leg_side, cfg.trade_on, cfg.slippage_bps, cfg.spread_bps)
                qty = abs(delta) * qty_per_pos
                notional = fill_px * qty
                cost, brk = estimate_trade_costs(notional, side=leg_side, market=cfg.market, product=cfg.product, plan=cfg.plan)
                cash += notional
                cash -= cost
                trades.append(Trade(ts=nxt_ts, side=leg_side, price=fill_px, qty=qty, costs=cost))
                # Closed a long? track win/loss on round-trip (simple)
                if desired == 0 and last_entry_px > 0 and pos > 0:
                    pnl = (fill_px - last_entry_px) * qty_per_pos * pos
                    if pnl >= 0: wins += 1; gross_win += pnl
                    else: losses += 1; gross_loss += -pnl
                if desired == 0 and last_entry_px > 0 and pos < 0:
                    pnl = (last_entry_px - fill_px) * qty_per_pos * abs(pos)
                    if pnl >= 0: wins += 1; gross_win += pnl
                    else: losses += 1; gross_loss += -pnl
                pos = desired

    # Final mark at last bar
    last_bar = bars[-1]
    mtm = pos * qty_per_pos * last_bar["close"]
    equity_val = cash + mtm
    equity.append((int(last_bar["ts"]), equity_val))

    ret = (equity[-1][1] - cfg.initial_cash) / cfg.initial_cash if cfg.initial_cash > 0 else 0.0
    mdd = _max_drawdown(equity)
    total_trades = len(trades)
    win_rate = (wins / (wins + losses)) if (wins + losses) > 0 else 0.0
    profit_factor = (gross_win / gross_loss) if gross_loss > 0 else (gross_win if gross_win > 0 else 0.0)

    stats = {
        "trades": total_trades,
        "wins": wins,
        "losses": losses,
        "ret_pct": round(ret*100, 2),
        "mdd_pct": round(mdd*100, 2),
        "win_rate_pct": round(win_rate*100, 2),
        "profit_factor": round(profit_factor, 3),
        "final_equity": round(equity[-1][1], 2),
    }

    return Result(
        equity=equity,
        trades=trades,
        pnl_total=round(equity[-1][1] - cfg.initial_cash, 2),
        return_pct=round(ret*100, 2),
        max_dd_pct=round(mdd*100, 2),
        win_rate=round(win_rate*100, 2),
        profit_factor=round(profit_factor, 3),
        stats=stats,
    )

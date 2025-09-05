from __future__ import annotations
from typing import Dict, Tuple
from costs.model_india import estimate_leg_costs, load_costs

def estimate_trade_costs(notional: float, side: str, market: str = "NSE", product: str = "equity_intraday", plan: str = "INDIA_DISCOUNT", cfg: dict | None = None) -> Tuple[float, Dict[str, float]]:
    """
    Wrapper to select appropriate regional model. For now market=NSE → India model.
    """
    if market.upper() in ("NSE","BSE","NFO","NSE_EQ"):
        return estimate_leg_costs(notional, side, product=product, plan_name=plan, cfg=cfg)
    # Extend here for NYSE/NASDAQ etc.
    return estimate_leg_costs(notional, side, product=product, plan_name=plan, cfg=cfg)

def apply_slippage_spread(fill_price: float, side: str, slippage_bps: float = 1.0, spread_bps: float = 0.0) -> float:
    """
    Adjust fill price by slippage + half-spread in a side-aware manner.
    side: "buy" (price up), "sell" (price down)
    """
    side = side.lower()
    adj_bps = float(slippage_bps) + float(spread_bps)
    if side == "buy":
        return fill_price * (1.0 + adj_bps / 1e4)
    return fill_price * (1.0 - adj_bps / 1e4)

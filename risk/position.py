# risk/position.py
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Any, Dict, List, Optional, Literal
from .utils import atr_last, closes_from_bars, pct_returns, pearson_corr
from .slip_guard import slip_ok

Side = Literal["buy", "sell"]

@dataclass
class RiskConfig:
    equity: float
    max_risk_pct: float
    port_max_risk_pct: float
    sl_atr: float
    tp_atr: float
    trail_atr: float
    atr_len: int
    corr_window: int
    corr_alpha: float
    corr_min_scale: float
    slip_bps_guard: float
    lot_size: int

@dataclass
class OpenPos:
    symbol: str
    side: Side
    qty: int
    entry: float
    sl: float
    bars: Optional[List[dict]] = None  # for correlation

def _risk_per_unit(side: Side, entry: float, sl: float) -> float:
    if side == "buy":
        return max(0.0, entry - sl)
    else:
        return max(0.0, sl - entry)

def _round_lot(qty: float, lot: int) -> int:
    if lot <= 1:
        return max(0, int(qty))
    return max(0, int(qty // lot) * lot)

def _max_abs_corr(candidate_bars: List[dict], open_positions: List[OpenPos], corr_window: int) -> float:
    if not open_positions:
        return 0.0
    c_cl = closes_from_bars(candidate_bars)[-corr_window:]
    c_rets = pct_returns(c_cl)
    mx = 0.0
    for p in open_positions:
        if not p.bars:
            continue
        o_cl = closes_from_bars(p.bars)[-corr_window:]
        o_rets = pct_returns(o_cl)
        rho = abs(pearson_corr(c_rets, o_rets))
        mx = max(mx, rho)
    return mx

def _apply_port_cap(equity: float, port_max_risk_pct: float,
                    open_positions: List[OpenPos], new_risk_value: float, qty: int, risk_per_unit: float) -> tuple[int, float]:
    """
    Ensure total risk (sum of per-position risk values) stays within cap.
    For open positions, approximate risk_value ≈ qty * risk_per_unit.
    """
    active_risk = 0.0
    for p in open_positions or []:
        # approximate risk per unit from entry/sl (if usable)
        rpu = _risk_per_unit(p.side, p.entry, p.sl)
        active_risk += float(p.qty) * max(0.0, rpu)

    cap = equity * port_max_risk_pct
    if active_risk + new_risk_value <= cap or qty <= 0:
        return qty, new_risk_value

    # scale down qty to fit in the remaining cap
    rem = max(0.0, cap - active_risk)
    new_qty = int(rem // risk_per_unit) if risk_per_unit > 0 else 0
    return new_qty, float(new_qty) * risk_per_unit

def quote_position(
    *,
    symbol: str,
    side: Side,
    price: float,
    equity: float,
    bars: List[dict],
    open_positions: Optional[List[OpenPos]] = None,
    risk_scale: float = 1.0,
    ref_price: Optional[float] = None,
    cfg: Optional[RiskConfig] = None,
) -> Dict[str, Any]:
    """
    Return a quote dict with qty, SL/TP/trailing, guards & reasons.
    """
    # Defaults (can be injected)
    cfg = cfg or RiskConfig(
        equity=equity,
        max_risk_pct=0.010,
        port_max_risk_pct=0.020,
        sl_atr=1.50, tp_atr=3.00, trail_atr=1.00,
        atr_len=14, corr_window=40,
        corr_alpha=0.60, corr_min_scale=0.20,
        slip_bps_guard=10.0,
        lot_size=1,
    )
    # Use provided equity in cfg
    cfg.equity = equity

    # ATR & SL/TP levels
    atr = atr_last(bars, cfg.atr_len)
    if atr <= 0.0:
        return {"ok": False, "error": "atr_zero_or_short_series"}

    if side == "buy":
        sl = price - cfg.sl_atr * atr
        tp = price + cfg.tp_atr * atr
        trail = price - cfg.trail_atr * atr if cfg.trail_atr > 0 else None
    else:
        sl = price + cfg.sl_atr * atr
        tp = price - cfg.tp_atr * atr
        trail = price + cfg.trail_atr * atr if cfg.trail_atr > 0 else None

    rpu = _risk_per_unit(side, price, sl)  # risk per unit
    if rpu <= 0.0:
        return {"ok": False, "error": "invalid_stop_levels"}

    # Base qty from per-position risk
    risk_budget = equity * cfg.max_risk_pct * max(0.0, min(1.0, risk_scale))
    qty = int(risk_budget // rpu)

    # Correlation-aware scaling vs open positions
    mx_rho = _max_abs_corr(bars, open_positions or [], cfg.corr_window)
    scale_corr = max(cfg.corr_min_scale, 1.0 - cfg.corr_alpha * mx_rho)
    qty = int(qty * scale_corr)

    # Portfolio cap
    new_risk_value = float(qty) * rpu
    qty, new_risk_value = _apply_port_cap(equity, cfg.port_max_risk_pct, open_positions or [], new_risk_value, qty, rpu)

    # Lot rounding
    qty = _round_lot(qty, cfg.lot_size)

    # Slippage guard
    slip_guard = None
    if ref_price is not None:
        ok, bps = slip_ok(price, ref_price, cfg.slip_bps_guard)
        slip_guard = {"ok": ok, "bps": bps, "limit_bps": cfg.slip_bps_guard}

    return {
        "ok": True,
        "symbol": symbol,
        "side": side,
        "price": price,
        "atr": round(atr, 6),
        "levels": {
            "sl": round(sl, 6),
            "tp": round(tp, 6),
            "trail": (round(trail, 6) if trail is not None else None),
            "sl_atr": cfg.sl_atr,
            "tp_atr": cfg.tp_atr,
            "trail_atr": cfg.trail_atr,
        },
        "risk": {
            "risk_per_unit": round(rpu, 6),
            "risk_budget": round(risk_budget, 2),
            "new_risk_value": round(new_risk_value, 2),
            "max_risk_pct": cfg.max_risk_pct,
            "port_max_risk_pct": cfg.port_max_risk_pct,
            "corr_max_abs": round(mx_rho, 4),
            "corr_scale": round(scale_corr, 3),
            "risk_scale": round(max(0.0, min(1.0, risk_scale)), 3),
        },
        "qty": int(qty),
        "lot_size": cfg.lot_size,
        "guards": {
            "slippage": slip_guard,
        },
    }

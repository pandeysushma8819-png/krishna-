# risk/slip_guard.py
from __future__ import annotations

def price_to_bps(a: float, b: float) -> float:
    if b == 0:
        return 0.0
    return abs((a - b) / b) * 10000.0

def slip_ok(order_price: float, ref_price: float, max_bps: float) -> tuple[bool, float]:
    bps = price_to_bps(order_price, ref_price)
    return (bps <= max_bps, bps)

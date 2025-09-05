from __future__ import annotations
from typing import Dict, Tuple, List
import yaml

def load_costs(path: str = "config/costs.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def _min(x: float, cap: float) -> float:
    if cap is None or cap <= 0:
        return x
    return min(x, cap)

def estimate_leg_costs(notional: float, side: str, product: str, plan_name: str = "INDIA_DISCOUNT", cfg: dict | None = None) -> Tuple[float, Dict[str, float]]:
    """
    Estimate per-leg (buy or sell) costs in INR.
    side: "buy" | "sell"
    product: equity_delivery | equity_intraday | futures | options
    notional: price * quantity * lot_size (or premium*qty*lot_size for options)
    """
    side = side.lower()
    assert side in ("buy","sell")
    cfg = cfg or load_costs()
    plan = (cfg.get("plans") or {}).get(plan_name)
    if not plan:
        raise ValueError(f"plan not found: {plan_name}")
    p = plan.get(product)
    if not p:
        raise ValueError(f"product not found: {product}")

    brokerage = _min(notional * float(p.get("brokerage_pct", 0.0)), float(p.get("brokerage_cap", 0.0)))
    if float(p.get("min_brokerage", 0.0)) > 0.0:
        brokerage = max(brokerage, float(p["min_brokerage"]))

    stt_pct = float(p.get(f"stt_pct_{side}", 0.0))
    stt  = notional * stt_pct
    exch = notional * float(p.get("exch_txn_pct", 0.0))
    sebi = notional * float(p.get("sebi_pct", 0.0))
    stamp = notional * (float(p.get("stamp_pct_buy", 0.0)) if side == "buy" else 0.0)

    gst_base = 0.0
    for key in (p.get("gst_pct_on") or []):
        if key == "brokerage": gst_base += brokerage
        if key == "exch_txn":  gst_base += exch
    gst = float(p.get("gst_pct", 0.0)) * gst_base

    total = brokerage + stt + exch + sebi + stamp + gst
    brk = {
        "brokerage": round(brokerage, 2),
        "stt": round(stt, 2),
        "exch_txn": round(exch, 2),
        "sebi": round(sebi, 2),
        "stamp": round(stamp, 2),
        "gst": round(gst, 2),
    }
    return round(total, 2), brk

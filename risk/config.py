# risk/config.py
from __future__ import annotations

# Global/default risk settings (tune per your taste)
RISK = {
    # Position risk
    "max_risk_pct": 0.010,         # 1.0% of equity per position
    "port_max_risk_pct": 0.020,    # 2.0% total active risk budget

    # Stops/targets (ATR-based)
    "atr_len": 14,
    "sl_atr": 1.50,                # stop = entry -/+ sl_atr * ATR
    "tp_atr": 3.00,                # take-profit multiple
    "trail_atr": 1.00,             # trailing stop multiple (0 = off)

    # Correlation awareness
    "corr_window": 40,             # bars used for corr
    "corr_alpha": 0.60,            # scaling factor strength for |rho|max
    "corr_min_scale": 0.20,        # never scale below 20% even if highly correlated

    # Slippage acceptance guard
    "slip_bps_guard": 10.0,        # reject/flag if |price-ref| > 10 bps

    # Cooldown on losing streak (e.g., 3 SL in 15m => 20m pause)
    "cooldown_hits": 3,
    "cooldown_window_min": 15,
    "cooldown_minutes": 20,

    # Rounding
    "lot_size": 1,                 # default lot rounding (1 = shares)
}

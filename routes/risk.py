# routes/risk.py
from __future__ import annotations
from typing import Any, Dict, List, Optional
from flask import Blueprint, request, jsonify
import time

from risk.position import quote_position, OpenPos, RiskConfig
from risk.cooldown import on_trade_outcome, is_in_cooldown
from risk.config import RISK

risk_bp = Blueprint("risk", __name__)

@risk_bp.get("/risk/ping")
def ping() -> Any:
    return jsonify(ok=True, msg="risk alive")

def _parse_open_positions(raw: List[Dict]) -> List[OpenPos]:
    out: List[OpenPos] = []
    for p in raw or []:
        out.append(OpenPos(
            symbol=str(p.get("symbol","")),
            side=str(p.get("side","buy")).lower() in ("buy","long") and "buy" or "sell",
            qty=int(p.get("qty",0)),
            entry=float(p.get("entry",0.0)),
            sl=float(p.get("sl",0.0)),
            bars=p.get("bars"),
        ))
    return out

@risk_bp.post("/risk/quote")
def quote() -> Any:
    """
    Body:
    {
      "symbol":"NIFTY", "side":"buy", "price":123.4, "equity":1000000,
      "bars":[...],               # recent bars for candidate
      "open_positions":[{...}],   # optional list with bars for corr
      "risk_scale": 0.7,          # optional (from meta guard)
      "ref_price": 123.3          # optional: for slippage guard
    }
    """
    data = request.get_json(silent=True) or {}
    symbol = str(data.get("symbol","")).upper()
    side = str(data.get("side","buy")).lower()
    price = float(data.get("price", 0.0))
    equity = float(data.get("equity", 0.0))
    bars = data.get("bars") or []
    risk_scale = float(data.get("risk_scale", 1.0))
    ref_price = data.get("ref_price", None)
    open_positions = _parse_open_positions(data.get("open_positions") or [])

    if not symbol or price <= 0.0 or equity <= 0.0 or not bars:
        return jsonify(ok=False, error="bad_request"), 400

    # Build config from global RISK with ability to override via payload.cfg
    cfg_over = data.get("cfg") or {}
    cfg = RiskConfig(
        equity=equity,
        max_risk_pct=float(cfg_over.get("max_risk_pct", RISK["max_risk_pct"])),
        port_max_risk_pct=float(cfg_over.get("port_max_risk_pct", RISK["port_max_risk_pct"])),
        sl_atr=float(cfg_over.get("sl_atr", RISK["sl_atr"])),
        tp_atr=float(cfg_over.get("tp_atr", RISK["tp_atr"])),
        trail_atr=float(cfg_over.get("trail_atr", RISK["trail_atr"])),
        atr_len=int(cfg_over.get("atr_len", RISK["atr_len"])),
        corr_window=int(cfg_over.get("corr_window", RISK["corr_window"])),
        corr_alpha=float(cfg_over.get("corr_alpha", RISK["corr_alpha"])),
        corr_min_scale=float(cfg_over.get("corr_min_scale", RISK["corr_min_scale"])),
        slip_bps_guard=float(cfg_over.get("slip_bps_guard", RISK["slip_bps_guard"])),
        lot_size=int(cfg_over.get("lot_size", RISK["lot_size"])),
    )

    qt = quote_position(
        symbol=symbol, side="buy" if side in ("buy","long") else "sell",
        price=price, equity=equity, bars=bars,
        open_positions=open_positions, risk_scale=risk_scale, ref_price=ref_price,
        cfg=cfg,
    )
    return jsonify(qt), (200 if qt.get("ok") else 400)

@risk_bp.get("/risk/state")
def state() -> Any:
    """
    /risk/state?symbol=XYZ
    """
    symbol = str(request.args.get("symbol","")).upper()
    if not symbol:
        return jsonify(ok=False, error="symbol_required"), 400
    ok, sec = is_in_cooldown(symbol)
    return jsonify(ok=True, cooldown=ok, seconds_left=sec)

@risk_bp.post("/risk/cooldown/update")
def cooldown_update() -> Any:
    """
    Body:
    { "symbol":"NIFTY", "outcome":"sl|tp|flat", "now_ts": <optional epoch> }
    """
    data = request.get_json(silent=True) or {}
    symbol = str(data.get("symbol","")).upper()
    outcome = str(data.get("outcome","")).lower()
    now_ts = int(data.get("now_ts", time.time()))
    if outcome not in ("sl","tp","flat") or not symbol:
        return jsonify(ok=False, error="bad_request"), 400

    st = on_trade_outcome(
        symbol, outcome,
        cooldown_hits=int(RISK["cooldown_hits"]),
        window_min=int(RISK["cooldown_window_min"]),
        pause_min=int(RISK["cooldown_minutes"]),
        now_ts=now_ts,
    )
    ok, sec = is_in_cooldown(symbol, now_ts)
    return jsonify(ok=True, state=st, cooldown=ok, seconds_left=sec)

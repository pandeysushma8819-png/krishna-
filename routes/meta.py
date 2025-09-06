from __future__ import annotations
from flask import Blueprint, request, jsonify
from typing import List, Dict, Any

# Internal imports (P9 components)
from meta.regime import classify_latest
from meta.anomaly import detect_anomalies, decide_guard

# Blueprint
meta_bp = Blueprint("meta", __name__)

@meta_bp.route("/meta/ping")
def ping() -> Any:
    """Lightweight liveness check for P9 endpoints."""
    return jsonify(ok=True, msg="meta alive")

def _error(msg: str, code: int = 400):
    return jsonify(ok=False, error=msg), code

@meta_bp.route("/meta/scan", methods=["POST"])
def scan() -> Any:
    """
    POST JSON body:
    {
      "bars": [ { "ts": <int>, "open": <num>, "high": <num>, "low": <num>, "close": <num>, "volume": <num> }, ... ],
      "tf_sec": 900
    }
    Response:
    {
      "ok": true,
      "regime": "<trend|mean|sideways|high_vol>",
      "snap": { "trend_strength": ..., "vol_abs": ..., "persist": ... },
      "anomalies": [ {...}, ... ],
      "guard": { "action": "<none|scale_down|pause>", "risk_scale": <0..1>, "cooldown_min": <int>, "reason": "<text>" }
    }
    """
    data = request.get_json(silent=True) or {}

    # Validate inputs
    bars: List[Dict] = data.get("bars", [])
    if not isinstance(bars, list) or not bars:
        return _error("no_bars", 400)

    try:
        tf_sec = int(data.get("tf_sec", 900))
    except Exception:
        return _error("invalid tf_sec", 400)

    # Basic schema guard on the last bar to catch obvious payload mistakes
    last = bars[-1]
    for k in ("ts", "open", "high", "low", "close"):
        if k not in last:
            return _error(f"bar_missing_field:{k}", 400)

    try:
        regime, snap = classify_latest(bars, tf_sec)
        anomalies = detect_anomalies(bars, tf_sec)
        guard = decide_guard(regime, anomalies)
        return jsonify(ok=True, regime=regime, snap=snap, anomalies=anomalies, guard=guard)
    except Exception as e:
        # Avoid leaking stack traces to clients
        return _error(str(e), 500)

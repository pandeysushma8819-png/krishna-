from __future__ import annotations
from flask import Blueprint, request, jsonify
from typing import List, Dict, Any

from meta.regime import classify_latest
from meta.anomaly import detect_anomalies, decide_guard

meta_bp = Blueprint("meta", __name__)

@meta_bp.route("/meta/ping")
def ping() -> Any:
    return jsonify(ok=True, msg="meta alive")

def _error(msg: str, code: int = 400):
    return jsonify(ok=False, error=msg), code

@meta_bp.route("/meta/scan", methods=["POST"])
def scan() -> Any:
    data = request.get_json(silent=True) or {}
    bars: List[Dict] = data.get("bars", [])
    if not isinstance(bars, list) or not bars:
        return _error("no_bars", 400)
    try:
        tf_sec = int(data.get("tf_sec", 900))
    except Exception:
        return _error("invalid tf_sec", 400)

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
        return _error(str(e), 500)

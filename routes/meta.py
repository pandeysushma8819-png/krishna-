from __future__ import annotations
from flask import Blueprint, request, jsonify
from typing import List, Dict
from meta.regime import classify_latest
from meta.anomaly import detect_anomalies, decide_guard

meta_bp = Blueprint("meta", __name__)

@meta_bp.route("/meta/ping")
def ping():
    return jsonify(ok=True, msg="meta alive")

@meta_bp.route("/meta/scan", methods=["POST"])
def scan():
    """
    Body:
      {
        "bars": [ {ts,open,high,low,close,volume}, ... ],
        "tf_sec": 900
      }
    """
    try:
        data = request.get_json(force=True) or {}
        bars: List[Dict] = data.get("bars", [])
        tf_sec = int(data.get("tf_sec", 900))
        if not bars:
            return jsonify(ok=False, error="no_bars"), 400
        regime, snap = classify_latest(bars, tf_sec)
        anomalies = detect_anomalies(bars, tf_sec)
        guard = decide_guard(regime, anomalies)
        return jsonify(ok=True, regime=regime, snap=snap, anomalies=anomalies, guard=guard)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500

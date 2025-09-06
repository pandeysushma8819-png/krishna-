# routes/ops.py
from __future__ import annotations
from typing import Any
from flask import Blueprint, request, jsonify
from ops.acceptance import acceptance_check

ops_bp = Blueprint("ops", __name__)

@ops_bp.get("/ops/ping")
def ping() -> Any:
    return jsonify(ok=True, msg="ops alive")

@ops_bp.get("/ops/acceptance")
def acceptance() -> Any:
    try:
        period = request.args.get("period", "daily").strip().lower()
        if period not in ("daily","weekly"):
            period = "daily"
        out = acceptance_check(period)
        return jsonify(out)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500

@ops_bp.post("/ops/soak/start")
def soak_start() -> Any:
    """
    Paper soak helper: we do not toggle live approval directly here
    (that is handled by /exec/approve_live). We just return a recommended plan.
    """
    plan = {
      "steps": [
        "POST /exec/approve_live {\"on\": false}   # keep live OFF",
        "Ensure TradingView alerts are firing to /tv_alert",
        "Signals intake ON (via Telegram /signals or control)",
        "Monitor /report/daily and /ops/acceptance?period=daily"
      ]
    }
    return jsonify(ok=True, plan=plan)

@ops_bp.post("/ops/soak/stop")
def soak_stop() -> Any:
    plan = {
      "steps": [
        "Turn signals OFF",
        "POST /exec/approve_live {\"on\": false}   # keep live OFF",
        "Tag repo last-good; archive reports; run /dr/snapshot"
      ]
    }
    return jsonify(ok=True, plan=plan)

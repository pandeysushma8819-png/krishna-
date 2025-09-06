# routes/exec.py
from __future__ import annotations
from typing import Any, Dict
from flask import Blueprint, request, jsonify
import os

from exec.om import submit_order, cancel_order, order_status, set_live_approval, get_control

exec_bp = Blueprint("exec", __name__)

@exec_bp.get("/exec/ping")
def ping() -> Any:
    return jsonify(ok=True, msg="exec alive", mode=(os.environ.get("RUN_MODE") or "shadow"))

@exec_bp.post("/exec/order/submit")
def order_submit() -> Any:
    try:
        payload: Dict[str, Any] = request.get_json(force=True, silent=False) or {}
        res = submit_order(payload, os.environ)
        code = 200 if res.get("ok") else 400
        return jsonify(res), code
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500

@exec_bp.post("/exec/order/cancel")
def order_cancel() -> Any:
    try:
        data: Dict[str, Any] = request.get_json(force=True) or {}
        order_id = str(data.get("order_id") or "")
        if not order_id:
            return jsonify(ok=False, error="order_id required"), 400
        res = cancel_order(order_id, os.environ)
        code = 200 if res.get("ok") else 400
        return jsonify(res), code
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500

@exec_bp.get("/exec/order/status")
def order_stat() -> Any:
    try:
        order_id = request.args.get("order_id", "")
        if not order_id:
            return jsonify(ok=False, error="order_id required"), 400
        res = order_status(order_id, os.environ)
        code = 200 if res.get("ok") else 400
        return jsonify(res), code
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500

# --- approval gate (owner-only) ---
def _is_owner(req) -> bool:
    # allow with shared secret header or TELEGRAM_OWNER_ID numeric id in query (for quick ops)
    want = os.environ.get("OWNER_SECRET") or os.environ.get("TELEGRAM_WEBHOOK_SECRET") or ""
    got  = req.headers.get("X-Owner-Token", "")
    if want and got and got == want:
        return True
    # fallback: not strong; use only for quick local ops
    return False

@exec_bp.post("/exec/approve_live")
def approve_live() -> Any:
    try:
        if not _is_owner(request):
            return jsonify(ok=False, error="unauthorized"), 403
        body = request.get_json(force=True) or {}
        on = bool(body.get("on", False))
        st = set_live_approval(on, by="exec_api")
        return jsonify(ok=True, control=st)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500

@exec_bp.get("/exec/control")
def control_state() -> Any:
    try:
        return jsonify(ok=True, control=get_control(), mode=(os.environ.get("RUN_MODE") or "shadow"))
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500

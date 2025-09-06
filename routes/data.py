# routes/data.py
from __future__ import annotations
from typing import Any
from flask import Blueprint, request, jsonify

from data.router import get_bars, data_status

data_bp = Blueprint("data", __name__)

@data_bp.get("/data/ping")
def ping() -> Any:
    st = data_status()
    return jsonify(ok=True, msg="data alive", status=st)

@data_bp.get("/data/mode")
def mode() -> Any:
    return jsonify(ok=True, status=data_status())

@data_bp.get("/data/bars")
def bars() -> Any:
    try:
        symbol = request.args.get("symbol", "").strip()
        tf_sec = int(request.args.get("tf_sec", "900"))
        limit  = int(request.args.get("limit", "200"))
        if not symbol:
            return jsonify(ok=False, error="symbol required"), 400
        rows = get_bars(symbol, tf_sec, limit)
        return jsonify(ok=True, symbol=symbol.upper(), tf_sec=tf_sec, rows=rows, count=len(rows))
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500

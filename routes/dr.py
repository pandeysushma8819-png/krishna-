# routes/dr.py
from __future__ import annotations
from typing import Any
from flask import Blueprint, request, jsonify

from integrations.sheets_backup import snapshot_tabs, cleanup_old_snapshots, restore_check

dr_bp = Blueprint("dr", __name__)

@dr_bp.get("/dr/ping")
def ping() -> Any:
    return jsonify(ok=True, msg="dr alive")

@dr_bp.post("/dr/snapshot")
def dr_snapshot() -> Any:
    try:
        tabs_q = request.args.get("tabs", "").strip()
        tabs = [t.strip() for t in tabs_q.split(",") if t.strip()] if tabs_q else None
        out = snapshot_tabs(tabs)
        return jsonify(out)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500

@dr_bp.post("/dr/cleanup")
def dr_cleanup() -> Any:
    try:
        rd = int(request.args.get("retention_days", "14"))
        out = cleanup_old_snapshots(retention_days=rd)
        return jsonify(out)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500

@dr_bp.get("/dr/restore_test")
def dr_restore_test() -> Any:
    try:
        n = int(request.args.get("sample_rows", "5"))
        out = restore_check(sample_rows=n)
        return jsonify(out)
    except Exception as e:
        return jsonify(ok=False, error=str(e)), 500

from __future__ import annotations
from flask import Blueprint, request, jsonify
from typing import Any, Dict
import os, json, hmac, hashlib, time

# Sheets append funcs; no class import (avoids import errors)
from integrations import sheets

tv_bp = Blueprint("tv", __name__)

# in-memory duplicate drop (per process)
_last_seen: Dict[str, float] = {}
RT_WINDOW = float(os.environ.get("TV_RATE_WINDOW_SEC", "1.5"))

def _env_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return str(v).strip().lower() in {"1", "true", "yes", "on"}

def _secret() -> str:
    return os.environ.get("TRADINGVIEW_WEBHOOK_SECRET", "")

def _verify_hmac(raw: bytes) -> bool:
    sig = request.headers.get("X-TV-Signature", "").strip().lower()
    if not sig:
        return False
    expect = hmac.new(_secret().encode(), raw, hashlib.sha256).hexdigest()
    return hmac.compare_digest(sig, expect)

@tv_bp.route("/tv_alert", methods=["POST"])
def tv_alert() -> Any:
    raw = request.get_data()
    try:
        payload = json.loads(raw.decode() or "{}")
    except Exception:
        return jsonify(ok=False, error="bad_json"), 400

    # Auth
    if _env_bool("HMAC_REQUIRED", False):
        if not _verify_hmac(raw):
            return jsonify(ok=False, error="auth_failed: bad_signature"), 401
    else:
        sec = _secret()
        if sec and payload.get("secret") != sec:
            return jsonify(ok=False, error="auth_failed: bad_secret"), 401

    # Required fields
    symbol = str(payload.get("symbol", "")).upper()
    tf     = str(payload.get("tf", ""))
    try:
        ts = int(payload.get("ts", 0))
    except Exception:
        ts = 0
    uid    = str(payload.get("id", ""))

    if not (symbol and tf and ts):
        return jsonify(ok=False, error="missing_fields"), 400

    # Idempotent hash for duplicate drop
    base = f"{symbol}|{tf}|{ts}|{uid}"
    sig  = hashlib.sha256(base.encode()).hexdigest()

    now = time.time()
    last = _last_seen.get(sig, 0.0)
    if now - last < RT_WINDOW:
        return jsonify(ok=True, duplicate=True, hash=sig, sheet_logged=False)
    _last_seen[sig] = now

    # Log to Sheets (best-effort)
    sheet_ok = False
    try:
        sheet_ok = sheets.append_signal({
            "symbol": symbol, "tf": tf, "ts": ts, "id": uid, "hash": sig
        })
    except Exception:
        sheet_ok = False

    return jsonify(ok=True, hash=sig, sheet_logged=sheet_ok)

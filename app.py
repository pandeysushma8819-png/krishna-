# app.py
from __future__ import annotations
import os
import time
import logging
from typing import Any, Dict
from flask import Flask, jsonify

# ---------- helpers ----------
def _read_bool(name: str, default: bool = False) -> bool:
    v = os.environ.get(name)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")

def _read_float(name: str, default: float = 0.0) -> float:
    try:
        return float(os.environ.get(name, default))
    except Exception:
        return float(default)

def _now_utc_str() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

def _now_ist_str() -> str:
    # IST = UTC + 5h30m = 19800 sec
    return time.strftime("%Y-%m-%d %H:%M:%S IST", time.gmtime(time.time() + 19800))

def _status_payload() -> Dict[str, Any]:
    budget_cap = _read_float("OPENAI_BUDGET_USD", 23.0)
    budget_used = _read_float("OPENAI_BUDGET_USED", 0.0)
    return {
        "app": os.environ.get("APP_NAME", "krishna-trade-worker"),
        "utc": _now_utc_str(),
        "ist": _now_ist_str(),
        "budget_cap": budget_cap,
        "budget_used": budget_used,
        "budget_remaining": max(0.0, budget_cap - budget_used),
        "flags": {
            "weekend_backtest_only": _read_bool("WEEKEND_BACKTEST_ONLY", True),
            "budget_guard_enabled": _read_bool("BUDGET_GUARD_ENABLED", True),
            "ntp_check_enabled": _read_bool("NTP_CHECK_ENABLED", True),
            "hmac_required": _read_bool("HMAC_REQUIRED", False),
        },
    }

# ---------- factory ----------
def create_app() -> Flask:
    app = Flask(__name__)
    app.config["JSON_AS_ASCII"] = False

    # root: lightweight status
    @app.get("/")
    def root():
        return jsonify(_status_payload())

    log = app.logger or logging.getLogger(__name__)

    # P9: meta blueprint
    try:
        from routes.meta import meta_bp
        app.register_blueprint(meta_bp)
    except Exception as e:
        log.warning("[boot] meta_bp not loaded: %s", e)

    # P10: risk blueprint
    try:
        from routes.risk import risk_bp
        app.register_blueprint(risk_bp)
    except Exception as e:
        log.warning("[boot] risk_bp not loaded: %s", e)

    # Optional blueprints (present if earlier phases committed)
    try:
        from routes.health import health_bp  # type: ignore
        app.register_blueprint(health_bp)
    except Exception as e:
        log.warning("[boot] health_bp not loaded: %s", e)

    try:
        from routes.tv import tv_bp  # type: ignore
        app.register_blueprint(tv_bp)
    except Exception as e:
        log.warning("[boot] tv_bp not loaded: %s", e)

    try:
        from routes.telegram import telegram_bp  # type: ignore
        app.register_blueprint(telegram_bp)
    except Exception as e:
        log.warning("[boot] telegram_bp not loaded: %s", e)

    return app

# WSGI app (Flask)
app = create_app()

# ASGI wrapper for uvicorn
try:
    from asgiref.wsgi import WsgiToAsgi
    asgi_app = WsgiToAsgi(app)  # use this in Render start command
except Exception:
    # fallback: expose same name so imports don't break (WSGI)
    asgi_app = app

if __name__ == "__main__":
    # local dev
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", "8000")), debug=True)

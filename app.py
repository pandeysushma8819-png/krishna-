# app.py
from __future__ import annotations
import os, time, json, socket
from typing import Dict, Any
from flask import Flask, jsonify
from werkzeug.middleware.proxy_fix import ProxyFix

APP_NAME = os.getenv("APP_NAME", "krishna-trade-worker")

def _bool(env_name: str, default: bool = False) -> bool:
    v = os.getenv(env_name)
    if v is None:
        return default
    return str(v).strip().lower() in ("1", "true", "yes", "on")

def _now_utc_str() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

def _now_ist_str() -> str:
    # IST = UTC + 5:30, no DST
    return time.strftime("%Y-%m-%d %H:%M:%S IST", time.gmtime(time.time() + 19800))

def _flags() -> Dict[str, Any]:
    # Same names you see in /healthz to avoid confusion
    return {
        "weekend_backtest_only": _bool("WEEKEND_BACKTEST_ONLY", True),
        "budget_guard_enabled": _bool("BUDGET_GUARD", True) or bool(os.getenv("OPENAI_BUDGET_USD")),
        "ntp_check_enabled": _bool("NTP_CHECK", True),
        # TradingView webhook HMAC: set TV_HMAC_REQUIRED=true to require X-TV-Signature
        "hmac_required": _bool("TV_HMAC_REQUIRED", False),
    }

def _budget() -> Dict[str, float]:
    cap = float(os.getenv("OPENAI_BUDGET_USD", "23") or 23)
    # If you persist usage elsewhere, read and show. Here we just expose 0 used.
    used = float(os.getenv("OPENAI_BUDGET_USED", "0") or 0)
    remain = max(0.0, cap - used)
    return {"budget_cap": cap, "budget_used": used, "budget_remaining": remain}

def create_app() -> Flask:
    app = Flask(__name__)
    # Render / proxies
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_port=1)

    @app.get("/")
    def root():
        """Lightweight ping with status (mirrors style of /healthz header)."""
        b = _budget()
        return jsonify(
            ok=True,
            app=APP_NAME,
            host=socket.gethostname(),
            utc=_now_utc_str(),
            ist=_now_ist_str(),
            **b,
            flags=_flags(),
        )

    # ------------------ Blueprint registrations ------------------
    # P1: TradingView webhook + health
    try:
        from routes.health import health_bp  # expected to expose /healthz and counters
        app.register_blueprint(health_bp)
    except Exception as e:
        app.logger.warning(f"[boot] health_bp not loaded: {e}")

    try:
        from routes.tv import tv_bp  # expected to expose /tv_alert (POST)
        app.register_blueprint(tv_bp)
    except Exception as e:
        app.logger.warning(f"[boot] tv_bp not loaded: {e}")

    # P4: Telegram control webhook (/telegram/<hook>)
    try:
        from routes.telegram import telegram_bp
        app.register_blueprint(telegram_bp)
    except Exception as e:
        app.logger.warning(f"[boot] telegram_bp not loaded: {e}")

    # P9: Meta-model & anomaly guard (/meta/*)
    try:
        from routes.meta import meta_bp
        app.register_blueprint(meta_bp)
    except Exception as e:
        app.logger.warning(f"[boot] meta_bp not loaded: {e}")

    # Optional: CORS for local tests or cross-origin dashboards
    if _bool("ENABLE_CORS", False):
        try:
            from flask_cors import CORS
            CORS(app, resources={r"/*": {"origins": "*"}})
            app.logger.info("CORS enabled (all origins)")
        except Exception as e:
            app.logger.warning(f"ENABLE_CORS set but flask-cors missing: {e}")

    return app


app = create_app()

if __name__ == "__main__":
    port = int(os.getenv("PORT", "10000"))
    app.run(host="0.0.0.0", port=port)

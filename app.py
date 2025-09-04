# app.py — P2 server: /tv_alert + /healthz + schedulers
from __future__ import annotations
import os, yaml, asyncio
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from utils.time_utils import now_utc, now_ist, fmt
from utils.budget_guard import BudgetGuard
from utils.metrics import METRICS, snapshot_metrics
from routes.tv import tv_alert
from policy.state import POLICY
from scheduling.jobs import start_background

def load_settings(path: str = "config/settings.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

async def root(request):
    return JSONResponse({"ok": True, "msg": "KTW P2 running. Endpoints: /tv_alert (POST), /healthz (GET)"})

async def healthz(request):
    cfg = load_settings()
    cap = float(os.getenv("OPENAI_BUDGET_USD", cfg["budget"]["openai_budget_usd"]))
    guard = BudgetGuard(cap, cfg["budget"]["hard_stop"], cfg["budget"]["state_path"])
    metrics = snapshot_metrics()
    policy = POLICY.snapshot()
    return JSONResponse({
        "status": "ok",
        "app": cfg["app"]["name"],
        "utc": fmt(now_utc()),
        "ist": fmt(now_ist()),
        "budget_cap": float(cap),
        "budget_used": float(guard.usage()),
        "budget_remaining": float(guard.remaining()),
        "flags": cfg.get("feature_flags", {}),
        "metrics": metrics,
        "policy": policy,
    })

routes = [
    Route("/", root),
    Route("/healthz", healthz),
    Route("/tv_alert", tv_alert, methods=["POST"]),
]

app = Starlette(debug=False, routes=routes)

# kick off background tasks on startup
@app.on_event("startup")
async def _startup():
    app.state.bg_task = asyncio.create_task(start_background())

@app.on_event("shutdown")
async def _shutdown():
    t = getattr(app.state, "bg_task", None)
    if t:
        t.cancel()

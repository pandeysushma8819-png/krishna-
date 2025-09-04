# app.py — P0 stub server (Render health only, no FastAPI/Pydantic)
from __future__ import annotations
import os, yaml
from starlette.applications import Starlette
from starlette.responses import JSONResponse
from starlette.routing import Route
from utils.time_utils import now_utc, now_ist, fmt
from utils.budget_guard import BudgetGuard

def load_settings(path: str = "config/settings.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

async def root(request):
    return JSONResponse({"ok": True, "msg": "KTW P0 stub running. See /healthz."})

async def healthz(request):
    cfg = load_settings()
    cap = float(os.getenv("OPENAI_BUDGET_USD", cfg["budget"]["openai_budget_usd"]))
    guard = BudgetGuard(cap, cfg["budget"]["hard_stop"], cfg["budget"]["state_path"])
    return JSONResponse({
        "status": "ok",
        "app": cfg["app"]["name"],
        "utc": fmt(now_utc()),
        "ist": fmt(now_ist()),
        "budget_cap": float(cap),
        "budget_used": float(guard.usage()),
        "budget_remaining": float(guard.remaining()),
        "flags": cfg.get("feature_flags", {}),
    })

routes = [
    Route("/", root),
    Route("/healthz", healthz),
]

app = Starlette(debug=False, routes=routes)

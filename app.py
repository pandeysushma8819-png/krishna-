# app.py — P0 stub server (Render health only)
from __future__ import annotations
from fastapi import FastAPI
from pydantic import BaseModel
import os, yaml
from utils.time_utils import now_utc, now_ist, fmt
from utils.budget_guard import BudgetGuard

app = FastAPI(title="KTW P0 Stub")

def load_settings(path: str = "config/settings.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

class HealthResp(BaseModel):
    status: str
    app: str
    utc: str
    ist: str
    budget_cap: float
    budget_used: float
    budget_remaining: float
    flags: dict

@app.get("/")
def root():
    return {"ok": True, "msg": "KTW P0 stub running. See /healthz."}

@app.get("/healthz", response_model=HealthResp)
def healthz():
    cfg = load_settings()
    cap = float(os.getenv("OPENAI_BUDGET_USD", cfg["budget"]["openai_budget_usd"]))
    guard = BudgetGuard(cap, cfg["budget"]["hard_stop"], cfg["budget"]["state_path"])
    return HealthResp(
        status="ok",
        app=cfg["app"]["name"],
        utc=fmt(now_utc()),
        ist=fmt(now_ist()),
        budget_cap=float(cap),
        budget_used=float(guard.usage()),
        budget_remaining=float(guard.remaining()),
        flags=cfg.get("feature_flags", {}),
    )

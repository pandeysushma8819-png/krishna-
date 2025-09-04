# scheduling/holiday_gate.py — holiday halt using config/calendars.yaml
from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo
import yaml, os

IST = ZoneInfo("Asia/Kolkata")

def _load_calendars(path: str = "config/calendars.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def holiday_reason(markets_csv: str, now_ist: datetime | None = None, cfg: dict | None = None) -> tuple[bool, str]:
    now_ist = (now_ist or datetime.now(IST)).astimezone(IST)
    date_str = now_ist.strftime("%Y-%m-%d")
    cfg = cfg or _load_calendars()
    mkt_map = (cfg.get("markets") or {})
    active = []
    for m in [m.strip().upper() for m in (markets_csv or "").split(",") if m.strip()]:
        days = [d.strip() for d in mkt_map.get(m, [])]
        if date_str in days:
            active.append(m)
    if active:
        return True, f"holiday:{','.join(active)}@{date_str}"
    return False, ""

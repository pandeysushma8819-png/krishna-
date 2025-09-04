# scheduling/news_freeze.py — time-window freezes from config/policy.yaml
from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo
import yaml

def _load_policy(path: str = "config/policy.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def _to_utc(dt_str: str, tz_name: str) -> datetime:
    # dt_str: "YYYY-MM-DD HH:MM"
    local = datetime.strptime(dt_str, "%Y-%m-%d %H:%M")
    z = ZoneInfo(tz_name)
    return local.replace(tzinfo=z).astimezone(ZoneInfo("UTC"))

def active_freeze(now_utc: datetime | None = None, cfg: dict | None = None) -> tuple[bool, str]:
    cfg = cfg or _load_policy()
    now_utc = now_utc or datetime.utcnow().astimezone(ZoneInfo("UTC"))
    for w in (cfg.get("news_freezes") or []):
        try:
            tz = w.get("tz") or "UTC"
            start = _to_utc(w["start"], tz)
            end = _to_utc(w["end"], tz)
            if start <= now_utc <= end:
                return True, str(w.get("tag") or "FREEZE")
        except Exception:
            continue
    return False, ""

def next_weekly_digest_utc(cfg: dict | None = None) -> datetime:
    cfg = cfg or _load_policy()
    tz = ZoneInfo( (cfg.get("weekly_digest") or {}).get("tz") or "Asia/Kolkata" )
    weekday = int( (cfg.get("weekly_digest") or {}).get("weekday") or 6 )
    hour = int( (cfg.get("weekly_digest") or {}).get("hour") or 18 )
    minute = int( (cfg.get("weekly_digest") or {}).get("minute") or 0 )

    now = datetime.now(tz)
    # find next desired weekday/hour/minute
    days_ahead = (weekday - now.weekday()) % 7
    candidate = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    if days_ahead == 0 and candidate <= now:
        days_ahead = 7
    target_local = (candidate if days_ahead == 0 else (candidate + timedelta(days=days_ahead)))
    return target_local.astimezone(ZoneInfo("UTC"))

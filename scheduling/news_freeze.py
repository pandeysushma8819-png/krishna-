from __future__ import annotations
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
import yaml

def _load_policy(path: str = "config/policy.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f) or {}

def _to_utc(dt_str: str, tz_name: str) -> datetime:
    # dt_str format: "YYYY-MM-DD HH:MM"
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
    wd = cfg.get("weekly_digest") or {}
    tz = ZoneInfo(wd.get("tz") or "Asia/Kolkata")
    weekday = int(wd.get("weekday", 6))   # 0=Mon ... 6=Sun
    hour = int(wd.get("hour", 18))
    minute = int(wd.get("minute", 0))

    now = datetime.now(tz)
    target = now.replace(hour=hour, minute=minute, second=0, microsecond=0)
    days_ahead = (weekday - now.weekday()) % 7
    if days_ahead == 0 and target <= now:
        days_ahead = 7
    target_local = target + timedelta(days=days_ahead)
    return target_local.astimezone(ZoneInfo("UTC"))

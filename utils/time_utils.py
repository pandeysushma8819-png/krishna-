from __future__ import annotations
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

IST_TZ = ZoneInfo("Asia/Kolkata")

def now_utc() -> datetime:
    return datetime.now(timezone.utc)

def now_ist() -> datetime:
    return now_utc().astimezone(IST_TZ)

def fmt(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S %Z")

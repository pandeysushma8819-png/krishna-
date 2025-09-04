from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

def is_weekend_ist(now: datetime | None = None) -> bool:
    now = (now or datetime.now(IST)).astimezone(IST)
    # Monday=0 ... Sunday=6
    return now.weekday() >= 5  # Sat(5) or Sun(6)

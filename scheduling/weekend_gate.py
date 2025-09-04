# scheduling/weekend_gate.py — weekend detector (IST)
from __future__ import annotations
from datetime import datetime
from zoneinfo import ZoneInfo

IST = ZoneInfo("Asia/Kolkata")

def is_weekend_ist(now: datetime | None = None) -> bool:
    now = (now or datetime.now(IST)).astimezone(IST)
    # Saturday=5, Sunday=6 in Python's weekday()
    return now.weekday() >= 5

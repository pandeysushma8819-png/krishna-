# policy/state.py — global policy flags + snapshot
from __future__ import annotations
import threading, time
from dataclasses import dataclass, asdict

@dataclass
class PolicyFlags:
    weekend_on: bool = False
    holiday_halt: bool = False
    holiday_reason: str = ""
    freeze_on: bool = False
    freeze_tag: str = ""
    updated_ts: int = 0

class _State:
    def __init__(self):
        self._lock = threading.Lock()
        self.flags = PolicyFlags()

    def set_weekend(self, on: bool) -> bool:
        with self._lock:
            changed = (self.flags.weekend_on != on)
            if changed:
                self.flags.weekend_on = on
                self.flags.updated_ts = int(time.time())
            return changed

    def set_holiday(self, on: bool, reason: str = "") -> bool:
        with self._lock:
            changed = (self.flags.holiday_halt != on or self.flags.holiday_reason != reason)
            if changed:
                self.flags.holiday_halt = on
                self.flags.holiday_reason = reason if on else ""
                self.flags.updated_ts = int(time.time())
            return changed

    def set_freeze(self, on: bool, tag: str = "") -> bool:
        with self._lock:
            changed = (self.flags.freeze_on != on or self.flags.freeze_tag != tag)
            if changed:
                self.flags.freeze_on = on
                self.flags.freeze_tag = tag if on else ""
                self.flags.updated_ts = int(time.time())
            return changed

    def snapshot(self) -> dict:
        with self._lock:
            return asdict(self.flags)

POLICY = _State()

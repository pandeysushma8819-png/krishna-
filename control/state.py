from __future__ import annotations
import threading, time
from dataclasses import dataclass, asdict

@dataclass
class ControlFlags:
    panic_on: bool = False          # kill-switch blocks new entries
    approved_live: bool = False     # live approval gate (used in later phases)
    signals_on: bool = True         # intake allowed?
    updated_ts: int = 0
    updated_by: str = ""

class _Control:
    def __init__(self):
        self._lock = threading.Lock()
        self.flags = ControlFlags()

    def set_panic(self, on: bool, who: str = "sys") -> bool:
        with self._lock:
            changed = (self.flags.panic_on != on)
            if changed:
                self.flags.panic_on = on
                self.flags.updated_ts = int(time.time())
                self.flags.updated_by = who
            return changed

    def set_approved(self, on: bool, who: str = "sys") -> bool:
        with self._lock:
            changed = (self.flags.approved_live != on)
            if changed:
                self.flags.approved_live = on
                self.flags.updated_ts = int(time.time())
                self.flags.updated_by = who
            return changed

    def set_signals(self, on: bool, who: str = "sys") -> bool:
        with self._lock:
            changed = (self.flags.signals_on != on)
            if changed:
                self.flags.signals_on = on
                self.flags.updated_ts = int(time.time())
                self.flags.updated_by = who
            return changed

    def snapshot(self) -> dict:
        with self._lock:
            return asdict(self.flags)

CONTROL = _Control()

# utils/lease_status.py — in-process shared lease state
from __future__ import annotations
import threading, time
from dataclasses import dataclass, asdict

@dataclass
class LeaseInfo:
    lease_owner: str = ""
    heartbeat_ts: int = 0
    lease_ttl_sec: int = 45
    host_id: str = ""
    host_kind: str = ""
    mode: str = "passive"  # "active" or "passive"
    updated_ts: int = 0

class _LeaseState:
    def __init__(self):
        self._lock = threading.Lock()
        self.info = LeaseInfo()

    def set(self, **kwargs):
        with self._lock:
            for k, v in kwargs.items():
                setattr(self.info, k, v)
            self.info.updated_ts = int(time.time())

    def snapshot(self) -> dict:
        with self._lock:
            return asdict(self.info)

    def is_active(self) -> bool:
        with self._lock:
            return self.info.mode == "active" and self.info.lease_owner == self.info.host_id

LEASE = _LeaseState()

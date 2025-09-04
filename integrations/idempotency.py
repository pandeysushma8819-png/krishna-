# integrations/idempotency.py
from __future__ import annotations
import hashlib, time, random

def idem_hash(symbol: str, tf: str, ts: str, sid: str, raw: bytes) -> str:
    base = f"{symbol}|{tf}|{ts}|{sid}".encode("utf-8")
    h = hashlib.sha256()
    h.update(base)
    h.update(b"|")
    h.update(raw or b"")
    return h.hexdigest()

class IdempotencyTTL:
    def __init__(self, ttl_sec: int = 300, max_size: int = 5000):
        self.ttl = ttl_sec
        self.max = max_size
        self._store: dict[str, float] = {}

    def _gc(self):
        now = time.monotonic()
        if len(self._store) > self.max:
            # drop old items
            keys = sorted(self._store, key=lambda k: self._store[k])[: len(self._store)//4 ]
            for k in keys:
                self._store.pop(k, None)
        # ttl cleanup (cheap)
        for k, exp in list(self._store.items()):
            if exp < now:
                self._store.pop(k, None)

    def seen(self, key: str) -> bool:
        self._gc()
        return key in self._store

    def remember(self, key: str) -> None:
        self._gc()
        self._store[key] = time.monotonic() + self.ttl

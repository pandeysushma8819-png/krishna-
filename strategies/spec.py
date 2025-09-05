from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Dict, Any
import json, hashlib, time

@dataclass
class StrategySpec:
    strategy_id: str                # e.g., "ema_cross", "rsi_reversion"
    params: Dict[str, Any]          # hyperparams
    seed: int = 0                   # for stochastic generators
    window: str = ""                # e.g., "2024-01-01..2024-06-30"
    version: str = ""               # auto: hash of (strategy_id+params+seed)

    def materialize(self) -> "StrategySpec":
        if not self.version:
            h = hashlib.sha256(json.dumps({
                "sid": self.strategy_id,
                "params": self.params,
                "seed": self.seed
            }, sort_keys=True).encode("utf-8")).hexdigest()[:12]
            self.version = f"v{int(time.time())}-{h}"
        return self

    def to_json(self) -> str:
        return json.dumps(asdict(self), separators=(",",":"), ensure_ascii=False)

    @staticmethod
    def from_json(s: str) -> "StrategySpec":
        obj = json.loads(s)
        return StrategySpec(**obj)

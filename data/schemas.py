from __future__ import annotations
from dataclasses import dataclass
from typing import List, Dict, Literal

BarDict = Dict[str, float]  # keys: ts, open, high, low, close, volume

@dataclass
class Bar:
    ts: int         # epoch seconds (UTC)
    open: float
    high: float
    low: float
    close: float
    volume: float = 0.0

ActionType = Literal["split","dividend"]

@dataclass
class CorporateAction:
    ts: int              # action timestamp (session close of prior day recommended)
    type: ActionType
    value: float         # split: ratio (e.g., 2.0 for 1:2); dividend: cash per share

def to_bar_dict(b: Bar) -> BarDict:
    return {"ts": b.ts, "open": b.open, "high": b.high, "low": b.low, "close": b.close, "volume": b.volume}

# data/providers/base.py
from __future__ import annotations
from typing import List, Dict, Any

class BaseDataProvider:
    name: str = "base"

    def is_available(self) -> bool:
        """Return True if provider is configured & can be used (keys, etc.)."""
        return True

    def get_bars(self, symbol: str, tf_sec: int, limit: int = 200) -> List[Dict[str, Any]]:
        """
        Return list of bars (oldest→newest). Each bar:
          {"ts": <epoch_sec>, "open": float, "high": float, "low": float, "close": float, "volume": float}
        """
        raise NotImplementedError

from __future__ import annotations
import os, json
from datetime import datetime

DEFAULT_STATE_PATH = os.getenv("BUDGET_STATE_PATH", "data/budget_state.json")

class BudgetGuard:
    def __init__(self, cap_usd: float, hard_stop: bool = True, state_path: str = DEFAULT_STATE_PATH):
        self.cap = float(cap_usd or 0)
        self.hard_stop = bool(hard_stop)
        self.path = state_path
        self.state = self._load()

    def _month_key(self) -> str:
        return datetime.utcnow().strftime("%Y-%m")

    def _load(self) -> dict:
        try:
            with open(self.path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}

    def _save(self) -> None:
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(self.state, f, indent=2)

    def usage(self) -> float:
        return float(self.state.get(self._month_key(), 0.0))

    def remaining(self) -> float:
        return max(0.0, self.cap - self.usage())

    def allow(self, cost: float) -> bool:
        if self.cap <= 0:
            return True
        if self.usage() + cost <= self.cap:
            return True
        return not self.hard_stop  # if soft mode, allow but warn (later)

    def add(self, cost: float) -> None:
        key = self._month_key()
        self.state[key] = round(self.usage() + float(cost), 4)
        self._save()

# risk/cooldown.py
from __future__ import annotations
from typing import Dict, List, Literal
import time

Outcome = Literal["sl", "tp", "flat"]

_state: Dict[str, dict] = {}
# shape: { symbol: {"hits": [ts,...], "cooldown_until": ts} }

def is_in_cooldown(symbol: str, now_ts: int | None = None) -> tuple[bool, int]:
    now = int(now_ts or time.time())
    st = _state.get(symbol) or {}
    until = int(st.get("cooldown_until") or 0)
    return (now < until, max(0, until - now))

def _prune_hits(hits: List[int], window_sec: int, now: int) -> List[int]:
    cap_t = now - window_sec
    return [t for t in hits if t >= cap_t]

def on_trade_outcome(symbol: str, outcome: Outcome, *,
                     cooldown_hits: int, window_min: int, pause_min: int,
                     now_ts: int | None = None) -> dict:
    """
    Record trade outcome; return current state.
    - sl  => count towards losing streak within window
    - tp/flat => reset streak
    """
    now = int(now_ts or time.time())
    st = _state.setdefault(symbol, {"hits": [], "cooldown_until": 0})

    if outcome == "sl":
        st["hits"] = _prune_hits(st.get("hits", []), window_min * 60, now)
        st["hits"].append(now)
        if len(st["hits"]) >= cooldown_hits:
            st["cooldown_until"] = now + pause_min * 60
            st["hits"].clear()
    else:
        # reset on win/flat
        st["hits"].clear()

    return {"cooldown_until": st["cooldown_until"], "hits": list(st["hits"])}

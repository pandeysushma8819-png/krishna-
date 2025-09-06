# data/router.py
from __future__ import annotations
from typing import List, Dict, Any
import os, time

from data.providers.base import BaseDataProvider
from data.providers.binance import PROVIDER as BINANCE
from data.providers.polygon import PROVIDER as POLYGON
from data.providers.dummy import PROVIDER as DUMMY

_PROVIDERS = {
    "binance": BINANCE,
    "polygon": POLYGON,
    "dummy": DUMMY,
}

_STATE: Dict[str, Any] = {
    "chain": [],
    "active": "",
    "last_error": "",
    "safe_mode": False,  # read-only signal; set via env
    "updated_ts": 0,
}

def _parse_chain(env: dict) -> List[str]:
    chain = (env.get("DATA_PROVIDER_CHAIN") or "binance,polygon,dummy").strip()
    items = [x.strip().lower() for x in chain.split(",") if x.strip()]
    return [x for x in items if x in _PROVIDERS] or ["dummy"]

def _set_state(active: str = "", err: str = ""):
    _STATE["active"] = active
    _STATE["last_error"] = err
    _STATE["updated_ts"] = int(time.time())
    _STATE["safe_mode"] = str(os.environ.get("DATA_SAFE_MODE","")).lower() in ("1","true","yes","on")

def data_status() -> Dict[str, Any]:
    _STATE["chain"] = _parse_chain(os.environ)
    _STATE["safe_mode"] = str(os.environ.get("DATA_SAFE_MODE","")).lower() in ("1","true","yes","on")
    return dict(_STATE)

def get_bars(symbol: str, tf_sec: int, limit: int = 200) -> List[Dict[str, Any]]:
    chain = _parse_chain(os.environ)
    last_err = ""
    for name in chain:
        prov: BaseDataProvider = _PROVIDERS[name]
        try:
            if not prov.is_available():
                last_err = f"{name}: not available"
                continue
            bars = prov.get_bars(symbol, tf_sec, limit)
            if not bars:
                last_err = f"{name}: 0 bars"
                continue
            _set_state(active=name, err="")
            if name != "dummy":
                # best-effort sheet status
                try:
                    from integrations import sheets
                    sheets.append_status("data_mode", {"active": name, "symbol": symbol, "tf_sec": tf_sec})
                except Exception:
                    pass
            return bars
        except Exception as e:
            last_err = f"{name}: {e}"
            continue
    _set_state(active="", err=last_err or "no provider ok")
    # log to sheets
    try:
        from integrations import sheets
        sheets.append_event({"kind":"data","tag":"fallback_failed","detail":_STATE,"source":"data"})
    except Exception:
        pass
    raise RuntimeError(_STATE["last_error"] or "data providers failed")

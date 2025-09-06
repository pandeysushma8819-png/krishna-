# exec/om.py
from __future__ import annotations
from typing import Dict, Any, Optional, Tuple
import time, math, hashlib, threading

from exec.broker import BROKERS, BaseBroker, Order, OrderResult

# ---- control / approval (in-proc; can be wired to Telegram later)
CONTROL = {
    "approved_live": False,
    "signals_on": True,
    "panic_on": False,
    "updated_ts": 0,
    "updated_by": "api",
}

def set_live_approval(on: bool, by: str = "api") -> Dict[str, Any]:
    CONTROL["approved_live"] = bool(on)
    CONTROL["updated_ts"] = int(time.time())
    CONTROL["updated_by"] = by
    return dict(CONTROL)

def get_control() -> Dict[str, Any]:
    return dict(CONTROL)

# ---- symbol meta / rounding
DEFAULT_TICK = 0.05
DEFAULT_LOT  = 1

TICK_TABLE = {}   # e.g., {"NIFTY": 0.05, "BANKNIFTY": 0.05}
LOT_TABLE  = {}   # e.g., {"NIFTY": 1}

def tick(symbol: str) -> float:
    return float(TICK_TABLE.get(symbol, DEFAULT_TICK))

def lot(symbol: str) -> int:
    return int(LOT_TABLE.get(symbol, DEFAULT_LOT))

def round_to_tick(px: float, symbol: str) -> float:
    t = tick(symbol)
    return round(math.floor(px / t + 0.5) * t, 10)

def round_qty(qty: float, symbol: str) -> int:
    l = lot(symbol)
    return int(max(l, int(qty // l) * l))

# ---- idem store
_IDEM: Dict[str, Dict[str, Any]] = {}
_LOCK = threading.Lock()

def _make_idem(payload: Dict[str, Any], key: Optional[str]) -> str:
    if key: return key
    raw = str(sorted(payload.items())).encode()
    return hashlib.sha256(raw).hexdigest()[:24]

def idem_get(key: str) -> Optional[Dict[str, Any]]:
    return _IDEM.get(key)

def idem_put(key: str, resp: Dict[str, Any]):
    with _LOCK:
        _IDEM[key] = resp

# ---- mode & broker helpers
def current_mode(env: Dict[str, str]) -> str:
    return (env.get("RUN_MODE") or "shadow").strip().lower()

def pick_broker(mode: str) -> Tuple[Optional[BaseBroker], str]:
    if mode == "paper":
        return BROKERS["paper"], "paper"
    if mode == "live":
        # placeholder; real broker later
        return None, "live"
    return None, "shadow"

# ---- Sheets audit (best-effort)
def _sheets_event(kind: str, detail: Dict[str, Any]):
    try:
        from integrations import sheets
        sheets.append_event({"kind": "exec", "tag": kind, "detail": detail, "source": "exec"})
    except Exception:
        pass

def _sheets_trade(symbol: str, side: str, qty: int, price: float, pnl: float = 0.0, fees: float = 0.0, slippage: float = 0.0, strategy_id: str = ""):
    try:
        from integrations import sheets
        sheets.append_trade({
            "symbol": symbol, "side": side, "qty": qty, "price": price,
            "pnl": pnl, "fees": fees, "slippage": slippage, "strategy_id": strategy_id
        })
    except Exception:
        pass

# ---- primary API
def submit_order(payload: Dict[str, Any], env: Dict[str, str]) -> Dict[str, Any]:
    """
    Expected payload fields:
      symbol, side("buy"/"sell"), type("MKT"/"LMT"/"SL"/"SL-M"), qty, price?, stop?,
      ref_price?(for paper MKT/LMT fills), idempotency_key?,
      oco: {"tp": {"type":"LMT","price":...}, "sl":{"type":"SL"|"SL-M","stop":..., "price"?}},
      strategy_id? (for audit)
    """
    mode = current_mode(env)
    idem_key = _make_idem(payload, payload.get("idempotency_key"))
    if (prev := idem_get(idem_key)) is not None:
        return {"ok": True, "idempotent": True, **prev}

    if CONTROL.get("panic_on"):
        resp = {"ok": False, "status": "rejected", "reason": "panic_on"}
        idem_put(idem_key, resp); return resp

    if mode == "live" and not CONTROL.get("approved_live"):
        resp = {"ok": False, "status": "rejected", "reason": "live_not_approved"}
        idem_put(idem_key, resp); return resp

    sym  = str(payload.get("symbol") or "").upper()
    side = str(payload.get("side") or "").lower()
    typ  = str(payload.get("type") or "MKT").upper()
    qty  = int(payload.get("qty") or 0)
    qty  = max(0, round_qty(qty, sym))
    if not (sym and side in ("buy","sell") and qty > 0):
        resp = {"ok": False, "status": "rejected", "reason": "bad_params"}
        idem_put(idem_key, resp); return resp

    # rounding of price/stop if present
    ref_price = float(payload.get("ref_price") or 0.0)
    price = payload.get("price")
    stop  = payload.get("stop")
    if isinstance(price, (int,float)): price = round_to_tick(float(price), sym)
    if isinstance(stop,  (int,float)): stop  = round_to_tick(float(stop),  sym)

    oco = payload.get("oco") or {}
    strategy_id = str(payload.get("strategy_id") or "")

    # shadow mode: only log + return synthetic id
    if mode == "shadow":
        oid = f"SH-{int(time.time())}"
        out = {"ok": True, "mode": mode, "order_id": oid, "status": "shadowed"}
        idem_put(idem_key, out)
        _sheets_event("shadow", {"symbol": sym, "side": side, "qty": qty, "type": typ, "price": price, "stop": stop, "oco": oco})
        return out

    brk, bname = pick_broker(mode)
    if bname == "live" and brk is None:
        resp = {"ok": False, "status": "rejected", "reason": "live_broker_not_configured"}
        idem_put(idem_key, resp); return resp

    # place parent
    order = Order(symbol=sym, side=side, type=typ, qty=qty,
                  price=float(price or 0.0), stop=float(stop or 0.0),
                  client_order_id=idem_key, meta={"ref_price": ref_price})
    res: OrderResult = brk.place(order)  # type: ignore

    result = {
        "ok": res.ok,
        "mode": bname,
        "order_id": res.order_id,
        "status": res.status,
        "filled_qty": res.filled_qty,
        "avg_price": res.avg_price,
    }

    # if filled and paper → write trade (no PnL here; that's P/L pipeline)
    if res.ok and res.status == "filled" and bname == "paper":
        _sheets_trade(sym, side, res.filled_qty, res.avg_price, strategy_id=strategy_id)

    # OCO children
    oco_ids = {}
    if res.ok and oco and bname in ("paper",):  # in paper we just register 'working'
        group = f"{res.order_id}-OCO"
        for key in ("tp","sl"):
            leg = oco.get(key)
            if not isinstance(leg, dict): continue
            ltyp  = str(leg.get("type") or ("LMT" if key=="tp" else "SL")).upper()
            lpx   = float(leg.get("price") or 0.0)
            lstp  = float(leg.get("stop")  or 0.0)
            if lpx:  lpx  = round_to_tick(lpx, sym)
            if lstp: lstp = round_to_tick(lstp, sym)
            child = Order(symbol=sym, side=("sell" if side=="buy" else "buy"),
                          type=ltyp, qty=qty, price=lpx, stop=lstp,
                          client_order_id=f"{idem_key}-{key}", oco_group=group,
                          meta={"ref_price": ref_price})
            cres = brk.place(child)  # type: ignore
            oco_ids[key] = {"order_id": cres.order_id, "status": cres.status}
        result["oco_ids"] = oco_ids

    idem_put(idem_key, result)
    _sheets_event("submit", {"mode": bname, **result})
    return result

def cancel_order(order_id: str, env: Dict[str, str]) -> Dict[str, Any]:
    mode = current_mode(env)
    if mode == "shadow":
        return {"ok": True, "mode": "shadow", "order_id": order_id, "status": "canceled"}
    brk, bname = pick_broker(mode)
    if bname == "live" and brk is None:
        return {"ok": False, "status": "rejected", "reason": "live_broker_not_configured"}
    res = brk.cancel(order_id)  # type: ignore
    out = {"ok": res.ok, "mode": bname, "order_id": res.order_id, "status": res.status}
    _sheets_event("cancel", out)
    return out

def order_status(order_id: str, env: Dict[str, str]) -> Dict[str, Any]:
    mode = current_mode(env)
    if mode == "shadow":
        return {"ok": True, "mode": "shadow", "order_id": order_id, "status": "unknown"}
    brk, bname = pick_broker(mode)
    if bname == "live" and brk is None:
        return {"ok": False, "status": "rejected", "reason": "live_broker_not_configured"}
    res = brk.status(order_id)  # type: ignore
    return {"ok": res.ok, "mode": bname, "order_id": res.order_id, "status": res.status,
            "filled_qty": res.filled_qty, "avg_price": res.avg_price}

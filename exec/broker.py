# exec/broker.py
from __future__ import annotations
from dataclasses import dataclass, asdict
from typing import Optional, Dict, Any, Tuple
import time
import itertools
import threading

_id_seq = itertools.count(1)
_lock = threading.Lock()

@dataclass
class Order:
    symbol: str
    side: str        # "buy" | "sell"
    type: str        # "MKT" | "LMT" | "SL" | "SL-M"
    qty: int
    price: float = 0.0
    stop: float = 0.0
    client_order_id: str = ""
    oco_group: Optional[str] = None   # parent group id for protective orders
    meta: Dict[str, Any] = None       # freeform

@dataclass
class OrderResult:
    ok: bool
    order_id: str
    status: str      # "accepted" | "filled" | "rejected" | "canceled" | "working"
    filled_qty: int
    avg_price: float
    reason: str = ""
    ts: int = 0

class BaseBroker:
    def place(self, order: Order) -> OrderResult:
        raise NotImplementedError
    def cancel(self, order_id: str) -> OrderResult:
        raise NotImplementedError
    def status(self, order_id: str) -> OrderResult:
        raise NotImplementedError

class PaperBroker(BaseBroker):
    """
    Super-simple simulator:
      - MKT fills at .meta['ref_price'] (or price if provided)
      - LMT fills immediately if ref_price crosses
      - SL / SL-M never auto-triggers here (use your engine/ticks to trigger);
        but for demo we treat SL/SL-M as 'working'.
      - OCO: only bookkeeping (pair ids under same group)
    """
    def __init__(self):
        self.orders: Dict[str, Dict[str, Any]] = {}

    def _new_id(self) -> str:
        with _lock:
            return f"PB-{next(_id_seq)}"

    def place(self, order: Order) -> OrderResult:
        ref = 0.0
        if order.meta and "ref_price" in order.meta:
            ref = float(order.meta["ref_price"])
        elif order.price:
            ref = float(order.price)

        oid = self._new_id()
        now = int(time.time())
        status = "working"
        filled = 0
        avg = 0.0

        # fill logic
        if order.type == "MKT":
            status = "filled"; filled = order.qty; avg = ref or order.price
        elif order.type == "LMT":
            # buy: if ref <= limit  |  sell: if ref >= limit
            if order.side == "buy" and ref and ref <= order.price:
                status = "filled"; filled = order.qty; avg = ref
            elif order.side == "sell" and ref and ref >= order.price:
                status = "filled"; filled = order.qty; avg = ref
            else:
                status = "working"; filled = 0; avg = 0.0
        elif order.type in ("SL", "SL-M"):
            status = "working"

        self.orders[oid] = {
            "order": asdict(order),
            "status": status,
            "filled_qty": filled,
            "avg_price": avg,
            "ts": now,
        }
        return OrderResult(True, oid, status, filled, avg, "", now)

    def cancel(self, order_id: str) -> OrderResult:
        now = int(time.time())
        o = self.orders.get(order_id)
        if not o:
            return OrderResult(False, order_id, "rejected", 0, 0.0, "not_found", now)
        if o["status"] in ("filled", "canceled"):
            return OrderResult(True, order_id, o["status"], o["filled_qty"], o["avg_price"], "", now)
        o["status"] = "canceled"
        return OrderResult(True, order_id, "canceled", o["filled_qty"], o["avg_price"], "", now)

    def status(self, order_id: str) -> OrderResult:
        now = int(time.time())
        o = self.orders.get(order_id)
        if not o:
            return OrderResult(False, order_id, "rejected", 0, 0.0, "not_found", now)
        return OrderResult(True, order_id, o["status"], o["filled_qty"], o["avg_price"], "", now)

BROKERS = {
    "paper": PaperBroker(),
    # real brokers later: "zerodha": ZerodhaBroker(...), etc.
}

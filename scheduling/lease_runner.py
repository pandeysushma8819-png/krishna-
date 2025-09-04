from __future__ import annotations
import asyncio, time, os
from utils.lease_status import LEASE
from utils.host import host_id, host_kind
from integrations.sheets import SheetsClient
from integrations.render_control import pause_render_if_enabled, resume_render_if_enabled
from utils.metrics import METRICS

HEARTBEAT_SEC = int(os.getenv("HEARTBEAT_SEC", "15"))
LEASE_TTL_SEC = int(os.getenv("LEASE_TTL_SEC", "45"))

_sheets = SheetsClient()
_MY_ID = host_id()
_KIND  = host_kind()

async def _try_acquire_or_refresh():
    now = int(time.time())
    status = _sheets.read_status() or {}
    owner = str(status.get("lease_owner") or "")
    hb    = int(status.get("heartbeat_ts") or 0)
    ttl   = int(status.get("lease_ttl_sec") or LEASE_TTL_SEC)
    expired = (now - hb) > ttl

    if not owner or expired or owner == _MY_ID:
        # Acquire or refresh
        new = {
            "lease_owner": _MY_ID,
            "heartbeat_ts": now,
            "lease_ttl_sec": ttl,
            "host_id": _MY_ID,
            "host_kind": _KIND,
            "mode": "active",
            "updated_ts": now,
        }
        ok = _sheets.write_status(new)
        if ok:
            LEASE.set(**new)
            METRICS.bump("lease_active")
            return True
        else:
            # Can't write -> be passive for safety
            LEASE.set(lease_owner=owner, heartbeat_ts=hb, lease_ttl_sec=ttl,
                      host_id=_MY_ID, host_kind=_KIND, mode="passive")
            METRICS.bump("sheet_errors")
            return False
    else:
        # Someone else owns → passive
        data = {
            "lease_owner": owner,
            "heartbeat_ts": hb,
            "lease_ttl_sec": ttl,
            "host_id": _MY_ID,
            "host_kind": _KIND,
            "mode": "active" if owner == _MY_ID else "passive",
        }
        LEASE.set(**data)
        return owner == _MY_ID

async def lease_loop():
    """Maintain single active host and call optional Render pause/resume hooks."""
    await _try_acquire_or_refresh()
    was_active = False

    while True:
        active = await _try_acquire_or_refresh()

        # Optional cost-save hooks
        try:
            if active and not was_active and _KIND == "local":
                await pause_render_if_enabled()     # local became active → pause Render
            if not active and was_active and _KIND == "local":
                await resume_render_if_enabled()    # local lost lease → resume Render
            if not active and was_active and _KIND == "render":
                await pause_render_if_enabled()     # render lost active → may pause self (optional)
        except Exception:
            METRICS.bump("errors_total")

        was_active = active
        await asyncio.sleep(HEARTBEAT_SEC)

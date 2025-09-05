from __future__ import annotations
import os, json, re
from starlette.requests import Request
from starlette.responses import JSONResponse
import httpx
import yaml

from utils.metrics import METRICS
from utils.lease_status import LEASE
from integrations.render_control import pause_render_if_enabled, resume_render_if_enabled
from control.state import CONTROL
from utils.ratelimit import TokenBucket

# per-user rate limit (tokens/min)
_BUCKET = None

def _cfg():
    with open("config/settings.yaml","r",encoding="utf-8") as f:
        return yaml.safe_load(f)

def _owner_id() -> int:
    try:
        return int(os.getenv("TELEGRAM_OWNER_ID","0"))
    except Exception:
        return 0

def _bot_token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN","").strip()

def _webhook_secret() -> str:
    return os.getenv("TELEGRAM_WEBHOOK_SECRET", _cfg().get("telegram",{}).get("webhook_secret","tg-hook")).strip()

async def _send(chat_id: int, text: str) -> None:
    token = _bot_token()
    if not token or not chat_id:
        return
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    async with httpx.AsyncClient(timeout=10) as cli:
        try:
            await cli.post(url, json={"chat_id": chat_id, "text": text, "disable_web_page_preview": True})
        except Exception:
            pass

def _bucket() -> TokenBucket:
    global __BUCKET
    if __BUCKET is None:
        rate = int(_cfg().get("telegram",{}).get("rate_limit_per_min", 20))
        __BUCKET = TokenBucket(capacity=rate, refill_secs=60.0)
    return __BUCKET

async def telegram_webhook(request: Request):
    # path param: secret
    secret = request.path_params.get("secret") or ""
    if secret != _webhook_secret():
        METRICS.bump("tg_cmds_denied")
        return JSONResponse({"ok": False, "error": "bad_webhook_secret"}, status_code=401)

    if request.method == "GET":
        return JSONResponse({"ok": True, "msg": "telegram webhook alive"})

    try:
        data = await request.json()
    except Exception:
        METRICS.bump("errors_total")
        return JSONResponse({"ok": True})

    msg = data.get("message") or data.get("edited_message") or {}
    chat = msg.get("chat") or {}
    text = str(msg.get("text") or "").strip()
    chat_id = int(chat.get("id") or 0)
    user_id = int((msg.get("from") or {}).get("id") or 0)

    # owner-only
    if _owner_id() and user_id != _owner_id():
        METRICS.bump("tg_cmds_denied")
        await _send(chat_id, "⛔️ not authorized")
        return JSONResponse({"ok": True})

    # rate limit
    if not _bucket().allow(str(user_id)):
        METRICS.bump("tg_rate_limited")
        await _send(chat_id, "⌛️ slow down (rate limited)")
        return JSONResponse({"ok": True})

    METRICS.bump("tg_cmds_total")

    # Commands
    t = text.lower()

    if t in ("/start","/help"):
        await _send(chat_id,
            "KTW Ops Bot\n"
            "Commands:\n"
            "• /host who — lease & status\n"
            "• /render status|pause|resume\n"
            "• /panic_flat — emergency off (blocks new entries)\n"
            "• /approve on|off — live approval flag\n"
            "• /signals on|off — intake gate\n"
            "• /report daily|weekly — sheet links (stub)")
        return JSONResponse({"ok": True})

    if t.startswith("/host"):
        lease = LEASE.snapshot()
        ctrl = CONTROL.snapshot()
        await _send(chat_id, f"Lease: {lease}\nControl: {ctrl}")
        return JSONResponse({"ok": True})

    if t.startswith("/render"):
        if "status" in t:
            await _send(chat_id, f"Render hooks: AUTOPAUSE={os.getenv('RENDER_AUTOPAUSE','false')}")
            return JSONResponse({"ok": True})
        if "pause" in t:
            ok = await pause_render_if_enabled()
            await _send(chat_id, f"Render pause → {'ok' if ok else 'no-op'}")
            return JSONResponse({"ok": True})
        if "resume" in t:
            ok = await resume_render_if_enabled()
            await _send(chat_id, f"Render resume → {'ok' if ok else 'no-op'}")
            return JSONResponse({"ok": True})
        await _send(chat_id, "Usage: /render status|pause|resume")
        return JSONResponse({"ok": True})

    if t.startswith("/panic_flat"):
        changed = CONTROL.set_panic(True, who="tg")
        await _send(chat_id, "🆘 PANIC ON — new entries will be blocked")
        return JSONResponse({"ok": True})

    if t.startswith("/approve"):
        on = "on" in t
        CONTROL.set_approved(on, who="tg")
        await _send(chat_id, f"Approve live → {'ON' if on else 'OFF'}")
        return JSONResponse({"ok": True})

    if t.startswith("/signals"):
        on = "on" in t
        CONTROL.set_signals(on, who="tg")
        await _send(chat_id, f"Signals intake → {'ON' if on else 'OFF'}")
        return JSONResponse({"ok": True})

    if t.startswith("/report"):
        sid = os.getenv("GSHEET_SPREADSHEET_ID","")
        base = f"https://docs.google.com/spreadsheets/d/{sid}/edit" if sid else "(sheet unset)"
        await _send(chat_id, f"Reports stub:\nSignals: {base}#gid=0\nEvents: {base}")
        return JSONResponse({"ok": True})

    await _send(chat_id, "Unknown cmd. Try /help")
    return JSONResponse({"ok": True})

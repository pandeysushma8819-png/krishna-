from __future__ import annotations
import os, json, time, asyncio
from starlette.responses import JSONResponse
from starlette.requests import Request
import yaml

from utils.metrics import METRICS
from utils.lease_status import LEASE
from utils.ratelimit import GlobalRateLimiter
from integrations.hmac_verify import verify_hmac
from integrations.idempotency import idem_hash, IdempotencyTTL
from integrations.sheets import SheetsClient

# ---- singletons ----
_rate: GlobalRateLimiter | None = None
_idem = IdempotencyTTL(ttl_sec=300, max_size=5000)  # 5 min dedupe window
_sheets = SheetsClient()

def _load_settings() -> dict:
    with open("config/settings.yaml", "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def _get_rate() -> GlobalRateLimiter:
    global _rate
    if _rate is None:
        cfg = _load_settings()
        _rate = GlobalRateLimiter(int(cfg["intake"]["rate_limit_per_sec"]))
    return _rate

def _pick_header(req: Request, names: list[str]) -> str | None:
    for n in names:
        v = req.headers.get(n)
        if v:
            return v
    return None

def _extract_fields(payload: dict) -> tuple[str, str, str, str]:
    # symbol, timeframe, ts, id (with tolerant fallbacks)
    sym = payload.get("symbol") or payload.get("ticker") or payload.get("s") or "UNKNOWN"
    tf  = payload.get("tf") or payload.get("timeframe") or payload.get("interval") or "NA"
    ts  = payload.get("ts") or payload.get("timestamp") or payload.get("time") or payload.get("t")
    if ts is None:
        ts = str(int(time.time()))
    else:
        ts = str(ts)
    sid = payload.get("id") or payload.get("alert_id") or payload.get("uid") or payload.get("uuid") or ""
    return str(sym), str(tf), str(ts), str(sid)

async def tv_alert(request: Request):
    t0 = time.perf_counter()
    cfg = _load_settings()
    METRICS.bump("requests_total")

    # 0) Lease gate — drop if this host is passive
    if not LEASE.is_active():
        METRICS.bump("passive_drop")
        _sheets.log_event("passive_drop", "host not active", "tv")
        return JSONResponse({"ok": True, "passive": True})

    # 1) Global rate-limit
    rl = _get_rate()
    if not rl.allow():
        METRICS.bump("rate_limited")
        return JSONResponse({"ok": False, "error": "rate_limited"}, status_code=429)

    # 2) Small jitter to smooth bursts
    jmin = int(cfg["intake"]["jitter_ms_min"])
    jmax = int(cfg["intake"]["jitter_ms_max"])
    if jmax > 0 and jmax >= jmin:
        await asyncio.sleep((jmin + (jmax - jmin) * rl.rand()) / 1000.0)

    # 3) Read body
    try:
        body = await request.body()
    except Exception as e:
        METRICS.bump("errors_total")
        return JSONResponse({"ok": False, "error": f"body_read_failed: {e}"}, status_code=400)

    # 4) HMAC / secret verify
    secret = os.getenv("TRADINGVIEW_WEBHOOK_SECRET", "")
    h_required = bool(cfg["feature_flags"].get("hmac_required", True))
    sig_header = _pick_header(request, cfg["intake"]["signature_headers"])
    ok, reason = verify_hmac(body, sig_header, secret, allow_plain=(not h_required))
    if not ok:
        METRICS.bump("auth_failed")
        _sheets.log_event("auth_fail", f"{reason}", "tv")
        return JSONResponse({"ok": False, "error": f"auth_failed: {reason}"}, status_code=401)

    # 5) Parse JSON (allow nested string)
    try:
        payload = json.loads(body.decode("utf-8"))
        if isinstance(payload, str):
            payload = json.loads(payload)
    except Exception as e:
        METRICS.bump("errors_total")
        _sheets.log_event("bad_json", f"{e}", "tv")
        return JSONResponse({"ok": False, "error": f"bad_json: {e}"}, status_code=400)

    symbol, tf, ts, sid = _extract_fields(payload)

    # 6) Idempotency
    ihash = idem_hash(symbol, tf, ts, sid, body)
    if _idem.seen(ihash):
        METRICS.bump("duplicates")
        _sheets.append_signal(symbol, tf, sid, ihash, status="duplicate", raw=payload,
                              rtt_ms=int((time.perf_counter() - t0) * 1000))
        return JSONResponse({"ok": True, "duplicate": True, "hash": ihash})

    _idem.remember(ihash)

    # 7) Log to Sheets (best-effort)
    ok_sheet = _sheets.append_signal(symbol, tf, sid, ihash, status="new", raw=payload,
                                     rtt_ms=int((time.perf_counter() - t0) * 1000))
    if not ok_sheet:
        METRICS.bump("sheet_errors")

    # 8) Metrics & return
    METRICS.bump("success")
    METRICS.observe_latency_ms((time.perf_counter() - t0) * 1000.0)
    METRICS.set_last_signal_now()

    return JSONResponse({"ok": True, "hash": ihash, "sheet_logged": ok_sheet})

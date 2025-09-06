# integrations/sheets.py
from __future__ import annotations

import os
import json
import time
import hashlib
import threading
from typing import Any, Dict, List, Optional

# Third-party
try:
    import gspread  # type: ignore
    from google.oauth2.service_account import Credentials  # type: ignore
except Exception as e:  # Keep import-time failures visible via get_status()
    gspread = None  # type: ignore
    Credentials = None  # type: ignore
    _import_error = str(e)
else:
    _import_error = ""

# ---------- Globals ----------
_LOCK = threading.RLock()
_GC: Optional[gspread.Client] = None  # type: ignore
_SS: Optional[gspread.Spreadsheet] = None  # type: ignore
_HAS_SESSION: bool = False
_LAST_ERROR: str = ""
_CLIENT_EMAIL: str = ""
_SHEET_ID: str = os.environ.get("GSHEET_SPREADSHEET_ID", "").strip()

# Tabs & headers
SIGNALS_SHEET = "Signals"
EVENTS_SHEET = "Events"
SNAPSHOTS_SHEET = "Snapshots"
STATUS_SHEET = "Status"

SIGNALS_HEADERS = [
    "ts", "ist", "symbol", "tf", "id", "hash", "source", "extra_json"
]
EVENTS_HEADERS = [
    "ts", "ist", "kind", "tag", "detail", "severity",
    "action", "risk_scale", "cooldown_min", "reason", "source"
]
SNAPSHOTS_HEADERS = ["ts", "ist", "title", "json"]
STATUS_HEADERS = ["ts", "ist", "key", "value_json"]

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ---------- Utils ----------
def _now_ist_str(ts: Optional[int] = None) -> str:
    if ts is None:
        ts = int(time.time())
    # IST = UTC + 19800 sec
    return time.strftime("%Y-%m-%d %H:%M:%S IST", time.gmtime(ts + 19800))

def _set_err(msg: str) -> None:
    global _LAST_ERROR
    _LAST_ERROR = msg

def _clear_err() -> None:
    global _LAST_ERROR
    _LAST_ERROR = ""

def _compute_signal_hash(symbol: str, tf: str, ts: int, sig_id: str) -> str:
    raw = f"{symbol}|{tf}|{ts}|{sig_id}".encode()
    return hashlib.sha256(raw).hexdigest()

def _get_env_json() -> Dict[str, Any]:
    raw = os.environ.get("GOOGLE_SA_JSON", "").strip()
    # Allow accidental quoting
    if raw.startswith("'") and raw.endswith("'"):
        raw = raw[1:-1]
    if raw.startswith('"') and raw.endswith('"'):
        raw = raw[1:-1]
    try:
        return json.loads(raw) if raw else {}
    except Exception:
        # Try to recover common \n issues
        try:
            return json.loads(raw.replace("\\n", "\n"))
        except Exception:
            raise

# ---------- Session ----------
def _ensure_session() -> bool:
    """
    Lazy-initialize gspread + Spreadsheet.
    Returns True if connected and sheets ensured; else False (and _LAST_ERROR set).
    """
    global _GC, _SS, _HAS_SESSION, _CLIENT_EMAIL

    if _HAS_SESSION and _GC is not None and _SS is not None:
        return True

    if gspread is None or Credentials is None:
        _set_err(f"import_error: {(_import_error or 'missing deps')}")
        return False

    if not _SHEET_ID:
        _set_err("missing GSHEET_SPREADSHEET_ID")
        return False

    info = {}
    try:
        info = _get_env_json()
    except Exception as e:
        _set_err(f"env/GOOGLE_SA_JSON parse: {e}")
        return False

    if not info:
        _set_err("missing GOOGLE_SA_JSON")
        return False

    try:
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        gc = gspread.authorize(creds)  # type: ignore
        ss = gc.open_by_key(_SHEET_ID)  # type: ignore
        _CLIENT_EMAIL = info.get("client_email", "")
    except Exception as e:
        _set_err(f"auth/open: {e}")
        return False

    # Ensure required worksheets exist with headers
    try:
        _ensure_worksheets(ss)
    except Exception as e:
        _set_err(f"ensure_tabs: {e}")
        return False

    with _LOCK:
        _GC = gc
        _SS = ss
        _HAS_SESSION = True
        _clear_err()
    return True

def _ensure_worksheets(ss) -> None:
    """Create missing tabs and write header rows."""
    title_to_headers = {
        SIGNALS_SHEET: SIGNALS_HEADERS,
        EVENTS_SHEET: EVENTS_HEADERS,
        SNAPSHOTS_SHEET: SNAPSHOTS_HEADERS,
        STATUS_SHEET: STATUS_HEADERS,
    }
    existing = {ws.title for ws in ss.worksheets()}
    for title, headers in title_to_headers.items():
        if title not in existing:
            ws = ss.add_worksheet(title=title, rows=100, cols=max(8, len(headers)))
            ws.append_row(headers, value_input_option="USER_ENTERED")
        else:
            # make sure first row has headers (idempotent safety)
            ws = ss.worksheet(title)
            try:
                row1 = ws.row_values(1)
                if row1 != headers:
                    # Overwrite header row
                    ws.delete_rows(1)
                    ws.insert_row(headers, index=1, value_input_option="USER_ENTERED")
            except Exception:
                # If any failure reading, just re-set headers
                ws.insert_row(headers, index=1, value_input_option="USER_ENTERED")

def _ws(title: str):
    if not _ensure_session():
        return None
    assert _SS is not None
    return _SS.worksheet(title)

# ---------- Public: status ----------
def get_status() -> Dict[str, Any]:
    return {
        "enabled": bool(os.environ.get("GSHEET_SPREADSHEET_ID")),
        "sheet_id": _SHEET_ID,
        "client_email": _CLIENT_EMAIL,
        "has_session": _HAS_SESSION,
        "last_error": _LAST_ERROR,
    }

# ---------- Public: append APIs ----------
def append_signal(payload: Dict[str, Any]) -> bool:
    """
    payload expects: {ts:int, symbol:str, tf:str, id:str, hash?:str, source?:str, ...}
    Any extra keys are archived in extra_json column.
    """
    try:
        ts = int(payload.get("ts") or payload.get("timestamp") or time.time())
        symbol = str(payload.get("symbol", "")).upper()
        tf = str(payload.get("tf", ""))
        sig_id = str(payload.get("id", ""))
        sig_hash = payload.get("hash") or _compute_signal_hash(symbol, tf, ts, sig_id)
        source = str(payload.get("source", "tv"))
        ist = _now_ist_str(ts)

        # archive full payload (compact)
        extra_json = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)

        row = [ts, ist, symbol, tf, sig_id, sig_hash, source, extra_json]

        ws = _ws(SIGNALS_SHEET)
        if ws is None:
            return False
        with _LOCK:
            ws.append_row(row, value_input_option="USER_ENTERED")
        return True
    except Exception as e:
        _set_err(f"append_signal: {e}")
        return False

def append_event(event: Dict[str, Any]) -> bool:
    """
    event: {
      ts:int, kind:str, tag:str, detail?:str, severity?:str, action?:str,
      risk_scale?:float, cooldown_min?:int, reason?:str, source?:str
    }
    """
    try:
        ts = int(event.get("ts") or time.time())
        ist = _now_ist_str(ts)
        row = [
            ts,
            ist,
            str(event.get("kind", "")),
            str(event.get("tag", "")),
            str(event.get("detail", "")),
            str(event.get("severity", "")),
            str(event.get("action", "")),
            float(event.get("risk_scale", 0.0)) if event.get("risk_scale") not in (None, "") else "",
            int(event.get("cooldown_min", 0)) if event.get("cooldown_min") not in (None, "") else "",
            str(event.get("reason", "")),
            str(event.get("source", "app")),
        ]
        ws = _ws(EVENTS_SHEET)
        if ws is None:
            return False
        with _LOCK:
            ws.append_row(row, value_input_option="USER_ENTERED")
        return True
    except Exception as e:
        _set_err(f"append_event: {e}")
        return False

def append_snapshot(title: str, obj: Dict[str, Any]) -> bool:
    """
    Save an arbitrary JSON snapshot (e.g., leaderboards, specs).
    """
    try:
        ts = int(time.time())
        ist = _now_ist_str(ts)
        js = json.dumps(obj, separators=(",", ":"), ensure_ascii=False)
        row = [ts, ist, title, js]
        ws = _ws(SNAPSHOTS_SHEET)
        if ws is None:
            return False
        with _LOCK:
            ws.append_row(row, value_input_option="USER_ENTERED")
        return True
    except Exception as e:
        _set_err(f"append_snapshot: {e}")
        return False

def append_status(key: str, value: Any) -> bool:
    """
    Append a key/value JSON to Status sheet (audit breadcrumbs).
    """
    try:
        ts = int(time.time())
        ist = _now_ist_str(ts)
        val_js = json.dumps(value, separators=(",", ":"), ensure_ascii=False)
        row = [ts, ist, key, val_js]
        ws = _ws(STATUS_SHEET)
        if ws is None:
            return False
        with _LOCK:
            ws.append_row(row, value_input_option="USER_ENTERED")
        return True
    except Exception as e:
        _set_err(f"append_status: {e}")
        return False

# ---------- Convenience: high-level helpers ----------
def log_tv_signal(symbol: str, tf: str, ts: int, sig_id: str, source: str = "tv",
                  extra: Optional[Dict[str, Any]] = None) -> bool:
    """
    Convenience wrapper to log a simple TradingView signal.
    """
    payload = {
        "symbol": symbol,
        "tf": tf,
        "ts": ts,
        "id": sig_id,
        "source": source,
    }
    if extra:
        payload.update(extra)
    return append_signal(payload)

def log_meta_guard(regime: str, guard: Dict[str, Any], now_ts: Optional[int] = None) -> bool:
    """
    Log a compact meta-event summarizing current guard action.
    """
    ts = int(now_ts or time.time())
    evt = {
        "ts": ts,
        "kind": "meta",
        "tag": regime,
        "detail": json.dumps(guard, separators=(",", ":"), ensure_ascii=False),
        "action": guard.get("action", ""),
        "risk_scale": guard.get("risk_scale", ""),
        "cooldown_min": guard.get("cooldown_min", ""),
        "reason": guard.get("reason", ""),
        "source": "meta.scan",
    }
    return append_event(evt)

# ---------- Module export ----------
__all__ = [
    "get_status",
    "append_signal",
    "append_event",
    "append_snapshot",
    "append_status",
    "log_tv_signal",
    "log_meta_guard",
]

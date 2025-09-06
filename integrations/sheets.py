# integrations/sheets.py
from __future__ import annotations
import os, json, time
from typing import Optional, Tuple, Dict, Any, List

# lazy imports so app boots even if gspread not installed in some envs
try:
    import gspread  # type: ignore
    from google.oauth2.service_account import Credentials  # type: ignore
except Exception:  # pragma: no cover
    gspread = None  # type: ignore
    Credentials = None  # type: ignore

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

# ===== module state =====
_SS = None            # Spreadsheet handle
_STATUS: Dict[str, Any] = {
    "enabled": False,
    "sheet_id": "",
    "client_email": "",
    "has_session": False,
    "last_error": "",
}

# ===== tab headers (SoT) =====
TAB_HEADERS: Dict[str, List[str]] = {
    "Signals":   ["ts", "ist", "symbol", "tf", "id", "hash", "raw"],
    "Events":    ["ts", "ist", "kind", "tag", "detail", "source"],
    "Status":    ["ts", "ist", "key", "value"],
    "Snapshots": ["ts", "ist", "title", "json"],
    # NEW for P11 reports
    "Trades":    ["ts", "ist", "symbol", "side", "qty", "price", "pnl", "fees", "slippage", "strategy_id"],
}

# ===== helpers =====
def _now_ts_ist() -> tuple[int, str]:
    ts = int(time.time())
    ist = time.strftime("%Y-%m-%d %H:%M:%S IST", time.gmtime(ts + 19800))
    return ts, ist

def _get_env_json(raw: str) -> dict:
    s = raw.strip()
    if s.startswith("'") and s.endswith("'"): s = s[1:-1]
    if s.startswith('"') and s.endswith('"'): s = s[1:-1]
    # allow \n-escaped private_key
    try:
        return json.loads(s) if s else {}
    except Exception:
        return json.loads(s.replace("\\n", "\n"))

def _connect() -> Tuple[Optional[object], Optional[str], Optional[str], Optional[str]]:
    """Returns (Spreadsheet, sheet_id, client_email, error)"""
    if gspread is None or Credentials is None:
        return None, None, None, "gspread/credentials not available"

    sheet_id = os.environ.get("GSHEET_SPREADSHEET_ID", "").strip()
    if not sheet_id:
        return None, None, None, "GSHEET_SPREADSHEET_ID missing"

    raw = os.environ.get("GOOGLE_SA_JSON", "").strip()
    if not raw:
        return None, sheet_id, None, "GOOGLE_SA_JSON missing"

    try:
        info = _get_env_json(raw)
        client_email = info.get("client_email", "")
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)  # type: ignore
        gc = gspread.authorize(creds)  # type: ignore
        ss = gc.open_by_key(sheet_id)  # type: ignore
        return ss, sheet_id, client_email, None
    except Exception as e:
        return None, sheet_id, None, f"auth/open: {e}"

def _ws(ss, title: str):
    try:
        return ss.worksheet(title)
    except Exception:
        return None

def _ensure_ws(ss, title: str, headers: List[str]):
    ws = _ws(ss, title)
    if ws:
        return ws
    # create with headers
    try:
        ws = ss.add_worksheet(title=title, rows=1000, cols=max(8, len(headers)))  # type: ignore
        ws.append_row(headers, value_input_option="RAW")  # type: ignore
        return ws
    except Exception as e:
        raise RuntimeError(f"create_ws({title}): {e}")

def _append_dict(ss, tab: str, headers: List[str], rowdict: Dict[str, Any]) -> bool:
    ws = _ensure_ws(ss, tab, headers)
    ts, ist = _now_ts_ist()
    # auto-fill ts/ist if missing
    if "ts" not in rowdict: rowdict["ts"] = ts
    if "ist" not in rowdict: rowdict["ist"] = ist
    row = []
    for h in headers:
        v = rowdict.get(h, "")
        if isinstance(v, (dict, list)):
            v = json.dumps(v, separators=(",", ":"), ensure_ascii=False)
        row.append(v)
    ws.append_row(row, value_input_option="RAW")  # type: ignore
    return True

def _set_err(msg: str):
    _STATUS["last_error"] = msg

def _clear_err():
    _STATUS["last_error"] = ""

# ===== public API =====
def get_status() -> Dict[str, Any]:
    global _SS
    if _SS is None:
        ss, sid, email, err = _connect()
        _STATUS["enabled"] = (ss is not None and err is None)
        _STATUS["sheet_id"] = sid or ""
        _STATUS["client_email"] = email or ""
        _STATUS["has_session"] = ss is not None and err is None
        _STATUS["last_error"] = err or ""
        _SS = ss
    return dict(_STATUS)

def ensure_all_tabs() -> bool:
    ss = get_session()
    if not ss:
        return False
    try:
        for tab, hdrs in TAB_HEADERS.items():
            _ensure_ws(ss, tab, hdrs)
        _clear_err()
        return True
    except Exception as e:
        _set_err(str(e))
        return False

def ensure_trades_tab() -> bool:
    ss = get_session()
    if not ss:
        return False
    try:
        _ensure_ws(ss, "Trades", TAB_HEADERS["Trades"])
        _clear_err()
        return True
    except Exception as e:
        _set_err(str(e))
        return False

def get_session():
    """cached Spreadsheet (or None)"""
    global _SS
    if _SS is not None:
        return _SS
    ss, sid, email, err = _connect()
    _STATUS["enabled"] = (ss is not None and err is None)
    _STATUS["sheet_id"] = sid or ""
    _STATUS["client_email"] = email or ""
    _STATUS["has_session"] = ss is not None and err is None
    _STATUS["last_error"] = err or ""
    _SS = ss
    return _SS

# ----- append APIs -----
def append_signal(d: Dict[str, Any]) -> bool:
    ss = get_session()
    if not ss:
        return False
    try:
        ok = _append_dict(ss, "Signals", TAB_HEADERS["Signals"], d)
        _clear_err(); return ok
    except Exception as e:
        _set_err(str(e)); return False

def append_event(d: Dict[str, Any]) -> bool:
    ss = get_session()
    if not ss:
        return False
    try:
        ok = _append_dict(ss, "Events", TAB_HEADERS["Events"], d)
        _clear_err(); return ok
    except Exception as e:
        _set_err(str(e)); return False

def append_status(key: str, value: Any) -> bool:
    ss = get_session()
    if not ss:
        return False
    try:
        payload = {"key": key, "value": value}
        ok = _append_dict(ss, "Status", TAB_HEADERS["Status"], payload)
        _clear_err(); return ok
    except Exception as e:
        _set_err(str(e)); return False

def append_snapshot(title: str, obj: Dict[str, Any]) -> bool:
    ss = get_session()
    if not ss:
        return False
    try:
        payload = {"title": title, "json": obj}
        ok = _append_dict(ss, "Snapshots", TAB_HEADERS["Snapshots"], payload)
        _clear_err(); return ok
    except Exception as e:
        _set_err(str(e)); return False

def append_trade(tr: Dict[str, Any]) -> bool:
    """
    Expected keys:
      ts (epoch), symbol, side, qty, price, pnl, fees, slippage, strategy_id
    Missing ts/ist will be auto-filled. Non-provided numeric fields default to 0.
    """
    ss = get_session()
    if not ss:
        return False
    # normalize numeric fields
    for k in ("qty", "price", "pnl", "fees", "slippage"):
        if k in tr:
            try:
                tr[k] = float(tr[k]) if k != "qty" else int(tr[k])
            except Exception:
                tr[k] = 0 if k == "qty" else 0.0
    try:
        ok = _append_dict(ss, "Trades", TAB_HEADERS["Trades"], tr)
        _clear_err(); return ok
    except Exception as e:
        _set_err(str(e)); return False

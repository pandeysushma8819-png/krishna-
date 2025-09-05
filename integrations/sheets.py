from __future__ import annotations
import os, json, time
import gspread
from google.oauth2.service_account import Credentials

# ---- Sheet headers ----
SIGNALS_HDR = ["ts","symbol","tf","id","hash","status","recv_at_utc","latency_ms","source","raw_json"]
EVENTS_HDR  = ["ts","type","detail","who"]
STATUS_HDR  = ["lease_owner","heartbeat_ts","lease_ttl_sec","host_id","host_kind","mode","updated_ts"]

class SheetsClient:
    """
    Resilient Google Sheets client with simple diagnostics.
    Disabled if GSHEET_SPREADSHEET_ID or GOOGLE_SA_JSON missing/invalid.
    """
    def __init__(self):
        self.enabled = bool(os.getenv("GSHEET_SPREADSHEET_ID")) and bool(os.getenv("GOOGLE_SA_JSON"))
        self._gc = None
        self._ss = None
        self._ws_cache: dict[str, gspread.Worksheet] = {}
        self._last_error: str = ""
        self._client_email: str = ""
        self._sheet_id: str = os.getenv("GSHEET_SPREADSHEET_ID","")

        if self.enabled:
            try:
                sa_json = os.getenv("GOOGLE_SA_JSON")
                info = json.loads(sa_json)
                self._client_email = str(info.get("client_email",""))
                scopes = [
                    "https://www.googleapis.com/auth/spreadsheets",
                    "https://www.googleapis.com/auth/drive",
                ]
                creds = Credentials.from_service_account_info(info, scopes=scopes)
                self._gc = gspread.authorize(creds)
                self._ss = self._gc.open_by_key(self._sheet_id)
            except Exception as e:
                self._last_error = f"auth/open: {e}"
                self.enabled = False
                self._gc = None
                self._ss = None

    # ---------- internal helpers ----------
    def _get_ws(self, name: str, header: list[str]):
        if not self.enabled or not self._ss:
            return None
        if name in self._ws_cache:
            return self._ws_cache[name]
        try:
            try:
                ws = self._ss.worksheet(name)
            except gspread.exceptions.WorksheetNotFound:
                ws = self._ss.add_worksheet(title=name, rows=2000, cols=max(10, len(header)))
                ws.append_row(header)
            # ensure header row
            try:
                first = ws.row_values(1)
                if [h.strip() for h in first] != header:
                    ws.clear()
                    ws.append_row(header)
            except Exception:
                pass
            self._ws_cache[name] = ws
            return ws
        except Exception as e:
            self._last_error = f"get_ws:{name}: {e}"
            return None

    # ---------- diagnostics ----------
    def status_summary(self) -> dict:
        return {
            "enabled": bool(self.enabled),
            "sheet_id": self._sheet_id or "",
            "client_email": self._client_email or "",
            "has_session": bool(self._ss is not None),
            "last_error": self._last_error,
        }

    # ---------- public APIs ----------
    def append_signal(self, symbol: str, tf: str, sid: str, ihash: str, status: str, raw: dict, rtt_ms: int) -> bool:
        if not self.enabled:
            self._last_error = "disabled"
            return False
        ws = self._get_ws("Signals", SIGNALS_HDR)
        if not ws:
            return False
        try:
            now = int(time.time())
            row = [now, symbol, tf, sid, ihash, status, now, int(rtt_ms), "tv", json.dumps(raw, ensure_ascii=False)]
            ws.append_row(row, value_input_option="RAW")
            return True
        except Exception as e:
            self._last_error = f"append_signal: {e}"
            return False

    def log_event(self, etype: str, detail: str, who: str = "sys") -> bool:
        if not self.enabled:
            self._last_error = "disabled"
            return False
        ws = self._get_ws("Events", EVENTS_HDR)
        if not ws:
            return False
        try:
            ws.append_row([int(time.time()), etype, detail, who], value_input_option="RAW")
            return True
        except Exception as e:
            self._last_error = f"log_event: {e}"
            return False

    # ----- lease/status helpers -----
    def _get_status_ws(self):
        return self._get_ws("Status", STATUS_HDR)

    def read_status(self) -> dict | None:
        if not self.enabled:
            self._last_error = "disabled"
            return None
        ws = self._get_status_ws()
        if not ws:
            return None
        try:
            vals = ws.row_values(2)
            if not vals:
                return None
            data = dict(zip(STATUS_HDR, vals))
            for k in ("heartbeat_ts","lease_ttl_sec","updated_ts"):
                if k in data:
                    try: data[k] = int(float(data[k]))
                    except: data[k] = 0
            return data
        except Exception as e:
            self._last_error = f"read_status: {e}"
            return None

    def write_status(self, data: dict) -> bool:
        if not self.enabled:
            self._last_error = "disabled"
            return False
        ws = self._get_status_ws()
        if not ws:
            return False
        try:
            try:
                if ws.row_count < 2:
                    ws.add_rows(2 - ws.row_count)
            except Exception:
                pass
            row = [str(data.get(k,"")) for k in STATUS_HDR]
            ws.update("A2:G2", [row])
            return True
        except Exception as e:
            self._last_error = f"write_status: {e}"
            return False

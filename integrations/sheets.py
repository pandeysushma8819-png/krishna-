# integrations/sheets.py
from __future__ import annotations
import os, json, time
import gspread
from google.oauth2.service_account import Credentials

SIGNALS_HDR = ["ts", "symbol", "tf", "id", "hash", "status", "recv_at_utc", "latency_ms", "source", "raw_json"]
EVENTS_HDR  = ["ts", "type", "detail", "who"]

class SheetsClient:
    def __init__(self):
        self.enabled = bool(os.getenv("GSHEET_SPREADSHEET_ID")) and bool(os.getenv("GOOGLE_SA_JSON"))
        self._gc = None
        self._ss = None
        self._ws_cache = {}

        if self.enabled:
            try:
                sa_json = os.getenv("GOOGLE_SA_JSON")
                info = json.loads(sa_json)
                scopes = ["https://www.googleapis.com/auth/spreadsheets", "https://www.googleapis.com/auth/drive"]
                creds = Credentials.from_service_account_info(info, scopes=scopes)
                self._gc = gspread.authorize(creds)
                self._ss = self._gc.open_by_key(os.getenv("GSHEET_SPREADSHEET_ID"))
            except Exception as e:
                # Disable gracefully if auth fails
                self.enabled = False

    def _get_ws(self, name: str, header: list[str]):
        if not self.enabled:
            return None
        if name in self._ws_cache:
            return self._ws_cache[name]
        try:
            try:
                ws = self._ss.worksheet(name)
            except gspread.exceptions.WorksheetNotFound:
                ws = self._ss.add_worksheet(title=name, rows=2000, cols=max(10, len(header)))
                ws.append_row(header)
            # ensure header present
            try:
                first = ws.row_values(1)
                if [h.strip() for h in first] != header:
                    # set header explicitly
                    ws.clear()
                    ws.append_row(header)
            except Exception:
                pass
            self._ws_cache[name] = ws
            return ws
        except Exception:
            return None

    def append_signal(self, symbol: str, tf: str, sid: str, ihash: str, status: str, raw: dict, rtt_ms: int) -> bool:
        if not self.enabled:
            return False
        ws = self._get_ws("Signals", SIGNALS_HDR)
        if not ws:
            return False
        try:
            row = [
                int(time.time()),
                symbol,
                tf,
                sid,
                ihash,
                status,
                int(time.time()),
                int(rtt_ms),
                "tv",
                json.dumps(raw, ensure_ascii=False),
            ]
            ws.append_row(row, value_input_option="RAW")
            return True
        except Exception:
            return False

    def log_event(self, etype: str, detail: str, who: str = "sys") -> bool:
        if not self.enabled:
            return False
        ws = self._get_ws("Events", EVENTS_HDR)
        if not ws:
            return False
        try:
            ws.append_row([int(time.time()), etype, detail, who], value_input_option="RAW")
            return True
        except Exception:
            return False

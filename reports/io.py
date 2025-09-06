# reports/io.py
from __future__ import annotations
import os, json
from typing import Optional, Tuple

try:
    import gspread  # type: ignore
    from google.oauth2.service_account import Credentials  # type: ignore
except Exception:  # defer import errors to caller
    gspread = None  # type: ignore
    Credentials = None  # type: ignore

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

def _get_env_json(raw: str) -> dict:
    s = raw.strip()
    if s.startswith("'") and s.endswith("'"): s = s[1:-1]
    if s.startswith('"') and s.endswith('"'): s = s[1:-1]
    try:
        return json.loads(s) if s else {}
    except Exception:
        return json.loads(s.replace("\\n", "\n"))

def connect_spreadsheet() -> Tuple[Optional[object], Optional[str], Optional[str]]:
    """
    Returns (Spreadsheet or None, sheet_id, error_message)
    """
    if gspread is None or Credentials is None:
        return None, None, "gspread/credentials not available"
    sheet_id = os.environ.get("GSHEET_SPREADSHEET_ID", "").strip()
    if not sheet_id:
        return None, None, "GSHEET_SPREADSHEET_ID missing"
    raw = os.environ.get("GOOGLE_SA_JSON", "").strip()
    if not raw:
        return None, None, "GOOGLE_SA_JSON missing"
    try:
        info = _get_env_json(raw)
        creds = Credentials.from_service_account_info(info, scopes=SCOPES)
        gc = gspread.authorize(creds)  # type: ignore
        ss = gc.open_by_key(sheet_id)  # type: ignore
        return ss, sheet_id, None
    except Exception as e:
        return None, None, f"auth/open: {e}"

def get_ws(ss, title: str):
    try:
        return ss.worksheet(title)
    except Exception:
        return None

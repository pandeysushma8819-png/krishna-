# integrations/sheets_backup.py
from __future__ import annotations
from typing import List, Dict, Any, Tuple
import os, json, time
import gspread
from google.oauth2.service_account import Credentials

DEFAULT_TABS = ["Signals", "Events", "Trades", "Status", "Policy", "Control", "Lease", "Metrics"]

def _now_utc_str() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime())

def _now_ist_str() -> str:
    return time.strftime("%Y-%m-%d %H:%M:%S IST", time.gmtime(time.time() + 19800))

def _stamp_prefix() -> str:
    return time.strftime("SNAP_%Y%m%d_%H%M", time.gmtime())

def _authorize() -> gspread.Client:
    info = os.environ.get("GOOGLE_SA_JSON", "").strip()
    if not info:
        raise RuntimeError("GOOGLE_SA_JSON missing")
    creds = Credentials.from_service_account_info(
        json.loads(info),
        scopes=["https://www.googleapis.com/auth/spreadsheets",
                "https://www.googleapis.com/auth/drive"]
    )
    return gspread.authorize(creds)

def _open_main(gc: gspread.Client) -> gspread.Spreadsheet:
    sid = os.environ.get("GSHEET_SPREADSHEET_ID", "").strip()
    if not sid:
        raise RuntimeError("GSHEET_SPREADSHEET_ID missing")
    return gc.open_by_key(sid)

def _get_or_create_snapshots_sheet(ss: gspread.Spreadsheet):
    try:
        ws = ss.worksheet("Snapshots")
    except Exception:
        ws = ss.add_worksheet(title="Snapshots", rows=1, cols=10)
        ws.append_row(["ts_utc","ist","prefix","tabs_count","notes"], value_input_option="RAW")
    return ws

def _existing_titles(ss: gspread.Spreadsheet) -> List[str]:
    return [w.title for w in ss.worksheets()]

def _duplicate_sheet(ss: gspread.Spreadsheet, title: str, new_title: str) -> None:
    ws = ss.worksheet(title)
    # Prefer worksheet.duplicate if available; fallback to spreadsheet.duplicate_sheet
    try:
        ws.duplicate(new_sheet_name=new_title)
    except Exception:
        ss.duplicate_sheet(ws.id, new_sheet_name=new_title)

def snapshot_tabs(tab_names: List[str] | None = None) -> Dict[str, Any]:
    """
    Duplicate selected tabs within the same spreadsheet with a timestamp prefix.
    Example new titles: SNAP_20250906_1205_Signals
    """
    gc = _authorize()
    ss = _open_main(gc)
    titles = _existing_titles(ss)
    want = [t for t in (tab_names or DEFAULT_TABS) if t in titles]
    if not want:
        raise RuntimeError("no matching tabs to snapshot")

    prefix = _stamp_prefix()
    for t in want:
        _duplicate_sheet(ss, t, f"{prefix}_{t}")

    # Log into Snapshots tab
    snap = _get_or_create_snapshots_sheet(ss)
    snap.append_row([_now_utc_str(), _now_ist_str(), prefix, len(want), ""], value_input_option="RAW")
    return {"ok": True, "prefix": prefix, "tabs": want, "sheet_url": ss.url}

def list_snapshots(ss: gspread.Spreadsheet) -> List[Tuple[str,int]]:
    """Return list of (title, sheetId) for sheets whose title starts with SNAP_."""
    out = []
    for ws in ss.worksheets():
        if ws.title.startswith("SNAP_"):
            out.append((ws.title, ws.id))
    return out

def _parse_snap_ts(title: str) -> int | None:
    # Title starts with SNAP_YYYYMMDD_HHMM_...
    try:
        stamp = title.split("_", 2)[:2]  # ["SNAP", "YYYYMMDD", "HHMM..."]? Actually prefix is SNAP_YYYYMMDD_HHMM_...
        # More robust:
        parts = title.split("_")
        ymd = parts[1]  # YYYYMMDD
        hm = parts[2]   # HHMM
        tm = time.strptime(ymd + hm, "%Y%m%d%H%M")
        return int(time.mktime(tm))
    except Exception:
        return None

def cleanup_old_snapshots(retention_days: int = 14) -> Dict[str, Any]:
    gc = _authorize()
    ss = _open_main(gc)
    snaps = list_snapshots(ss)
    now = int(time.time())
    keep_after = now - retention_days*86400
    deleted = []
    for title, sid in snaps:
        ts = _parse_snap_ts(title)
        if ts is not None and ts < keep_after:
            try:
                ws = ss.worksheet(title)
                ss.del_worksheet(ws)
                deleted.append(title)
            except Exception:
                # ignore delete failure to avoid hard crash
                pass
    return {"ok": True, "deleted": deleted, "sheet_url": ss.url, "retention_days": retention_days}

def restore_check(sample_rows: int = 5) -> Dict[str, Any]:
    """
    Simple DR drill: load last SNAP_* copies (if any) and read first N rows from each.
    """
    gc = _authorize()
    ss = _open_main(gc)
    snaps = sorted(list_snapshots(ss), key=lambda x: x[0])  # by title
    if not snaps:
        return {"ok": False, "error": "no snapshots found", "sheet_url": ss.url}
    # Group by prefix so we read a cohesive set
    last_prefix = snaps[-1][0].split("_", 3)
    prefix = "_".join(last_prefix[:3])  # SNAP_YYYYMMDD_HHMM
    sample = {}
    for ws in ss.worksheets():
        if ws.title.startswith(prefix + "_"):
            vals = ws.get_all_values()[:sample_rows]
            sample[ws.title] = {"rows": len(vals)}
    return {"ok": True, "prefix": prefix, "samples": sample, "sheet_url": ss.url}

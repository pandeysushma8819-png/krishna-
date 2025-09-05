from __future__ import annotations
import json, argparse, time
from pathlib import Path
from typing import List, Dict
from meta.regime import classify_latest, ts_to_ist_str
from meta.anomaly import detect_anomalies, decide_guard

def load_bars(path: str) -> List[dict]:
    return json.load(open(path, "r"))

def to_events(regime: str, snap: Dict[str,float], anomalies: List[Dict], now_ts: int) -> List[Dict]:
    events = []
    # regime event (always)
    events.append({
        "ts": now_ts, "ist": ts_to_ist_str(now_ts),
        "kind": "regime", "tag": regime, "score": snap.get("trend_strength", 0.0),
        "severity": "", "action": "", "risk_scale": "", "cooldown_min": 0,
        "reason": f"ts={snap.get('trend_strength')}, vol={snap.get('vol_abs')}, pers={snap.get('persist')}"
    })
    # anomalies (if any)
    events.extend(anomalies)
    return events

def write_sheets_if_enabled(events: List[Dict], sheet_id: str | None):
    if not sheet_id:
        print("Sheets: disabled (no GSHEET_SPREADSHEET_ID)."); return
    import os, json as _json, gspread
    from google.oauth2.service_account import Credentials
    sa = os.environ.get("GOOGLE_SA_JSON", "")
    if not sa:
        print("Sheets: missing GOOGLE_SA_JSON."); return
    info = _json.loads(sa)
    creds = Credentials.from_service_account_info(info, scopes=[
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive"
    ])
    gc = gspread.authorize(creds)
    ss = gc.open_by_key(sheet_id)
    try:
        ws = ss.worksheet("Events")
    except:
        ws = ss.add_worksheet(title="Events", rows=1000, cols=12)
        ws.append_row(["ts","ist","kind","tag","score","severity","action","risk_scale","cooldown_min","reason"])
    rows = []
    for e in events:
        rows.append([
            int(e.get("ts", 0)),
            e.get("ist",""),
            e.get("kind",""),
            e.get("tag",""),
            e.get("score",""),
            e.get("severity",""),
            e.get("action",""),
            e.get("risk_scale",""),
            e.get("cooldown_min",""),
            e.get("reason","")
        ])
    if rows:
        ws.append_rows(rows, value_input_option="RAW")
        print(f"Sheets: appended {len(rows)} rows to Events")

def main():
    ap = argparse.ArgumentParser("Meta Regime + Anomaly scanner (P9)")
    ap.add_argument("--bars-json", required=True)
    ap.add_argument("--tf-sec", type=int, default=900)
    ap.add_argument("--out", default="events_meta.json")
    ap.add_argument("--write-sheets", action="store_true")
    args = ap.parse_args()

    bars = load_bars(args.bars_json)
    regime, snap = classify_latest(bars, args.tf_sec)
    anomalies = detect_anomalies(bars, args.tf_sec)
    guard = decide_guard(regime, anomalies)
    now_ts = int(bars[-1]["ts"])

    events = to_events(regime, snap, anomalies, now_ts)
    Path(args.out).write_text(json.dumps({
        "ok": True, "regime": regime, "snap": snap, "anomalies": anomalies, "guard": guard, "events": events
    }, indent=2), encoding="utf-8")
    print(f"OK: regime={regime} guard={guard} -> wrote {args.out}")

    if args.write_sheets:
        import os
        write_sheets_if_enabled(events, os.environ.get("GSHEET_SPREADSHEET_ID"))

if __name__ == "__main__":
    main()

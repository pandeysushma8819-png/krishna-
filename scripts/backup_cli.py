# scripts/backup_cli.py
from __future__ import annotations
import argparse, json
from integrations.sheets_backup import snapshot_tabs, cleanup_old_snapshots, restore_check

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tabs", default="", help="comma-separated tabs (default: Signals,Events,Trades,...)")
    ap.add_argument("--retention-days", type=int, default=14)
    ap.add_argument("--restore-check", action="store_true")
    args = ap.parse_args()

    tabs = [t.strip() for t in args.tabs.split(",") if t.strip()] if args.tabs else None
    out1 = snapshot_tabs(tabs)
    out2 = cleanup_old_snapshots(retention_days=args.retention_days)
    print("SNAPSHOT:", json.dumps(out1, indent=2))
    print("CLEANUP :", json.dumps(out2, indent=2))

    if args.restore_check:
        out3 = restore_check(sample_rows=5)
        print("RESTORE :", json.dumps(out3, indent=2))

if __name__ == "__main__":
    main()

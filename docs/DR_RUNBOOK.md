# DR RUNBOOK (P14)

## Daily
- Render cron (or external): `python scripts/backup_cli.py --retention-days 14`
- Verify `Snapshots` tab updated and SNAP_* sheets created.

## On-demand
- Snapshot: `POST /dr/snapshot[?tabs=Signals,Events,Trades]`
- Cleanup: `POST /dr/cleanup?retention_days=14`
- Restore drill: `GET /dr/restore_test?sample_rows=5`

## Incidents
- Webhook down: test `/tv_alert` via curl; check `Snapshots` & app logs (`/tmp/ktw_app.log`).
- Double host: ensure only one active lease; switch Render service to single instance.
- Rate-limit: if 429 on provider APIs, keep `DATA_PROVIDER_CHAIN=dummy` until quota recovers.

> Compliance: Project is for education; live trading requires broker ToS compliance and proper approvals.

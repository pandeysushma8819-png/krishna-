from __future__ import annotations
import asyncio, os, json
from policy.state import POLICY
from scheduling.weekend_gate import is_weekend_ist
from scheduling.holiday_gate import holiday_reason, _load_calendars
from scheduling.news_freeze import active_freeze, next_weekly_digest_utc, _load_policy
from utils.metrics import METRICS
from integrations.sheets import SheetsClient
from utils.time_utils import now_utc

_sheets = SheetsClient()

async def policy_watchdog():
    """
    Periodically evaluate weekend/holiday/freeze and emit events when state changes.
    """
    cfg_cal = _load_calendars()
    cfg_pol = _load_policy()
    markets = os.getenv("MARKETS", "NSE,BANKNIFTY,FINNIFTY,BTCUSD")

    while True:
        try:
            # Weekend (IST)
            wk_on = is_weekend_ist()
            if POLICY.set_weekend(wk_on):
                if wk_on:
                    _sheets.log_event("policy_weekend_on", "Sat/Sun IST", "sched")
                    METRICS.bump("policy_weekend_on")
                else:
                    _sheets.log_event("policy_weekend_off", "Weekday IST", "sched")
                    METRICS.bump("policy_weekend_off")

            # Holiday by calendars
            h_on, h_reason = holiday_reason(markets, cfg=cfg_cal)
            if POLICY.set_holiday(h_on, h_reason):
                if h_on:
                    _sheets.log_event("holiday_halt_on", h_reason, "sched")
                    METRICS.bump("holiday_halt_on")
                else:
                    _sheets.log_event("holiday_halt_off", "", "sched")
                    METRICS.bump("holiday_halt_off")

            # News freeze windows
            f_on, f_tag = active_freeze(cfg=cfg_pol)
            if POLICY.set_freeze(f_on, f_tag):
                if f_on:
                    _sheets.log_event("news_freeze_on", f_tag, "sched")
                    METRICS.bump("news_freeze_on")
                else:
                    _sheets.log_event("news_freeze_off", "", "sched")
                    METRICS.bump("news_freeze_off")

        except Exception:
            METRICS.bump("errors_total")

        await asyncio.sleep(20)  # watchdog tick

async def weekly_digest():
    """
    Once per week (policy.yaml), log a metrics snapshot to Events.
    """
    while True:
        try:
            target = next_weekly_digest_utc()
            now = now_utc()
            wait_sec = max(5.0, (target - now).total_seconds())
            await asyncio.sleep(wait_sec)

            snap = METRICS.snapshot()
            _sheets.log_event("weekly_digest", json.dumps(snap), "sched")
        except Exception:
            METRICS.bump("errors_total")
            await asyncio.sleep(60)  # backoff then retry

async def start_background():
    # Run both loops concurrently
    await asyncio.gather(policy_watchdog(), weekly_digest())

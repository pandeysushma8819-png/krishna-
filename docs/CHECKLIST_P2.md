# Phase 2 — Pen Checklist ✅

## Config
- [ ] `config/calendars.yaml` updated with your real NSE/NYSE holiday dates
- [ ] `config/policy.yaml` news_freezes windows set (CPI/Fed/RBI)
- [ ] weekly_digest schedule set (IST day/time)

## ENV
- [ ] MARKETS covers your active symbols (e.g., "NSE,BANKNIFTY,FINNIFTY,BTCUSD")

## Deploy
- [ ] Service deploy green; `/healthz` shows `"policy": {...}`

## Verify
- [ ] Weekend IST me `policy.weekend_on = true` (Sat/Sun)
- [ ] Aaj agar date holiday list me add karo → `policy.holiday_halt = true` + Events row
- [ ] News freeze window me enter/exit par Events me `news_freeze_on/off`
- [ ] Sunday digest time par `weekly_digest` event log

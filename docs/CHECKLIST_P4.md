# Phase 4 — Telegram Owner Control ✅

## ENV (Render + Local)
- [ ] TELEGRAM_BOT_TOKEN
- [ ] TELEGRAM_OWNER_ID (numeric Telegram user id)
- [ ] TELEGRAM_WEBHOOK_SECRET (e.g., tg-hook)
- [ ] APP_BASE_URL (e.g., https://<service>.onrender.com)

## Webhook
- [ ] Set webhook:
      https://api.telegram.org/bot<TELEGRAM_BOT_TOKEN>/setWebhook?url=<APP_BASE_URL>/telegram/<TELEGRAM_WEBHOOK_SECRET>

## Commands (owner-only)
- /host who                      → lease & control snapshot
- /render status|pause|resume    → optional cost-save hooks
- /panic_flat                    → PANIC ON (blocks new entries)
- /approve on|off                → live approval gate flip (future use)
- /signals on|off                → intake allow/deny
- /report daily|weekly           → links to Signals/Events (stub)

## Verify
- [ ] /host who returns JSON snapshots
- [ ] /panic_flat → `/healthz.control.panic_on = true` and tv_alert returns {"blocked":"panic_on"}
- [ ] /signals off → tv_alert returns {"blocked":"signals_off"}
- [ ] Rate limit: spam commands → "slow down (rate limited)"

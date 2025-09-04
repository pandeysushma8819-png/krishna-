# Phase 3 — Pen Checklist ✅

## ENV
- [ ] HEARTBEAT_SEC set (default 15)
- [ ] LEASE_TTL_SEC set (default 45)
- [ ] HOST_KIND set to "local" on your PC; "render" on Render (optional but clearer)
- [ ] HOST_ID optional (auto-generated if missing)
- [ ] RENDER_AUTOPAUSE=true (optional)
- [ ] RENDER_PAUSE_URL / RENDER_RESUME_URL configured (optional hooks)

## Sheets
- [ ] Service Account has Editor on your Sheet
- [ ] "Status" tab appears with header row
- [ ] Row 2 fills with current lease (owner, heartbeat, ttl, host_id, kind, mode)

## Verify
- [ ] Local boot: `/healthz` shows `"lease": {"mode":"active", "lease_owner":"<LOCAL_HOST_ID>"}`; Render `/healthz` shows `"mode":"passive"`
- [ ] `/tv_alert` on passive host → `{"ok":true,"passive":true}`
- [ ] Kill local (or stop app) → within ~TTL, Render becomes active
- [ ] Optional hooks: local active triggers pause URL; losing lease triggers resume URL (as configured)

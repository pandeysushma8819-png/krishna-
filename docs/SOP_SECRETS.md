# Secrets Hygiene — SOP (Phase 0)

**Golden rules**
1) Secrets sirf ENV me — kabhi repo me nahi.
2) Google Service Account JSON ko **one-line** bana ke env `GOOGLE_SA_JSON` me store karein.
3) Rotation plan: critical secrets (OpenAI, Telegram, Render) **30/60/90 day** cadence par rotate.
4) Access: least-privilege; owner-only for Telegram; Render env only.
5) Backups me secrets NAHI jayenge.

## One-line SA JSON
- Original JSON ko minify karein (remove spaces/newlines) → single line.
- Windows PowerShell:
  ```powershell
  (Get-Content sa.json -Raw) -replace '\s','' | Set-Content -NoNewline sa_oneline.txt

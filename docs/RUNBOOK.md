# RUNBOOK (P0 stub)

## Local setup
1) Python 3.11.8, create venv, `pip install -r requirements.txt`
2) Copy `config/secrets_template.env` → `.env` and fill placeholders
3) Run health: `python krishna_main.py health`
4) Optional NTP check: `python krishna_main.py ntp-check`
5) Budget dry-run: `python krishna_main.py budget-test --cost 0.50`

## Render (later phases)
- Procfile & runtime.txt already set; deploy hook to be wired in P3.

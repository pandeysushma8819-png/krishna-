# Phase 5 — Data Layer & Backtesting ✅

## Data hygiene
- [ ] Input bars run through: dedupe → fill_missing (tf) → spike clamp (≤15% jump)
- [ ] Corporate actions applied (splits/dividends), futures continuous roll (ratio)

## Costs model
- [ ] `config/costs.yaml` edited for your broker/plan
- [ ] `market`, `product`, `plan`, `lot_size` correct per instrument

## Backtest
- [ ] No look-ahead: fills at **next bar open** (or close) with slippage & spread
- [ ] Costs deducted per leg (STT/Exch/SEBI/Stamp/GST/Brokerage)
- [ ] Outputs: equity curve, trades, KPIs (PF, Win%, MaxDD, Return%)

## Quick CLI test
```bash
python scripts/backtest_cli.py --bars-json samples/bars.json --target-json samples/target.json --tf-sec 900 --lot-size 50 --market NSE --product futures --plan INDIA_DISCOUNT --slip-bps 1.5 --spread-bps 0.5

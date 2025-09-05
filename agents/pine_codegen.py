from __future__ import annotations
import json
from typing import Dict, Any

def _pine_header(name: str, initial_capital: float = 1_000_000.0) -> str:
    return f"""//@version=5
strategy("{name}",
     overlay=true,
     initial_capital={initial_capital},
     default_qty_type=strategy.fixed,
     default_qty_value=input.float(1.0, "Order size (shares/contracts)", minval=0.0),
     commission_type=strategy.commission.percent,
     commission_value=input.float(0.03, "Commission % per leg", step=0.001),
     slippage=input.int(0, "Slippage (ticks)"),
     calc_on_every_tick=false,
     calc_on_order_fills=false,
     process_orders_on_close=true,
     pyramiding=0)"""

def _pine_body_ema_cross(fast: int, slow: int) -> str:
    return f"""
// === Inputs
fastLen = input.int({fast}, "Fast EMA", minval=2)
slowLen = input.int({slow}, "Slow EMA", minval=3)
slowLen := math.max(slowLen, fastLen + 1)  // ensure slow > fast

// === Series
emaFast = ta.ema(close, fastLen)
emaSlow = ta.ema(close, slowLen)

// === No look-ahead: base signals on previous bar state
longSig = ta.crossover(emaFast[1], emaSlow[1])
flatSig = ta.crossunder(emaFast[1], emaSlow[1])

// === Execution: act only on confirmed bars
if barstate.isconfirmed
    if (longSig and strategy.position_size <= 0)
        strategy.entry("L", strategy.long)
    if (flatSig and strategy.position_size > 0)
        strategy.close("L")

// === Plots
plot(emaFast, color=color.new(color.teal, 0), title="EMA Fast")
plot(emaSlow, color=color.new(color.orange, 0), title="EMA Slow")
plotshape(barstate.isconfirmed and longSig, title="Long", style=shape.triangleup, color=color.new(color.teal,0), location=location.belowbar, size=size.tiny, text="L")
plotshape(barstate.isconfirmed and flatSig,  title="Flat", style=shape.triangledown, color=color.new(color.orange,0), location=location.abovebar, size=size.tiny, text="F")

// === Notes
// • Signals are computed from [1] (prior bar) and executed on the current confirmed bar.
// • With process_orders_on_close=true, fills occur on the bar's close (TradingView model).
// • Your live engine fills on the next bar; treat this script as a sanity backtest.
"""

def _pine_body_rsi_reversion(period: int, buy_th: float, sell_th: float) -> str:
    return f"""
// === Inputs
rsiLen  = input.int({period}, "RSI Length",  minval=2)
buyTh   = input.float({buy_th}, "Buy RSI ≤",  step=0.1)
sellTh  = input.float({sell_th}, "Sell RSI ≥", step=0.1)

// === Series
r = ta.rsi(close, rsiLen)

// === No look-ahead: use prior bar RSI
goLong = r[1] <= buyTh
goFlat = r[1] >= sellTh

if barstate.isconfirmed
    if (goLong and strategy.position_size <= 0)
        strategy.entry("L", strategy.long)
    if (goFlat and strategy.position_size > 0)
        strategy.close("L")

plot(r, title="RSI", color=color.new(color.aqua, 0))
hline(buyTh, "BuyTh", color=color.new(color.green, 50))
hline(sellTh, "SellTh", color=color.new(color.red,   50))
"""

def generate_pine(spec: Dict[str, Any]) -> str:
    sid = spec["strategy_id"].lower()
    ver = spec.get("version", "v0")
    name = f"KTW — {sid.upper()} ({ver})"
    header = _pine_header(name)
    if sid == "ema_cross":
        p = spec.get("params", {})
        fast = int(p.get("fast", 10))
        slow = int(p.get("slow", 30))
        return header + _pine_body_ema_cross(fast, slow)
    elif sid == "rsi_reversion":
        p = spec.get("params", {})
        period  = int(p.get("period", 14))
        buy_th  = float(p.get("buy_th", 30.0))
        sell_th = float(p.get("sell_th", 55.0))
        return header + _pine_body_rsi_reversion(period, buy_th, sell_th)
    else:
        return header + "\n// TODO: unsupported strategy_id\n"

if __name__ == "__main__":
    import argparse, sys, pathlib
    ap = argparse.ArgumentParser("KTW Pine v5 codegen")
    ap.add_argument("--spec-json", required=True, help="StrategySpec JSON file")
    ap.add_argument("--out", default="", help="Write to file (optional)")
    args = ap.parse_args()
    spec = json.load(open(args.spec_json))
    code = generate_pine(spec)
    if args.out:
        pathlib.Path(args.out).write_text(code, encoding="utf-8")
        print(f"OK: wrote {args.out}")
    else:
        sys.stdout.write(code)

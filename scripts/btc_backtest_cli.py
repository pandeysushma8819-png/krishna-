# scripts/btc_backtest_cli.py
# Backtest runner for Bitcoin (4H CSV) using strategies/auto_shift_buy.py
# Usage:
#   python scripts/btc_backtest_cli.py --csv data/BTCUSDT_4H.csv --out out/btc

from __future__ import annotations
import argparse, os, json
import pandas as pd

from strategies.auto_shift_buy import generate_trades, to_target_json

def load_4h_csv(path: str) -> pd.DataFrame:
    df = pd.read_csv(path)
    # Expect either 'ts' or 'timestamp'
    if "ts" not in df.columns and "timestamp" in df.columns:
        df = df.rename(columns={"timestamp": "ts"})
    need = ["ts", "open", "high", "low", "close", "volume"]
    miss = [c for c in need if c not in df.columns]
    if miss:
        raise ValueError(f"CSV missing columns: {miss}")
    # Normalize types
    df["ts"] = pd.to_datetime(df["ts"])
    for c in ["open","high","low","close","volume"]:
        df[c] = df[c].astype(float)
    df = df.sort_values("ts").reset_index(drop=True)
    return df

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv", required=True, help="Path to BTC 4H OHLCV CSV (ts,open,high,low,close,volume)")
    ap.add_argument("--out", default="out/btc", help="Output dir (will be created)")
    ap.add_argument("--target", type=float, default=1000.0, help="Target per entry (points)")
    ap.add_argument("--ecr_pct", type=float, default=10.0, help="ECR overlap % (re-entry gate)")
    ap.add_argument("--ma_len", type=int, default=50, help="MA length (all TFs)")
    ap.add_argument("--vol_len", type=int, default=20, help="Volume SMA length (all TFs)")
    ap.add_argument("--max_entries", type=int, default=4, help="Per-TF window quota")
    args = ap.parse_args()

    os.makedirs(args.out, exist_ok=True)
    df = load_4h_csv(args.csv)

    params = {
        "target_per_entry": args.target,
        "ecr_overlap_pct": args.ecr_pct,
        "ma_len": args.ma_len,
        "vol_sma_len": args.vol_len,
        "max_entries_per_window": args.max_entries,
    }

    trades = generate_trades(df, params)
    out_json = to_target_json(trades)

    # Save trades.csv + trades.json
    trades_df = pd.DataFrame(trades)
    trades_csv = os.path.join(args.out, "trades.csv")
    trades_json = os.path.join(args.out, "trades.json")
    trades_df.to_csv(trades_csv, index=False)
    with open(trades_json, "w", encoding="utf-8") as f:
        json.dump(out_json, f, ensure_ascii=False)

    # Summary
    total = len(trades_df)
    total_pnl = float(trades_df["pnl"].sum()) if total else 0.0
    avg_pnl = float(trades_df["pnl"].mean()) if total else 0.0
    by_tf = trades_df["tf"].value_counts().to_dict() if total else {}

    print("==== BTC Backtest Summary ====")
    print(f"trades_closed: {total}")
    print(f"pnl_total: {total_pnl:.2f}")
    print(f"pnl_avg_per_trade: {avg_pnl:.2f}")
    print(f"trades_by_tf: {by_tf}")
    print(f"saved: {trades_csv}")
    print(f"saved: {trades_json}")

    # Preview
    if total:
        print("---- sample rows ----")
        print(trades_df.head(5).to_string(index=False))

if __name__ == "__main__":
    main()

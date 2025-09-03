from __future__ import annotations
import os, argparse, yaml, sys
from utils.time_utils import now_utc, now_ist, fmt
from utils.budget_guard import BudgetGuard
from ops.ntp_check import ntp_skew_seconds

def load_settings(path: str = "config/settings.yaml") -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def cmd_health(args) -> int:
    cfg = load_settings()
    print("== HEALTH ==")
    print(f"App: {cfg['app']['name']}")
    print(f"UTC now: {fmt(now_utc())}")
    print(f"IST now: {fmt(now_ist())}")
    print(f"Heartbeat: {cfg['app']['heartbeat_sec']}s, LeaseTTL: {cfg['app']['lease_ttl_sec']}s")
    print(f"FeatureFlags: {cfg['feature_flags']}")
    # Budget
    cap = float(os.getenv("OPENAI_BUDGET_USD", cfg["budget"]["openai_budget_usd"]))
    guard = BudgetGuard(cap, cfg["budget"]["hard_stop"], cfg["budget"]["state_path"])
    print(f"Budget cap: ${cap:.2f}, used: ${guard.usage():.2f}, remaining: ${guard.remaining():.2f}")
    print("Health: OK (P0)")
    return 0

def cmd_ntp_check(args) -> int:
    cfg = load_settings()
    if not cfg["feature_flags"].get("ntp_check_enabled", True):
        print("NTP check disabled.")
        return 0
    max_skew = float(cfg["ntp"]["max_skew_seconds"])
    timeout = float(cfg["ntp"]["timeout_sec"])
    servers = cfg["ntp"]["servers"]
    ok = False
    for s in servers:
        try:
            used, skew = ntp_skew_seconds(s, timeout)
            print(f"NTP {used} skew: {skew:.3f}s (max {max_skew:.3f}s)")
            if abs(skew) <= max_skew:
                ok = True
                break
        except Exception as e:
            print(f"NTP {s} failed: {e}")
            continue
    print("NTP status:", "OK" if ok else "WARN: skew>limit or all servers failed")
    return 0 if ok else 1

def cmd_budget_test(args) -> int:
    cfg = load_settings()
    cap = float(os.getenv("OPENAI_BUDGET_USD", cfg["budget"]["openai_budget_usd"]))
    guard = BudgetGuard(cap, cfg["budget"]["hard_stop"], cfg["budget"]["state_path"])
    cost = float(args.cost)
    allowed = guard.allow(cost)
    print(f"Proposed cost: ${cost:.2f}")
    print(f"Current usage: ${guard.usage():.2f} / ${cap:.2f} (remaining ${guard.remaining():.2f})")
    print("Allow? ", "YES" if allowed else "NO (cap hit + hard_stop)")
    if allowed:
        guard.add(cost)
        print(f"New usage: ${guard.usage():.2f}")
    return 0 if allowed else 2

def main():
    ap = argparse.ArgumentParser(prog="krishna_main", description="KTW core (Phase 0)")
    sub = ap.add_subparsers(dest="cmd")

    p1 = sub.add_parser("health", help="show health & flags")
    p1.set_defaults(func=cmd_health)

    p2 = sub.add_parser("ntp-check", help="query NTP servers and show clock skew")
    p2.set_defaults(func=cmd_ntp_check)

    p3 = sub.add_parser("budget-test", help="simulate a spend and apply budget guard")
    p3.add_argument("--cost", required=True, help="dollars to add (e.g., 0.50)")
    p3.set_defaults(func=cmd_budget_test)

    args = ap.parse_args()
    if not getattr(args, "cmd", None):
        ap.print_help()
        sys.exit(1)
    rc = args.func(args)
    sys.exit(rc)

if __name__ == "__main__":
    main()

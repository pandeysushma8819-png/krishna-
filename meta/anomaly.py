from __future__ import annotations
from typing import List, Dict, Tuple
import statistics, time
from .regime import pct_returns, ema, ts_to_ist_str

def detect_anomalies(bars: List[dict],
                     tf_sec: int,
                     z_lookback: int = 30,
                     z_thr_spike: float = 3.0,
                     chop_window: int = 20,
                     chop_switches_thr: int = 6) -> List[Dict]:
    """Return list of anomaly events with recommended actions."""
    if len(bars) < max(z_lookback+2, chop_window+2):
        return []

    closes = [float(b["close"]) for b in bars]
    rets = pct_returns(closes)

    # spike: latest return z-score
    w = rets[-z_lookback:]
    mu = statistics.fmean(w); sd = statistics.pstdev(w) or 1e-9
    z = (rets[-1] - mu) / sd
    events: List[Dict] = []
    now_ts = int(bars[-1]["ts"])

    if abs(z) >= z_thr_spike:
        severity = "high" if abs(z) >= z_thr_spike + 1.0 else "med"
        action = "pause" if severity == "high" else "scale_down"
        events.append({
            "ts": now_ts, "ist": ts_to_ist_str(now_ts),
            "kind": "anomaly", "tag": "return_spike",
            "score": round(abs(z), 2), "severity": severity,
            "action": action, "risk_scale": 0.0 if action=="pause" else 0.5,
            "cooldown_min": 20 if action=="pause" else 10,
            "reason": f"|z|={abs(z):.2f} over {z_lookback} bars"
        })

    # chop: fast/slow EMA delta sign switches in recent window
    fast = 8; slow = 21
    efast = ema(closes, fast); eslow = ema(closes, slow)
    delta_sign = [1 if (efast[i]-eslow[i])>0 else -1 for i in range(len(closes))]
    w = delta_sign[-chop_window:]
    switches = sum(1 for i in range(1, len(w)) if w[i]!=w[i-1])
    if switches >= chop_switches_thr:
        events.append({
            "ts": now_ts, "ist": ts_to_ist_str(now_ts),
            "kind": "anomaly", "tag": "chop_whipsaw",
            "score": switches, "severity": "med",
            "action": "scale_down", "risk_scale": 0.5,
            "cooldown_min": 15,
            "reason": f"{switches} EMA-cross reversals in {chop_window} bars"
        })
    return events

def decide_guard(regime: str, anomalies: List[Dict]) -> Dict:
    """Combine regime & anomalies to recommend guard state."""
    action = "none"; risk_scale = 1.0; cooldown_min = 0; reason = ""
    sev = {"low":1, "med":2, "high":3}
    top = max(anomalies, key=lambda e: sev.get(e.get("severity","low"),1)) if anomalies else None

    if top:
        action = top["action"]; risk_scale = top["risk_scale"]; cooldown_min = top["cooldown_min"]
        reason = f"anomaly:{top['tag']} ({top['severity']})"
    elif regime == "high_vol":
        action = "scale_down"; risk_scale = 0.6; cooldown_min = 10; reason = "regime:high_vol"
    elif regime == "sideways":
        action = "scale_down"; risk_scale = 0.8; cooldown_min = 0; reason = "regime:sideways"

    return {
        "action": action,
        "risk_scale": risk_scale,
        "cooldown_min": cooldown_min,
        "reason": reason
    }

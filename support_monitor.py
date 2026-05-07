#!/usr/bin/env python3
"""
Real-time support/resistance level monitor for OKLL.

Reads config.json for tier definitions and watches signal.json (written by the
running poller) for live price + TradingView TA data.  Outputs one status line
every <interval> seconds; emits ALERT lines when price is within
<alert_pct>% of any tier.

Usage:
    python support_monitor.py [interval_seconds] [alert_pct]

Defaults: interval=30s, alert_pct=2.0%
"""
import json
import os
import sys
import time
from datetime import datetime

CONFIG = json.load(open("config.json"))
SYMBOL = CONFIG["instrument"]
AVG_COST = CONFIG["avg_cost"]
SIGNAL_FILE = "signal.json"

SELL_TIERS = [
    {
        "label": f"+{t['gain_pct']}% resistance",
        "price": AVG_COST * (1 + t["gain_pct"] / 100),
        "action": f"sell {t['sell_pct']}% of position",
        "kind": "resistance",
    }
    for t in CONFIG["scale_out"]["tiers"]
]

# Buy tiers are calculated from avg_cost as a static baseline.
# At runtime the poller uses peak_trim_price, but avg_cost gives a useful
# standing reference visible without a live poller session.
BUY_TIERS = [
    {
        "label": f"-{t['pullback_pct']}% support",
        "price": AVG_COST * (1 - t["pullback_pct"] / 100),
        "action": f"buy {t['buy_pct_cash']}% of cash",
        "kind": "support",
    }
    for t in CONFIG["scale_in"]["tiers"]
]

ALL_TIERS = SELL_TIERS + BUY_TIERS


def _load_signal() -> dict:
    try:
        if os.path.exists(SIGNAL_FILE):
            with open(SIGNAL_FILE) as f:
                return json.load(f)
    except Exception:
        pass
    return {}


def _ts() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _pct(a: float, b: float) -> float:
    return (a - b) / b * 100


def _nearest(price: float, kind: str) -> tuple[dict, float] | None:
    tiers = [t for t in ALL_TIERS if t["kind"] == kind]
    if not tiers:
        return None
    # For resistance: nearest = lowest price above current; pct = how far away
    # For support:    nearest = highest price below current; pct = how far above
    if kind == "resistance":
        above = [t for t in tiers if t["price"] > price]
        if not above:
            return None
        t = min(above, key=lambda x: x["price"])
        return t, _pct(t["price"], price)
    else:
        below = [t for t in tiers if t["price"] < price]
        if not below:
            return None
        t = max(below, key=lambda x: x["price"])
        return t, _pct(price, t["price"])


def emit_status(price: float | None, sig: dict, alert_pct: float) -> None:
    ta = (
        f"TA={sig.get('ta_overall','?')} "
        f"RSI={sig.get('ta_rsi','?')} "
        f"MACD={sig.get('ta_macd','?')} "
        f"MA={sig.get('ta_ma','?')}"
    )

    if price is None:
        print(f"[{_ts()}] {SYMBOL} — waiting for poller data | {ta}", flush=True)
        return

    gain = _pct(price, AVG_COST)
    print(
        f"[{_ts()}] {SYMBOL} ${price:.4f} ({gain:+.1f}%) | {ta}",
        flush=True,
    )

    # Proximity alerts
    res = _nearest(price, "resistance")
    sup = _nearest(price, "support")

    if res:
        tier, dist = res
        flag = " *** ALERT ***" if dist <= alert_pct else ""
        print(
            f"         Nearest resistance: {tier['label']} @ ${tier['price']:.4f} "
            f"({dist:.1f}% away) → {tier['action']}{flag}",
            flush=True,
        )

    if sup:
        tier, dist = sup
        flag = " *** ALERT ***" if dist <= alert_pct else ""
        print(
            f"         Nearest support:    {tier['label']} @ ${tier['price']:.4f} "
            f"({dist:.1f}% above) → {tier['action']}{flag}",
            flush=True,
        )

    # New signal notice
    last_sig = sig.get("signal")
    last_ts = sig.get("timestamp")
    if last_sig and last_ts and time.time() - last_ts < 300:
        age = int(time.time() - last_ts)
        print(
            f"         Last signal: {last_sig.upper()} {sig.get('pct',0)*100:.0f}% "
            f"@ ${sig.get('price',0):.4f}  ({age}s ago)",
            flush=True,
        )


def print_tier_table() -> None:
    print(f"[{_ts()}] Tier map for {SYMBOL} (avg cost ${AVG_COST})", flush=True)
    print("  RESISTANCE:", flush=True)
    for t in SELL_TIERS:
        print(f"    {t['label']:20s}  ${t['price']:.4f}  → {t['action']}", flush=True)
    print("  SUPPORT (from avg cost):", flush=True)
    for t in BUY_TIERS:
        print(f"    {t['label']:20s}  ${t['price']:.4f}  → {t['action']}", flush=True)
    print(flush=True)


def main() -> None:
    interval = int(sys.argv[1]) if len(sys.argv) > 1 else 30
    alert_pct = float(sys.argv[2]) if len(sys.argv) > 2 else 2.0

    print(
        f"[{_ts()}] Support monitor started — {SYMBOL} | "
        f"refresh={interval}s | alert within {alert_pct}%",
        flush=True,
    )
    print_tier_table()

    last_sig_ts: float | None = None

    while True:
        sig = _load_signal()
        price: float | None = sig.get("price")

        sig_ts = sig.get("timestamp")
        if sig_ts != last_sig_ts and sig.get("signal"):
            last_sig_ts = sig_ts
            print(
                f"[{_ts()}] *** NEW SIGNAL: {sig['signal'].upper()} "
                f"{sig.get('pct',0)*100:.0f}% @ ${sig.get('price',0):.4f} ***",
                flush=True,
            )

        emit_status(price, sig, alert_pct)
        print(flush=True)
        time.sleep(interval)


if __name__ == "__main__":
    main()

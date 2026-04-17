"""
Main entry point: runs scale-out/scale-in signal loop with TA gating and heartbeat.
Persists cycle state to state.json so the dashboard and restarts stay in sync.
"""
import asyncio
import json
import os
import time
from datetime import datetime, timezone

from session import connect, ensure_session, heartbeat_loop
from poller import get_price, evaluate_signal, POLL_INTERVAL, HEARTBEAT_INTERVAL, TA_POLL_INTERVAL, BUY_TIERS
from technicals import fetch_ta, TASignal
from trader import execute_trim, execute_reload
from notifications import notify

CONFIG = json.load(open("config.json"))
STATE_FILE = CONFIG.get("state_file", "state.json")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _load_state() -> dict:
    if os.path.exists(STATE_FILE):
        try:
            return json.load(open(STATE_FILE))
        except Exception:
            pass
    return {
        "triggered_sell_tiers": [],
        "triggered_buy_tiers": [],
        "accumulated_cash": 0.0,
        "peak_trim_price": None,
    }


def _save_state(
    triggered_sell_tiers: set,
    triggered_buy_tiers: set,
    accumulated_cash: float,
    peak_trim_price: float | None,
    price: float | None,
    ta: TASignal,
) -> None:
    cfg = json.load(open("config.json"))
    state = {
        "instrument": cfg["instrument"],
        "current_shares": cfg.get("current_shares", 0),
        "avg_cost": cfg.get("avg_cost", 0),
        "last_price": price,
        "last_price_time": _now_iso(),
        "triggered_sell_tiers": sorted(triggered_sell_tiers),
        "triggered_buy_tiers": sorted(triggered_buy_tiers),
        "accumulated_cash": round(accumulated_cash, 4),
        "peak_trim_price": peak_trim_price,
        "ta": {
            "overall": ta.overall,
            "rsi": ta.rsi,
            "macd_action": ta.macd_action,
            "ma_action": ta.ma_action,
        },
        "scale_out_tiers": cfg["scale_out"]["tiers"],
        "scale_in_tiers": cfg["scale_in"]["tiers"],
        "last_updated": _now_iso(),
    }
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def _reset_cycle() -> tuple[set, set, float, None]:
    return set(), set(), 0.0, None


async def signal_loop(context) -> None:
    saved = _load_state()
    triggered_sell_tiers = set(saved.get("triggered_sell_tiers", []))
    triggered_buy_tiers = set(saved.get("triggered_buy_tiers", []))
    accumulated_cash = saved.get("accumulated_cash", 0.0)
    peak_trim_price = saved.get("peak_trim_price")

    page = await ensure_session(context)
    ta: TASignal = TASignal()
    last_ta_fetch = 0.0

    while True:
        try:
            now = time.time()
            if now - last_ta_fetch >= TA_POLL_INTERVAL:
                ta = await fetch_ta(context)
                last_ta_fetch = now

            price = await get_price(page)
            if price is not None:
                print(
                    f"[main] {CONFIG['instrument']} = ${price:.4f} | "
                    f"TA={ta.overall} RSI={ta.rsi} | "
                    f"sell_tiers={triggered_sell_tiers} buy_tiers={triggered_buy_tiers} "
                    f"cash=${accumulated_cash:.2f}"
                )
                result = evaluate_signal(
                    price, ta, triggered_sell_tiers, triggered_buy_tiers, peak_trim_price
                )

                if result:
                    signal, pct = result

                    if signal == "trim":
                        tier_idx = next(
                            i for i, _ in enumerate(CONFIG["scale_out"]["tiers"])
                            if i not in triggered_sell_tiers
                        )
                        cash = await execute_trim(context, price, pct)
                        triggered_sell_tiers.add(tier_idx)
                        accumulated_cash += cash
                        if peak_trim_price is None or price > peak_trim_price:
                            peak_trim_price = price

                    elif signal == "reload":
                        tier_idx = next(
                            i for i, _ in enumerate(BUY_TIERS)
                            if i not in triggered_buy_tiers
                        )
                        cash_for_tier = accumulated_cash * pct
                        await execute_reload(context, price, cash_for_tier)
                        triggered_buy_tiers.add(tier_idx)
                        accumulated_cash -= cash_for_tier

                        if len(triggered_buy_tiers) >= len(BUY_TIERS):
                            triggered_sell_tiers, triggered_buy_tiers, accumulated_cash, peak_trim_price = _reset_cycle()
                            await notify("Cycle complete — all scale-in tiers fired, resetting for next cycle")

                _save_state(triggered_sell_tiers, triggered_buy_tiers, accumulated_cash, peak_trim_price, price, ta)

        except Exception as e:
            print(f"[main] error: {e}")
            page = await ensure_session(context)

        await asyncio.sleep(POLL_INTERVAL)


async def main() -> None:
    browser, context = await connect()
    await notify("Robinhood OKLL automation started")
    await asyncio.gather(
        signal_loop(context),
        heartbeat_loop(context, HEARTBEAT_INTERVAL),
    )


if __name__ == "__main__":
    asyncio.run(main())

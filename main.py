"""
Main entry point: runs poller and heartbeat, triggers trader when signal fires.
"""
import asyncio
import json
import os
import time

from session import connect, ensure_session, heartbeat_loop
from poller import get_price, _evaluate_signal, POLL_INTERVAL, HEARTBEAT_INTERVAL
from trader import execute_trim, execute_reload
from notifications import notify

CONFIG = json.load(open("config.json"))
_last_trim_price: float | None = None
_trim_cash: float = 0.0


async def signal_loop(context) -> None:
    global _last_trim_price, _trim_cash
    page = await ensure_session(context)

    while True:
        try:
            price = await get_price(page)
            if price is not None:
                print(f"[main] {CONFIG['instrument']} = ${price:.4f}")
                signal = _evaluate_signal(price)

                if signal == "trim":
                    shares_before = CONFIG.get("current_shares", 0)
                    await execute_trim(context, price)
                    CONFIG_fresh = json.load(open("config.json"))
                    shares_after = CONFIG_fresh.get("current_shares", 0)
                    sold = shares_before - shares_after
                    _trim_cash = sold * price
                    _last_trim_price = price

                elif signal == "reload" and _trim_cash > 0:
                    await execute_reload(context, price, _trim_cash)
                    _trim_cash = 0.0
                    _last_trim_price = None

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

"""
Main entry point: runs price poller + TA fetcher + heartbeat, triggers trader on signals.
"""
import asyncio
import json

from session import connect, ensure_session, heartbeat_loop
from poller import get_price, evaluate_signal, POLL_INTERVAL, HEARTBEAT_INTERVAL, TA_POLL_INTERVAL
from technicals import fetch_ta, TASignal
from trader import execute_trim, execute_reload
from notifications import notify
import time

CONFIG = json.load(open("config.json"))
_last_trim_price: float | None = None
_trim_cash: float = 0.0


async def signal_loop(context) -> None:
    global _last_trim_price, _trim_cash
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
                print(f"[main] {CONFIG['instrument']} = ${price:.4f} | TA={ta.overall} RSI={ta.rsi}")
                signal = evaluate_signal(price, ta)

                if signal == "trim":
                    cfg = json.load(open("config.json"))
                    shares_before = cfg.get("current_shares", 0)
                    await execute_trim(context, price)
                    cfg_after = json.load(open("config.json"))
                    sold = shares_before - cfg_after.get("current_shares", 0)
                    _trim_cash += sold * price
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

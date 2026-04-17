"""
Main entry point: runs scale-out/scale-in signal loop with TA gating and heartbeat.

Cycle state:
  triggered_sell_tiers — which scale-out tiers have fired this cycle
  triggered_buy_tiers  — which scale-in tiers have fired this cycle
  accumulated_cash     — total cash from all scale-out trims this cycle
  peak_trim_price      — highest trim price (used as pullback reference)

Cycle resets when the final scale-in tier fires (all cash redeployed).
"""
import asyncio
import json
import time

from session import connect, ensure_session, heartbeat_loop
from poller import get_price, evaluate_signal, POLL_INTERVAL, HEARTBEAT_INTERVAL, TA_POLL_INTERVAL, BUY_TIERS
from technicals import fetch_ta, TASignal
from trader import execute_trim, execute_reload
from notifications import notify

CONFIG = json.load(open("config.json"))


def _reset_cycle() -> tuple[set, set, float, None]:
    return set(), set(), 0.0, None


async def signal_loop(context) -> None:
    page = await ensure_session(context)
    ta: TASignal = TASignal()
    last_ta_fetch = 0.0
    triggered_sell_tiers, triggered_buy_tiers, accumulated_cash, peak_trim_price = _reset_cycle()

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
                            i for i, t in enumerate(
                                [{"gain": x["gain_pct"]/100} for x in CONFIG["scale_out"]["tiers"]]
                            )
                            if i not in triggered_sell_tiers
                        )
                        cash = await execute_trim(context, price, pct)
                        triggered_sell_tiers.add(tier_idx)
                        accumulated_cash += cash
                        if peak_trim_price is None or price > peak_trim_price:
                            peak_trim_price = price

                    elif signal == "reload":
                        tier_idx = next(
                            i for i, t in enumerate(BUY_TIERS)
                            if i not in triggered_buy_tiers
                        )
                        cash_for_tier = accumulated_cash * pct
                        await execute_reload(context, price, cash_for_tier)
                        triggered_buy_tiers.add(tier_idx)
                        accumulated_cash -= cash_for_tier

                        if len(triggered_buy_tiers) >= len(BUY_TIERS):
                            triggered_sell_tiers, triggered_buy_tiers, accumulated_cash, peak_trim_price = _reset_cycle()
                            await notify("Cycle complete — all scale-in tiers fired, resetting for next cycle")

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

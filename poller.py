"""
Price poller: evaluates scale-out trim tiers and scale-in reload tiers,
gated by TradingView technical analysis.

Scale-out: as price climbs through gain thresholds, sell increasing slices.
Scale-in:  after peak trim, as price drops through pullback thresholds,
           redeploy increasing portions of accumulated cash.
Each tier fires once per cycle; cycle resets when all scale-in cash is spent.
"""
import asyncio
import json
import re
import time
from playwright.async_api import BrowserContext, Page

from session import connect, ensure_session, heartbeat_loop
from technicals import TASignal, fetch_ta
from notifications import notify

CONFIG = json.load(open("config.json"))
SYMBOL = CONFIG["instrument"]
POLL_INTERVAL = CONFIG["poll_interval_seconds"]
HEARTBEAT_INTERVAL = CONFIG["heartbeat_interval_seconds"]
TA_POLL_INTERVAL = CONFIG["technicals"]["poll_interval_seconds"]
AVG_COST = CONFIG["avg_cost"]

SELL_TIERS = [
    {"gain": t["gain_pct"] / 100, "sell_pct": t["sell_pct"] / 100}
    for t in CONFIG["scale_out"]["tiers"]
]
BUY_TIERS = [
    {"pullback": t["pullback_pct"] / 100, "buy_pct_cash": t["buy_pct_cash"] / 100}
    for t in CONFIG["scale_in"]["tiers"]
]


async def get_price(page: Page) -> float | None:
    url = f"https://robinhood.com/stocks/{SYMBOL}/"
    if SYMBOL.lower() not in page.url.lower():
        await page.goto(url)
        await page.wait_for_load_state("domcontentloaded")

    try:
        price_el = page.locator('[data-testid="price"], span[class*="price"]').first
        text = await price_el.inner_text(timeout=8000)
        return float(re.sub(r"[^\d.]", "", text))
    except Exception:
        pass

    try:
        content = await page.content()
        matches = re.findall(r'\$(\d+\.\d{2})', content)
        if matches:
            return float(matches[0])
    except Exception:
        pass

    return None


def evaluate_signal(
    price: float,
    ta: TASignal,
    triggered_sell_tiers: set[int],
    triggered_buy_tiers: set[int],
    peak_trim_price: float | None,
) -> tuple[str, float] | None:
    """
    Returns:
      ("trim", sell_pct)           — scale-out tier fired; sell sell_pct of position
      ("reload", buy_pct_cash)     — scale-in tier fired; spend buy_pct_cash of accumulated cash
      None                         — no action
    Scale-out tiers take priority; scale-in only evaluates after at least one trim has fired.
    """
    gain = (price - AVG_COST) / AVG_COST

    for i, tier in enumerate(SELL_TIERS):
        if i not in triggered_sell_tiers and gain >= tier["gain"]:
            if ta.trim_confirmed():
                return ("trim", tier["sell_pct"])
            print(
                f"[poller] sell tier {i} (+{tier['gain']*100:.0f}%) blocked "
                f"by TA (overall={ta.overall}, RSI={ta.rsi})"
            )
            break  # only surface the lowest un-triggered tier at a time

    if peak_trim_price is not None:
        pullback = (peak_trim_price - price) / peak_trim_price
        for i, tier in enumerate(BUY_TIERS):
            if i not in triggered_buy_tiers and pullback >= tier["pullback"]:
                if ta.reload_confirmed():
                    return ("reload", tier["buy_pct_cash"])
                print(
                    f"[poller] buy tier {i} ({tier['pullback']*100:.0f}% pullback) blocked "
                    f"by TA (overall={ta.overall}, RSI={ta.rsi})"
                )
                break

    return None


async def poll_loop(context: BrowserContext) -> None:
    page = await ensure_session(context)
    ta: TASignal = TASignal()
    last_ta_fetch = 0.0
    triggered_sell_tiers: set[int] = set()
    triggered_buy_tiers: set[int] = set()
    peak_trim_price: float | None = None

    while True:
        try:
            now = time.time()
            if now - last_ta_fetch >= TA_POLL_INTERVAL:
                ta = await fetch_ta(context)
                last_ta_fetch = now

            price = await get_price(page)
            if price is None:
                print("[poller] could not read price")
            else:
                print(f"[poller] {SYMBOL} = ${price:.4f} | TA={ta.overall} RSI={ta.rsi}")
                result = evaluate_signal(
                    price, ta, triggered_sell_tiers, triggered_buy_tiers, peak_trim_price
                )
                if result:
                    signal, pct = result
                    await notify(
                        f"Signal: {signal.upper()} {pct*100:.0f}% at ${price:.4f} "
                        f"| TA={ta.overall} RSI={ta.rsi}"
                    )
                    with open("signal.json", "w") as f:
                        json.dump({
                            "signal": signal,
                            "pct": pct,
                            "price": price,
                            "ta_overall": ta.overall,
                            "ta_rsi": ta.rsi,
                            "ta_macd": ta.macd_action,
                            "ta_ma": ta.ma_action,
                            "timestamp": now,
                        }, f)
        except Exception as e:
            print(f"[poller] error: {e}")
            page = await ensure_session(context)

        await asyncio.sleep(POLL_INTERVAL)


async def main() -> None:
    browser, context = await connect()
    await asyncio.gather(
        poll_loop(context),
        heartbeat_loop(context, HEARTBEAT_INTERVAL),
    )


if __name__ == "__main__":
    asyncio.run(main())

"""
Price poller: reads OKLL price from Robinhood page, evaluates trim/reload
conditions, and writes a signal file when action is needed.
"""
import asyncio
import json
import re
import time
from playwright.async_api import BrowserContext, Page

from session import connect, ensure_session, heartbeat_loop
from notifications import notify

CONFIG = json.load(open("config.json"))
SYMBOL = CONFIG["instrument"]
POLL_INTERVAL = CONFIG["poll_interval_seconds"]
HEARTBEAT_INTERVAL = CONFIG["heartbeat_interval_seconds"]
AVG_COST = CONFIG["avg_cost"]
TRIM_LOW = CONFIG["trim"]["trigger_gain_pct_low"] / 100
TRIM_HIGH = CONFIG["trim"]["trigger_gain_pct_high"] / 100
RELOAD_LOW = CONFIG["reload"]["pullback_pct_low"] / 100
RELOAD_HIGH = CONFIG["reload"]["pullback_pct_high"] / 100

_last_trim_price: float | None = None


async def get_price(page: Page) -> float | None:
    url = f"https://robinhood.com/stocks/{SYMBOL}/"
    if SYMBOL.lower() not in page.url.lower():
        await page.goto(url)
        await page.wait_for_load_state("domcontentloaded")

    try:
        # Primary: span containing the current price near the chart header
        price_el = page.locator('[data-testid="price"], span[class*="price"]').first
        text = await price_el.inner_text(timeout=8000)
        return float(re.sub(r"[^\d.]", "", text))
    except Exception:
        pass

    try:
        # Fallback: scrape page text for a dollar amount near the ticker
        content = await page.content()
        matches = re.findall(r'\$(\d+\.\d{2})', content)
        if matches:
            return float(matches[0])
    except Exception:
        pass

    return None


def _evaluate_signal(price: float) -> str | None:
    global _last_trim_price
    gain = (price - AVG_COST) / AVG_COST

    if TRIM_LOW <= gain <= TRIM_HIGH:
        _last_trim_price = price
        return "trim"

    if _last_trim_price is not None:
        pullback = (_last_trim_price - price) / _last_trim_price
        if RELOAD_LOW <= pullback <= RELOAD_HIGH:
            return "reload"

    return None


async def poll_loop(context: BrowserContext) -> None:
    page = await ensure_session(context)
    while True:
        try:
            price = await get_price(page)
            if price is None:
                print(f"[poller] could not read price")
            else:
                print(f"[poller] {SYMBOL} = ${price:.4f}")
                signal = _evaluate_signal(price)
                if signal:
                    await notify(f"Signal: {signal.upper()} at ${price:.4f}")
                    with open("signal.json", "w") as f:
                        json.dump({"signal": signal, "price": price, "timestamp": time.time()}, f)
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

"""
Trader: executes trim and reload orders on Robinhood via CDP/Playwright.
"""
import asyncio
import json
import re
from playwright.async_api import BrowserContext, Page

from session import ensure_session
from logger import log_trade
from notifications import notify

CONFIG = json.load(open("config.json"))
SYMBOL = CONFIG["instrument"]
SELL_PCT_LOW = CONFIG["trim"]["sell_pct_low"] / 100
SELL_PCT_HIGH = CONFIG["trim"]["sell_pct_high"] / 100


async def _nav_to_stock(page: Page) -> None:
    url = f"https://robinhood.com/stocks/{SYMBOL}/"
    if SYMBOL.lower() not in page.url.lower():
        await page.goto(url)
        await page.wait_for_load_state("domcontentloaded")


async def _get_shares_owned(page: Page) -> float:
    try:
        el = page.locator('text=/\\d+\\.?\\d* Shares/i').first
        text = await el.inner_text(timeout=8000)
        m = re.search(r"([\d.]+)", text)
        return float(m.group(1)) if m else 0.0
    except Exception:
        return 0.0


async def _place_order(page: Page, side: str, shares: float) -> float:
    """Click Buy or Sell, enter share count, submit. Returns fill price."""
    await _nav_to_stock(page)

    btn = page.locator(f'button:has-text("{side.capitalize()}")')
    await btn.click(timeout=10000)

    # Switch to "Shares" order type if needed
    try:
        shares_tab = page.locator('button:has-text("Shares"), [data-testid="order-type-shares"]')
        await shares_tab.click(timeout=5000)
    except Exception:
        pass

    qty_input = page.locator('input[aria-label*="Shares"], input[placeholder*="0"], input[name*="quantity"]').first
    await qty_input.fill(str(int(shares)))

    review_btn = page.locator('button:has-text("Review"), button:has-text("Review Order")')
    await review_btn.click(timeout=10000)

    submit_btn = page.locator('button:has-text("Submit"), button:has-text("Place Order")')
    await submit_btn.click(timeout=10000)

    await page.wait_for_timeout(3000)

    # Try to scrape confirmed fill price
    try:
        price_el = page.locator('[data-testid="confirmation-price"], span:has-text("$")').first
        text = await price_el.inner_text(timeout=5000)
        return float(re.sub(r"[^\d.]", "", text))
    except Exception:
        return 0.0


async def execute_trim(context: BrowserContext, current_price: float) -> None:
    page = await ensure_session(context)
    shares_owned = await _get_shares_owned(page) or CONFIG["current_shares"]

    sell_shares = round(shares_owned * ((SELL_PCT_LOW + SELL_PCT_HIGH) / 2))
    sell_shares = max(1, sell_shares)

    await notify(f"TRIM: selling {sell_shares} shares of {SYMBOL} at ~${current_price:.4f}")
    fill_price = await _place_order(page, "sell", sell_shares)
    cash = sell_shares * (fill_price or current_price)

    log_trade("trim", sell_shares, fill_price or current_price, cash)
    await notify(f"TRIM done: {sell_shares} shares @ ${fill_price:.4f}, cash=${cash:.2f}")

    CONFIG["current_shares"] = shares_owned - sell_shares
    with open("config.json", "w") as f:
        json.dump(CONFIG, f, indent=2)


async def execute_reload(context: BrowserContext, current_price: float, cash_available: float) -> None:
    page = await ensure_session(context)

    buy_shares = int(cash_available / current_price)
    if buy_shares < 1:
        await notify("RELOAD skipped — insufficient cash")
        return

    await notify(f"RELOAD: buying {buy_shares} shares of {SYMBOL} at ~${current_price:.4f}")
    fill_price = await _place_order(page, "buy", buy_shares)
    spent = buy_shares * (fill_price or current_price)

    log_trade("reload", buy_shares, fill_price or current_price, -spent)
    await notify(f"RELOAD done: {buy_shares} shares @ ${fill_price:.4f}, spent=${spent:.2f}")

    CONFIG["current_shares"] = CONFIG.get("current_shares", 0) + buy_shares
    with open("config.json", "w") as f:
        json.dump(CONFIG, f, indent=2)

"""
Trader: executes scale-out trim and scale-in reload orders via CDP/Playwright.
"""
import json
import re
from playwright.async_api import BrowserContext, Page

from session import ensure_session
from logger import log_trade
from notifications import notify

CONFIG = json.load(open("config.json"))
SYMBOL = CONFIG["instrument"]


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


async def _place_order(page: Page, side: str, shares: int) -> float:
    """Submit a market order. Returns fill price (0.0 if unconfirmed)."""
    await _nav_to_stock(page)

    await page.locator(f'button:has-text("{side.capitalize()}")').click(timeout=10000)

    try:
        await page.locator('button:has-text("Shares"), [data-testid="order-type-shares"]').click(timeout=5000)
    except Exception:
        pass

    qty = page.locator('input[aria-label*="Shares"], input[placeholder*="0"], input[name*="quantity"]').first
    await qty.fill(str(shares))

    await page.locator('button:has-text("Review"), button:has-text("Review Order")').click(timeout=10000)
    await page.locator('button:has-text("Submit"), button:has-text("Place Order")').click(timeout=10000)
    await page.wait_for_timeout(3000)

    try:
        text = await page.locator('[data-testid="confirmation-price"], span:has-text("$")').first.inner_text(timeout=5000)
        return float(re.sub(r"[^\d.]", "", text))
    except Exception:
        return 0.0


async def execute_trim(context: BrowserContext, current_price: float, sell_pct: float) -> float:
    """Sell sell_pct of current position. Returns cash received."""
    page = await ensure_session(context)
    cfg = json.load(open("config.json"))
    shares_owned = await _get_shares_owned(page) or cfg["current_shares"]
    sell_shares = max(1, round(shares_owned * sell_pct))

    await notify(f"SCALE-OUT: selling {sell_shares} shares ({sell_pct*100:.0f}%) at ~${current_price:.4f}")
    fill_price = await _place_order(page, "sell", sell_shares)
    cash = sell_shares * (fill_price or current_price)

    log_trade("trim", sell_shares, fill_price or current_price, cash)
    await notify(f"TRIM done: {sell_shares} shares @ ${fill_price:.4f} → ${cash:.2f} cash")

    cfg["current_shares"] = shares_owned - sell_shares
    with open("config.json", "w") as f:
        json.dump(cfg, f, indent=2)

    return cash


async def execute_reload(context: BrowserContext, current_price: float, cash_to_spend: float) -> None:
    """Buy as many shares as cash_to_spend allows at current_price."""
    page = await ensure_session(context)
    buy_shares = int(cash_to_spend / current_price)
    if buy_shares < 1:
        await notify("SCALE-IN skipped — insufficient cash for this tier")
        return

    await notify(f"SCALE-IN: buying {buy_shares} shares at ~${current_price:.4f} (${cash_to_spend:.2f} cash)")
    fill_price = await _place_order(page, "buy", buy_shares)
    spent = buy_shares * (fill_price or current_price)

    log_trade("reload", buy_shares, fill_price or current_price, -spent)
    await notify(f"RELOAD done: {buy_shares} shares @ ${fill_price:.4f}, spent=${spent:.2f}")

    cfg = json.load(open("config.json"))
    cfg["current_shares"] = cfg.get("current_shares", 0) + buy_shares
    with open("config.json", "w") as f:
        json.dump(cfg, f, indent=2)

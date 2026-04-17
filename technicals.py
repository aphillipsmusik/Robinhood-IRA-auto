"""
TradingView technical analysis reader.

Opens (or reuses) a TradingView technicals tab in the existing Chromium
instance and scrapes the overall rating, RSI, and MACD action for OKLL.

Logic:
  - TRIM is blocked if overall rating is in config trim_block_ratings (e.g. "Strong Buy")
    — don't sell into a roaring uptrend.
  - RELOAD is blocked if overall rating is in config reload_block_ratings (e.g. "Strong Sell")
    — don't buy into a collapsing trend.
  - RSI provides a secondary override: if RSI >= rsi_overbought, trim is confirmed
    even if TA is bullish; if RSI <= rsi_oversold, reload is confirmed even if TA is bearish.
"""
import asyncio
import json
import re
import time
from dataclasses import dataclass, field

from playwright.async_api import BrowserContext, Page

CONFIG = json.load(open("config.json"))
_TA_CFG = CONFIG["technicals"]
TV_SYMBOL = _TA_CFG["tv_symbol"]
RSI_OVERBOUGHT = _TA_CFG["rsi_overbought"]
RSI_OVERSOLD = _TA_CFG["rsi_oversold"]
TRIM_BLOCK = set(_TA_CFG["trim_block_ratings"])
RELOAD_BLOCK = set(_TA_CFG["reload_block_ratings"])

# technicals summary page — no login required
_TV_URL = f"https://www.tradingview.com/symbols/{TV_SYMBOL.replace(':', '-')}/technicals/"


@dataclass
class TASignal:
    overall: str = "Neutral"
    rsi: float | None = None
    macd_action: str | None = None
    ma_action: str | None = None
    timestamp: float = field(default_factory=time.time)

    def trim_confirmed(self) -> bool:
        """Return True when TA does not block a trim."""
        if self.rsi is not None and self.rsi >= RSI_OVERBOUGHT:
            return True
        return self.overall not in TRIM_BLOCK

    def reload_confirmed(self) -> bool:
        """Return True when TA does not block a reload."""
        if self.rsi is not None and self.rsi <= RSI_OVERSOLD:
            return True
        return self.overall not in RELOAD_BLOCK


async def _get_or_open_tv_page(context: BrowserContext) -> Page:
    for page in context.pages:
        if "tradingview.com" in page.url:
            return page
    page = await context.new_page()
    await page.goto(_TV_URL)
    return page


async def _read_overall_rating(page: Page) -> str:
    selectors = [
        '[class*="speedometerSignal"]',
        '[data-name="technical-analysis-gauge-signal"]',
        '[class*="signal-"]',
        'span[class*="Signal"]',
    ]
    for sel in selectors:
        try:
            el = page.locator(sel).first
            text = (await el.inner_text(timeout=4000)).strip()
            if text in {"Strong Buy", "Buy", "Neutral", "Sell", "Strong Sell"}:
                return text
        except Exception:
            pass

    # Last resort: full-text scan
    try:
        content = await page.content()
        for rating in ["Strong Buy", "Strong Sell", "Buy", "Sell", "Neutral"]:
            if rating in content:
                return rating
    except Exception:
        pass

    return "Neutral"


async def _read_rsi(page: Page) -> float | None:
    try:
        # RSI row in the oscillators table
        rsi_row = page.locator('tr:has-text("RSI"), [data-name="RSI"]').first
        cells = await rsi_row.locator("td, span").all_inner_texts(timeout=5000)
        for cell in cells:
            m = re.search(r"(\d{1,3}(?:\.\d+)?)", cell)
            if m:
                val = float(m.group(1))
                if 0 < val <= 100:
                    return val
    except Exception:
        pass
    return None


async def _read_indicator_action(page: Page, name: str) -> str | None:
    try:
        row = page.locator(f'tr:has-text("{name}"), [data-name="{name}"]').first
        action_el = row.locator('td:last-child, span[class*="action"], span[class*="signal"]').first
        text = (await action_el.inner_text(timeout=4000)).strip()
        if text in {"Buy", "Sell", "Neutral", "Strong Buy", "Strong Sell"}:
            return text
    except Exception:
        pass
    return None


async def fetch_ta(context: BrowserContext) -> TASignal:
    page = await _get_or_open_tv_page(context)

    if _TV_URL not in page.url:
        await page.goto(_TV_URL)
        await page.wait_for_load_state("domcontentloaded")

    # Allow React widgets time to render
    await page.wait_for_timeout(3000)

    overall = await _read_overall_rating(page)
    rsi = await _read_rsi(page)
    macd_action = await _read_indicator_action(page, "MACD")
    ma_action = await _read_overall_ma_rating(page)

    ta = TASignal(overall=overall, rsi=rsi, macd_action=macd_action, ma_action=ma_action)
    print(
        f"[technicals] overall={ta.overall} RSI={ta.rsi} "
        f"MACD={ta.macd_action} MA={ta.ma_action}"
    )
    return ta


async def _read_overall_ma_rating(page: Page) -> str | None:
    try:
        # "Moving Averages" section summary
        ma_section = page.locator('div:has-text("Moving Averages") [class*="signal"], '
                                  'div:has-text("Moving Averages") [class*="Signal"]').first
        text = (await ma_section.inner_text(timeout=4000)).strip()
        if text in {"Buy", "Sell", "Neutral", "Strong Buy", "Strong Sell"}:
            return text
    except Exception:
        pass
    return None

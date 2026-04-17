"""
Session manager: connects to Chromium via CDP, verifies Robinhood is logged in,
and re-logs-in with TOTP 2FA when the session has expired.
"""
import asyncio
import os
import time
from dotenv import load_dotenv
from playwright.async_api import async_playwright, Page, Browser, BrowserContext

from totp import get_totp_code
from notifications import notify

load_dotenv()

RH_URL = "https://robinhood.com"
RH_LOGIN_URL = "https://robinhood.com/login"
CDP_URL = os.environ.get("CDP_URL", "http://localhost:9222")


async def _find_robinhood_page(context: BrowserContext) -> Page:
    for page in context.pages:
        if "robinhood.com" in page.url:
            return page
    page = await context.new_page()
    await page.goto(RH_URL)
    return page


async def _is_logged_in(page: Page) -> bool:
    try:
        await page.wait_for_selector('[data-testid="nav-account-link"], [aria-label="Account"]', timeout=5000)
        return True
    except Exception:
        return False


async def _login(page: Page) -> None:
    username = os.environ["RH_USERNAME"]
    password = os.environ["RH_PASSWORD"]

    await page.goto(RH_LOGIN_URL)
    await page.wait_for_selector('input[name="username"]', timeout=15000)
    await page.fill('input[name="username"]', username)
    await page.fill('input[name="password"]', password)
    await page.click('button[type="submit"]')

    # Handle TOTP prompt
    try:
        await page.wait_for_selector('input[name="mfa_code"], input[placeholder*="code"]', timeout=15000)
        code = get_totp_code()
        await page.fill('input[name="mfa_code"], input[placeholder*="code"]', code)
        await page.click('button[type="submit"]')
    except Exception:
        pass  # No MFA prompt appeared

    # "Stay logged in" prompt
    try:
        stay_btn = page.locator('button:has-text("Stay Logged In"), button:has-text("Keep me logged in")')
        await stay_btn.click(timeout=8000)
    except Exception:
        pass

    await page.wait_for_selector('[data-testid="nav-account-link"], [aria-label="Account"]', timeout=20000)


async def ensure_session(context: BrowserContext) -> Page:
    page = await _find_robinhood_page(context)
    if not await _is_logged_in(page):
        await notify("Session expired — re-logging in to Robinhood")
        await _login(page)
        await notify("Re-login successful")
    return page


async def heartbeat_loop(context: BrowserContext, interval: int = 1800) -> None:
    while True:
        await asyncio.sleep(interval)
        try:
            await ensure_session(context)
        except Exception as e:
            await notify(f"Heartbeat failed: {e}")


async def connect() -> tuple[Browser, BrowserContext]:
    pw = await async_playwright().start()
    browser = await pw.chromium.connect_over_cdp(CDP_URL)
    context = browser.contexts[0] if browser.contexts else await browser.new_context()
    return browser, context

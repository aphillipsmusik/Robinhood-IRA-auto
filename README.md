# Robinhood OKLL Automation

Automated trim-and-reload trading strategy for **OKLL** (Defiance 2X Long OKLO ETF) running on a Raspberry Pi with an always-on Chromium browser.

---

## Algorithm Intent

The strategy targets continuous, unlimited accumulation of OKLL shares by recycling profits from short-term overbought spikes back into dip reloads — buying back more shares than were sold each cycle.

### Trim (Sell)
1. Monitor OKLL price continuously against the average cost basis.
2. When price rises **30–40% above avg cost**, a trim signal is raised.
3. Before executing, confirm with TradingView technical analysis:
   - **Block** the trim if the overall TA rating is **"Strong Buy"** (trend may still have room to run), unless RSI ≥ 65 (overbought override).
4. If confirmed, sell **10–20% of current position** at market.
5. Log the trade and store the cash proceeds for the reload phase.

### Reload (Buy)
1. After a trim, track price from the trim level.
2. When price pulls back **15–20% from the trim price**, a reload signal is raised.
3. Before executing, confirm with TradingView technical analysis:
   - **Block** the reload if the overall TA rating is **"Strong Sell"** (trend may continue lower), unless RSI ≤ 40 (oversold override).
4. If confirmed, buy back using the full cash proceeds from the trim — acquiring **more shares** than were sold (lower price = more shares per dollar).
5. Net result each cycle: same cash spent, larger share count. Position grows over time.

### No Share Cap
There is no target share ceiling. The position accumulates indefinitely with each trim/reload cycle.

---

## Technical Analysis (TradingView)

A dedicated Chromium tab stays open on the TradingView technicals summary page for OKLL. Every **5 minutes** the system scrapes:

| Signal | Source | Use |
|---|---|---|
| Overall rating | Speedometer gauge | Primary gate for trim/reload |
| RSI | Oscillators table | Overbought/oversold override |
| MACD action | Oscillators table | Logged with each signal |
| Moving Average rating | MA summary | Logged with each signal |

TA data is included in every push notification and in `signal.json`.

---

## Architecture

```
main.py
├── session.py       — CDP connect to Chromium:9222, TOTP re-login, 30min heartbeat
├── poller.py        — Price read loop (every 60s), evaluate_signal with TA gating
├── technicals.py    — TradingView scraper (every 5min), returns TASignal
├── trader.py        — Playwright order execution (buy/sell)
├── logger.py        — Append trade records to trades.json
├── totp.py          — Generate TOTP codes via pyotp
└── notifications.py — Push alerts via ntfy.sh or Pushover
```

---

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt
playwright install chromium

# 2. Configure credentials
cp .env.example .env
# Fill in RH_USERNAME, RH_PASSWORD, TOTP_SECRET

# 3. Launch Chromium with remote debugging (do this once, keep running)
chromium-browser --remote-debugging-port=9222 --no-sandbox &

# 4. Run
python main.py
```

### config.json reference

| Key | Description |
|---|---|
| `instrument` | Ticker symbol |
| `current_shares` | Live position size (auto-updated on trades) |
| `avg_cost` | Cost basis per share |
| `trim.trigger_gain_pct_low/high` | Gain % range that triggers a trim |
| `trim.sell_pct_low/high` | % of position to sell on trim |
| `reload.pullback_pct_low/high` | % pullback from trim price that triggers reload |
| `technicals.rsi_overbought` | RSI level that overrides a "Strong Buy" TA block on trim |
| `technicals.rsi_oversold` | RSI level that overrides a "Strong Sell" TA block on reload |
| `technicals.trim_block_ratings` | TA ratings that block a trim |
| `technicals.reload_block_ratings` | TA ratings that block a reload |

---

## Files

| File | Purpose |
|---|---|
| `main.py` | Entry point |
| `poller.py` | Price monitoring and signal logic |
| `technicals.py` | TradingView TA scraper |
| `session.py` | Browser session management |
| `trader.py` | Order execution |
| `logger.py` | Trade logging |
| `totp.py` | 2FA code generation |
| `notifications.py` | Push notifications |
| `config.json` | Strategy parameters |
| `.env` | Credentials (never committed) |
| `trades.json` | Trade log (auto-created) |

# Robinhood OKLL Automation

Automated scale-out/scale-in trading strategy for **OKLL** (Defiance 2X Long OKLO ETF) running on a Raspberry Pi with an always-on Chromium browser, TradingView TA gating, and a live web dashboard.

---

## Algorithm Intent

Continuously accumulate OKLL shares by selling into overbought spikes across multiple tiers and buying back more shares than were sold as the price dips.

### Scale-Out (Sell Tiers)

As price rises above avg cost, progressively larger slices of the position are sold. Each tier fires once per cycle.

| Gain from avg cost | Sell % of position |
|---|---|
| +20% | 5% |
| +30% | 10% |
| +40% | 15% |
| +50% | 20% |

Before each trim: TA is checked — **blocked if overall rating is "Strong Buy"**, unless RSI ≥ 65 (overbought override).

### Scale-In (Buy Tiers)

After a trim, cash accumulates and is redeployed in stages as price pulls back from the peak trim price.

| Pullback from peak | Cash deployed |
|---|---|
| −10% | 20% |
| −15% | 25% |
| −20% | 25% |
| −30% | 15% ← reserve |
| −40% | 15% ← reserve |

70% is deployed on normal dips. 30% is held in reserve for deeper 30–40% drops.

Before each reload: TA is checked — **blocked if overall rating is "Strong Sell"**, unless RSI ≤ 40 (oversold override).

When all buy tiers fire, the cycle resets and scale-out monitoring resumes.

### No Share Cap
There is no target share ceiling. The position grows with each completed cycle.

---

## Technical Analysis (TradingView)

A dedicated Chromium tab stays open on the TradingView technicals page for OKLL, refreshing every **5 minutes**.

| Signal | Use |
|---|---|
| Overall rating | Primary gate for trim/reload |
| RSI | Overbought/oversold override |
| MACD | Logged with each signal |
| Moving Averages | Logged with each signal |

---

## Dashboard

A live web dashboard is served on port **8080** and accessible from any device on the same network.

```
http://<raspberry-pi-ip>:8080
```

The dashboard shows:
- Current price, shares, avg cost, unrealized P&L
- Scale-out and scale-in tier status (which have fired this cycle)
- Live TradingView TA ratings with color coding
- Accumulated cash and peak trim price
- Full trade history table
- Auto-refreshes every 30 seconds

---

## Architecture

```
main.py             — signal loop, cycle state, writes state.json
├── session.py      — CDP connect to Chromium:9222, TOTP re-login, 30min heartbeat
├── poller.py       — price read loop (60s), scale-out/scale-in evaluation with TA gating
├── technicals.py   — TradingView scraper (5min), returns TASignal
├── trader.py       — Playwright order execution (buy/sell)
├── logger.py       — append trade records to trades.json
├── totp.py         — generate TOTP codes via pyotp
└── notifications.py — push alerts via ntfy.sh or Pushover

dashboard.py        — aiohttp web server, serves /api/state + static/index.html
```

### Service chain (systemd)
```
okll-xvfb → okll-chromium → okll-trader
                                          okll-dashboard (independent)
```

---

## Raspberry Pi Deployment (Ubuntu 24.04 LTS)

```bash
git clone https://github.com/aphillipsmusik/Robinhood-IRA-auto
cd Robinhood-IRA-auto
sudo bash deploy/install.sh
nano .env          # fill in credentials
make start
make logs          # watch trader logs
```

The install script handles all apt dependencies, Python venv, Playwright, and systemd service registration.

### Makefile commands

| Command | Action |
|---|---|
| `make start` | Start all 4 services |
| `make stop` | Stop all services |
| `make restart` | Restart trader + dashboard |
| `make status` | Status of all services |
| `make logs` | Stream trader logs |
| `make logs-dashboard` | Stream dashboard logs |
| `make update` | `git pull` + restart |

---

## config.json reference

| Key | Description |
|---|---|
| `instrument` | Ticker symbol |
| `current_shares` | Live position size (auto-updated on trades) |
| `avg_cost` | Cost basis per share |
| `scale_out.tiers` | Gain thresholds and sell percentages |
| `scale_in.tiers` | Pullback thresholds and cash deployment percentages |
| `technicals.rsi_overbought` | RSI that overrides "Strong Buy" block on trim |
| `technicals.rsi_oversold` | RSI that overrides "Strong Sell" block on reload |
| `technicals.trim_block_ratings` | TA ratings that block a trim |
| `technicals.reload_block_ratings` | TA ratings that block a reload |
| `dashboard_port` | Port for the web dashboard (default 8080) |

---

## Files

| File | Purpose |
|---|---|
| `main.py` | Entry point, cycle state management |
| `poller.py` | Price monitoring and signal logic |
| `technicals.py` | TradingView TA scraper |
| `session.py` | Browser session management |
| `trader.py` | Order execution |
| `logger.py` | Trade logging |
| `totp.py` | 2FA code generation |
| `notifications.py` | Push notifications |
| `dashboard.py` | Web dashboard server |
| `static/index.html` | Dashboard UI |
| `config.json` | Strategy parameters |
| `.env` | Credentials (never committed) |
| `trades.json` | Trade log (auto-created) |
| `state.json` | Live cycle state (auto-created) |
| `deploy/install.sh` | Pi setup script |
| `deploy/*.service` | systemd unit files |
| `Makefile` | Convenience commands |

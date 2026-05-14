# FxBot — Production-Grade Forex Trading Bot

A fully-featured, production-ready algorithmic Forex trading bot written in Python. Supports OANDA and MetaTrader 5, 30+ technical indicators, Smart Money Concepts, 20 trading strategies, a Streamlit dashboard, Telegram alerts, comprehensive backtesting, and risk management.

> **Default mode is PAPER TRADING** — the bot uses real prices but never places real orders unless you pass `--live` and confirm.

---

## Table of Contents

1. [Features](#features)
2. [Project Structure](#project-structure)
3. [Prerequisites](#prerequisites)
4. [Installation](#installation)
5. [API Key Setup](#api-key-setup)
6. [Configuration](#configuration)
7. [Running the Bot](#running-the-bot)
8. [Backtesting](#backtesting)
9. [Streamlit Dashboard](#streamlit-dashboard)
10. [Telegram Commands](#telegram-commands)
11. [Risk Management](#risk-management)
12. [Troubleshooting](#troubleshooting)
13. [Contributing](#contributing)
14. [Disclaimer](#disclaimer)

---

## Features

- **10 currency pairs**: EUR/USD, GBP/USD, USD/JPY, AUD/USD, USD/CHF, NZD/USD, USD/CAD, XAU/USD, GBP/JPY, EUR/JPY
- **Multi-timeframe analysis**: M1 → W1
- **30+ technical indicators** across Trend, Momentum, Volatility, Volume, Support/Resistance, Oscillators
- **Chart & candlestick pattern recognition**: 20+ candlestick patterns, Head & Shoulders, triangles, wedges, flags, all harmonic patterns (Gartley, Butterfly, Bat, Crab, ABCD…), Elliott Wave
- **Smart Money Concepts (SMC/ICT)**: Order blocks, FVG, BOS/CHoCH, liquidity sweeps, OTE zones, ICT kill zones, Judas swing
- **20 trading strategies**: Price Action, SMC, Trend Following, Breakout, Pullback, Mean Reversion, Momentum, Scalping, Swing, Session, News, Harmonic, Elliott Wave, Carry Trade, Ichimoku, VWAP, Wyckoff, VSA, Grid, Multi-TF Confluence
- **Confluence scoring engine**: 0–100 score, minimum 65 to trade
- **News & fundamental filter**: Forex Factory + Investing.com calendar, auto-pause around high-impact events
- **Risk management**: 1% risk/trade, ATR-based SL, 3-TP partial closes (30/40/30%), trailing stop, drawdown protection
- **Backtesting**: 10-year history, walk-forward optimization, Monte Carlo simulation (1 000 runs)
- **Streamlit dashboard**: 6 pages — live overview, trade journal, strategy performance, news, backtest, risk monitor
- **Alerts**: Telegram (trade open/close, daily summary) + weekly HTML email with equity curve
- **Safety**: Paper mode by default, live mode requires `--live` flag + typed confirmation

---

## Project Structure

```
FxBot/
├── forex_bot/
│   ├── main.py                    # Entry point
│   ├── config.yaml                # All configuration
│   ├── requirements.txt
│   ├── .env.example               # Template for API keys
│   ├── core/                      # Engine, broker, execution, heartbeat, session
│   ├── indicators/                # 30+ technical indicators
│   ├── patterns/                  # Candlestick, chart, harmonic, Elliott Wave, SMC
│   ├── strategies/                # 20 strategies + strategy manager
│   ├── risk/                      # Position sizing, SL/TP, trailing stop, drawdown
│   ├── news/                      # Forex Factory, Investing.com, news filter
│   ├── scoring/                   # Confluence engine, adaptive weighting
│   ├── data/                      # Live feed, historical data, data cleaner
│   ├── backtest/                  # Engine, walk-forward, Monte Carlo, report
│   ├── alerts/                    # Telegram bot, email reporter
│   ├── dashboard/                 # Streamlit app (6 pages)
│   ├── database/                  # SQLAlchemy models, DB manager
│   ├── utils/                     # Logger, config loader, helpers, timeframe utils
│   └── tests/                     # pytest test suite
└── .github/
    └── workflows/
        └── ci.yml                 # GitHub Actions CI
```

---

## Prerequisites

- Python 3.11 or later
- An [OANDA](https://www.oanda.com) account (practice or live)
- (Optional) MetaTrader 5 desktop app installed — Windows only
- (Optional) Telegram account for alerts
- (Optional) Gmail (or other SMTP) account for weekly email reports
- (Optional) [NewsAPI](https://newsapi.org) key for geopolitical monitoring

---

## Installation

```bash
# 1. Clone the repo
git clone https://github.com/ianwanjohi475/fxbot.git
cd fxbot/forex_bot

# 2. Create a virtual environment
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Copy and fill in the environment file
cp .env.example .env
nano .env          # (or your favourite editor)
```

---

## API Key Setup

### OANDA (required)

1. Go to [https://www.oanda.com](https://www.oanda.com) and create a **practice** account (free).
2. Log in → My Account → Manage API Access → **Generate** a new personal access token.
3. Note your **Account ID** from the dashboard (format: `001-001-XXXXXXX-001`).
4. Set in `.env`:
   ```
   OANDA_API_KEY=your_token_here
   OANDA_ACCOUNT_ID=001-001-XXXXXXX-001
   OANDA_ENVIRONMENT=practice    # or "live" for live account
   ```

### MetaTrader 5 (optional)

1. Install MetaTrader 5 from [https://www.metatrader5.com](https://www.metatrader5.com) (Windows only).
2. Open a demo account through any broker that supports MT5.
3. Set in `.env`:
   ```
   MT5_LOGIN=your_account_number
   MT5_PASSWORD=your_password
   MT5_SERVER=YourBroker-Demo
   ```

### Telegram Bot (optional but recommended)

1. Open Telegram and message **@BotFather**.
2. Send `/newbot`, choose a name and username.
3. Copy the **API token** shown.
4. Start a chat with your new bot, then visit:
   `https://api.telegram.org/bot<TOKEN>/getUpdates` to find your **chat_id**.
5. Set in `.env`:
   ```
   TELEGRAM_BOT_TOKEN=1234567890:ABCDEF...
   TELEGRAM_CHAT_ID=123456789
   ```

### Email Reports (optional)

1. For Gmail: enable 2-Factor Authentication → Google Account → Security → App Passwords → generate one for "Mail".
2. Set in `.env`:
   ```
   EMAIL_SENDER=yourbot@gmail.com
   EMAIL_PASSWORD=your_app_password_here
   EMAIL_RECIPIENT=you@example.com
   EMAIL_SMTP_HOST=smtp.gmail.com
   EMAIL_SMTP_PORT=587
   ```

### NewsAPI (optional — geopolitical monitoring)

1. Register at [https://newsapi.org](https://newsapi.org) — free tier is sufficient.
2. Copy your API key from the dashboard.
3. Set in `.env`:
   ```
   NEWS_API_KEY=your_newsapi_key_here
   ```

---

## Configuration

All trading parameters live in `config.yaml`. Key sections:

| Section | What it controls |
|---------|-----------------|
| `trading.pairs` | Which currency pairs to watch |
| `trading.timeframes` | Timeframes to analyse |
| `risk.risk_per_trade_pct` | Fraction of account risked per trade (default `0.01` = 1%) |
| `risk.max_open_trades` | Maximum concurrent positions (default `5`) |
| `risk.max_daily_loss_pct` | Daily drawdown limit (default `0.05` = 5%) |
| `confluence.min_score` | Minimum confluence score to open a trade (default `65`) |
| `backtesting.years_of_data` | Historical data window for backtests |
| `paper_trading.enabled` | Overridden by CLI flags; leave as `true` |
| `strategy_weights` | Per-strategy weights (auto-adjusted by adaptive engine) |

---

## Running the Bot

```bash
# Paper trading (default — safe, no real money)
python main.py

# Live trading — requires explicit confirmation at startup
python main.py --live

# Override which pairs to trade
python main.py --pairs EUR_USD GBP_USD USD_JPY

# Increase log verbosity
python main.py --log-level DEBUG

# Use a different config file
python main.py --config /path/to/my_config.yaml
```

The bot auto-restarts on unhandled exceptions with exponential back-off (30 s → 60 s → 120 s → … capped at 5 min).

---

## Backtesting

```bash
# Run backtests for all configured pairs
python main.py --backtest

# Or run the interactive backtest page in the dashboard
streamlit run dashboard/app.py
# Navigate to the "Backtesting" page
```

Backtest output includes:
- Win rate, profit factor, net profit, Sharpe ratio, Sortino ratio, max drawdown, CAGR
- Walk-forward validation (70 % train / 30 % test)
- Monte Carlo simulation (1 000 runs) with probability of profit and ruin
- Equity curve, drawdown chart, and monthly P&L heatmap

---

## Streamlit Dashboard

```bash
streamlit run dashboard/app.py
```

Open `http://localhost:8501` in your browser. Pages:

| Page | Description |
|------|-------------|
| **Live Overview** | Account equity, open trades, live price grid |
| **Trade Journal** | Filterable trade history with CSV export |
| **Strategy Performance** | Per-strategy stats, adaptive weights |
| **News & Events** | Economic calendar, central bank schedule, geopolitical feed |
| **Backtesting** | Interactive backtest runner with charts |
| **Risk Monitor** | Daily/weekly drawdown gauges, correlation exposure |

---

## Telegram Commands

Once the bot is running and the Telegram listener is active, send these commands to your bot:

| Command | Action |
|---------|--------|
| `/stop` | **Emergency stop** — immediately closes all open trades and shuts the bot down |
| `/status` | Current account balance, open trades, today's P&L |
| `/help` | List all available commands |

The bot also sends automatic alerts for:
- Trade opened / closed
- TP1 / TP2 / TP3 hit
- SL hit
- Danger zone detected (news, spread, drawdown)
- Daily P&L summary (6:00 PM EST)
- Weekly report link (Sunday 8:00 AM EST)

---

## Risk Management

FxBot is designed with capital preservation as the top priority:

- **1% risk per trade** (configurable 0.5 % – 3 %) — position size auto-calculated
- **ATR-based stop loss** — adapts to market volatility
- **Three take-profit levels** (1:1, 1:2, 1:3 RR) with partial closes (30 % / 40 % / 30 %)
- **Trailing stop** activates after TP1 is hit, trails by 1× ATR
- **Breakeven** SL moves to entry after TP1
- **Maximum 5 open trades** simultaneously
- **Daily loss limit**: stops trading if 5 % account is lost in a day
- **Weekly loss limit**: pauses until Monday if 10 % is lost in a week
- **3 consecutive losses** → 1-hour pause
- **Correlation filter**: blocks opening EUR/USD and GBP/USD in the same direction simultaneously
- **No Martingale** — position size never increases after a loss
- **News filter**: pauses 30–60 min around high-impact releases (NFP, FOMC, CPI…)
- **Spread filter**: skips any pair with spread > 3 pips (configurable)
- **Friday afternoon filter**: no new trades after 3:00 PM EST on Fridays

---

## Troubleshooting

**`ModuleNotFoundError: No module named 'oandapyV20'`**
```bash
pip install -r requirements.txt
```

**`OANDA API error: 401 Unauthorized`**
- Check `OANDA_API_KEY` and `OANDA_ACCOUNT_ID` in `.env`
- Confirm `OANDA_ENVIRONMENT=practice` matches your account type

**`Telegram bot not responding`**
- Verify `TELEGRAM_BOT_TOKEN` is correct
- Make sure you have started a conversation with the bot on Telegram
- Check `TELEGRAM_CHAT_ID` matches the chat you started

**`No data returned for pair`**
- OANDA practice accounts support all 10 pairs
- Check market hours — Forex is closed Friday 5 PM – Sunday 5 PM EST

**`Backtests are slow`**
- Reduce `years_of_data` in `config.yaml`
- Cached Parquet files are stored in `backtest/cache/` after the first download

**Dashboard shows "Connection refused"**
- Make sure you started the bot first: `python main.py`
- The dashboard reads from the SQLite database — it doesn't require a live connection

**MetaTrader 5 not connecting**
- MT5 Python library only works on Windows
- Make sure MT5 is running and logged in before starting the bot
- The bot falls back to OANDA-only if MT5 fails to connect

---

## Running Tests

```bash
cd forex_bot
pytest tests/ -v

# With coverage report
pytest tests/ -v --cov=. --cov-report=term-missing
```

---

## Contributing

1. Fork the repository
2. Create a feature branch: `git checkout -b feature/my-feature`
3. Make your changes and add tests
4. Ensure all tests pass: `pytest tests/ -v`
5. Submit a pull request

---

## Disclaimer

**This software is for educational and research purposes only.**

- Trading Forex and CFDs carries significant risk of loss
- Past performance (including backtest results) is not indicative of future results
- Never risk money you cannot afford to lose
- The authors are not financial advisors
- Always start with a practice/demo account and paper trading mode
- The `--live` flag is deliberately hard to enable to prevent accidental use

By using this software you agree that you are solely responsible for any trading decisions and financial outcomes.

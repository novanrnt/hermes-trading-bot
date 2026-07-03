# Hermes Exness Trading Bot 🤖💰

**Multi-agent AI trading system** for MetaTrader 5 (Exness) — day trade & scalping with full safety gates, running on Hermes Agent.

## Architecture

```
Scanner → Technical Agent → Fundamental Agent → Sentiment Agent → Risk Agent → Manager → Executor (Demo)
```

5 autonomous AI agents analyze markets in sequence, powered by `deepseek-v4-flash` via SumoPod API.

## Features

### Day Trade (2h cycle)
- H4→H1→M15 timeframe analysis
- Full 5-agent swarm: Technical, Fundamental, Sentiment, Risk, Manager
- ADX trend filter (min 20), ATR-based SL, RR ≥ 1.8

### Scalping (10min cycle)
- M5 live scan across 8 forex pairs
- EMA20 + ADX + RSI(7) + volume spike + price action filters
- Max 3 scalp trades/day, overlap check

### Crypto Scanner (DRAFT — Binance Futures)
- Scan Top 100 CoinGecko → filter volume + volatility → ambil funding rate + OI dari Binance
- Score & ranking → 3-5 kandidat siap pipeline
- 24/7 nonstop trading
- 🔴 **Not activated yet** — file: `crypto_scanner.py`

### Safety
- ✅ DEMO ONLY — no live execution
- ✅ Breakeven stop after 2× ATR
- ✅ Max 5 positions, 20% daily DD
- ✅ Big news block ±2h
- ✅ Drawdown lock at 5%

### Monitoring
- Live Telegram reports to RNT Autotrade group (5 bot topics)
- HTML Dashboard (`:5555`)
- Kai Review Agent — performance reviews every 20 trades
- Monte Carlo simulation (daily)
- Health check + watchdog every 5min

## Tech Stack

| Component | Tech |
|-----------|------|
| Agent Framework | Hermes Agent |
| AI Models | deepseek-v4-flash (SumoPod) |
| Trading Platform | MetaTrader 5 (Exness) |
| Messaging | Telegram Bot API |
| Dashboard | Python HTTP server |
| Deployment | Windows Server VPS |

## Setup

```bash
# Clone
git clone git@github.com:novanrnt/hermes-trading-bot.git
cd hermes-trading-bot

# Setup .env with API keys
# Setup config.yaml with MT5 credentials
# Run!
```

## Repo Structure

```
├── agent_swarm.py            # Day trade pipeline
├── crypto_scanner.py         # Crypto Binance scanner (DRAFT)
├── scalping_framework.py     # Scalping scanner
├── trade_executor_demo.py    # Demo MT5 executor
├── trail_check.py            # Trailing stop manager
├── dashboard/                # Live HTML dashboard
├── scripts/                  # Cron job scripts
├── prompts/                  # Agent system prompts
├── data/                     # Runtime state files
└── config/                   # Agent configurations
```

## License

Private — @novanrnt

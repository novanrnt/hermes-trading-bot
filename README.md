# Hermes Exness Trading Bot 🤖💰

**Multi-agent AI trading system** untuk MetaTrader 5 (Exness) — **2 sistem terpisah**: Day Trade (agent pipeline) & Scalping (M5 quant scanner). Full safety gates, running on Hermes Agent.

## Architecture

### Day Trade — Full Agent Pipeline
```
Scanner → Technical → Fundamental → Sentiment → Risk → Manager → Executor (Demo)
```
5 autonomous AI agents, cycle tiap 2 jam. Powered by `deepseek-v4-flash` via SumoPod API.

### Scalping — M5 Quant Scanner (NO Agent)
```
M5 Scanner (ADX + RSI + Volume + Price Action) → Risk Check → Executor (Demo)
```
Direct M5 scan, 10-15 menit cycle. **Tidak pakai agent pipeline.**

## Features

### Day Trade (2h cycle)
- H4→H1→M15 timeframe analysis
- Full 5-agent swarm: Technical, Fundamental, Sentiment, Risk, Manager
- ADX trend filter (H1, min 18), ATR-based SL, RR ≥ 1.8
- Risk 0.5%/trade, max 3 positions, max 20% DD/day

### Scalping (10-15min cycle)
- M5 live scan across 8 forex pairs (EURUSD, GBPUSD, USDJPY, USDCHF, USDCAD, AUDUSD, NZDUSD, XAUUSD)
- **M5 ADX Filter** (min 20) — skip kalo M5 choppy
- Session Filter — **Asian block** (00:00-06:00 UTC), **London-NY window** (14:00-22:00 UTC), penalty -10 di luar peak
- **News Blackout** — 30 menit before/after high impact news (config: `data/news_blackout.json`)
- EMA20 + RSI(7) + volume spike + momentum/pullback triggers
- Max 3 scalp trades/scan, overlap check
- Risk 0.3%/trade, RR ≥ 1.5, SL based on M15 ATR
- **Quant Learner** — auto-tune ADX, RSI, trigger bias based on trade history
- **Decoupled dari Day Trade** — `scalp_decision.json` terpisah, ga campur sama `final_decision.json`

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
├── agent_swarm.py              # Day trade pipeline
├── agent_orchestrator.py       # Agent orchestration logic
├── crypto_scanner.py           # Crypto Binance scanner (DRAFT)
├── trade_executor_demo.py      # Demo MT5 executor (supports --file)
├── trail_check.py              # Trailing stop manager
├── scripts/
│   ├── scalping_scanner.py     # M5 scalping scanner (+ filters)
│   ├── day_trade_cron.py       # Day trade cron trigger
│   ├── quant_learner.py        # Auto-tune scalping params
│   ├── kai_interactive.py      # Kai review agent poller
│   ├── health_check.py         # System health check
│   └── ...                     # Other cron scripts
├── data/
│   ├── news_blackout.json      # High impact news schedule (scalping)
│   ├── scalp_decision.json     # Scalping decisions (separate file)
│   └── ...                     # Runtime state
├── prompts/
│   └── review/
│       └── kai_system.txt      # Kai system prompt (2-system aware)
├── dashboard/                  # Live HTML dashboard
├── config.yaml                 # Main config
└── .env                        # Environment variables
```

## License

Private — @novanrnt

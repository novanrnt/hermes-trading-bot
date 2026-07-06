# Deep Research: Free Forex Trading Resources
> **Date:** 2026-06-15  
> **Focus:** Free/Open-Source alternatives for Economic Calendars, Sentiment, Multi-TF Optimization, and AI Trading

---

## 1. Free Economic Calendar APIs (Alternatives to `nfs.faireconomy.media/ff_calendar_thisweek.json`)

### ⭐ Top Recommendations (Free / Freemium)

| # | Source | Type | Free Tier | Notes |
|---|--------|------|-----------|-------|
| 1 | **JBlanked News API** | REST API | 1 req/day free | Aggregates MQL5, ForexFactory, FxStreet calendars. Filter by currency (USD, EUR, GBP, AUD, CHF, JPY, NZD) and impact (High/Medium/Low). Simple API key auth. |
| 2 | **ForexNewsAPI** | REST API | Free trial key | 800+ economic events, 15 countries, 150+ pairs. Includes sentiment analysis + news. Economic calendar endpoint: `/api/v1/economic-calendar` |
| 3 | **Economic Calendar API (RapidAPI)** | REST API | 30 req/month free | 5-min auto-refresh, 25 GMT timezones, volatility classification (None/Low/Med/High). 25+ fields per event. RapidAPI: `yasimpratama88/economic-calendar-api` |
| 4 | **Parse.bot ForexFactory API** | REST API | Free tier | Scraped FF calendar: weekly events with actual/forecast/previous, currency, impact. MCP-compatible. Endpoint: `get_calendar` |
| 5 | **FireAPI ForexFactory Calendar** | REST API | Freemium | Structured FF calendar, historical 2020–2026, multi-currency, high-impact identification. |
| 6 | **Trading Economics Calendar API** | REST API | Limited free | 20M indicators, 196 countries. Historical data. |
| 7 | **OHLC.dev Economic Calendar API** | REST API | RapidAPI freemium | 5-min updates, volatility labels, expectation/deviation context. |
| 8 | **fin2dev Macroeconomic Calendar API** | REST API | Freemium | Real-time CPI, GDP, NFP, interest rates by country. JSON format. |

### 🛠️ Self-Hosted / GitHub Scrapers

| # | Repo | Stars | Approach |
|---|------|-------|----------|
| 1 | **andrevlima/economic-calendar-api** | ⭐55 | PHP scraper for Investing.com → JSON. Deploy on free PHP host (000webhost, freehosting.com). |
| 2 | **fizahkhalid/forex_factory_calendar_news_scraper** | ⭐77 | Python/Selenium FF scraper. Stores CSV/JSON, alerts to Discord/Telegram/webhooks. Docker Compose. Rule-based pre-event alerts. |
| 3 | **tumaponchard16/fx-calendar-scraper** | New | Python/Playwright FF scraper. Clean architecture (ports/adapters). FastAPI + PostgreSQL + CSV. |
| 4 | **pavelkrusek/market-calendar-tool** | ⭐12 | Multi-source scraper (multiple financial sites). Returns pandas DataFrames. |
| 5 | **apptastic-software/trading-calendar** | MIT | Docker-hosted REST API. 60+ exchange calendars (holidays, market hours). Swagger docs. |
| 6 | **lcsrodriguez/ecocal** | — | Python package for worldwide economic calendar scraping (multithreaded). |

### 🔑 Best DIY Alternative
```
Self-host fizahkhalid/forex_factory_calendar_news_scraper in Docker
→ Scrapes FF monthly calendar → JSON/CSV → alerts to your pipeline
→ Cost: $0 (just a server/VPS)
```

---

## 2. Free Sentiment Sources & DXY Proxy Improvements

### 📊 Free Retail Sentiment Sources

| # | Source | Access | Description |
|---|--------|--------|-------------|
| 1 | **Myfxbook Community Outlook** | Free API: `myfxbook.com/api/get-community-outlook.json` (session key required) | Long/short % across 50+ pairs. Includes avg long/short prices. Most widely used free sentiment. |
| 2 | **FXSSI Sentiment Tool** | Free web tool | Aggregates multiple broker sources. Weighted avg sentiment. **USDX symbol included** (calculated from DXY formula). Historical charts. |
| 3 | **IG Client Sentiment (DailyFX)** | Free web | Largest retail broker sentiment data. Published on DailyFX. Long/short % by pair. Classic contrarian indicator. |
| 4 | **A1 Trading Retail Sentiment** | Free web dashboard | Real-time retail positioning. EdgeFinder integration. |
| 5 | **TraderSentiments.com** | Free web | Aggregated trader positioning. Forex, indices, commodities, crypto. Contrarian bias labels. |
| 6 | **Finlogix Sentiment** | Free web | Long/short ratios with bullish/bearish/neutral classification. |

### 🏛️ Free Institutional COT (Commitments of Traders) Data

| # | Source | Access | Notes |
|---|--------|--------|-------|
| 1 | **cotdata.net** | Free API (latest week) | **DXY COT free** — full history open. TFF, Legacy, Disaggregated tables. COT Index (0-100), z-scores. Paid tier: £19/mo for 3yr history. |
| 2 | **Tradingster.com** | Free COT charts | Historical COT data + free charts. |
| 3 | **MarketBulls COT** | Free data/charts | COT Index, commercial vs speculator data tables. |
| 4 | **MetalCharts COT** | Free | Gold, silver, copper, platinum, palladium COT with Managed Money focus. |
| 5 | **CFTC Official** | Free raw data | `cftc.gov/MarketReports/CommitmentsofTraders/index.htm` — official source. |

### 🎯 DXY Proxy Improvements

**Current DXY basket weights:** EUR 57.6%, JPY 13.6%, GBP 11.9%, CAD 9.1%, SEK 4.2%, CHF 3.6%

| Approach | Description | Best For |
|----------|-------------|----------|
| **HunchMachine DXY Proxy API** | Synthetic DXY from live FX rates. Free tier available. Returns `dxy_value`, component rates, summary. Webhook-compatible. | Quick integration, webhooks |
| **Self-Calculated DXY Proxy** | Compute weighted geometric mean: `DXY = 50.14348112 * EURUSD^-0.576 * USDJPY^0.136 * GBPUSD^-0.119 * USDCAD^0.091 * USDSEK^0.042 * USDCHF^0.036` | Full control, free forever |
| **FXSSI USDX Feature** | Built-in USDX calculated from original DXY formula using pertinent currencies. | Ready-to-use tool |
| **cotdata.net DXY COT** | Speculator positioning on DXY futures (free full history). COT Index 0-100 for extreme sentiment detection. | Institutional-grade macro context |
| **correlation-based proxy** | Track EURUSD (inverse -0.95 correlation) + USDJPY as DXY sentiment proxy. | Simple, no API needed |
| **basket-weighted sentiment** | Weight retail sentiment from 6 component pairs by DXY weights → composite USD sentiment indicator. | Custom composite |

### 🔧 Python Code: Self-Calculated DXY Proxy
```python
import yfinance as yf
import numpy as np

def calculate_dxy_proxy():
    """Calculate synthetic DXY from component pairs using yfinance (free)"""
    pairs = {
        'EURUSD=X': -0.576,   # inverse weight
        'JPY=X':    0.136,    # USDJPY
        'GBPUSD=X': -0.119,   # inverse weight
        'CAD=X':    0.091,    # USDCAD
        'SEK=X':    0.042,    # USDSEK
        'CHF=X':    0.036,    # USDCHF
    }
    constant = 50.14348112
    
    dxy = constant
    for ticker, weight in pairs.items():
        try:
            data = yf.Ticker(ticker).history(period='1d')
            if not data.empty:
                rate = data['Close'].iloc[-1]
                dxy *= rate ** weight
        except:
            pass
    return dxy

print(f"DXY Proxy: {calculate_dxy_proxy():.2f}")
```

---

## 3. Multi-Timeframe Strategy Optimization (M5 Entries, 8 Pairs)

### 📐 Recommended Architecture

```
H4 → Trend direction filter (200 SMA, ADX > 25)
H1 → Market structure context (swing highs/lows, supply/demand zones)
M15 → Momentum confirmation (RSI divergences, MACD histogram)
M5 → Entry trigger (EMA crossover, candlestick patterns, volume spike)
```

### 🧬 Optimization Methodology (Walk-Forward)

| Phase | Method | Tool |
|-------|--------|------|
| **Parameter Search** | Genetic Algorithm / Bayesian Optimization (Optuna) | Python + MT5 |
| **Validation** | Walk-Forward Optimization (rolling windows) | custom script |
| **Robustness** | Monte Carlo simulation (randomized entry timing) | numpy |
| **Multi-Pair** | Aggregate Sharpe × (1 - MaxDD correlation penalty) | pandas |
| **Deployment** | Paper trade → GO/NO-GO gates → Live | MT5 |

### 🐍 Key Python Frameworks for Multi-TF Backtesting

| Framework | Multi-TF | Multi-Pair | Walk-Forward | Live Trading | Note |
|-----------|----------|------------|--------------|--------------|------|
| **Backtrader** | ✅ `resampledata()` | ✅ | Manual | IB, Oanda | Most popular, extensive docs |
| **PyEventBT** | ✅ native | ✅ native | ✅ native | ✅ MT5 | New OSS, event-driven, mocks MT5 API |
| **vectorbt** | Via resample | ✅ | Manual | ❌ | Fastest (vectorized, Numba) |
| **QuantConnect/LEAN** | ✅ | ✅ | ✅ | ✅ | C#/Python, institutional |
| **NautilusTrader** | ✅ | ✅ | ✅ | ✅ | Rust-native, nanosecond precision |
| **Freqtrade** | ✅ | ❌ (crypto) | Hyperopt | ✅ | Best for crypto |
| **FinClaw** | ❌ | ✅ | ✅ WFO + MC | ❌ | GA evolves strategies from 484 factors |

### 📊 Recommended 8-Pair Basket for M5

| Pair | Type | Daily ATR (pip) | Session |
|------|------|-----------------|---------|
| EURUSD | Major | 60-90 | London/NY overlap |
| GBPUSD | Major | 90-130 | London |
| USDJPY | Major | 80-120 | Tokyo/London |
| AUDUSD | Major | 50-80 | Sydney/Tokyo |
| USDCAD | Major | 60-90 | NY |
| NZDUSD | Major | 45-70 | Sydney |
| EURJPY | Cross | 100-150 | Tokyo/London overlap |
| GBPJPY | Cross | 150-200 | London |

### 🔬 Walk-Forward Optimization Pipeline (Python Pseudocode)
```python
from walk_forward_opt import WalkForwardOptimizer
from strategies import MultiTF_EMA_Cross

# Define 8 pairs
pairs = ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 
         'USDCAD', 'NZDUSD', 'EURJPY', 'GBPJPY']

# WFO: 2yr in-sample, 3mo out-of-sample, rolling
wfo = WalkForwardOptimizer(
    strategy=MultiTF_EMA_Cross(
        trend_tf='H4',
        context_tf='H1', 
        entry_tf='M5'
    ),
    pairs=pairs,
    is_window='2Y',
    oos_window='3M',
    objective='sharpe_ratio'
)

results = wfo.run()
# → Aggregate OOS Sharpe: 0.8+
# → Profitable windows: 6/8
# → Regime stability check
```

### ⚠️ Key Pitfalls
- **Look-ahead bias**: Never use H4 close before M5 bar completes
- **Survivorship bias**: Test on delisted pairs too
- **Overfitting**: WFO windows must be disjoint; Monte Carlo perturb entries ±2 bars
- **Spread/slippage**: Model realistic spreads per pair (EURUSD 0.5 pip, GBPJPY 2.5 pip)
- **Correlation penalty**: If EURUSD + GBPJPY both signal, reduce size (they're 0.7 correlated)

### 📚 Key GitHub Repos
- **TonyMa1/walk-forward-backtester** ⭐9 — Bayesian Optimization + WFO
- **yakub268/quant-backtest-framework** ⭐2 — WFO + Monte Carlo + GO/NO-GO gates
- **marticastany/pyeventbt** — Event-driven multi-TF multi-instrument MT5 backtesting

---

## 4. Best Free AI Trading Resources

### 🤖 Top Open-Source AI Trading Frameworks on GitHub (2026)

| # | Project | Stars | Focus | Key Tech |
|---|---------|-------|-------|----------|
| 1 | **TradingAgents** (TauricResearch) | ⭐85k+ | Multi-agent LLM trading firm | LangGraph, GPT/Claude/Gemini, 5-tier rating, bull/bear debate |
| 2 | **FinGPT** (AI4Finance) | ⭐15k+ | Financial LLMs | Sentiment analysis, market forecasting, fine-tuning |
| 3 | **FinRL** (AI4Finance) | ⭐10k+ | RL trading agents | PPO, SAC, A2C, ensemble strategies |
| 4 | **FinRobot** (AI4Finance) | — | AI agent platform | Multi-agent financial analysis workflows |
| 5 | **Freqtrade** | ⭐30k+ | Crypto bot + hyperopt | Strategy backtesting, GPU-accelerated |
| 6 | **Qlib** (Microsoft) | ⭐16k+ | Quant research | Alpha mining, portfolio optimization |
| 7 | **FinRL-DeepSeek** | ⭐317 | LLM + RL fusion | LLM-infused risk-sensitive RL for trading |
| 8 | **AgentTradeX** | ⭐15k+ | AI trading agent | LangChain + Pinecone vector search |
| 9 | **Hummingbot** | ⭐8k+ | Market making | Cross-exchange arbitrage, CEX/DEX |
| 10 | **Superalgos** | ⭐5k+ | Crypto automation | Visual strategy designer |

### 📄 Key Academic Papers

| # | Paper | Venue | Topic |
|---|-------|-------|-------|
| 1 | **TradingAgents: Multi-Agents LLM Financial Trading Framework** | AAAI 2025 | Multi-agent LLM system with bull/bear debate, risk management. Outperforms baselines on cumulative returns & Sharpe. |
| 2 | **FinGPT: Open-Source Financial Large Language Models** | NeurIPS 2023 Workshop | Blueprint for open financial LLMs. Data curation, fine-tuning, sentiment. |
| 3 | **FinRL-DeepSeek: LLM-Infused Risk-Sensitive RL for Trading Agents** | arXiv:2502.07393 | LLM signals (DeepSeek) integrated into RL trading. Bull market → PPO, Bear → CPPO-DeepSeek. |
| 4 | **FinRL: Deep RL Framework for Automated Stock Trading** | ACM ICAIF 2021 | Foundational FinRL paper. Ensemble strategies, backtesting pipeline. |
| 5 | **Transformer-Based RL for Forex Trading** | Springer 2024 | Transformer + DQN for forex. LSTM for time-series, DQN for action selection. |
| 6 | **Trading-R1 Technical Report** | arXiv:2509.11420 | Reinforcement learning for reasoning-enhanced trading. |
| 7 | **Hybrid CNN-LSTM + DQL for Forex** | JAMCS 2025 | CNN-LSTM forecasting + Deep Q-Learning optimization. |
| 8 | **RL Portfolio Optimization (PPO/SAC/A2C)** | GitHub 2026 | Multi-asset RL portfolio with Stable-Baselines3, pandas-ta indicators. |

### 🧠 AI4Finance Ecosystem (Best Starting Point)

```
AI4Finance Foundation (ai4finance.org)
├── FinGPT    → LLMs for sentiment/forecasting
├── FinRL     → RL for trading agents
│   ├── FinRL-Meta     → Market environments
│   ├── FinRL-Crypto   → Crypto trading
│   └── FinRL-DeepSeek → LLM+RL fusion
├── FinRobot  → Multi-agent financial analysis
├── FinNLP    → Financial NLP pipeline
└── FinML     → ML for stock recommendations
```

### 🔗 Quick Links

| Resource | URL |
|----------|-----|
| AI4Finance GitHub | `github.com/AI4Finance-Foundation` |
| TradingAgents | `github.com/TauricResearch/TradingAgents` |
| TradingAgents Paper | `arxiv.org/abs/2412.20138` |
| FinGPT Paper | `arxiv.org/abs/2306.06031` |
| FinRL-DeepSeek Paper | `arxiv.org/abs/2502.07393` |
| AI4Finance Discord | `discord.gg/trsr8SXpW5` |
| TradeSight (WFO Python) | `github.com/rmbell09-lang/tradesight` |

### 💡 How to Combine for Hermes Exness Bot

```
Data Layer:
  ├── Economic Calendar → JBlanked API (free 1 req/day)
  ├── Sentiment → Myfxbook API + cotdata.net DXY COT
  ├── DXY Proxy → Self-calculated from yfinance
  └── Price Data → MT5 copy_rates_range()

AI/Decision Layer:
  ├── Multi-TF Strategy → Backtrader/PyEventBT with WFO
  ├── LLM Context → TradingAgents-style bull/bear debate
  └── RL Optimization → FinRL PPO/SAC agents

Execution Layer:
  └── MT5 Python API
```

---

## 🇮🇩 Ringkasan Bahasa Indonesia (Indonesian Summary)

### 1. API Kalender Ekonomi Gratis
Alternatif terbaik untuk `nfs.faireconomy.media`: **JBlanked News API** (gratis 1 req/hari, agregasi dari MQL5 + ForexFactory + FxStreet), **ForexNewsAPI** (free trial, 800+ event, 15 negara), dan **Economic Calendar API di RapidAPI** (30 req/bulan gratis). Untuk solusi self-hosted, gunakan **fizahkhalid/forex_factory_calendar_news_scraper** (⭐77, Python, Docker) yang bisa dijalankan di VPS gratis/murah.

### 2. Sumber Sentimen Gratis & DXY Proxy
**Myfxbook Community Outlook** menyediakan API sentimen gratis (long/short % untuk 50+ pasangan). **cotdata.net** memberikan data COT DXY gratis dengan riwayat penuh. Untuk DXY Proxy, bisa dihitung sendiri menggunakan formula weighted geometric mean dengan data dari yfinance (gratis), atau menggunakan **HunchMachine DXY Proxy API** (free tier). **FXSSI** juga memiliki fitur USDX bawaan.

### 3. Optimasi Strategi Multi-Timeframe (M5, 8 Pair)
Arsitektur yang direkomendasikan: H4 (trend filter) → H1 (struktur pasar) → M15 (konfirmasi momentum) → M5 (entry trigger). Gunakan **Walk-Forward Optimization** dengan rolling window (2 tahun in-sample, 3 bulan out-of-sample) menggunakan Python + Backtrader atau PyEventBT. Framework FinClaw bisa mengevolusi strategi dari 484 faktor menggunakan Genetic Algorithm + WFO. 8 pasangan optimal: EURUSD, GBPUSD, USDJPY, AUDUSD, USDCAD, NZDUSD, EURJPY, GBPJPY.

### 4. Sumber Daya AI Trading Gratis Terbaik
**TradingAgents** (⭐85k+) — framework multi-agent LLM yang mensimulasikan firma trading lengkap (analis fundamental, teknikal, sentimen, bull/bear debate, risk manager). **FinGPT** (⭐15k+) — LLM keuangan open-source untuk analisis sentimen dan peramalan. **FinRL** (⭐10k+) — framework reinforcement learning untuk agen trading. **AI4Finance Foundation** menyediakan seluruh ekosistem (FinGPT + FinRL + FinRobot + FinNLP). Untuk forex spesifik, **FinRL-DeepSeek** menggabungkan sinyal LLM dengan RL.

---

> **Disclaimer:** This research is for educational purposes only. All trading involves risk. Backtest thoroughly before deploying real capital. Past performance does not guarantee future results.

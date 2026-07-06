# Crypto Binance Futures Extension

> **Status:** `crypto_scanner.py` written (DRAFT) — 2026-07-04.
> **Not activated — scanning logic only, no pipeline integration yet.**
> **User preference:** metski prefers Binance futures over Exness crypto CFDs.

## Implemented: `crypto_scanner.py`

**File:** `crypto_scanner.py` (root of hermes folder)

A standalone Python script that:
1. Fetches Top 100 coins from CoinGecko API
2. **Pass 1 filter:** volume ≥ $50M + price change ≥ 2% in 24h
3. **Pass 2 filter:** fetches Binance futures funding rate + open interest for each candidate
4. **Pass 3 scoring:** ranks by volume score + volatility score + funding rate score + OI score
5. Returns top 3-5 candidates with full metadata

**Output:** saves to `crypto_candidates.json` (ready for pipeline consumption)

**Run:** `python crypto_scanner.py`
**GitHub:** committed to `novanrnt/hermes-trading-bot`

## Planned Architecture (not yet implemented)

Same Hermes multi-agent swarm pattern as forex, adapted for Binance futures:

```
→ crypto_scanner.py → Top 100 CoinGecko → filter 3-5
→ Full 5-Agent Pipeline:
  → Technical Agent — 1m/5m/15m analysis (crypto timeframes, faster than forex)
  → Fundamental Agent — on-chain data (TVL, halving, ETF flow, Binance listings)
  → Sentiment Agent — funding rate, open interest, Fear & Greed Index, social hype
  → Risk Agent — ATR sizing, SL/TP, max drawdown, overlap
  → Manager Agent — final BUY/SELL/WAIT
→ Execute on Binance futures API (not MT5)
→ Telegram reports same as forex pipeline
```

## Key Differences from Forex Pipeline

| Aspect | Forex (current) | Crypto (planned) |
|--------|----------------|------------------|
| **Data source** | MT5 (Exness) | Binance API (futures) |
| **Market hours** | 07:00-22:00 WIB, no weekends | 24/7 — no session gate |
| **Scan source** | 8 enabled symbols | Top 100 CoinGecko → filter 3-5 |
| **Fundamental agent** | Macro economics (CPI, NFP, FOMC) | On-chain data (TVL, halving, ETF) |
| **Sentiment agent** | DXY proxy, retail positioning | Funding rate, OI, Fear & Greed |
| **Extra filter** | ADX gate, news ±2h | Funding rate (+ = avoid long) |
| **Execution** | MT5 market orders | Binance futures API |
| **Timeframes (scalp)** | M5 | 1m-5m (crypto moves faster) |
| **Timeframes (day)** | H4→H1→M15 | 15m-1h |

## Data Sources for Crypto Agents

- **Technical:** Binance API klines (candles) — same indicator logic (EMA, ADX, RSI, ATR)
- **Fundamental:** CoinGecko API (market data, rankings), Glassnode (on-chain if available), news feeds (CoinDesk, Binance blog)
- **Sentiment:** Binance funding rate API, Coinglass (OI), alternative.me Fear & Greed Index
- **Scanner:** CoinGecko top 100 → filter by 24h volume + price change momentum

## Constraints

- **Max 5 positions total** (same as forex, but crypto-only pool since separate account)
- **Funding rate filter:** positive funding (longs pay shorts) → prefer short bias; negative → prefer long. Skips if abs(funding) > extreme threshold
- **Leverage:** Binance futures supports 1-125x. Suggest conservative (3-5x for day, 10x for scalp)
- **No session gate** — 24/7 means continuous scanning. Consider cooldown between same-coin entries
- **API rate limits:** Binance has strict WS weight limits — scanner must batch requests

## References

Main pipeline architecture: `SKILL.md` in `hermes-exness-bot`
Forex scalping framework: `references/scalping-framework.md`
Forex day trade pipeline: `references/multi-agent-bots.md`
Bull/Bear debate: `references/bull-bear-debate.md`

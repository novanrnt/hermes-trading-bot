# Crypto Binance Futures Extension

> **Status:** Design discussion only (2026-07-04) — no code written.
> **User preference:** metski prefers Binance futures over Exness crypto CFDs.
> **Next step:** User said "nanti lagi" — revisit when ready.

## Architecture (Planned)

Same Hermes multi-agent swarm pattern as forex, adapted for Binance futures:

```
→ CoinGecko Top 100 scan (volume + momentum filter)
→ Filter to 3-5 candidates (highest volume + volatility)
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

## Scan → Pipeline Flow

1. **Scanner:** CoinGecko Top 100 → sort by 24h volume → pick top 5-10 with momentum (ADX/RSI)
2. **Filter:** eliminate duplikat, coins with extreme spreads, low liquidity futures pairs
3. **Technical Agent:** analyze chart 1m-15m per candidate (parallelized)
4. **Fundamental Agent:** on-chain/news context per candidate
5. **Sentiment Agent:** funding rate + OI + Fear & Greed
6. **Risk Agent:** Binance-specific lot sizing (contract size, leverage), SL/TP
7. **Manager:** merge all → BUY/SELL/WAIT per candidate

## Constraints

- **Max 5 positions total** (same as forex, but crypto-only pool since separate account)
- **Funding rate filter:** positive funding (longs pay shorts) → prefer short bias; negative → prefer long. Skips if abs(funding) > extreme threshold
- **Leverage:** Binance futures supports 1-125x. Suggest conservative (3-5x for day, 10x for scalp) — metski can decide
- **No session gate** — 24/7 means continuous scanning. Consider cooldown between same-coin entries
- **API rate limits:** Binance has strict WS weight limits — scanner must batch requests

## References

Main pipeline architecture: `SKILL.md` in `hermes-exness-bot`
Forex scalping framework: `references/scalping-framework.md`
Forex day trade pipeline: `references/multi-agent-bots.md`

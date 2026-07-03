# Free Data Feeds for Hermes Exness Bot

## News Calendar (Economic Events)

**Source:** `https://nfs.faireconomy.media/ff_calendar_thisweek.json`

Free, no API key required. Returns JSON array of this week's economic events.

**Field mapping:**
- `country` → currency (USD, EUR, GBP, JPY, CHF, CAD, AUD, NZD)
- `title` → event name
- `impact` → "High" / "Medium" / "Low" (with color hints like "red"/"orange")
- `date` → ISO 8601 timestamp
- `actual` / `forecast` / `previous` → values (may be empty)

**Filtering strategy (critical for prompt size):**
1. Filter to RELEVANT_CURRENCIES only (8 major)
2. Filter to high + medium impact only
3. Filter to current Mon-Fri week only
4. Result: ~27 events (down from ~93 raw)

**Why filtering matters:**
93 events × 8 symbols × 4 TFs in MT5 payload = >25K chars → deepseek model returns empty JSON due to prompt overflow. 27 events keeps it manageable.

## Big News Filtering (Pair Blocking)

Not all high-impact events block pairs. The system uses a two-tier approach:

### Tier 1: `big_news` flag (set by `news_feed_collector.py`)
Events flagged as `big_news: true` are truly market-moving:
- **Rate decisions**: Federal Funds Rate, BOJ Policy Rate, Cash Rate (RBA), SNB Policy Rate, Official Bank Rate (BOE)
- **Inflation**: CPI y/y (all currencies)
- **Employment**: NFP, Claimant Count Change (only if high impact)
- **GDP**: GDP q/q (all currencies)
- **FOMC**: Statement, Economic Projections, Press Conference

Events that are high-impact but NOT big_news:
- Press conferences (RBA, BOJ, SNB)
- Policy statements (Monetary Policy Statement)
- Secondary indicators (Retail Sales, PMI, Claimant Count)

### Tier 2: Time window (±2 hours)
Even big_news events only block pairs within ±2 hours of the event time. This is enforced in:
- `agent_orchestrator.py` → `load_economic_calendar()`
- `telegram_reporter.py` → `_load_news_payload()`

**Both functions must stay in sync.** When changing filtering logic, update BOTH.

### Example
FOMC at 14:00 UTC on June 17:
- USD pairs blocked: 12:00–16:00 UTC only
- Before 12:00: USD pairs tradeable
- After 16:00: USD pairs tradeable

GBP Claimant Count Change (high impact, not big_news):
- GBP pairs: NEVER blocked by this event

## Sentiment Feed (Market Mood)

**Source:** Computed from live MT5 data — no external API needed.

**DXY Proxy:** Average % change of 5 USD pairs: EURUSDm, GBPUSDm, USDJPYm, USDCHFm, USDCADm.
- DXY up ≈ USD bullish → risk_off bias
- DXY down ≈ USD bearish → risk_on bias

**Market Mood:** Based on H4 trend alignment across 8 symbols:
- risk_on: 5+ symbols bullish on H4
- risk_off: 5+ symbols bearish on H4
- neutral: mixed

**Other signals:**
- gold_sentiment: XAUUSDm H4 trend + volume proxy
- jpy_safe_haven: USDJPYm correlation with risk mood
- dxy_bias: weak/strong/neutral based on proxy change magnitude

## Collector Scripts

```
python news_feed_collector.py          # → economic_calendar_payload.json
python sentiment_feed_collector.py     # → sentiment_payload.json
```

Both scripts handle fallback gracefully — if network fails, existing payload is preserved.

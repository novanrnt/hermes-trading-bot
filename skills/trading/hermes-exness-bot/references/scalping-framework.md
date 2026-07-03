# Scalping Framework — M5 Quick Entry System

## Philosophy

Two independent systems: **Day Trade** (H4→H1→M15, 2h interval) and **Scalping** (M5, 10min quick scan). They share position limits (max 5 total) and risk controls, but have separate entry rules, timeframes, and reporting labels. Reports always marked `[SCALP]` vs `[DAY]`.

Scalping catches intra-session pullbacks and micro-trends that the day trade system's 2-hour scan window misses. Designed to complement day trade — not compete with it. Max 2 scalping positions at any time, separate from day trade.

## Entry Sequence (M5, 6-step confirmation chain)

Each step must pass BEFORE checking the next — no shortcuts. If any step fails, reject and wait for next candle.

### Step 1: H1 Trend Bias (the "why")
- **H1 EMA20** > H1 SMA50 → bias LONG (price above EMAs = uptrend)
- **H1 EMA20** < H1 SMA50 → bias SHORT (price below EMAs = downtrend)
- **H1 ADX ≥ 22** — confirms trend has strength. ADX < 22 = ranging → skip this pair
- If ADX ≥ 22 but EMA is flat/crossed → skip (trend is weakening despite momentum)

### Step 2: M5 Value Zone (the "where")
- Price must be **near H1 EMA20** on M5 chart (within 2.5× M5 ATR)
- This is the "value zone" — waiting zone, NOT the entry itself
- If price is far from EMA20 → skip (too extended, risk of chasing)
- **Changed 2026-07-03:** from 1.5× to 2.5× ATR. In strong trends price rides 1-2 ATR above EMA — 1.5× was too tight for trend-continuation entries.

### Step 3: M5 Candle Trigger (the "when")
Choose ONE trigger type per setup to avoid overtrading:

**A) Pin Bar / Rejection Candle**
- Wick ≥ 60% of total candle range
- Body ≤ 40% of range
- For LONG: lower wick ≥ upper wick, close in upper half
- For SHORT: upper wick ≥ lower wick, close in lower half
- Direction must match H1 bias (bullish pin → long bias, bearish pin → short bias)

**B) Engulfing Candle**
- Current candle body completely engulfs previous candle body
- For LONG: green body closes above previous candle's open
- For SHORT: red body closes below previous candle's open
- Direction must match H1 bias

**C) Trend Continuation Candle (NEW 2026-07-03)**
- Candle closes in H1 trend direction AND close > M5 EMA20
- Volume ≥ 0.8× 10-bar average volume
- No reversal pattern needed — simple continuation in trend direction
- Added because trending markets rarely form pinbars/engulfings at M5 value zones
- Trigger priority: Pin Bar > Engulfing > Trend Continuation

### Step 4: RSI(7) Momentum Confirmation
- Period: 7 (not 14 — more responsive for scalping)
- **For LONG:** RSI(7) between 30-70 (filter only extreme overbought/oversold). Cross up from <30 oversold also valid.
- **For SHORT:** RSI(7) between 30-70 (same range). Cross down from >70 overbought also valid.
- **Changed 2026-07-03:** Originally 40-50 for long / 50-60 for short — too tight for trending markets where RSI naturally runs 55-65. Widened to 30-70 for both directions.

### Step 5: Volume Spike (optional but preferred)
- Current candle volume ≥ average volume of last 10 M5 candles
- Confirms real buying/selling pressure, not garbage candles
- If volume OK → confidence +4 (82 vs 78)
- If volume weak → still enterable but mark as lower confidence

### Step 6: Structure (market micro-structure)
- **FVG (Fair Value Gap):** look for 3-candle imbalance — gaps between candle 1 high and candle 3 low (bullish) or candle 1 low and candle 3 high (bearish). Entry at FVG edge in trend direction.
- **Order Flow:** recent M5 momentum bars (2+ consecutive directional candles with increasing range) confirm the bias
- **Liquidity sweep:** if price swept below recent swing low (for long) or above swing high (for short) then reversed into entry zone → higher confidence
- At minimum, check for a clean swing structure (higher highs/lower lows for trend). Counter-trend wick into value zone is neutral — price needs to SHOW direction before entry.

## Risk Management

- **SL:** 1.5× M5 ATR below entry candle's low (long) or above entry candle's high (short). Must be beyond candle trigger range.
- **TP:** 1.5× SL distance (RR 1.5). Tighter than day trade's RR 2.0 because scalping has higher frequency and lower per-trade confidence.
- **Risk per trade:** 0.3% (half of day trade's 0.5%) — compensates for lower RR.
- **Max scalping positions:** 2 (total combined with day trade = max 5)
- **Pair cooldown:** Same as day trade (240 min after entry)
- **No martingale, no averaging, no grid** — identical rule to day trade

After the quick scan finds a candidate, the scanner triggers a **2-agent fleet** (Risk + Manager only):

```
every 10 min (cron b6752100c443):
  scripts/scalping_scanner.py  (Python, no LLM)
    ├─ check 8 symbols on M5 + H1
    ├─ Steps 1-6 above (H1 trend -> M5 value -> trigger -> RSI -> volume -> structure)
    ├─ IF candidate found
    │   ├─ print report to stdout (cron delivers to Telegram)
    │   └─ subprocess: agent_swarm.py --mode scalp --symbol <SYM>
    │       ├─ [SCALP] Skip Technical/Fundamental/Sentiment — handled by scanner
    │       ├─ Risk agent validates (RR 1.5 min, 0.3% risk) -> posts to Topic 973
    │       ├─ Manager reviews Risk output + scanner data -> Topic 974 with [SCALP] label
    │       ├─ Auto-parse decision -> final_decision.json (mode_trade: "scalp")
    │       └─ trade_executor_demo.py --execute -> posts result to Topic 974
    └─ IF no candidate -> silent (zero output = no message)
```

The scanner runs indicators in Python — zero LLM cost. Only triggers the **Risk + Manager agents** when a validated candidate emerges. Technical/Fundamental/Sentiment agents are SKIPPED for scalping because the scanner already handles technical analysis, and M5 timeframe doesn't benefit from fundamental/sentiment analysis (economic data moves daily, not every 10 minutes).

## Scalping vs Day Trade Differentiation

| Dimension | Day Trade [DAY] | Scalping [SCALP] |
|-----------|----------------|------------------|
| Timeframes | H4 → H1 → M15 | H1 → M5 |
| Scan interval | Every 2 hours | Every 10 min |
| Entry engine | 5-agent LLM swarm (agent_swarm.py --mode day) — Tech+Funda+Senti+Risk+Manager | Python scanner + 2-agent fleet (agent_swarm.py --mode scalp) — Risk+Manager only |
| Trigger | S/D zone + ADX + agent debate | Pin bar / Engulfing + RSI + volume |
| SL basis | H1 swing + H1 ATR × 2.0 | M5 ATR × 1.5 below trigger candle |
| TP / RR | 2.0 | 1.5 |
| Risk / trade | 0.5% | 0.3% |
| Max positions | 3 | 2 |
| Report label | `[DAY]` | `[SCALP]` |
| Entry method | Market order after pipeline | Market order after quick scan |

## Scalping-Specific Pitfalls

- **Language requirement (2026-07-03):** The scalping pipeline uses the same agent_swarm.py prompts as day trade — all agents MUST output in Bahasa Indonesia. Only the 6-entry-step process flow in this reference remains in English as a design spec; actual bot output is Indonesian.
- **Don't blend signals:** M5 scalping and day trade H4 analysis use incompatible timeframes. A day trade SELL is NOT automatically a scalping SELL. Each system evaluates independently.
- **Slow vs fast model mismatch:** The 10-min scanner runs pure Python. If you want the full pipeline to also validate scalping entries, it takes ~180s with qwen3.7-plus. The signal may be stale by then. Now the scanner triggers agent_swarm.py --mode scalp which runs the same qwen3.7-plus for all agents — M5 setups with strong pinbar/engulfing triggers + volume confirmation tend to hold for 2-5 candles (10-25 min), so 180s latency is acceptable. If too many signals expire before the pipeline finishes, consider using deepseek-v4-flash for the scalping pipeline instead.
- **RSI(7) whipsaws:** RSI(7) is more sensitive than RSI(14) — it can cross 40→50 and back down within 2 candles. Wait for the candle to CLOSE confirming the cross before entering. An open-candle cross is a trap.
- **Pin bar vs engulfing:** Choose ONE per entry, not both OR'd together. OR logic doubles false signals — every candle has either a wick or a body. Pin bar catches reversals, engulfing catches continuation. Use engulfing only when trend is clear and ADX > 30; use pin bar for ADX 22-30.
- **Max 2 scalping positions:** Hard limit in `.env` or scanner config. Scalping is higher frequency — without a cap, it can dominate the account and conflict with day trade risk limits.
- **10 min scan during low volume (Asian session 07:00-10:00 WIB):** M5 candles during Asian session often have tiny ranges and low volume. The scanner may produce many qualified-but-weak signals. Consider raising ADX min to 25 during Asian session or adding a minimum M5 ATR filter.
- **No OCO / chandelier exit for scalping:** The trailing stop operates on M15 timeframe (every 5 min). For M5 scalping (typical hold 15-45 min), the trailing stop may be too slow. Consider a fixed TP exit for scalping entries — or accept that scalping hits TP more often than trailing modifies SL.

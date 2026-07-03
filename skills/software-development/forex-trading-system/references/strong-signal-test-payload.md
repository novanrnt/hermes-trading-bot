# Strong Signal Test Payload

Use this pattern to test the full pipeline with a setup that should produce an ENTRY decision. All agents should agree.

## EURUSD Strong Bullish (confirmed working)

```json
{
  "generated_at": "2026-06-14T04:30:00",
  "mode": "dummy_strong_signal",
  "symbols": {
    "EURUSD": {
      "bid": 1.0862, "ask": 1.0864, "spread": 0.00020,
      "H4": {
        "ema20": 1.0835, "ema50": 1.0800,
        "rsi14": 62, "atr14": 0.0070, "adx14": 32,
        "trend": "bullish", "close": 1.0862,
        "support": 1.0800, "resistance": 1.0900
      },
      "H1": {
        "ema20": 1.0848, "ema50": 1.0830,
        "rsi14": 58, "atr14": 0.0030, "adx14": 28,
        "trend": "bullish", "close": 1.0862
      },
      "M15": {
        "ema20": 1.0855, "ema50": 1.0845,
        "rsi14": 54, "atr14": 0.0012,
        "trend": "bullish_pullback", "close": 1.0862
      },
      "M5": {
        "ema20": 1.0858, "ema50": 1.0852,
        "rsi14": 52, "atr14": 0.0006,
        "trend": "neutral_consolidation", "close": 1.0862
      },
      "m5_candle_size": 0.0005
    }
  },
  "account": {
    "balance": 1000.00, "equity": 1000.00, "margin": 0.00,
    "free_margin": 1000.00, "leverage": 2000
  },
  "daily_loss": 0.00,
  "xauusd_daily_loss": 0.00,
  "open_positions": 0,
  "news": [
    {"time": "2026-06-14T09:00:00", "currency": "USD", "impact": "low", "event": "Import Prices m/m"},
    {"time": "2026-06-16T12:30:00", "currency": "USD", "impact": "high", "event": "Retail Sales m/m"}
  ]
}
```

## Why This Works

| Factor | Value | Why It Passes |
|--------|-------|---------------|
| H4 trend | bullish | EMA20 > EMA50, ADX 32 (>25 threshold) |
| H1 trend | bullish | Matches H4 direction |
| M15 trend | bullish_pullback | Pullback in bullish context = entry opportunity |
| M5 trend | neutral_consolidation | Acceptable — timing not yet confirmed |
| RSI range | 52-62 | Healthy, not overbought |
| ADX | 28-32 | Above 25 = trending |
| Spread | 0.00020 | Normal for EURUSD |
| News | low-impact only nearby | No high-impact blocking |
| Account | clean | No daily loss, no open positions |

## Expected Pipeline Output

- Technical: EURUSD buy, score 7-8, strong setup
- Fundamental: conditional (news available, Retail Sales high-impact in 2 days)
- Sentiment: conditional (no sentiment data)
- Risk: allowed (RR valid, spread normal, daily loss 0)
- Manager: ENTRY — EURUSD buy, confidence 80+
- Safety gate: PASS

## Rejected Pairs Pattern

Include GBPUSD (ranging, ADX 18) and XAUUSD (near resistance) as rejected to exercise the rejection path.

## Key Requirements for Strong Signal

1. **Multi-TF alignment** — H4 and H1 MUST show same direction
2. **ADX > 25** — Below 25 = "weak trend", Technical Agent rejects
3. **M15 pullback** — Not continuation, but pullback FROM the trend = entry opportunity
4. **RSI not extreme** — 45-65 range ideal, >70 = overbought reject
5. **Spread normal** — EURUSD < 0.00030, XAUUSD < 1.0
6. **No high-impact news within 4 hours** — Fundamental Agent blocks
7. **Account clean** — daily_loss = 0, open_positions = 0

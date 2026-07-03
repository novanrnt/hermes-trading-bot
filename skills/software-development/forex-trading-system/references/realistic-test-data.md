# Realistic MT5 Test Data Patterns

## What Makes a Signal Pass Technical Agent

The Technical Agent is very conservative. It rejects candidates when:
- M15/M5 timeframes show "neutral" trend (even if H4/H1 are bullish)
- ADX < 25 on H4 (weak trend strength)
- RSI overbought (>70) or not oversold for reversal setups
- No clear pullback to EMA zone
- High spread relative to ATR

### Minimum Signal Requirements for Technical Agent Approval

For a BUY candidate to pass:
```
H4:  ema20 > ema50, rsi 50-65, adx >= 25, trend = "bullish"
H1:  ema20 > ema50, rsi 50-60, trend = "bullish"
M15: rsi 40-50 (pullback zone), trend = "bullish" or showing reversal candle
M5:  rsi recovering from dip, entry timing confirmation
```

For a SELL candidate to pass:
```
H4:  ema20 < ema50, rsi 35-50, adx >= 25, trend = "bearish"
H1:  ema20 < ema50, rsi 40-50, trend = "bearish"
M15: rsi 50-60 (pullback zone), trend = "bearish" or showing rejection candle
M5:  rsi declining from high, entry timing confirmation
```

## Realistic Spread Values (Weekday, Normal Conditions)

| Symbol | Normal Spread | Weekend Spread | Impact |
|--------|--------------|----------------|--------|
| EURUSD | 1.0-2.0 pips | 3-5 pips | Low |
| GBPUSD | 1.5-3.0 pips | 4-8 pips | Medium |
| USDJPY | 1.0-2.0 pips | 3-6 pips | Low |
| XAUUSD | 2.0-5.0 pips | 15-30 pips | HIGH - often rejected |
| USDCHF | 1.5-3.0 pips | 4-8 pips | Medium |
| USDCAD | 1.5-3.0 pips | 4-8 pips | Medium |
| AUDUSD | 1.5-3.0 pips | 4-8 pips | Medium |
| NZDUSD | 2.0-3.5 pips | 5-10 pips | Medium |

**Rule:** Never test with weekend spreads if you want signals to pass. XAUUSD with spread > 10 pips will be auto-rejected.

## Sample Bullish EURUSD Payload (Should Pass Technical)

```json
{
  "EURUSD": {
    "bid": 1.08520, "ask": 1.08535, "spread": 1.5,
    "h4": {
      "ema20": 1.0835, "ema50": 1.0800, "rsi14": 58.5, "atr14": 0.0065, "adx14": 28.5,
      "support": [1.0800, 1.0780], "resistance": [1.0870, 1.0900], "trend": "bullish"
    },
    "h1": {
      "ema20": 1.0845, "ema50": 1.0825, "rsi14": 55.2, "atr14": 0.0030, "adx14": 24.0,
      "support": [1.0830, 1.0815], "resistance": [1.0860, 1.0880], "trend": "bullish"
    },
    "m15": {
      "ema20": 1.0848, "ema50": 1.0838, "rsi14": 45.5, "atr14": 0.0014, "adx14": 20.0,
      "support": [1.0835, 1.0825], "resistance": [1.0855, 1.0865], "trend": "bullish"
    },
    "m5": {
      "ema20": 1.0850, "ema50": 1.0846, "rsi14": 52.0, "atr14": 0.0007
    }
  }
}
```

Key differences from failing test data:
- M15 trend = "bullish" (not "neutral")
- M15 RSI = 45.5 (pullback zone, not 52+)
- ADX = 28.5 on H4 (>= 25 threshold)
- Spread = 1.5 pips (realistic weekday)

## Creating Test Payloads

When creating test payloads for full pipeline testing:

1. **Set realistic weekday spreads** — 1-3 pips for majors, 2-5 for gold
2. **Make M15/M5 match H4/H1 direction** — neutral lower TFs = automatic rejection
3. **Keep RSI in tradeable range** — not overbought (>70) or oversold (<30)
4. **ADX >= 25 on H4** — below this = "weak trend" rejection
5. **Include pullback structure** — M15 RSI should be pulling back (40-50 for buys)
6. **Use 2-3 candle data per timeframe** — minimum for pattern recognition

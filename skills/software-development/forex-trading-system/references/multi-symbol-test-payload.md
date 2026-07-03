# Multi-Symbol Test Payload (Confirmed Working 2026-06-14)

4-symbol payload that produces ENTRY decision with EURUSD buy. Other symbols get rejected cleanly.

```json
{
  "timestamp": "2026-06-14T08:00:00Z",
  "source": "realistic_test_data",
  "symbols": {
    "EURUSD": {
      "resolved": "EURUSD",
      "bid": 1.0845,
      "ask": 1.0847,
      "spread_points": 2.0,
      "H4": {
        "ema20": 1.0860, "ema50": 1.0820,
        "rsi": 62, "atr": 0.0070, "adx": 32,
        "trend": "bullish",
        "support": 1.0800, "resistance": 1.0900
      },
      "H1": {
        "ema20": 1.0855, "ema50": 1.0835,
        "rsi": 58, "atr": 0.0042, "adx": 28,
        "trend": "bullish"
      },
      "M15": {
        "ema20": 1.0848, "ema50": 1.0842,
        "rsi": 45, "atr": 0.0018, "adx": 24,
        "trend": "pullback_bullish"
      },
      "M5": {
        "ema20": 1.0846, "ema50": 1.0844,
        "rsi": 42, "atr": 0.0010, "adx": 20,
        "trend": "neutral"
      }
    },
    "GBPUSD": {
      "resolved": "GBPUSD",
      "bid": 1.2720, "ask": 1.2723,
      "spread_points": 3.0,
      "H4": {
        "ema20": 1.2700, "ema50": 1.2730,
        "rsi": 44, "atr": 0.0085, "adx": 18,
        "trend": "bearish",
        "support": 1.2650, "resistance": 1.2780
      },
      "H1": { "ema20": 1.2710, "ema50": 1.2725, "rsi": 46, "atr": 0.0050, "adx": 15, "trend": "ranging" },
      "M15": { "ema20": 1.2718, "ema50": 1.2720, "rsi": 48, "atr": 0.0022, "adx": 12, "trend": "neutral" },
      "M5": { "ema20": 1.2720, "ema50": 1.2722, "rsi": 50, "atr": 0.0012, "adx": 10, "trend": "neutral" }
    },
    "USDJPY": {
      "resolved": "USDJPY",
      "bid": 157.80, "ask": 157.83,
      "spread_points": 3.0,
      "H4": {
        "ema20": 157.50, "ema50": 156.80,
        "rsi": 65, "atr": 1.20, "adx": 35,
        "trend": "bullish",
        "support": 156.50, "resistance": 158.50
      },
      "H1": { "ema20": 157.60, "ema50": 157.20, "rsi": 60, "atr": 0.80, "adx": 30, "trend": "bullish" },
      "M15": { "ema20": 157.75, "ema50": 157.55, "rsi": 55, "atr": 0.35, "adx": 26, "trend": "bullish" },
      "M5": { "ema20": 157.80, "ema50": 157.70, "rsi": 52, "atr": 0.18, "adx": 22, "trend": "neutral" }
    },
    "XAUUSD": {
      "resolved": "XAUUSD",
      "bid": 2320.50, "ask": 2321.00,
      "spread_points": 50.0,
      "H4": {
        "ema20": 2330.00, "ema50": 2310.00,
        "rsi": 55, "atr": 35.00, "adx": 25,
        "trend": "volatile",
        "support": 2300.00, "resistance": 2350.00
      },
      "H1": { "ema20": 2325.00, "ema50": 2315.00, "rsi": 50, "atr": 22.00, "adx": 20, "trend": "ranging" },
      "M15": { "ema20": 2322.00, "ema50": 2318.00, "rsi": 48, "atr": 10.00, "adx": 18, "trend": "neutral" },
      "M5": { "ema20": 2321.00, "ema50": 2320.00, "rsi": 47, "atr": 5.00, "adx": 15, "trend": "neutral" }
    }
  }
}
```

## Expected Results

- **Technical:** EURUSD buy (score 8, strong), USDJPY buy (score 7, medium)
- **Fundamental:** conditional (no news data)
- **Sentiment:** conditional (no sentiment data)
- **Risk:** conditional approve (RR valid, spread ok)
- **Manager:** ENTRY → EURUSD buy, confidence 82, RR 2.0
- **Safety Gate:** PASSED

## Why Each Symbol Gets Expected Result

| Symbol | Expected | Reason |
|--------|----------|--------|
| EURUSD | ENTRY candidate | H4/H1 bullish, M15 pullback RSI 45, ADX 32/28, spread 2.0 |
| USDJPY | Candidate but rejected by Manager | Bullish but RSI 65 near overbought, stretched above EMAs |
| GBPUSD | Rejected by Technical | ADX 18/15/12/10 weak, H1 ranging, no trend clarity |
| XAUUSD | Rejected by Technical | Spread 50pts, volatile/ranging, ADX weak |

## Key Signal Strengths for EURUSD

1. Multi-TF alignment: H4 + H1 + M15 all bullish
2. M15 pullback: RSI 45 = healthy pullback in uptrend
3. ADX 32/28: strong trend strength (>25 threshold)
4. Spread 2.0: very low, good for entry
5. Support at 1.0800: clear SL reference below entry

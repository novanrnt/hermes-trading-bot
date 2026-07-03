# Example: Hermes Exness Trading System v1.2 — Agent Test Results (2026-06-14)

## Test Setup

- **System:** 6 agents — Technical, Fundamental, Sentiment, Risk, Manager, Boss
- **Test method:** delegate_task in 2 batches of 3, toolsets=[]
- **Model used:** mimo-v2.5-pro (SumoPod)
- **Data:** Dummy MT5 payload with 3 symbols: EURUSD (bullish weak), GBPUSD (ranging), XAUUSD (bullish aligned)

## Test Data Used

```json
{
  "EURUSD": {"h4": {"ema20": 1.0850, "ema50": 1.0830, "rsi": 58, "atr": 0.0065, "adx": 22, "trend": "bullish"}, "h1": {"ema20": 1.0855, "ema50": 1.0840, "rsi": 55, "trend": "bullish"}, "m15": {"rsi": 52, "trend": "neutral"}, "m5": {"rsi": 50}},
  "GBPUSD": {"h4": {"ema20": 1.2700, "ema50": 1.2720, "rsi": 42, "atr": 0.0080, "adx": 18, "trend": "bearish"}, "h1": {"ema20": 1.2690, "ema50": 1.2710, "rsi": 44, "trend": "ranging"}, "m15": {"rsi": 46, "trend": "neutral"}, "m5": {"rsi": 48}},
  "XAUUSD": {"h4": {"ema20": 2320, "ema50": 2310, "rsi": 62, "atr": 15.0, "adx": 20, "trend": "bullish"}, "h1": {"ema20": 2322, "ema50": 2318, "rsi": 57, "trend": "bullish"}, "m15": {"rsi": 55, "trend": "bullish"}, "m5": {"rsi": 54}}
}
```

## Batch Results

| Agent | Status | Key Behavior |
|-------|--------|--------------|
| Technical | ✅ | XAUUSD buy (score 85 strong), EURUSD rejected (M15/M5 neutral), GBPUSD rejected (ranging ADX 18). Wrapped in ```json fence — mimo quirk. |
| Fundamental | ✅ | "limited" / "reject" — no news data, conservative, didn't fabricate |
| Sentiment | ✅ | "limited" / "conditional" — no sentiment data, didn't fabricate |
| Risk | ✅ | blocked — dummy data had no TP defined, RR unverifiable. Correct behavior. |
| Manager | ✅ | SKIP — Risk blocked only candidate, confidence ~68 < 75. Safety-first. |
| Boss | ✅ | Cold start. 6 findings, 3 prompt proposals, 4 config proposals. |

## Full Orchestrator End-to-End (`agent_orchestrator.py --mode test --skip-boss`)

```
Pipeline: MT5 → Technical → [Fundamental|Sentiment|Risk] → Manager

Stage 1: Technical — XAUUSD buy (score 85) .......... 11.8s
Stage 2: Fundamental — reject .......................  8.8s
         Sentiment — conditional ....................  5.5s
         Risk — blocked (missing TP) ................  7.0s
Stage 3: Manager — SKIP ............................. 10.5s
Safety Gate: passed
Total: ~44s | Output: output/cycle_*.json
```

## Verified Behaviors

1. ✅ All agents output valid JSON matching their schema
2. ✅ No agent violated role constraints (no trade execution, no invented data)
3. ✅ Conservative on missing data — Fundamental/Sentiment marked "limited"
4. ✅ Risk blocked when critical data missing (no TP = unverifiable RR)
5. ✅ Manager skipped when all agents conditional/weak
6. ✅ Safety Gate correctly allowed skip (skip is always safe)
7. ✅ Dummy fallback works when no MT5 data file present
8. ⚠ Technical agent wrapped JSON in ```json fence — orchestrator's _extract_json() strips it

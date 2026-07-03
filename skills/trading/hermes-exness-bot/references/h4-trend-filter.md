# H4 Trend Filter (v1.2.2)

## Why

Kai review identified that 5 out of 6 losses were BUY trades during bearish markets. The Technical Agent was catching pullbacks and lower-timeframe setups without checking whether the H4 macro trend supported that direction.

## What

A gate that runs AFTER Technical Agent outputs candidates but BEFORE normalization. It auto-rejects any candidate whose trade direction contradicts the H4 macro trend.

## Rule

- Get H4 EMA50 from MT5 payload
- Compare current price (bid) to EMA50_H4
- If `price > EMA50_H4` → H4 is **bullish** → reject all SELL candidates
- If `price < EMA50_H4` → H4 is **bearish** → reject all BUY candidates
- If EMA50_H4 missing → pass through (don't block)

## Implementation

### Code (`agent_orchestrator.py` lines 891-936)

```python
# After Technical Agent outputs candidates, before normalize:
symbols_data = self.mt5.get("symbols", {})
h4_trend_blocked = []
passed_candidates = []
for c in candidates:
    sym = c.get("symbol", "")
    sym_payload = symbols_data.get(sym, {})
    h4 = sym_payload.get("H4") or sym_payload.get("h4") or {}
    h4_ema50 = h4.get("ema50", 0)
    current_price = sym_payload.get("bid") or sym_payload.get("ask", 0)
    side = c.get("side", "").lower()

    if h4_ema50 and current_price:
        h4_trend = "bullish" if current_price > h4_ema50 else "bearish"
        if (side == "buy" and h4_trend == "bearish") or (side == "sell" and h4_trend == "bullish"):
            h4_trend_blocked.append({...})
            continue
    passed_candidates.append(c)
```

### Prompt (`technical_agent_prompt.txt`)

```
- ⛔ H4 TREND RULE (WAJIB): Cek H4 bias dulu sebelum tentuin side. 
  Kalau H4 bearish (harga di bawah EMA50 H4), JANGAN PERNAH kasih kandidat BUY. 
  Kalau H4 bullish (harga di atas EMA50 H4), JANGAN PERNAH kasih kandidat SELL. 
  Hanya trade searah macro trend H4. Ini aturan mutlak tanpa pengecualian.
```

## Gate Order

The pipeline now has 3 sequential gates:

1. **ADX Gate** — filters ranging/choppy (H1 ADX < 20) — BEFORE Technical Agent
2. **H4 Trend Gate** — filters counter-trend — AFTER Technical, BEFORE normalize ← NEW
3. **Risk Gate** — filters SL/RR/risk violations — in Risk Agent stage

## Tuning History

- 2026-06-16: Kai identified 5/6 losses were counter-trend BUYs
- 2026-06-17: Implemented in both code and prompt

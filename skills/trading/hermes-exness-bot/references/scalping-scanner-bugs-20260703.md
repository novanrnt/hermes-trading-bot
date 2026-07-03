# Scalping Scanner Bug Fixes (2026-07-03)

Two critical bugs found in `scripts/scalping_scanner.py` that caused **ZERO scalping signals for 2+ days**. Both are alignment bugs in indicator calculations.

## Bug 1: ADX Returns None For All Pairs

### Symptom
Scanner runs every 10min but never finds candidates. Debugging shows `ADX=None` for ALL 8 pairs. Manager reports `Analysis unavailable — manager` and never sees scalping entries.

### Root Cause
The `adx()` function used `[None] * (period + 1)` = 15 Nones as initial array, then appended actual ADX values. For 50 H1 candles, this produced ~38 entries (15 pad + 23 ADX), leaving the last 12 candles as None. Since `adx_arr[-1]` was always None, the `ADX_MIN` check at line 229 blocked every pair.

### Old Code (BROKEN)
```python
adx_vals = [None] * (period + 1)  # 15 Nones
if len(dx) >= period:
    adx_vals.append(sum(dx[:period]) / period)  # 16th entry
    for i in range(period, len(dx)):
        adx_vals.append(...)  # more entries = ~38 total of 50 needed
while len(adx_vals) < len(candles):
    adx_vals.append(None)  # pad rest with None
```

### Fix
Build clean ADX values, then pad front with Nones to align end values with last candle:
```python
adx_vals = [None] * len(candles)
if len(dx) >= period:
    adx_raw = []
    adx_raw.append(sum(dx[:period]) / period)
    for i in range(period, len(dx)):
        adx_raw.append((adx_raw[-1] * (period - 1) + dx[i]) / period)
    pad = len(candles) - len(adx_raw)
    if pad >= 0:
        adx_vals = [None] * pad + adx_raw
```

## Bug 2: RSI TypeError (None in list comprehension)

### Symptom
After fixing ADX, scanner crashes with:
```
TypeError: unsupported operand type(s) for +: 'int' and 'NoneType'
```

### Root Cause
The `rsi_values()` function used `[None] * (period + 1)` as placeholders in the RS list, but then computed `RSI = [100 - (100 / (1 + r)) for r in rs]` — the None values caused the division to crash.

### Old Code (BROKEN)
```python
rs = [None] * (period + 1)
rs.append(avg_gain / avg_loss if avg_loss > 0 else 100)
# ... append more RS values ...
rsi = [100 - (100 / (1 + r)) for r in rs]  # CRASH: None in list
return [None] * (period + 1 - len(rs) + 1) + rsi if len(rsi) < len(closes) else rsi[-len(closes):]
```

### Fix
Build clean RS values without placeholders, compute RSI, pad front:
```python
rs_vals = [avg_gain / avg_loss if avg_loss > 0 else 100]
for i in range(period + 1, n):
    # ... same logic ...
    rs_vals.append(...)
rsi = [100 - (100 / (1 + r)) for r in rs_vals]
pad = n - len(rsi)
return [None] * pad + rsi
```

## Bug 3: RSI Range Too Tight For Trending Markets

### Symptom
Even after fixing ADX and RSI, scanner found NO candidates because RSI condition was too strict. For bullish (long) bias, RSI was required to be between 40-50. But in strong bullish trends (EURUSD ADX=35, GBPUSD ADX=28), RSI is naturally 54-60 — everything blocked.

### Filter That Blocked Everything
```python
if h1_bias == "long":
    rsi_ok = (prev_rsi < RSI_OVERSOLD and crsi >= RSI_OVERSOLD) or (RSI_OVERSOLD <= crsi <= 50)
```

With `RSI_OVERSOLD=40` and upper cap `50`, long entries need RSI 40-50. In trending markets RSI sits at 54-60.

### Fix (applied 2026-07-03)
1. Widen extreme thresholds: `RSI_OVERSOLD=40→30`, `RSI_OVERBOUGHT=60→70`
2. Remove the hardcoded `50` divider — both long and short now use the full 30-70 range:
```python
if h1_bias == "long":
    rsi_ok = (prev_rsi < RSI_OVERSOLD and crsi >= RSI_OVERSOLD) or (RSI_OVERSOLD <= crsi <= RSI_OVERBOUGHT)
else:
    rsi_ok = (prev_rsi > RSI_OVERBOUGHT and crsi <= RSI_OVERBOUGHT) or (RSI_OVERSOLD <= crsi <= RSI_OVERBOUGHT)
```
Now filters only extreme RSI (<30 oversold, >70 overbought) instead of forcing RSI below 50 for long.

## Bug 4: EMA Distance Too Tight For Strong Trends

### Symptom
After RSI fix, pairs still blocked by `"Price not near EMA"`. EURUSD diff=0.00071 but ATR×1.5=0.00057 — price 1.2 ATR from EMA, still rejected.

### Root Cause
`price_near_ema = abs(price - ema) <= m5_atr * 1.5` — in strong trends, price naturally rides 1-2 ATR above EMA. Requiring pullback to 1.5 ATR misses trend-continuation entries.

### Fix
Loosen to `m5_atr * 2.5` — catches both pullbacks (to 1.5 ATR) and mild pushes from EMA (1.5-2.5 ATR). Still prevents entries when price is parabolic (>2.5 ATR from EMA).

## Bug 5: Scanner→Pipeline Data Gap

### Symptom
Risk Agent rejected scalping entries with `"Tidak ada detail entry (harga, SL, TP)"` even though scanner found detailed signal.

### Root Cause
Scanner calls `agent_swarm.py --mode scalp --symbol SYM` via subprocess. The pipeline builds a generic `tech_result` string from the symbol name only — doesn't receive the scanner's entry/SL/TP/confidence/reason.

### Fix
Scanner writes `scalp_candidate.json` to `<hermes>/` before calling pipeline. Pipeline scalp mode reads this file and injects full details into agent context:
```
Entry Price, Stop Loss, Take Profit, RR, Confidence, H1 Trend, Trigger, RSI, Volume, Reason
```
Pipeline falls back gracefully: JSON missing → "failed to load details" text → agents post fallback analysis.

## Bug 6: No Guardrails Against Repeated Entries

### Symptom
Scanner could trigger pipeline for the same symbol every 10 minutes (multiple entries on EURUSDm per day).

### Fix
Three guardrails added before triggering pipeline:
1. **Check existing MT5 positions** — skips if symbol already has open position
2. **Max 3 scalp trades/day** — checks MT5 history for today's SCALP-labeled trades
3. **Max 3 candidates per scan** — `candidates[:3]` caps pipeline triggers
4. **MT5 comment label** — scalp trades use `"Hermes v1.2 SCALP DEMO CENT"` comment for identification

To get entries in trending markets where pinbars/engulfings are rare, added a third trigger:

**New trigger:** Trend continuation — candle direction matches H1 trend AND close is above M5 EMA20 AND volume >= 0.8× average.

```python
trigger_ok = pin_match or engulf_match  # original triggers
if trend_cont_match:  # NEW: candle searah trend + close > M5 EMA
    vol_ok_tc = current_vol >= avg_vol * 0.8
    if vol_ok_tc:
        trigger_ok = True
```

This allows entries on simple continuation candles (no reversal pattern needed) when:
- H1 trend is clear (ADX >= 22)
- Price is near M5 EMA20 (value zone)
- Candle closes in trend direction above EMA
- Volume is reasonable (not the lowest)

## Verification Checklist

After fixing these bugs:
1. Run `python debug_scalp.py` — should show actual ADX values for each pair (not None)
2. All 8 pairs should have ADX > 0 (even low-trend pairs show the true value)
3. No TypeError from RSI calculation
4. Some pairs should pass all filters if market has any trend at all

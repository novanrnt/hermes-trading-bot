---
name: scalping-m5
description: Scalping strategy M5 entry based on H1 trend bias — EMA20, price action, RSI(7)
---

# Scalping M5 Strategy Framework

## Core Concept
Day trade: H4→H1 **bias penentu**. Scalping: M5 **entry execution**.
Trend besar dari H1, entry presisi di M5.

## Timeframes
- **H1:** Trend bias (EMA20 > 50, ADX > 20)
- **M5:** Entry execution (EMA20 zona, candle konfirmasi, RSI)
- **Scan:** Every 10 minutes

## Entry Rules (checklist urutan)

### 1. H1 Trend Bias
- EMA20 > 50 + ADX > 20 → BULLISH (cari long)
- EMA20 < 50 + ADX > 20 → BEARISH (cari short)
- ADX < 20 → SKIP (no trend)

### 2. M5 Value Zone
- Harga pullback sentuh / nembus tipis EMA20 di M5
- Arah pullback berlawanan trend H1

### 3. Candle Confirmation (pilih SATU)
**Pin Bar / Rejection Candle:**
- Wick ≥ 60% dari total candle range
- Wick nunjuk lawan trend (bullish trend → wick bawah panjang)
- Close di atas/bawah EMA20

ATAU

**Engulfing Candle:**
- Candle terakhir nutup lebih tinggi (bullish) dari open candle sebelumnya
- Body "menelan" candle sebelumnya searah trend

### 4. RSI(7) Confirmation
- **Long:** RSI baru cross naik dari zona 40-50
- **Short:** RSI baru cross turun dari zona 50-60
- Jangan entry kalau RSI > 70 (overbought) / < 30 (oversold) — tunggu pullback

### 5. Volume Spike (opsional)
- Candle trigger volume ≥ rata-rata 10 candle terakhir
- Filter candle kosong / fakeout

## Entry Rules
- **SL:** Di luar swing candle konfirmasi
- **TP:** RR 1.5
- **Max positions:** 5 (shared with day trade system)
- **Min Confidence:** 75 (lower than day trade due to M5 noise)

## Flow
```
1. Timed scan every 10 min
2. Check H1 bias → reject if no trend
3. Scan M5 candles → find EMA20 touch
4. Check candle confirmation (pin bar / engulfing)
5. Check RSI(7) zone
6. Send candidate to agents:
   - Technical: quick M5 validation
   - Risk: SL/TP check, max pos check
   - Manager: final decision
7. Execute demo entry (tag: scalping)
```

## Indicator Configuration
- EMA: Same as day trade (already in system)
- ADX: Same as day trade (already in system)
- RSI(7): New — period 7 for responsiveness
- Volume: Average last 10 candles (std indicator)

## Risk
- Risk per trade: 0.3% (smaller than day trade 0.5%)
- Max daily loss: 5% (same as system)
- No martingale/grid
- 1 pair maks 2 loss beruntun → skip pair for 1 hour

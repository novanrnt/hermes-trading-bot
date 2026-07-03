---
name: scalping-framework
description: Scalping trading framework — H1 trend filter → M5 price action + RSI(7) + EMA20 confluence entry. Runs on 10-min scan cycle, pairs with day trade system.
---

## Trigger
When user wants to: run scalping scan, check scalping logic, add scalping rules, or understand the scalping framework.

## Overview
Dual-system approach: Day trade (H4→H1→M15, 2-hour scan) + Scalping (H1→M5, 10-min scan). Scalping report ditandai `[SCALP]` di judul.

## Framework Indicators

### 1. H1 Trend Bias (Filter)
- EMA20 > 50 + ADX(14) > 22 → Bias Long
- EMA20 < 50 + ADX(14) > 22 → Bias Short
- ADX < 20 → Skip (ranging)

### 2. H1 Fair Value Gap (FVG)
FVG = 3-candle imbalance:
- **Bullish FVG:** Candle high < candle[1] low (gap naik)
- **Bearish FVG:** Candle low > candle[1] high (gap turun)
- Entry hanya saat harga *kembali* ke gap, bukan setelah bounce

### 3. H1 Market Structure (MSS/CHoCH)
Tentukan struktur trend H1 untuk mengetahui bias utama:
- **BOS (Break of Structure):** harga nembus swing high/low terakhir
- **CHoCH (Change of Character):** harga nembus swing structure berlawanan arah
- Pakai LLM reasoning aja — cocok buat reasoning model (qwen3.7-plus)

### 4. M5 Entry Zone — EMA20
Harga pullback nyentuh atau tembus tipis ke EMA20 M5, searah bias H1+H1 trend+FVG zone. Ini "value zone", bukan entry sendiri.

### 5. M5 Trigger — Candle Price Action
Pilih salah satu (konsisten):
- **Pin bar:** Wick ≥ 60% total candle range, nunjuk lawan trend
- **Engulfing:** Body "nelen" candle sebelumnya, searah bias

### 6. M5 Momentum — RSI(7)
- Long: RSI cross naik dari 40-50
- Short: RSI cross turun dari 50-60
- Period 7 (responsif), konfirmasi momentum entry

### 7. Volume/Tick Volume (Opsional)
Candle trigger idealnya volume > rata-rata 10 candle terakhir.

## Sequential Confirmation (WAJIB)

**Urutan cek — ga boleh skip:**
1. H1: EMA20>50 + ADX>22 → bias (STOP kalau ga lolos)
2. H1: FVG searah bias? (STOP kalau ga ada gap)
3. H1: Order flow (BOS/CHoCH) support bias?
4. M5: Harga masuk FVG zone + dekat EMA20?
5. M5: Candle konfirmasi (pin bar/engulfing searah bias)?
6. M5: RSI(7) cross searah bias dari zona netral?
7. Entry. SL swing candle + 3 pip buffer. TP RR 1.5-2.0

## Risk Management
- Risk/trade: 0.3-0.5% per trade
- Min RR: 1.5
- Max posisi: 5 total (day trade + scalping)
- SL: swing candle + buffer 3 pip
- Max 3 scalping loss/day → stop
- News block ±15 menit

## Execution
- Scan every 10 menit via `scripts/scalping_scanner.py` (Python indicator check, no LLM)
- Cron: `b6752100c443` — silent when no candidate
- **When candidate found: 2-Agent fleet via `agent_swarm.py --mode scalp --symbol SYM`**
  - Risk Agent (Topic 973) + Manager Agent (Topic 974) ONLY
  - Technical/Fundamental/Sentiment SKIPPED (scanner handles technical, M5 doesn't need macro)
  - All messages labeled [SCALP], ALL agents speak Bahasa Indonesia
- Sesi: 07:00-22:00 WIB
- Demo entry via pipeline (sama kayak day trade)
- Same MT5 account, same risk controls as day trade system (shared via `hermes-exness-bot` skill)

## Audit Trail
All parameter changes suggested by Kai (via `scripts/audit_trail.py`) are saved as PENDING — user must approve/deny before taking effect. Changes are NOT auto-applied. Rollback available via `--rollback ID`.

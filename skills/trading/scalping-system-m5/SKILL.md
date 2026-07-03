---
name: scalping-system-m5
title: Scalping System M5
description: M5 scalping framework — scan tiap 10 menit (tanpa LLM), monitor entry setup, dispatch agent hanya saat setup siap
---

# Scalping System M5 — Framework

## Implementasi Aktual (2026-07-01)

### Files
- **`scripts/scalping_scanner.py`** — Scanner actual: cek 8 symbols (H1 EMA20/ADX trend filter → M5 EMA20 value zone → candle trigger (pin bar/engulfing) → RSI(7) cross → volume). Silent jika ga ada candidate. Python murni, NO LLM.
- **Cron:** `b6752100c443`, `every 10m`, `no_agent=true`, deliver ke origin. Silent saat sehat. Output hanya saat ada kandidat scalping.

### Entry pipeline
Scanner = hanya indikator. Jika lolos → trigger `agent_swarm.py --mode scalp --symbol SYM` (2-agent fleet: Risk + Manager only). Label report = `[SCALP]`. ALL agents speak Bahasa Indonesia.

### Test koneksi bot
`python scripts/test_agent_bots.py` — verifikasi semua 5 bot bisa post ke topic masing-masing. Jalankan setelah ganti token.

### Pemisahan dari Day Trade
- [SCALP] vs [DAY] di report — jelas tercantum di Telegram
- Max 2 posisi scalping (terpisah dari pool day trade 5 slot)
- Cron dan scheduler tidak saling ganggu — scalping via cron, day trade via scheduler

## Konsep Dasar

Day trade (H4→H1→M15) + Scalping (H1→M5) jalan **paralel, terpisah**.

```
Day Trade:   H4 (trend) → H1 (bias) → M15 (entry)  ← pipeline agent lengkap
Scalping:    H1 (bias)  → M5  (entry)               ← screening-only, agent terpanggil saat entry siap
```

## Alur Scalping

### 1. Screening (tiap 10 menit, NO AGENT)

Scan cepat pake indikator — **tanpa LLM** (gratis, irit token):

```
1. Cek H1: EMA20 > 50 + ADX > 20 → tentuin BIAS (long/short)
2. Cek M5: harga dekat EMA20? Selisih ≤ 0.05% dari EMA20 M5
3. Cek M5: RSI(7) di zona netral (40-60), siap cross?
4. Kalau lolos 1-3 → MASUKKAN KE WATCHLIST
```

Yang lolos screening **tidak langsung entry**. Cuma di-monitor.

### 2. Monitor & Tunggu Konfirmasi

Daftar pair dari screening di-pantau terus (cek konfirmasi tiap candle M5 baru — 5 menit):

**Trigger konfirmasi (pilih SALAH SATU, jangan duaduanya):**

**A. Pin Bar / Rejection Candle**
- Wick minimal **60%** dari total candle range
- Wick nunjuk ke arah lawan bias
- Contoh: bias long → wick bawah panjang, close di atas EMA20

**B. Engulfing Candle**
- Candle terakhir nutup melebihi open candle sebelumnya
- Body "menelan" candle sebelumnya searah bias

**Konfirmasi lanjutan (WAJIB):**
- RSI(7) cross searah bias dari zona netral (40-50 → long, 50-60 → short)
- Candle trigger punya volume > rata-rata 10 candle terakhir (opsional tapi kuat)
- Order flow / market structure: HH/HL utk long, LH/LL utk short di M5

### 3. Dispatch Agent (LLM — TOKEN HANYA DISINI)

**Hanya** ketika konfirmasi terpenuhi ➔ panggil agent untuk validasi final.

### 4. Risk Management

- Risk per trade: **0.3-0.5%** (lebih kecil dari day trade karena frekuensi lebih tinggi)
- SL: **di bawah/atas swing candle konfirmasi** (tight, 10-25 pip)
- TP: RR **1.5** (cepat ambil profit, scalping bukan nunggu besar)
- Maks 2 posisi scalping paralel (day trade 5 posisi TERPISAH)
- Daily max loss: 3% total (combine day trade + scalping)
- **Big news ±30 menit** — skip scalping di pair terkait

### 5. Eksekusi

Entry di M5 candlestick close konfirmasi:
- Market order atau Limit di harga candle close + spread
- SL + TP attached langsung di MT5
- Trailing stop: 3x M5 ATR, aktif setelah profit > 1x ATR

**⚠️ PENTING: Executor Threshold Mismatch**
Executor `trade_executor_demo.py` punya threshold MIN_RR sendiri yang BISA berbeda dari RR scalping (1.5).
- **Scalp**: menggunakan `MIN_RR_SCALP=1.5`, `MIN_CONFIDENCE_SCALP=70` (dibaca dari `.env` atau default)
- **Day Trade**: tetap menggunakan `MIN_RR=1.8`, `MIN_CONFIDENCE=75` (general)
- Executor baca `mode_trade` dari `final_decision.json` — pastikan field ini terisi "scalp" oleh parser
- **Kalo executor pakai RR 1.8 buat semua trade → semua setup scalp RR 1.5 bakal kena block.**
- Fix: `trade_executor_demo.py` udah di-patch (2026-07-04) untuk bedain SCALP vs DAY di RR/confidence check.

## Pemisahan Day Trade vs Scalping

| Aspek | Day Trade | Scalping |
|-------|-----------|----------|
| Timeframe | H4→H1→M15 | H1→M5 |
| Scan rate | Tiap 2 jam | Tiap 10 menit (screening) |
| LLM usage | Full pipeline | Only at entry |
| Trades/day | 0-3 | 0-5 |
| RR | 2.0 | 1.5 |
| SL | 20-100 pip | 10-25 pip |
| Max posisi | 5 total | 2 khusus scalping |
| Big news | ±2 jam blok | ±30 menit blok |

## Indicator Setup

| Indikator | H1 | M5 |
|-----------|----|----|
| EMA20 | ✅ Trend filter | ✅ Entry zone |
| EMA50 | ✅ Trend filter | ❌ |
| ADX (14) | ✅ Min 20 | ❌ |
| RSI(7) | ❌ | ✅ Konfirmasi momentum |
| Volume | ❌ | ✅ Optional confirmation |

## Entry Rules (step-by-step)

```
STEP 1 — H1 Bias ✅
  EMA20 > 50 AND ADX(14) > 20 → BIAS BULLISH
  EMA20 < 50 AND ADX(14) > 20 → BIAS BEARISH
  ADX < 20 → NO BIAS, skip

STEP 2 — M5 Entry Zone ✅
  Harga sentuh/approach EMA20 di M5
  Jarak max 0.05% dari EMA20
  
STEP 3 — Candle Confirmation ✅
  Pin bar (wick ≥60%) ATAU Engulfing candle, searah bias

STEP 4 — RSI Confirmation ✅
  Long: RSI(7) cross UP from 40-50
  Short: RSI(7) cross DOWN from 50-60

STEP 5 — Structure Check (opsional kuat) ✅
  Long: Higher High + Higher Low confirmed
  Short: Lower High + Lower Low confirmed

STEP 6 → LLM VALIDATION (hanya jika 1-5 lolos)

STEP 7 → EXECUTE
  Entry: candle close M5
  SL: below/above swing candle
  TP: RR 1.5
```

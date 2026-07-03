# Agent Prompt Tuning (All 5 Agents)

All five decision agents were tuned from conservative → moderate on 2026-06-15 after the bot produced 0 candidates across 12+ consecutive cycles even during US session.

## Technical Agent: Konservatif → Moderat

**File:** `prompts/active/technical_agent_prompt.txt`

### Problem
Original prompt used conservative decision style with "tolak semua" fallback. Result: ALL 8 pairs rejected every cycle, even during US session with active markets.

### Fix

**Before (Konservatif):**
```
- Konservatif.
- Prioritaskan trend jelas + pullback + konfirmasi.
- Hindari kondisi ranging yang tidak jelas.
- Hindari entry jika alasan SL/TP lemah.
- Hindari XAUUSD jika volatilitas tidak normal.
- Kalau tidak ada setup bersih, tolak semua.
```

**After (Moderat):**
```
- Moderat — ambil setup yang cukup bagus, tidak harus sempurna.
- Prioritaskan trend jelas + pullback + konfirmasi minimal 2-3 sinyal.
- Ranging dengan support/resistance jelas masih bisa jadi kandidat (breakout atau pantulan).
- SL/TP cukup reasonable berdasarkan ATR, tidak harus optimal.
- XAUUSD tetap boleh kalau trend kuat meski volatil tinggi.
- Kalau ada setup yang layak (minimal 2 konfirmasi), masukkan sebagai kandidat.
- Minimal 1-3 kandidat terbaik wajib dioutput kalau ada sinyal yang cukup.
```

### Tuning levers
- `Minimal 2-3 konfirmasi`: Increase to 3-4 if too many low-quality candidates
- `Minimal 1-3 kandidat`: Reduce to 0-1 if noise becomes a problem

---

## Fundamental Agent

**File:** `prompts/active/fundamental_agent_prompt.txt`

### Changes
| Rule | Before | After |
|------|--------|-------|
| Limited data | `ambil sikap konservatif` | `approval boleh "conditional" kalau setup teknikal kuat` |
| USD high-impact news | `reject USD pairs dan XAUUSD` | `pertimbangkan reject atau conditional tergantung seberapa dekat` |
| High uncertainty | `pilih reject` | `pilih conditional, bukan langsung reject` |
| No known news risk | `approval boleh "conditional"` | `approval bisa "approve"` |

---

## Sentiment Agent

**File:** `prompts/active/sentiment_agent_prompt.txt`

### Changes
| Rule | Before | After |
|------|--------|-------|
| Contra-trend sentiment | `approval harus "reject" atau "conditional"` | `approval bisa "conditional" atau "reject"` |
| Neutral sentiment | `jangan memaksakan trade` | `tetap bisa approve kalau teknikal kuat` |
| Limited data | `jelaskan dengan jelas` | `jelaskan dengan jelas, jangan langsung tolak` |
| Output style | `utamakan output konservatif` | `utamakan output moderat — jangan terlalu konservatif` |

---

## Risk Agent

**File:** `prompts/active/risk_agent_prompt.txt`

### Changes
| Rule | Before | After |
|------|--------|-------|
| Risk posture | `harus lebih ketat dibanding agent lain` | `harus teliti, tapi tidak perlu paling ketat — moderat, pakai akal sehat` |

---

## Manager Agent

**File:** `prompts/active/manager_agent_prompt.txt`

### Changes
| Rule | Before | After |
|------|--------|-------|
| Min confidence | `75` | `70` |
| No clean setup | `action wajib skip` | `action wajib skip kalau <2 agent approve` |
| Setup quality | (implicit "must be clean") | `pilih setup terbaik yang tersedia, tidak harus sempurna` |

---

## Result After All-Agent Tuning
First cycle after changes: XAUUSDm BUY found, confidence 90, passed all 6 agents, demo-executed with ticket 3289094133. Went from 0 candidates in 12+ cycles to a valid trade in the first post-tuning cycle.

## How to Re-tighten
If too many low-quality trades appear, adjust individual agents:
- **Technical**: raise `minimal 2-3 konfirmasi` → `3-4`
- **Fundamental**: revert `conditional` → `reject` for uncertainty
- **Manager**: raise confidence from `70` → `75`
- **Risk**: add back `harus lebih ketat` if risk management slips

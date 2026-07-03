# Multi-Agent Telegram Bot System

## Architecture

Five independent Telegram bots, each with their own topic in the RNT AUTOTRADE group.
Each bot posts analysis autonomously via the multiagent pipeline; the Manager reads all
and makes the final decision. **The bots are delivery endpoints** — the actual LLM
analysis runs in the multiagent pipeline, which calls SumoPod for each agent and posts
results through the matching bot.

```
┌─────────────────────────────────────────────────────────────────┐
│                   RNT AUTOTRADE GROUP (-1004396608984)            │
│                                                                   │
│  Topic 969 ── @Techcharles_bot ──── H4/H1/M15 technical analysis │
│  Topic 970 ── @Herisfundamentalbot ── News, macro, events         │
│  Topic 972 ── @DafaSentiment_bot ──── Market mood, retail pos    │
│  Topic 973 ── @Kelvinrisk_bot ─────── SL/TP/spread/risk gate     │
│  Topic 974 ── @Alwinmanager_bot ──── Merges all 4 → final call   │
└─────────────────────────────────────────────────────────────────┘
```

## Files

### Pipeline
- `multiagent_pipeline.py` (root) — main orchestrator. Collects MT5 data, runs Technical,
  Fundamental, Sentiment, Risk agents **in parallel** (threading.Thread), then Manager
  synthesizes and posts final decision. Accepts `day` or `scalping` as CLI arg.
  Output: logs/multiagent/cycle_*.json.

- `agent_swarm.py` — sequential pipeline (v2.0). Runs agents one-by-one instead of parallel.
  **Has auto-execution** — see "Auto-Execution" section below.

- `scripts/test_agent_bots.py` — connectivity test for all 5 bots. Run after adding or
  changing tokens.

## Agent Personalities

Each agent has a defined IQ score and detailed personality injected as the system prompt.
All agents speak **Bahasa Indonesia** exclusively — no English except technical terms.
Defined in `agent_swarm.py` prompt constants.

| Agent | IQ | Bot | Karakter |
|-------|-----|-----|----------|
| **Technical** | 160 | @Techcharles_bot | Sangat logis, analitis, perfeksionis, disiplin tinggi, dingin dalam mengambil keputusan, anti-FOMO, sabar menunggu setup terbaik, fokus pada fakta dan data, keras kepala jika analisis teknikal mendukung, berbicara singkat dan langsung ke inti. |
| **Fundamental** | 165 | @Herisfundamentalbot | Bijaksana, tenang, rasional, haus akan informasi, gemar melakukan riset mendalam, berpikir jangka menengah dan panjang, tidak terburu-buru mengambil kesimpulan, mengutamakan data dibanding asumsi, mampu menjelaskan kondisi ekonomi secara sederhana dan objektif. |
| **Sentiment** | 158 | @DafaSentiment_bot | Sangat intuitif, peka terhadap psikologi pasar, fleksibel, berpikiran terbuka, mampu membaca emosi dan perilaku mayoritas trader, senang mencari pola perilaku manusia, cepat mendeteksi perubahan sentimen pasar, berani mengambil sudut pandang kontrarian jika didukung data. |
| **Risk** | 170 | @Kelvinrisk_bot | Sangat konservatif, protektif terhadap modal, teliti, disiplin, selalu memikirkan skenario terburuk, tidak emosional, tegas, sulit diyakinkan jika risiko belum terkendali, lebih memilih kehilangan peluang daripada kehilangan modal, menjadi pengkritik utama setiap keputusan trading. |
| **Manager** | 180 | @Alwinmanager_bot | Karismatik, bijaksana, objektif, adil, berpikir strategis, diplomatis, pendengar yang baik, tidak memihak kepada agent mana pun, tenang di bawah tekanan, mengambil keputusan berdasarkan bukti dan konsensus, mampu menyelesaikan perbedaan pendapat secara rasional, serta bertanggung jawab penuh atas keputusan akhir tim. |

### Bahasa Indonesia Requirement

ALL agent prompts include:
```
**Bahasa:** WAJIB pakai Bahasa Indonesia. [specific tone per agent]
```
- Technical: Singkat, padat, to the point. Tidak pakai bahasa Inggris kecuali istilah teknis (EMA, ADX, RR, SL, TP).
- Fundamental: Tenang, jelas, berbobot. Hindari drama dan clickbait.
- Sentiment: Ekspresif tapi tetap data-driven.
- Risk: Tegas, serius, no-nonsense.
- Manager: Formal, profesional, berwibawa. Rangkum argumen agent-agent sebelum ambil keputusan.

The user's context text (MT5 data, technical data, agent outputs) is also in Indonesian labels:
- `Konteks Pasar:` instead of `Market Context:`
- `Analisis Teknikal:` instead of `Technical Analysis:`
- etc.

### Implementation note
Prompts are defined in `agent_swarm.py` as `TECH_PROMPT`, `FUNDA_PROMPT`, `SENTI_PROMPT`, `RISK_PROMPT`, `MANAGER_PROMPT`. Each has `**IQ:**` and `**Personality:**` blocks, then a `**Bahasa:**` line, then `**Your Task:**` in Indonesian. The task instructions (ADX check, RR check, etc.) are also in Indonesian.

### Manager Decision Format (for auto-parsing)

The Manager outputs a structured FINAL DECISION block that gets parsed by regex:

```
## FINAL DECISION
**Action:** BUY/SELL/WAIT  
**Symbol:** EURUSDm  
**Entry Zone:** X.XXXX - X.XXXX  
**SL:** X.XXXX  
**TP:** X.XXXX  
**RR:** X.X  
**Confidence:** XX/100

**Rationale:** [brief reasoning]
```

**PITFALL:** The Manager prompt template explicitly shows **bolded** field names (`**Action:**`, `**Symbol:**`, etc.) with trailing double-space for newlines. If the LLM deviates from this format (no bold, different label, extra text between fields), the regex parser fails silently and skips execution. Always verify parsing in terminal output.

## Tokens (stored in .env)

| Env Var | Bot | Topic |
|---------|-----|-------|
| `AGENT_TECH_TOKEN` | @Techcharles_bot | 969 |
| `AGENT_FUND_TOKEN` | @Herisfundamentalbot | 970 |
| `AGENT_SENT_TOKEN` | @DafaSentiment_bot | 972 |
| `AGENT_RISK_TOKEN` | @Kelvinrisk_bot | 973 |
| `AGENT_MGR_TOKEN` | @Alwinmanager_bot | 974 |

All bots added as group admins (needed to read topic messages).
Group ID: `-1004396608984` (RNT AUTOTRADE).

### Acquiring Tokens
1. Create each bot via @BotFather
2. Add to RNT AUTOTRADE group as admin
3. Send the bot token to Duleh

### Pitfall: Token Redaction
Hermes auto-replaces text matching `\d{9,10}:[\w-]+` with `***` or `[REDACTED]` in ALL
tool output (write_file, patch, terminal, grep). The actual file IS correct — only the
display is censored. To write tokens to .env, use Python file operations in a terminal
call, e.g.:
```python
open('.env', 'a').write(f'AGENT_TECH_TOKEN={token}\n')
```
Never paste robot tokens directly into skill file contents.

### Pitfall: Verify Before Pipeline Run
Run `python scripts/test_agent_bots.py` after adding/changing tokens. A single failed
bot means the pipeline skips that agent's analysis and Manager gets incomplete data.

## Pipeline Flow

### `agent_swarm.py` (Sequential — with Auto-Execution)
1. Collect MT5 data (8 symbols, H4/H1/M15)
2. **Sequential**: Technical → Fundamental → Sentiment → Risk → Manager (one-by-one)
3. Each agent result posted to its topic via its bot's token
4. Manager posts to topic 974 with structured FINAL DECISION text
5. `parse_manager_decision()` extracts params from free-text → `final_decision.json`
6. `trade_executor_demo.py --execute` called automatically (120s timeout)
7. Execution result posted back to Manager topic 974

### `multiagent_pipeline.py` (Parallel — without Auto-Execution)
1. Collect MT5 data (8 symbols, H4/H1/M15)
2. **Parallel** (threading.Thread): Technical + Fundamental + Sentiment + Risk
   call SumoPod LLM simultaneously via their personality prompts
3. Each agent result posted to its topic via its bot's token
4. **Manager** reads all 4 results, calls SumoPod LLM with merge prompt
5. Manager posts final decision to topic 974
6. Decision logged to logs/multiagent/cycle_*.json
7. **NO auto-execution** — decision stays in chat, manual/executor triggered separately

### Running commands
```bash
python agent_swarm.py                    # sequential WITH auto-execution
python multiagent_pipeline.py day        # parallel, no auto-execution
python multiagent_pipeline.py scalping   # parallel, scalping mode
```

### Auto-Execution Details (agent_swarm.py only)

**Regex parsing fields:**
| Manager Format | Parsed Field | Logic |
|---------------|-------------|-------|
| `**Action:** BUY/SELL` | `action: "entry"`, `side: "buy"/"sell"` | Direct match |
| `**Action:** WAIT` | `action: "skip"` | Returns immediately |
| `**Symbol:** EURUSDm` | `best_symbol: "EURUSDm"` | Ensures `m` suffix |
| `**Entry Zone:** 1.14280 - 1.14360` | `planned_entry: 1.14320` | Midpoint of zone |
| `**Entry:** 1.14280` | `planned_entry: 1.14280` | Single price fallback |
| `**SL:** 1.14080` | `sl_price: 1.14080` | Direct |
| `**TP:** 1.14720` | `tp_price: 1.14720` | Direct |
| `**RR:** 1.7` | `rr: 1.7` | Direct |
| `**Confidence:** 85` | `confidence: 85` | Direct |
| `**Rationale:** ...` | `reason: ...` | Up to 200 chars |

**Parsing pitfalls:**
- Missing key fields → executor BLOCKED with "Symbol not enabled" or validation error
- LLM deviates from `**Label:**` format → action defaults to "skip"
- Entry Zone parsed as midpoint — actual entry may differ when market moves
- These regex patterns match EXACTLY the template in `MANAGER_PROMPT`. If the template changes, the regex must change too.

**Execution results posted to Topic 974:**
- ✅ **DEMO TEREKSEKUSI** — shows symbol, side, lot, ticket
- ⛔ **DIBLOKIR** — shows specific block reason from executor
- ⚠️ **Waktu Eksekusi Habis** — executor timeout
- ⚠️ **Gagal Eksekusi** — unexpected error
### Scalping Scanner Feed

When `scripts/scalping_scanner.py` finds a candidate (M5 quick check), it calls
`agent_swarm.py --mode scalp --symbol SYM` directly via subprocess — running only
**Risk Agent (Topic 973) + Manager Agent (Topic 974)**.
Technical/Fundamental/Sentiment are SKIPPED for scalping because:
1. The Python scanner already handles technical indicator analysis.
2. M5 timeframe doesn't benefit from fundamental/macro analysis (economic data moves daily, not every 10 min).
3. Saves tokens and speeds response time (~60s vs ~180s for full pipeline).

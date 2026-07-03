# Kai — Trade Review & Agent Coach

## Architecture

```
Trade Close → Counter (20 trades) → Kai Review Agent triggered
                                         ↓
         Kai analisa 20 trade → bikin review + rekomendasi
                                         ↓
         ┌───────────────┬──────────────────┐
         ↓               ↓                  ↓
   Topic Kai Room    Update prompt    Tuning suggestion
   (bisa di-chat)    tiap agent      (RR, confidence, ADX)
```
         Kai analisa 5 trade → bikin review + rekomendasi
                                         ↓
         ┌───────────────┬──────────────────┐
         ↓               ↓                  ↓
   Topic Kai Room    Update prompt    Tuning suggestion
   (bisa di-chat)    tiap agent      (RR, confidence, ADX)
```

## Files

| File | Purpose |
|------|---------|
| `review_agent.py` | Core engine: trade tracking, LLM call, feedback applier |
| `scripts/kai_cron.py` | Cron wrapper — silent, only prints if review generated |
| `prompts/review/kai_system.txt` | Kai's personality prompt |
| `data/kai_state.json` | Tracks last_review_ticket, total_reviews |
| `logs/kai_reviews/kai_review_*.json` | Review output logs |

## Personality

Kai is: **tegas, berwibawa, santai, perfeksionis, fair**.

- Bahasa Indonesia casual (pakai "gw", "lu", "bro" — tapi ga berlebihan)
- Bicara dengan otoritas, bukan sok tau
- Kasih pujian pas bagus, kritik pas jelek
- Detail-oriented — ga ada yg lolos
- Contoh tone: "Oke bro, technical agent lu kelamaan filter. Setup bagus kelewat terus tuh."

## Trigger & Schedule

- Cron job `e4c557bd3c09` — runs every 30 minutes
- Script: `kai_cron.py` (no_agent=true — script-only, no LLM)
- Checks for **20+** new closed trades since last review
- If not enough trades → silent exit (no Telegram message)
- If enough → runs `review_agent.py` → posts to Kai Room topic

## Review Framework

Every batch of **20 trades**, Kai analyzes:

1. **Per-Trade Verdict** — what went right/wrong for each trade
2. **Pattern Detection** — recurring issues: pair-specific? time-specific?
3. **Agent Performance** — grades each agent A+ to D
4. **Parameter Check** — confidence, RR, risk%, ADX, spread — any need adjustment?
5. **Priority Action** — single most important fix RIGHT NOW
6. **Coach Note** — motivational + warning message for the team

## Output Format

JSON with required fields: `review_id`, `overall_grade`, `trade_analysis[]`, `agent_feedback[]`, `parameter_tuning`, `priority_action`, `coach_note`.

Agent feedback auto-appended to agent prompt files as `<!-- KAI REVIEW NOTE -->` HTML comments.

## Telegram Integration

Kai uses **his own dedicated Telegram bot**, separate from the main reporting bot.

| Bot | Username | Token Env Var | Purpose |
|-----|----------|---------------|---------|
| Main | `@SignalFxNotif_bot` | `TELEGRAM_NOTIFY_BOT_TOKEN` | Trading reports, errors, all non-Kai topics |
| Kai | `@Kaiagentt_bot` | `TELEGRAM_KAI_BOT_TOKEN` | Batch reviews + interactive chat in OwnerRoom |

- Topic key: `kai_room` → env var: `TELEGRAM_TOPIC_KAI_ROOM`
- Topic ID: **6** (shares Owner Room topic in RNT AUTOTRADE group)
- Added to `TOPIC_KEYS` in `telegram_reporter.py`
- Emoji: 🎯
- `send_kai_message()` in `telegram_reporter.py` — sends using Kai's own bot token, falls back to main bot if not set

### Why separate bots?

1. **Personality separation** — Kai posts as `Agent•Kai`, not as `SIGNALNOTIF`. Different name, different avatar, clearer in chat.
2. **Privacy mode can differ** — Kai needs `can_read_all_group_messages: true` for interactive chat; the main bot can keep stricter privacy.
3. **No cross-contamination** — if the main bot's token is rotated or broken, Kai still works.

## Commands

```bash
# Check Kai status (pending trades, reviews done)
python review_agent.py --status

# Force review (even if < 5 trades)
python review_agent.py --force

# Cron wrapper (used by cron job)
python scripts/kai_cron.py
```

## Config (.env)

```
TELEGRAM_TOPIC_KAI_ROOM=6
KAI_REVIEW_INTERVAL_MINUTES=30
KAI_TRADES_PER_REVIEW=20
```

## Dual-Strategy Awareness (2026-07-03)

Kai's system prompt (`prompts/review/kai_system.txt`) was updated to include knowledge of the dual-strategy system:

- **DAY TRADE** [DAY] — timeframe H4→H1→M15, scan 2h, full 5-agent team, RR≥1.8, risk 0.5%
- **SCALP** [SCALP] — timeframe M5, scan 10m from M5 scanner, 2-agent fleet (Risk+Manager), RR≥1.5, risk 0.3%
- Both strategies run on the same MT5 account; orders are tagged with `SCALP` or `DAY` in the comment field
- Scalping = naturally lower win rate but higher frequency; day trade = fewer but larger RR trades

When reviewing trades, Kai checks the MT5 comment field to identify whether a trade came from the day or scalping system before diagnosing performance.

## Pitfalls

- **First review needs 20 trades** (changed from 5, 2026-07-03): Kai won't speak until 20 closed trades accumulate

### Files

| File | Purpose |
|------|---------|
| `kai_interactive.py` | Polls Topic 6 for new messages, responds as Kai via LLM |
| `data/kai_interactive_state.json` | Tracks last seen update_id and message_id |
| `data/kai_chat_history.json` | Last 20 conversation exchanges for context |

### Cron

- Job ID: `0d452db8e3c7`
- Schedule: every 1 minute (minimum cron interval)
- Mode: `no_agent=true` — script runs directly, no LLM agent
- Delivery: `local` — no Telegram delivery (script sends its own replies)

### How It Works

1. Polls Telegram Bot API `getUpdates` for messages with `message_thread_id=6`
2. Filters out bot messages to prevent loops
3. When a new user message is found, constructs Kai's system prompt + current trade context
4. Calls `qwen3.7-max` LLM with conversation history
5. Sends reply to Topic 6 via `sendMessage` with `reply_to_message_id`

### Prerequisites — Bot Privacy Mode MUST Be Disabled

**This is a hard requirement for interactive chat.** By default, bots have `can_read_all_group_messages: false`, meaning they ONLY see commands, mentions, and replies.

For Kai (`@Kaiagentt_bot`) to read free chat in OwnerRoom:
1. Open **@BotFather**
2. `/mybots` → select `@Kaiagentt_bot`
3. **Bot Settings** → **Group Privacy**
4. Select **Disable**

Run `getMe` to verify: `can_read_all_group_messages` should be `true`.

### URL Construction Pitfall

The Telegram `getUpdates` endpoint needs proper query string construction:

```python
# WRONG — produces /getUpdates&timeout=5 when last_update_id is 0 (404 error)
url = f"https://api.telegram.org/bot{token}/getUpdates"
if last_update_id:
    url += f"?offset={last_update_id + 1}"
url += "&timeout=5&limit=20"

# CORRECT — produces /getUpdates?timeout=5 when no offset
url = f"https://api.telegram.org/bot{token}/getUpdates?"
if last_update_id:
    url += f"offset={last_update_id + 1}&"
url += "timeout=5&limit=20"
```

Always include `?` even when no parameters follow — it ensures subsequent `&param` joins are valid.

### Context for LLM

Kai's interactive prompt receives:
- `kai_system.txt` personality prompt
- Current trade context: last decision, health status, recent P/L
- Last 6 conversation exchanges
- The user's new message

This makes Kai aware of system state when chatting.

## Pitfalls

- **Kai shares Owner Room (topic 6)**: No separate "Kai Room" topic needed. The `TELEGRAM_TOPIC_KAI_ROOM` env var points to the same topic 6 as Owner Room. Reviews appear there alongside owner messages.
- **First review needs 5 trades**: Kai won't speak until 5 closed trades accumulate
- **Agent feedback is appended, not replaced**: Kai adds `<!-- KAI REVIEW NOTE -->` to prompt files. Manual cleanup may be needed if notes accumulate.
- **`send_to_topic` uses topic KEY, not ID**: always use `"kai_room"` string, not the numeric thread ID
- **.env editing for topic ID changes**: `.env` is protected from the `patch` tool — use `sed` in terminal. After editing, the shell session may still cache the old env var. Prefix commands with the new value or update the shell snapshot at `cache/terminal/hermes-snap-*.sh`.
- **Cron script path**: Scripts referenced by cron job `script` parameter are resolved from `scripts/` directory. `kai_interactive.py` must live at `scripts/kai_interactive.py`, NOT at the project root. If the cron job reports "Script not found", check the path.
- **Health log JSON Lines format**: `logs/health/health_log.json` uses one-JSON-object-per-line (JSON Lines), NOT a JSON array. Reading it with `json.load()` fails with "Extra data" error. Use `json.loads(lines[-1].strip())` for the last entry, or `json.loads(line)` per line.
- **Hermes hijacking Kai's topic**: When Hermes (Duleh) is registered to listen to Topic 6 in `channel_directory.json`, it responds to user messages there instead of Kai. Two fixes: (1) user sends `/mute` in Topic 6 to tell Hermes to stop, or (2) remove `-1004396608984:6` from `channel_directory.json` and restart gateway. The `/mute` command is faster and doesn't require restart.
- **Cron delivery target stale**: When changing the topic ID (from 157 to 6), BOTH the .env file AND the cron job delivery target must be updated. `cronjob action=update job_id=<id> deliver=telegram:-1004396608984:6`. Otherwise the batch review cron still delivers to the old topic.
- **Cron no_agent=true spams chat with status prints**: When a no_agent=true cron job runs a script, ALL stdout is delivered to Telegram. A script that prints status every 30 minutes will spam the chat. Two fixes: (a) remove ALL print statements from the skip path, (b) set deliver=local so even if output leaks, it stays local. The script itself calls send_kai_message() only when there is an actual review to post.
- **Interactive reply silently fails**: Kai send_reply() can fail (network, rate limit) without the caller checking. The state file updates as handled, but no reply reaches Telegram. Symptoms: user sees no response, kai_chat_history.json shows a generated reply, but getUpdates confirms no bot message. Fix: reset last_message_id in data/kai_interactive_state.json to force re-processing, or manually send the cached reply.
- **Hermes hijacking Kai topic**: When Hermes (Duleh) is registered in channel_directory.json for Topic 6, it responds instead of Kai. Fix: remove the -1004396608984:6 entry from channel_directory.json. After this, OwnerRoom is Kai-only; Duleh responds only in DM and other topics.

## Kai Approval → Learning Log Flow (Topic 156)

When Kai posts a batch review with tuning suggestions, the user can approve it in OwnerRoom. Approval triggers auto-logging to the LEARNING topic (156).

### How it works

1. Kai posts review in OwnerRoom (Topic 6) — includes agent grades + parameter tuning suggestions
2. User replies with approval keyword: `setujui`, `gas`, `ok set`, `approve`, `jalan`, `lanjut`, `apply`, `terapkan`
3. `kai_interactive.py` detects the keyword → loads latest `logs/kai_reviews/kai_review_*.json`
4. Formats a learning log: grade, P/L, WR, agent scores, applied tuning changes
5. Sends to Topic 156 via Kai's bot: `send_kai_message("learning", ...)`
6. Kai replies in OwnerRoom: "✅ Siap bro! Tuning udah gw catat di learning log (Topic 156)."

### Config

- `TELEGRAM_TOPIC_LEARNING=156` in .env
- `"learning": "TELEGRAM_TOPIC_LEARNING"` added to TOPIC_KEYS in telegram_reporter.py
- Approval keywords are hardcoded in `kai_interactive.py` — edit the `is_approval` check to add/remove triggers

## SL Strategy: H1 Structure-Based (Not Arbitrary Pips)

Kai's review evaluates whether SL placement makes sense given the H1 structure. The trading system enforces:

**Rule:** SL MUST be placed at the nearest H1 swing low (for buys) or swing high (for sells), plus an ATR buffer. NEVER use arbitrary pip numbers.

**Agent prompt enforcement (Technical + Risk agents):**
- Technical agent: `SL/TP wajib berdasarkan struktur H1: SL di bawah/atas swing low/high H1 terdekat + buffer ATR, TP di resistance/support H1 berikutnya. Jangan SL/TP arbitrary.`
- Risk agent: `Hard reject: SL/TP tidak logis atau tidak berdasarkan struktur H1 (SL harus di swing low/high H1, bukan arbitrary).`

**Executor enforcement (hard safety net):**
- Forex: min 20 pips | JPY: min 30 pips | XAUUSD: min $10 (100 pips)
- Checked in `trade_executor_demo.py` before entry validation
- This is a FLOOR, not a target — SL should be wider based on H1 ATR

**Why this matters for Kai's review:**
When Kai grades agents, a tight SL that respects H1 structure is fine. A loose SL that ignores structure is bad, even if it's wide. Kai should check: does the SL sit below/above a valid H1 swing point with an ATR buffer?

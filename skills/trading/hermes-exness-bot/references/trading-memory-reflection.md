# Trading Memory & Reflection System

## Overview

Persistent store of every trade decision with full agent context, lesson tracking, and automated performance reflection. Added 2026-07-04.

Three components:
1. **Trading Memory** (`trading_memory.py` + `trading_memory.json`) — records every pipeline decision (entry AND skip) with all agent summaries
2. **Memory Injection** — before each pipeline run, loads memory context into ALL agent prompts
3. **Reflection Agent** — after every 5 closed trades, reviews last 10 trades and posts analysis to Manager topic (974)

## File Structure

| File | Purpose |
|------|---------|
| `trading_memory.py` | Module: load/save, add_trade, sync, reflect, get_memory_context |
| `trading_memory.json` | Persistent JSON: trades array, stats, lessons, last_reflection |

## JSON Structure (`trading_memory.json`)

```json
{
  "trades": [
    {
      "id": 1,
      "timestamp": "2026-07-04T14:30:00+07:00",
      "wib": "2026-07-04 14:30 WIB",
      "mode": "day",
      "symbol": "EURUSDm",
      "decision": "entry",
      "side": "buy",
      "entry_price": 1.14500,
      "sl": 1.14400,
      "tp": 1.14800,
      "rr": 2.0,
      "confidence": 85,
      "rationale": "...",
      "ticket": "12345678",
      "outcome": "pending|win|loss|skip",
      "pnl": null,
      "exit_price": null,
      "exit_reason": null,
      "closed_at": null,
      "analysis_summary": {
        "bull": "...",
        "bear": "...",
        "risk": "..."
      }
    }
  ],
  "stats": {
    "total_trades": 0,
    "wins": 0, "losses": 0, "pending": 0, "skips": 0,
    "win_rate": 0.0,
    "avg_rr": 0.0,
    "current_streak": "none",
    "best_pair": null, "worst_pair": null,
    "consecutive_losses": 0, "consecutive_wins": 0,
    "total_pnl": 0.0
  },
  "lessons": [...],
  "last_reflection": {
    "timestamp": "...",
    "wib": "...",
    "text": "...",
    "trade_ids": [1,2,3,4,5],
    "trade_range": "#1 - #5"
  },
  "last_reflection_trade_id": 5,
  "last_reflection_wib": "2026-07-04 15:00 WIB"
}
```

## Pipeline Integration

### Pre-Pipeline (memory injection)
`run_pipeline()` in `agent_swarm.py`:
1. Load `trading_memory.json`
2. Call `get_memory_context(memory, pair=symbol)` → generates string with:
   - Win rate, avg RR, streak, total PnL
   - Best/worst pair performance
   - Last 3 active lessons (if any)
   - Last 3 trades on THIS pair (if ≥ 2 exist)
   - Last reflection summary (30-char snippet)
3. Inject into ALL agent contexts:
   - `agent_context` → Technical, Fundamental, Sentiment (DAY mode) and Risk (both modes)
   - `debate_context` → Bull & Bear researchers
   - `mgr_context` → Manager

### Post-Pipeline (memory save)
After Manager decision + execution:
1. Call `add_trade(memory, parsed_decision)` — saves decision with bull/bear/risk summaries
2. Call `sync_closed_positions(memory)` — checks MT5 history for today's closed deals, matches by position_id, updates win/loss/pnl
3. Call `reflect(memory)` — auto-checks if ≥ 5 new closed trades since last reflection; if yes, runs review

### Reflection Trigger
- **Auto:** Every 5 closed trades (config: `REFLECTION_EVERY_N = 5` in `trading_memory.py`)
- **Manual:** `python trading_memory.py --reflect`
- **Minimum:** Needs ≥ 3 closed trades before first reflection
- **Model:** deepseek-v4-flash (uses Manager API key)
- **Delivery:** Posted to Manager topic (974) as 🪞 **Trading Reflection**

### Reflection Output
Reflection agent reviews last 10 closed trades and produces:
1. **Performa Ringkasan** — win rate, avg RR, profit factor
2. **Pola yang Terdeteksi** — what works, what fails
3. **Weakness** — recurring mistakes, biased agents, strategy flaws
4. **Strength** — what's good, keep doing it
5. **Lessons Learned** — 2-3 specific lessons (auto-extracted & saved)
6. **Agent Assessment** — which agents are accurate vs misleading
7. **Recommendation** — actionable concrete changes

Lessons are auto-extracted from reflection text (lines with "pelajar"/"lesson"/"ke depannya"/"jangan"/"harus"/"hindari") and saved to `lessons[]` array (max 20 active). Deduplicated by prefix match.

### Sync (`sync_closed_positions`)
Called after every pipeline run. Connects to MT5, fetches today's closed deals (type 1=close buy, 2=close sell), matches by `position_id` → pending trade's `ticket` field. Updates outcome to "win"/"loss" with real PnL and exit price.

## CLI Usage

```bash
# Summary
python trading_memory.py

# Force reflection (even if < 5 new trades)
python trading_memory.py --reflect

# Sync closed positions from MT5
python trading_memory.py --sync

# Full: sync + reflect
python trading_memory.py --sync --reflect
```

## Future Enhancements (not implemented)

- **Position-close webhook**: MT5 EA that pushes close events so reflection fires immediately instead of polling
- **Pair-specific win rate injection**: Give agents per-pair historical accuracy rates
- **Agent accuracy leaderboard**: Track which agent's recommendations correlate with wins/losses

# Kai Interaction Patterns

## Manual Trigger

When Kai doesn't respond to messages in OwnerRoom (Topic 6), the 1-minute cron poller (`0d452db8e3c7`) may have stale state or Telegram privacy mode blocking. Force-catch all pending messages:

```bash
cd ~/AppData/Local/hermes && python scripts/kai_interactive.py
```

This runs the poller synchronously and prints `[Kai] New message: ...` + `[Kai] Replied OK (N chars)` for each message processed.

**Checklist when Kai is silent:**
1. Run manual poller first — catches most cases
2. Check cron status: `cronjob action=list` → look for "Kai Interactive Poller" — `last_status: ok` and `enabled: true`
3. Check Kai's bot privacy mode — must have `can_read_all_group_messages: true` (set via @BotFather)
4. Check that messages are in Thread 6 (OwnerRoom). Kai filters by `message_thread_id == "6"` — messages in other threads are invisible.

## Log Delivery Pattern

Kai cannot access backend logs directly. He reads ONLY what appears in the OwnerRoom chat (Thread 6). The assistant (Duleh) must serve as the data courier:

1. Duleh reads today's logs from the filesystem (`logs/scheduler/`, `logs/cycles/`, `final_decision.json`)
2. Duleh compiles a formatted summary
3. Duleh posts it directly in the OwnerRoom chat
4. Kai reads it on the next poller tick and responds

**What Kai needs (minimum viable log):**
- Total cycles, entries executed, blocked, skipped
- Each entry: symbol, side, entry price, SL, TP, RR, confidence, reason
- Block reasons (safety gate, risk guard, etc.)
- Skip root causes (SL mismatch, ADX gate, no technical candidates)
- Account status: balance, equity, cumulative P/L

## Kai's Tuning Playbook

Kai follows a strict review protocol:
- **NO parameter changes** without ≥5 closed trades (statistical significance)
- Defensive adjustments (risk per trade, pair blacklisting) allowed immediately
- Recommendations are given as specific parameter changes — assistant executes them
- Kai never touches code — he gives instructions, Duleh applies them

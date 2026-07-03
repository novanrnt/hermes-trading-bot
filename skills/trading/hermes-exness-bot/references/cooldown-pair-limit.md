# Pair Cooldown & Max Trades Per Pair

Two new safety gates in `trade_executor_demo.py` (2026-06-20, Kai's defensive recommendations).

## Config (.env)

```
MAX_TRADES_PER_PAIR=1          # Max closed trades per pair per day (0=disabled)
TRADE_COOLDOWN_MINUTES=240     # Lock pair after entry (4 hours, 0=disabled)
ADX_MIN=22                     # H1 ADX minimum (tightened from 25 per Kai tuning)
```

## Cooldown Gate (TRADE_COOLDOWN_MINUTES)

- **State file:** `data/cooldown_state.json` — `{symbol: iso_timestamp}`
- **Functions:** `load_cooldown_state()`, `save_cooldown_state()`, `check_pair_cooldown()`, `record_pair_entry()`
- **Check:** Before executing, check if pair was entered within the last N minutes
- **Record:** After successful execution (`ok=True`), call `record_pair_entry(symbol)` to lock the pair
- **Location:** After position check, before daily risk check in `cmd_execute()`

## Max Trades Per Pair Gate (MAX_TRADES_PER_PAIR)

- **Check:** Count closed trades for this symbol today via MT5 `history_deals_get()` + `DEAL_ENTRY_OUT` deals
- **Location:** After cooldown check, before daily risk check
- **Only active when > 0** (backward compatible)

## Execution Flow (cmd_execute)

```
1. MT5 init
2. Account check (demo only)
3. Real blocked
4. Session check
5. Load final_decision.json
6. Safety gate
7. Symbol validation + RR/confidence
8. Position check (max open + same symbol)
9. [NEW] Cooldown gate ← TRADE_COOLDOWN_MINUTES
10. [NEW] Max trades per pair gate ← MAX_TRADES_PER_PAIR
11. Daily risk
12. Drawdown
13. Spread
14. Entry validation
15. Lot calculation
16. Execute → [NEW] record_pair_entry() if OK
```

## Pitfalls

- **Cooldown state file persists across sessions** — a pair locked at 22:00 WIB will still be locked at 07:00 next day if within 4 hours. Manual clear: delete `data/cooldown_state.json`
- **MAX_TRADES_PER_PAIR counts closed trades** — open positions don't count against the limit. Once TP/SL hits and deal closes, it counts.
- **Both gates are optional** — set to 0 to disable. Backward compatible.

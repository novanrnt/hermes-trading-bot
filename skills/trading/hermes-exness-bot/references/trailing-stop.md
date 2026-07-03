# Adaptive Trailing Stop — Architecture

ATR-based trailing stop that adapts per pair. Silent cron-based execution.

## How It Works

```
Every 5 min: trail_check.py → trailing_manager.py.main_silent()
  → MT5.positions_get()
  → For each position:
      1. Get M15 ATR from last 14 candles
      2. trail_distance = max(ATR × 1.5, min_distance)
      3. If position in profit AND new SL better than current SL:
         → MT5.order_send(TRADE_ACTION_SLTP) with new SL
  → If SL updated → print summary (cron delivers to LEARNING topic)
  → If nothing → print nothing (cron stays silent)
```

## Key Files

- `trailing_manager.py` — Core logic: ATR calc, trail distance, SL modification
- `scripts/trail_check.py` — Cron wrapper: imports from trailing_manager, calls main_silent()
- `logs/trailing/trail_*.json` — Detailed logs per check

## Trail Distance Formula

Trail distance = M15_ATR × 2.0 (pure ATR-based, no forced minimum). Fallbacks only apply when ATR is unavailable.

| Symbol Type | Fallback (ATR unavailable) | Example (ATR=0.0010) |
|-------------|---------------------------|----------------------|
| XAU | $2.00 | ATR × 2.0 |
| JPY | 0.15 | ATR × 2.0 |
| Forex | 0.0010 | ATR × 2.0 |

### Why pure ATR (no min_distance)?
Hardcoded minimum distances (e.g., 5 pips) were too tight for low-volatility pairs — positions got stopped by trailing before reaching TP. Pure ATR lets market volatility determine trail distance. Multiplier 2.0× (up from 1.5×) provides breathing room against wicks.

## Activation

Trailing activates when position profit ≥ 50% of risk amount (`activation_pct: 0.5`). The SL only moves forward (never backward). If the proposed new SL is worse than current SL, the position is skipped.

## Cron Integration

- **Job ID:** `b8bcbdbbd91d`
- **Schedule:** every 5 minutes
- **Mode:** `no_agent=true` — runs script directly, no LLM tokens
- **Script:** `trail_check.py` (must be in `~/AppData/Local/hermes/scripts/`)
- **Delivery:** `telegram:-1004396608984:156` (LEARNING topic)
- **Silent:** empty stdout = no message sent

## no_agent Cron Pattern

For ALL recurring script-only checks, use this pattern to save tokens:

```
cronjob(action='create', 
         no_agent=true, 
         script='trail_check.py',
         deliver='telegram:chat_id:thread_id',
         schedule='every 5m')
```

Requirements:
- Script must be placed in `~/AppData/Local/hermes/scripts/` (not elsewhere)
- `no_agent=true` means the script IS the job — the agent doesn't run
- Non-empty stdout → delivered as message to target
- Empty stdout → SILENT (nothing sent)
- Non-zero exit → error alert sent

## Pitfalls

- **ATR calc failure**: If `mt5.copy_rates_from_pos()` fails (no data), falls back to symbol-type defaults (gold $2.00, JPY 0.15, forex 0.0010). These are conservative — wider than typical ATR-based trails — but safe.
- **Trail too tight**: If pairs keep getting stopped early, increase `trail_atr_mult` (currently 2.0). Common values: 2.0 (standard), 2.5 (loose), 3.0 (very loose). Never add hardcoded minimums — they caused premature stops on low-ATR pairs.
- **SL modification limit**: MT5 may reject SLTP modifications if price is too close to current price. The `order_send` retcode is checked — failures are logged but not retried (next 5-min check will retry).
- **pip_value for profit calc**: The `_pip_value()` function uses simplified multipliers (100 for gold, 1000 for JPY, 100000 for forex) for cent accounts. These are approximate — actual pip value depends on account currency and lot size. Used only for logging, not for SL placement.
- **Must be in scripts/**: The cron `script` parameter requires paths relative to `~/.hermes/scripts/`. Absolute paths are rejected. Use a wrapper script that imports from the main codebase.

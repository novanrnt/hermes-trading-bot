# Self-Learning Auto-Tuner

Daily performance analysis + adaptive parameter tuning for the Hermes Exness Bot.

## File
`auto_tuner.py` at `C:\Users\Administrator\AppData\Local\hermes\auto_tuner.py`

## Architecture

```
Daily cron (00:00 WIB Mon-Fri)
  → auto_tuner.py
    → [1] Collect: demo_execution logs + MT5 closed trades
    → [2] Analyze: win rate, per-pair, per-hour, PnL, RR, block reasons
    → [3] Recommend: adaptive tuning based on metrics
    → [4] Apply: update .env parameters (if ≥10 executed trades)
    → Save: perf_db.json snapshot + tuning log
```

## Tunable Parameters

| Parameter | Range | Default | Step |
|-----------|-------|---------|------|
| MIN_CONFIDENCE | 55 – 85 | 70 | ±5 |
| MIN_RR | 1.3 – 2.5 | 1.8 | ±0.1 |
| RISK_PER_TRADE_PERCENT | 0.5 – 2.0 | 1.0 | ±0.1 |

## Tuning Rules

### Win rate < 40% (too many losses — needs ≥10 trades)
- ↑ MIN_CONFIDENCE (+5) — tighten entry criteria
- ↑ MIN_RR (+0.1) — demand better reward ratio

### Win rate > 65% (strong performance — needs ≥10 trades)
- ↓ MIN_CONFIDENCE (-5) — allow more entries

### Too few trades (≥20 cycles, <10 executed)
- ↓ MIN_CONFIDENCE (-5) — loosen up
- ↓ MIN_RR (-0.1) — increase frequency

### Per-pair disaster (all losses on one symbol)
- Flag pair for manual review — does NOT auto-disable

## Minimum Data Threshold
Auto-tuning only activates when **≥10 executed trades** exist. Win rate tuning requires ≥10 executed trades, per-pair analysis requires ≥5 losses on a single pair. Below these thresholds, the tuner collects data and generates recommendations but does not apply changes.

## Cron Job
- **Job ID:** `d0af9b81adbe`
- **Schedule:** `0 0 * * 1-5` (00:00 WIB, Mon-Fri)
- **Deliver to:** Telegram topic 156 (LEARNING) — `telegram:-1004396608984:156`
- **Workdir:** `C:\Users\Administrator\AppData\Local\hermes`

Reason for separate topic: keeps daily tuning reports out of main trading channels, preventing noise.

## Performance DB
- **Path:** `logs/performance/perf_db.json`
- **Structure:** `{trades: [], daily_snapshots: [], tuning_log: []}`
- Daily snapshots accumulate over time for trend analysis

## Manual Run
```bash
cd ~/AppData/Local/hermes
python auto_tuner.py
```
Output shows: collected trade count, metrics, recommendations, and applied changes.

## Pitfalls

### Demo logs missing `status` field are silently dropped
`analyze_demo_logs()` checks `d.get("status", "unknown")` and only recognizes `"executed"` or `"blocked"`. Demo logs created without a `status` field (e.g., manual test entries that only have `action`, `symbol`, `result`) are treated as `"unknown"` and skipped entirely. They won't appear in the per-pair breakdown or any metrics.

**Fix:** When creating manual test entries, include `"status": "executed"` in the JSON.

### Per-pair breakdown only shows pairs with executed or blocked trades
The `compute_metrics()` function builds `per_pair` from executed trades and blocked trades only. Pairs that were scanned but skipped in every cycle (never reaching the demo executor) are completely invisible in the report. When a user asks "why isn't EURUSD showing up?", the answer is: it was part of the skipped cycles — no signal met the entry criteria, so it never reached the demo executor stage.

### Auto-tuner aggregates ALL time, not just today
`analyze_demo_logs()` and `compute_metrics()` read all `demo_exec_*.json` and `cycle_run_*.json` files without any date filter. The "daily" report actually shows cumulative data. Plan: add a date filter based on the cron run timestamp.

## Design Decisions
- Tuning is conservative — only ±1 step per day, never drastic changes
- Per-pair disabling is manual only (no auto-disable to prevent accidentally removing good pairs after a bad streak)
- Risk parameters stay within safe ranges defined in TUNE_RANGES
- All changes logged to perf_db.json.tuning_log for audit trail

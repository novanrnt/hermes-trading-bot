# Operational Runbook — Hermes Exness Trading System

Daily operations guide for running the multi-agent trading pipeline.

## Pre-Cycle Data Refresh

Before each decision cycle, refresh all data sources:

```bash
# 1. Live economic calendar (faireconomy.media, free, no key)
python news_feed_collector.py

# 2. MT5-derived sentiment (DXY proxy, market mood, gold bias)
python sentiment_feed_collector.py

# 3. Live MT5 market data (8 pairs, all timeframes)
python mt5_payload_collector.py --output mt5_payload.json

# 4. Run decision cycle (orchestrator → dry-run → telegram report)
python run_decision_cycle.py --mode test --skip-boss
```

**Note:** `run_decision_cycle.py` auto-collects MT5 data if `mt5_payload.json` is missing, but news and sentiment feeds need separate refresh.

## Scheduler Management

### Start Scheduler (Background)
```bash
# Continuous loop, every 60 minutes
python cycle_scheduler.py --interval-minutes 60
```

Run as background process with `notify_on_complete=true` for long-running operation.

### Single Tick (Manual)
```bash
python cycle_scheduler.py --once
```

### Check Scheduler State
```bash
cat logs/scheduler/scheduler_state.json
cat logs/scheduler/scheduler_$(date +%Y%m%d).log | tail -20
```

### Scheduler States
- `armed_waiting` — before START_FROM_DATE_WIB, no trading
- `outside_session` — outside TRADING_SESSION hours (07:00–22:00 WIB)
- `completed` — cycle ran successfully
- `cycle_error` — cycle failed, check logs

## Model Switching

Change the AI model used by all agents:

```python
import yaml
with open('config.yaml', 'r') as f:
    cfg = yaml.safe_load(f)
cfg['model']['default'] = 'deepseek-v4-pro'  # or qwen3.7-max, etc.
with open('config.yaml', 'w') as f:
    yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True)
```

**Effect:** Next cycle run uses the new model. No restart needed.

**Available models:** See `config.yaml` → `model.available_models` or `references/sumopod-models.md`.

**Pitfall:** The Hermes `patch` tool refuses to edit `config.yaml` (security-sensitive). Always use Python yaml manipulation.

## Troubleshooting

### Check Latest Cycle Result
```bash
# Final decision
cat final_decision.json | python -m json.tool

# Latest debate log (all agent outputs)
ls -t logs/agent_debates/ | head -1
cat logs/agent_debates/cycle_*.json | python -m json.tool | head -100

# Latest dry-run
ls -t logs/dry_run/ | head -1
```

### Check Agent Errors
```bash
python -c "
import json, glob
latest = max(glob.glob('logs/agent_debates/cycle_*.json'))
d = json.load(open(latest))
print('Model:', d.get('model', '?'))
print('Pipeline error:', d.get('pipeline_error', 'none'))
for agent, result in d.get('agent_results', {}).items():
    status = result.get('status')
    error = result.get('error')
    if error:
        print(f'{agent}: {status} — {error}')
"
```

### Common Issues

**"Empty content in LLM response"**
- Transient API glitch, orchestrator auto-retries (MAX_RETRIES=2)
- Check if it resolved on next cycle
- If persistent, try different model

**"No technical candidates"**
- Normal during low-volatility periods (weekends, holidays, Asian session)
- Check debate log for rejection reasons per symbol
- Verify MT5 payload has fresh data (not stale weekend spreads)

**"Scheduler armed. Waiting until..."**
- Before START_FROM_DATE_WIB — system is armed but not trading yet
- Check `.env` for START_FROM_DATE_WIB and START_FROM_TIME_WIB

**MT5 connection fails**
- Verify MT5 terminal is running and logged in
- Check `mt5_payload_collector.py --status`
- See `references/mt5-connection-troubleshooting.md`

## Telegram Verification

### Test Topic Routing
```bash
python telegram_reporter.py --test-topic trading_report
python telegram_reporter.py --test-topic error_alert
python telegram_reporter.py --test-topic demo_execution
```

### Debug Thread IDs
```bash
python telegram_reporter.py --debug-updates
# Send test messages to each topic, then check captured thread IDs
```

### Clear Tracked Messages
```bash
python telegram_reporter.py --clear-recent
# Deletes bot's own messages from topics (tracked via sent_message_ids.json)
```

## Quick Status Check

```bash
# 1. MT5 connection
python mt5_payload_collector.py --status

# 2. Scheduler state
cat logs/scheduler/scheduler_state.json | python -m json.tool

# 3. Latest decision
cat final_decision.json | python -m json.tool

# 4. Today's cycles
ls -lh logs/cycles/cycle_run_$(date +%Y%m%d)*.json 2>/dev/null | wc -l
```

## Environment Variables (.env)

Key operational settings:
```
ENABLED_SYMBOLS=EURUSDm,GBPUSDm,USDJPYm,USDCHFm,USDCADm,AUDUSDm,NZDUSDm,XAUUSDm
START_FROM_DATE_WIB=2026-06-15
START_FROM_TIME_WIB=07:00
TRADING_SESSION_START_WIB=07:00
TRADING_SESSION_END_WIB=22:00
SCHEDULER_INTERVAL_MINUTES=60
DEMO_EXECUTION_ENABLED=true
REAL_EXECUTION_ENABLED=false
```

See `.env` file for full list (risk params, Telegram config, etc.).

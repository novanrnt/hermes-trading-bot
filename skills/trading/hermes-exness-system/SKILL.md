---
name: Hermes Exness Bot V1
description: Complete Hermes Exness trading system — architecture, file map, routing, and operational procedures
---

## Trigger
When working with Hermes Exness Bot V1 — any file updates, troubleshooting, routing, or operational tasks.

## Architecture
```
MT5 live data → mt5_payload_collector.py → mt5_payload.json
  → agent_orchestrator.py (6 agents → Safety Gate) → final_decision.json
  → trade_executor_dryrun.py → trade_executor_demo.py → Telegram report
  → cycle_scheduler.py (armed, runs every 60min)
```

## File Map
All under `C:\Users\Administrator\AppData\Local\hermes`:
- `mt5_payload_collector.py` — reads MT5, 8 symbols with suffix "m"
- `agent_orchestrator.py` — 6-agent pipeline + Safety Gate + env loading
- `run_decision_cycle.py` — master runner
- `trade_executor_dryrun.py` — WOULD EXECUTE / SKIP
- `trade_executor_demo.py` — full validation + demo order (--check / --execute)
- `cycle_scheduler.py` — armed, lock file, 60min interval
- `telegram_reporter.py` — topic routing, send_to_topic(), --debug-updates, --clear-recent
- `economic_calendar_payload.json` — static
- `sentiment_payload.json` — static

## Telegram Topic Routing
Group: RNT AUTOTRADE (-1004396608984)
| Topic | Thread ID |
|-------|-----------|
| Trading Report | 2 |
| Duleh Command | 3 |
| Agent Debate | 4 |
| Error & Alert | 5 |
| Owner Room | 6 |
| Demo Execution | 15 |

## Key Commands
```
python mt5_payload_collector.py --status
python run_decision_cycle.py --mode test
python trade_executor_demo.py --check
python trade_executor_demo.py --execute  # ONLY in trading hours
python cycle_scheduler.py --once
python telegram_reporter.py --debug-updates
python telegram_reporter.py --clear-recent
```

## Rules (NON-NEGOTIABLE)
- REAL EXECUTION OFF TOTAL
- Demo cent only, max 3 positions, 1% risk/trade, 20%/day
- No martingale/grid/averaging/revenge
- Market order only, must have SL + TP
- Lot via mt5.order_calc_profit()
- NEVER print tokens, keys, secrets, .env full

## Account
- Exness-MT5Trial14, 415880976, $10K, 1:1000
- Suffix: "m" (micro), MT5: C:\Program Files\MetaTrader 5

## Model
- SumoPod (ai.sumopod.com/v1), default: deepseek-v4-pro

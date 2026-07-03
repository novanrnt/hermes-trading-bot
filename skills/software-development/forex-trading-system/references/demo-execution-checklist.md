# Demo Cent Execution Checklist

Complete validation sequence for `trade_executor_demo.py --check` / `--execute`.

## Pre-flight

- [ ] MT5 terminal running, logged into Exness demo account
- [ ] `REAL_EXECUTION_ENABLED=false` in .env
- [ ] `DEMO_EXECUTION_ENABLED=true` in .env
- [ ] `ENABLED_SYMBOLS` set with correct broker suffix (check via `mt5.symbols_get()`)
- [ ] `START_FROM_DATE_WIB` + `START_FROM_TIME_WIB` in future or passed
- [ ] `TRADING_SESSION_START_WIB` / `TRADING_SESSION_END_WIB` configured

## Validation Gates (in order)

1. **MT5 Connect** — `_init_mt5()` returns valid handle
2. **Demo Account** — `confirm_demo_account()` server contains demo/trial/cent
3. **Real Lock** — `REAL_EXECUTION_ENABLED` must be false
4. **Session** — `is_trading_session_allowed()` checks WIB time + start date
5. **Decision** — `final_decision.json` has action=entry, safety_gate=passed
6. **Symbol** — `best_symbol` in `ENABLED_SYMBOLS`
7. **RR/Confidence** — `rr >= MIN_RR`, `confidence >= MIN_CONFIDENCE`
8. **Positions** — `< DEMO_MAX_OPEN_POSITIONS`, no duplicate symbol
9. **Daily Risk** — P&L < RISK_PER_DAY_PERCENT, losses < MAX_DAILY_LOSSES, XAU losses < MAX_XAUUSD_DAILY_LOSSES
10. **Spread** — Not abnormal (XAU >200 pts, forex >20 pts → BLOCK)
11. **Entry/SL/TP** — Price deviation within limits, BUY: SL<entry<TP, SELL: SL>entry>TP, actual RR >= MIN_RR
12. **Lot** — `calculate_lot_by_risk()` succeeds, projected loss % within 5% of target

## If ALL pass on --execute

- Market order sent with SL/TP
- Comment: "Hermes v1.2 DEMO CENT"
- Magic: 1206
- Filling: IOC
- Log saved to `logs/demo_execution/`
- Telegram report sent

## Block Scenarios

| Gate | Block Reason Example |
|------|---------------------|
| 2 | "Server 'Exness-MT5Real' is not demo/trial/cent" |
| 3 | "REAL_EXECUTION_ENABLED=true — BLOCKED" |
| 4 | "Scheduler armed. Waiting until 2026-06-15 07:00 WIB." |
| 5 | "Action is 'skip', not 'entry'" |
| 6 | "Symbol 'EURUSD' not in ENABLED_SYMBOLS" |
| 8 | "Max open positions reached (3/3)" |
| 9 | "Daily loss 22.3% >= 20%" |
| 10 | "XAUUSDm spread 320 points (abnormal)" |
| 11 | "Actual RR 1.6 < min 1.8" |
| 12 | "order_calc_profit returned None" |

## Lot Calculation Quick Reference

```
# For BUY EURUSDm with 5-digit pricing
entry = tick.ask                    # actual entry
sl = entry - 0.00216               # ATR M15 × 1.2
tp = entry + (entry - sl) × 2.0    # target RR 2.0

risk_amount = 10000 × 0.01         # $100 on $10K equity
loss_1_lot = order_calc_profit(0, "EURUSDm", 1.0, entry, sl)
# Returns approx -$21.60 (1 lot × 21.6 pips × $1/pip)
lot_raw = 100 / 21.60 = 4.63
lot_final = 4.60 (step 0.01)       # round DOWN
```

## Broker Suffix Reference

| Server | Suffix | Example |
|--------|--------|---------|
| Exness-MT5Trial14 | `m` (micro) | EURUSDm |
| Exness-MT5Real | varies | Check symbols_get() |
| Other trial servers | `m` or `c` | Always verify |

## Scheduler Integration

```
cycle_scheduler.py --once
  → run_decision_cycle.py --mode test
  → reads final_decision.json
  → if entry + stdout contains "WOULD EXECUTE"
    → trade_executor_demo.py --execute
```

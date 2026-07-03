# Monte Carlo Analysis for Hermes Exness Bot

## What It Does
Simulates 10,000 random shuffle sequences of your closed trades to reveal **the range of possible outcomes** — not just what happened, but what COULD have happened.

## Key Metrics

| Metric | Meaning | Target |
|--------|---------|--------|
| Final Equity Range | Best/worst equity after all trades | P95 > $10K (profitable) |
| Max Drawdown (95%) | 95% of runs stay below this DD | ≤15% for safe strategy |
| Ruin Risk | % of runs where equity drops 50%+ | 0% |
| Win/Loss Streak | Max consecutive wins/losses | Loss streak ≤5 for sanity |
| Profit Factor | Gross wins / gross losses | >1.2 for confidence |

## When to Run
- After every 5-10 new closed trades
- After Kai parameter changes (compare before/after)
- When user says "seberapa robust strategi gua?"

## How to Run
```bash
cd C:\Users\Administrator\AppData\Local\hermes
python monte_carlo.py          # Full report
python monte_carlo.py --quick   # One-line summary
```

## Interpreting Results

**✅ ROBUST (ruin <1%, DD <20%):** Strategy can survive bad sequences. Keep running.

**⚠️ OK (ruin <5%, DD <30%):** Moderate risk. Consider lower risk per trade or higher MIN_CONFIDENCE.

**❌ FRAGILE (ruin >5%, DD >30%):** High risk of large drawdowns. Strategy needs improvement — check win rate, position sizing, stop-loss quality.

**🔶 NOT ENOUGH DATA (<20 trades):** Take results with skepticism. Statistical confidence requires 20+ trades.

## Profit Factor vs Ruin Risk
Even an unprofitable strategy (PF <1.0) can have 0% ruin risk if loss sizes are small relative to equity. Conversely, high PF strategies can be fragile with oversized positions. **Low ruin risk + PF <1 = strategy is safe but needs better entries.**

## Integration with Kai
Kai should review Monte Carlo results in each review cycle and flag:
- Rising ruin risk (trend)
- Loss streak exceeding typical P95
- Drawdown approaching daily lock threshold (5%)

## Data Source (MT5 priority)
`load_trades()` reads from **MT5 closed trade history** (`history_deals_get()` from MetaTrader5) for accurate realized PnL, only falls back to `logs/demo_execution/` JSON files when MT5 has <3 trades. The MT5 data provides exact profit/loss per closed position; demo logs may show PnL=0 since they're entry-only records without exit PnL.

## Interpreting Output (11-trade example from 2026-06-30)
On the first run with real MT5 data (11 trades, WR 36%, PF 0.87): final equity per simulation was identical (~$9,939) because Monte Carlo only reorders the PnL sequence — the sum always equals total PnL. What matters is the **drawdown path** — 95% of runs had ≤3.8% max drawdown, 0% ruin risk. **Low DD + PF <1 = safe strategy, needs better entries.**

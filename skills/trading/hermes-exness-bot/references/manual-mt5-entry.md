# Manual MT5 Entry Bypass

When the user wants to execute a trade that was BLOCKED by the orchestrator (auto-tuner raised thresholds, e.g. confidence 82 < min 85), you can manually place a market order via MT5 directly — bypassing the executor's validation chain.

## When to use (must satisfy ALL)
- User explicitly says "entry", "eksekusi", "gas", or similar
- The trade was recently analyzed by the orchestrator (SL/TP structure still valid)
- Current price is close to planned entry (within ~20 pips forex / ~50 pips XAUUSD / ~5 JPY)
- Outside trading hours is OK if user explicitly requests

## Step-by-step

### 1. Verify current price vs planned entry
```python
import MetaTrader5 as mt5
mt5.initialize()
tick = mt5.symbol_info_tick('USDJPYm')
# For BUY: use tick.ask; for SELL: use tick.bid
print(f'Planned: 161.582, Current Ask: {tick.ask}')
```

### 2. Recalculate SL/TP from current price (keep original SL/TP distances)
```python
# Keep the original SL and TP distances from the blocked decision
sl_dist = abs(planned_entry - planned_sl)  # e.g. 0.343 for USDJPY
tp_dist = abs(planned_tp - planned_entry)  # e.g. 0.685
entry = tick.ask  # current market ask
sl = entry - sl_dist
tp = entry + tp_dist
# Verify RR still >= 1.8
rr = (tp - entry) / (entry - sl)
```

### 3. Validate minimum SL
```python
# Ensure SL meets minimum per pair category
MIN_SL = {'XAUUSD': 1.00, 'JPY': 0.25, 'default': 0.0018}  # price distance
pair_type = 'JPY' if 'JPY' in symbol else 'XAU' if 'XAU' in symbol else 'default'
if (entry - sl) < MIN_SL[pair_type]:
    raise ValueError(f'SL too tight')
```

### 4. Calculate lot size from risk
```python
risk_amount = balance * (RISK_PER_TRADE_PERCENT / 100)
symbol_info = mt5.symbol_info(symbol)
tick_value = symbol_info.trade_tick_value
tick_size = symbol_info.trade_tick_size
sl_ticks = (entry - sl) / tick_size
lot = risk_amount / (sl_ticks * tick_value)
lot = round(lot, 2)
if lot < 0.01:
    lot = 0.01
```

### 5. Send market order
```python
request = {
    'action': mt5.TRADE_ACTION_DEAL,
    'symbol': symbol,
    'volume': lot,
    'type': mt5.ORDER_TYPE_BUY,  # or ORDER_TYPE_SELL
    'price': entry,
    'sl': sl,
    'tp': tp,
    'deviation': 30,
    'magic': 999,
    'comment': 'Manual entry Duleh',
    'type_time': mt5.ORDER_TIME_GTC,
    'type_filling': mt5.ORDER_FILLING_IOC,
}
result = mt5.order_send(request)
# retcode 10009 = TRADE_RETCODE_DONE
```

### 6. Report to user
```python
# Success: Done bro! USDJPY BUY 0.23 lot @ 161.509 / SL 161.166 / TP 162.194 / RR 2.0
# Failure: show retcode and comment: result.comment
```

## Pitfalls
- **Don't skip SL/TP recalculation**: Always recalculate from current price, don't hardcode the planned entry
- **Verify ask vs bid**: BUY uses ask, SELL uses bid for current price
- **RR might drift slightly**: Slight price change can shift RR from 2.0 to 1.98 — acceptable if still above MIN_RR
- **Cooldown NOT enforced**: Manual entry bypasses the pair cooldown gate (240 min). Remind user if they just entered same pair
- **Max position check**: Still enforce manually — check `len(mt5.positions_get()) < max_open_positions`
- **No dashboard log**: Manual entry via MT5 direct doesn't create dry_run/ or demo_execution/ logs automatically. Dashboard will pick it up from MT5 history on next refresh
- **`.env` values still apply**: Uses RISK_PER_TRADE_PERCENT, not the executor's full validation chain
- **Comment truncated**: MT5 comment field max ~27 chars — "Manual entry Duleh" becomes "Manual entry Dul"

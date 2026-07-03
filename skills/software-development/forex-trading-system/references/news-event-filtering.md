# News Event Filtering — Implementation Reference

## Overview

Economic calendar events are classified into two tiers:
- **Big news** — Truly market-moving events that block currency pairs
- **Regular high-impact** — Important but not pair-blocking (press conferences, statements, etc.)

## Classification Keywords

Events are classified by matching their title against `BIG_NEWS_KEYWORDS`:

| Category | Keywords | Blocks? |
|----------|----------|---------|
| Central bank rates | "federal funds rate", "cash rate", "policy rate", "official bank rate", "interest rate decision" | ✅ Yes |
| FOMC | "fomc" | ✅ Yes |
| Inflation | "cpi", "consumer price index" | ✅ Yes |
| GDP | "gdp", "gross domestic product" | ✅ Yes |
| Employment | "non-farm payroll", "nonfarm payroll", "nfp", "employment change", "unemployment rate" | ✅ Yes |
| Central bank specific | "boj policy rate", "ecb interest rate", "snb policy rate", "monetary policy assessment" | ✅ Yes |
| Press conferences | "press conference", "statement", "monetary policy statement" | ❌ No |
| Secondary data | "claimant count", "retail sales", "pmi", "housing starts" | ❌ No |

## Time Window

Blocking is active ±2 hours (7200 seconds) from the event time. This prevents:
- Blocking pairs for events 3+ days away
- Missing blocks for events that just happened (post-event volatility)

## Example: FOMC Week

| Event | Time (UTC) | big_news | Blocks? |
|-------|------------|----------|---------|
| JPY BOJ Policy Rate | Mon 22:30 | true | ✅ JPY blocked 20:30-00:30 |
| AUD RBA Press Conference | Tue 01:30 | false | ❌ No block |
| GBP CPI y/y | Wed 02:00 | true | ✅ GBP blocked 00:00-04:00 |
| USD Federal Funds Rate | Wed 14:00 | true | ✅ USD blocked 12:00-16:00 |
| USD FOMC Press Conference | Wed 14:30 | false | ❌ No block |
| NZD GDP q/q | Wed 18:45 | true | ✅ NZD blocked 16:45-20:45 |

## Files Modified

1. `news_feed_collector.py` — adds `big_news` flag to each event
2. `agent_orchestrator.py` → `load_economic_calendar()` — filters by big_news + time window
3. `telegram_reporter.py` → `_load_news_payload()` — same filtering (must stay in sync!)

## Testing

```bash
# Verify classification
cd ~/AppData/Local/hermes
python -c "
import json
d=json.load(open('economic_calendar_payload.json'))
big = [e for e in d['events'] if e.get('big_news')]
small = [e for e in d['events'] if e.get('impact')=='high' and not e.get('big_news')]
print(f'Big news (blocks): {len(big)}')
for e in big: print(f'  BLOCKED: {e[\"currency\"]:4s} | {e[\"event\"]}')
print(f'Regular high (no block): {len(small)}')
for e in small: print(f'  PASS: {e[\"currency\"]:4s} | {e[\"event\"]}')
"

# Verify time window filtering
python -c "
from telegram_reporter import _load_news_payload
d = _load_news_payload()
print('Blocked currencies:', d.get('_blocked_currencies', []))
print('High impact nearby:', d.get('_high_impact_nearby', False))
"
```

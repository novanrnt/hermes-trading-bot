# Bot Health Check — Architecture & Performance

## Components Checked (5)

| Component | Method | Expensive? | Cache TTL |
|-----------|--------|------------|-----------|
| Scheduler | WMIC subprocess | Yes (1-2s) | 5 min |
| MT5 | `mt5.initialize()` + `account_info()` | Yes (2-5s) | 5 min or reuse |
| Payload | `os.path.getmtime()` | No | Fresh every 60s |
| Last Cycle | Newest file in `logs/cycles/` | No | Fresh every 60s |
| RAM | `ctypes.windll.kernel32.GlobalMemoryStatusEx` | No | Fresh every 60s |

## Performance: Why Caching is MANDATORY

Without caching, every dashboard refresh (60s) does:
1. WMIC subprocess (1-2s) 
2. MT5 init (2-5s, and dashboard ALSO does MT5 init in `collect_data()`)
Total: 3-7s BLOCKING per HTTP request → dashboard becomes unusable.

**Fix architecture:**
```python
# 1. Module-level cache dict
_cache = {"scheduler": None, "mt5": None, "last_full": 0}
CACHE_TTL = 300  # 5 minutes

# 2. collect_health() accepts mt5_account from dashboard
def collect_health(mt5_account=None):
    if mt5_account:
        # Reuse dashboard's already-open MT5 connection
        health["mt5"] = {...from mt5_account...}
    elif cache_valid:
        health["mt5"] = _cache["mt5"]
    else:
        health["mt5"] = check_mt5()  # expensive, only every 5 min
```

## Session Awareness

Payload and last_cycle checks MUST be session-aware to avoid false warnings during sleep hours (00:00-07:00 WIB):

```python
def is_trading_session_now():
    from datetime import time as dt_time
    current = dt_time(now.hour, now.minute)
    start = dt_time(7, 0)
    end = dt_time(0, 0)
    if end <= start:
        return current >= start or current < end
    return start <= current < end
```

Outside session: payload stale → "Sleeping" (healthy), last cycle old → "Sleeping" (healthy).
During session: payload >5min stale → warning, no cycle >90min → warning, >2h → critical.

## Midnight-Wrap Bug History

The string-comparison midnight bug (`"04:45" < "00:00"` → False) appeared in THREE files:
1. `cycle_scheduler.py` — `is_trading_hours()`
2. `trade_executor_demo.py` — `is_trading_session_allowed()`
3. `health_check.py` — `is_trading_session_now()` (fixed in this session)

The fix: use `datetime.time` objects, NEVER `strftime("%H:%M")` comparisons.

## .pyc Cache Staleness

When `health_check.py` is patched and the dashboard server is restarted, Python may still serve old bytecode from `__pycache__/`. The `-B` flag prevents writing NEW .pyc files, but does NOT delete existing ones.

**Clean restart recipe:**
```bash
rm -rf __pycache__/health_check*
kill_all_dashboard_servers
python -B server.py &
```

## RAM Thresholds (2GB VPS)

| Status | Threshold | Rationale |
|--------|-----------|-----------|
| 🟢 Healthy | <90% | Normal for Hermes+MT5 on 2GB |
| 🟡 Warning | 90-96% | Elevated, monitor |
| 🔴 Critical | >96% | Risk of swap thrashing |

VPS idle baseline: 85-88%. With Defender disabled: 65-70%.

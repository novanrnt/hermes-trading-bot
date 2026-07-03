# Lightweight Monitoring Dashboard

## Overview

A static HTML + JSON dashboard for monitoring the trading bot on low-memory VPS (2GB RAM). Uses Python's built-in `http.server` (~33MB) instead of Flask (~200MB+).

## Architecture

```
server.py (background thread)
  ├─ collect_data() — reads MT5 + log files every 60s
  ├─ save_data() → static/dashboard_data.json
  └─ HTTPServer on port 5555 serving static/
       ├─ index.html (Chart.js, dark theme, auto-refresh)
       └─ dashboard_data.json (live data endpoint)
```

## Files

| File | Purpose |
|------|---------|
| `dashboard/server.py` | Lightweight http.server version (~33MB RAM). Collects MT5 data, serves static files |
| `dashboard/templates/index.html` | Dashboard HTML (dark theme, Chart.js) |
| `dashboard/static/` | Generated: index.html + dashboard_data.json |

## Starting

```bash
cd ~/AppData/Local/hermes/dashboard
python server.py &
# Output: Dashboard running at http://0.0.0.0:5555
```

Port configurable via `DASHBOARD_PORT` env var.

## Dashboard Sections

1. **Stats Cards** — Balance, Equity, Floating P/L, Win Rate, Total PNL, Free Margin
2. **Charts** — Equity curve (line), PNL by trade (bar)
3. **Open Positions** — live from MT5
4. **Trade History** — 30-day deals from MT5
5. **Bot Decision Log** — from logs/agent_debates/cycle_*.json
6. **Demo Execution Log** — from logs/dry_run/dryrun_*.json

## Data Source

The `collect_data()` function reads from:
- MT5 terminal (account, positions, history)
- `logs/agent_debates/cycle_*.json` (decisions)
- `logs/dry_run/dryrun_*.json` (dry-run — **canonical source for dashboard display**)
- `logs/demo_execution/demo_exec_*.json` (trade executor format — NOT read by dashboard)
- `logs/scheduler/scheduler_state.json` (scheduler state)

Auto-refreshes every 60 seconds. The HTML page also polls `/dashboard_data.json` every 60 seconds.

### Log Format Compatibility

The dashboard normalizes field names from both log formats automatically:

| Dashboard field | `dry_run/` (run_decision_cycle) | `demo_execution/` (trade executor) |
|-----------------|------|------|
| `lot` | `lot_size` | `lot_size` |
| `entry` | `planned_entry` | `entry_price` |
| `sl` | `sl_price` | `sl_price` |
| `tp` | `tp_price` | `tp_price` |
| `action` | `final_action` or `action` | `action` |

**Always write test entries to `dry_run/` for dashboard visibility.** The `demo_execution/` directory is the trade executor's internal format and is NOT consumed by the dashboard.

## Pips Calculation (per Symbol Type)

Pips are calculated per-trade in `collect_data()` and aggregated into `total_pips`. The formula varies by symbol type:

```python
if "XAU" in sym:
    pips = profit / (vol * 10) if vol else 0
elif "JPY" in sym:
    pips = profit / (vol * 10) if vol else 0
else:
    pips = profit / (vol * 10) if vol else 0
```

**Why all three use `vol * 10`:** On Exness demo cent accounts (`Exness-MT5Trial14`), profit is in cents. For all instruments (forex majors, JPY pairs, XAUUSD), 1 pip per micro lot ≈ 10 cents on this account type. Using `profit / vol` (without ×10) produces wildly inflated numbers for XAUUSD — e.g. -29.72 profit ÷ 0.01 vol = -2972 pips (wrong) vs -29.72 ÷ (0.01 × 10) = -297 pips (correct).

**PITFALL:** If this is changed for one symbol type, verify against actual MT5 deal history before committing. A single-character formula difference between gold and forex breaks the total_pips stat card and per-trade pips column.

## Access

- **Local:** http://localhost:5555
- **Remote:** http://<VPS_IP>:5555
- **Firewall:** `netsh advfirewall firewall add rule name="Hermes Dashboard" dir=in action=allow protocol=tcp localport=5555`

## PITFALL: Flask port conflict

If Flask was running on the same port, `kill` the Flask process first. Flask on 5555 intercepts requests and returns 404 for the static JSON file. Check with `netstat -ano | grep ":5555"` and kill all PIDs before starting `server.py`.

## PITFALL: Multiple server instances on same port

On Windows, `kill PID` in MSYS may silently fail. Old processes accumulate on the same port without `SO_REUSEADDR`, resulting in 2-3 instances all listening. The latest instance wins requests; stale instances serve old cached data. Always:

1. List ALL PIDs on port: `netstat -ano | grep ":5555" | grep LISTEN`
2. Kill every one with `taskkill //PID <pid> //F` (double-slash for MSYS)
3. Wait 3s for TIME_WAIT to clear
4. Verify port is clean before starting: `netstat -ano | grep ":5555" | grep LISTEN || echo "clean"`

## PITFALL: Test entries not showing in dashboard

Two common causes:

1. **File sorting**: Old code sorted dryrun files by filename string, not modification time. Files with `_test` suffix (e.g. `dryrun_20260615_152136_test.json`) sorted differently from normal cycle files, hiding them from the 15-entry window. Fixed by sorting with `key=lambda p: p.stat().st_mtime, reverse=True`.

2. **Entry limit too small**: With 51+ dryrun files accumulating, the default 15-entry limit cuts off test entries. Increased to 30 entries in `server.py`. If test entries still don't appear, increase further in the `sorted(...)[:N]` call.

## Design: Glassmorphism Dark Theme

Dashboard uses a **glassmorphism** design system (requested by metski, 2026-06-15). Key elements:

- `backdrop-filter: blur(40px)` on all cards with `background: rgba(255,255,255,0.03)`
- Animated background orbs (large blurred radial gradients with float keyframes)
- Semi-transparent borders (`rgba(255,255,255,0.06)`)
- Hover effects with subtle lift (`translateY(-2px)`) and border brightening
- Stat cards with accent-colored top gradients (green/blue/yellow/purple/red/orange)
- Custom glass badges, frosted section headers, slim scrollbars
- Mobile-responsive (single-column charts below 900px)
- Color palette: `--green: #34d399`, `--red: #f87171`, `--blue: #60a5fa`, `--yellow: #fbbf24`, `--purple: #a78bfa`

**PITFALL:** When redesigning the template in `templates/index.html`, always copy to `static/index.html` afterward: `cp templates/index.html static/index.html`. The server.py copies templates → static on startup via `shutil.copy2()`.

## RAM Usage Comparison

| Approach | RAM | Notes |
|----------|-----|-------|
| Flask | ~200MB | Full framework, overkill for static serving |
| http.server | ~33MB | Built-in, zero dependencies, sufficient |
| Static HTML only | 0MB | No server, but can't auto-refresh data |

# Dashboard Zombie Nuke Procedure

## Problem
Windows http.server (`server.py`) on MSYS/git-bash accumulates zombie processes when killed/restarted repeatedly. Each restart spawns a parent `bash.exe` + child `python.exe` pair. After 5-10 restarts, 10-30+ zombie PIDs pile up holding port 5555. HTTP responses return 000 (connection refused) because only the newest process handles requests while zombies sit idle.

## Symptoms
- Dashboard returns `HTTP 000` / connection refused
- `netstat -ano | grep :5555 | grep LISTENING` shows many PIDs (should be exactly 1)
- `curl http://localhost:5555/` fails
- Task Manager shows dozens of python/bash processes

## Full Kill Procedure (run ALL steps sequentially)

```bash
# 1. Find ALL PIDs on port 5555
netstat -ano | grep ":5555" | grep LISTENING | awk '{print $NF}' | sort -u > /tmp/zombie_pids.txt
echo "Zombie PIDs found:" && cat /tmp/zombie_pids.txt

# 2. Kill EVERY PID using netstat results (not taskkill direct — use shell pipeline)
cat /tmp/zombie_pids.txt | while read pid; do taskkill //F //PID "$pid" 2>/dev/null; done

# 3. Wait for ports to release
sleep 3

# 4. Verify clean
echo "Remaining LISTENING:" && netstat -ano | grep ":5555" | grep LISTENING | wc -l

# 5. Clear Python bytecode cache
rm -rf /c/Users/Administrator/AppData/Local/hermes/dashboard/__pycache__/server*

# 6. Start fresh
cd /c/Users/Administrator/AppData/Local/hermes/dashboard
/c/Users/Administrator/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe -B server.py

# 7. Verify after startup delay
sleep 6 && curl -s -o /dev/null -w "%{http_code}" http://localhost:5555/
```

## Why Regular Kill Fails
MSYS/git-bash interprets double-slash syntax differently than native Windows. `taskkill //PID X //F` often produces ERROR: Invalid argument. The reliable workaround: use `cmd.exe //c` wrapper OR pipe `awk` output through a shell loop that calls `taskkill` with proper quoting.

## Prevention: Watchdog v2 (2026-07-01 rewrite)
The watchdog at `scripts/dashboard_watchdog.py` now handles this automatically:
- Uses `netstat | awk | kill` pipeline instead of wmic parsing (bypasses MSYS quoting bugs)
- Verifies port is truly clear before restart
- Clears __pycache__ before starting
- Has 5-retry loop to handle stubborn ports
- Uses explicit venv python path (not system python)
- Silent when healthy, alerts Topic 5 only on failure
- Cron: `efd4efc383e8` — every 5m, no_agent=true

## Key Files
- `scripts/dashboard_watchdog.py` — automated nuke + restart (v2 rewrite)
- `dashboard/server.py` — the HTTP server itself
- `Cron ID: efd4efc383e8` — watchdog trigger
- Herme-Agent path: `/c/Users/Administrator/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe`

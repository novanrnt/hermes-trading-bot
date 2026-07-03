# Process Management on Windows/MSYS

## Observed Cascading Spawn (2026-06-15)

When `cycle_scheduler.py --interval-minutes 60` starts, it can produce this process tree:

```
cycle_scheduler.py --interval-minutes 60     (loop process, 2 PIDs)
  └─ run_once() called immediately
      └─ run_decision_cycle.py --mode test   (subprocess, 2 PIDs)
          └─ agent_orchestrator.py            (subprocess, 2 PIDs)
```

Total: 6 python processes from 1 scheduler start (each = 2 PIDs on MSYS).

## Orphan Patterns to Kill

| CommandLine contains | Status |
|---|---|
| `cycle_scheduler.py --once` | Orphan one-shot run — kill |
| `cycle_scheduler.py --interval-minutes 60` | KEEP (only 1 instance) |
| `run_decision_cycle.py --mode test` | Orphan child — kill |
| `agent_orchestrator.py` | Orphan child — kill |
| `-c "import cycle_scheduler..."` | Orphan inline call — kill |
| `hermes.exe gateway` | Hermes gateway — NEVER kill |

## Kill Sequence

### Method 1: taskkill double-slash (MSYS native)
```bash
# List all non-gateway python
wmic process where "name='python.exe'" get ProcessId,CommandLine 2>/dev/null | grep -iv "hermes.exe\\|gateway"

# Kill all listed PIDs (MSYS double-slash)
for pid in <PIDS>; do taskkill //PID $pid //F; done
```

### Method 2: cmd.exe wrapper (fallback when Method 1 fails with "Invalid argument")
When `taskkill //PID` fails in git-bash (common with PID-only kills), route through cmd.exe directly:
```bash
# Single kill
cmd.exe //c "taskkill /PID 3524 /F"

# Multiple kills in one call (avoids ERROR on already-gone PIDs)
cmd.exe //c "taskkill /PID 3524 /F & taskkill /PID 3440 /F & taskkill /PID 7624 /F"
```
This bypasses git-bash's argument transformation entirely. Use single-slash `/PID` inside the cmd.exe quotes (not double-slash — you're in cmd now, not bash).
# Verify only gateway remains
tasklist | grep -i python
# Expected: exactly 2 lines (gateway)
```

## Restart and Verify

```bash
# Start
cd /c/Users/Administrator/AppData/Local/hermes
/c/Users/Administrator/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe cycle_scheduler.py --interval-minutes 60

# Wait 5 sec, then verify
wmic process where "name='python.exe'" get ProcessId,CommandLine 2>/dev/null | grep -i "cycle_scheduler\|run_decision"
# Expected: 2 lines (cycle_scheduler.py --interval-minutes 60), 2 PIDs
# NOT expected: --once, run_decision_cycle, agent_orchestrator
```

## Lock File Behavior

`cycle.lock` prevents concurrent `run_once()` execution but does NOT prevent duplicate instances from existing. Each instance sleeps, wakes, tries lock, fails or succeeds. With N instances, effective interval becomes ~60/N minutes during active session.

Lock file location: `C:\Users\Administrator\AppData\Local\hermes\cycle.lock`
Stale threshold: 2 hours (auto-removed).

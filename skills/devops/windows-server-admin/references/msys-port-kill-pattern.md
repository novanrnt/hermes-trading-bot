# MSYS Port-Based Process Kill Pattern

On Windows/MSYS (git-bash), `taskkill /PID <pid> /F` often fails silently because single-slash is interpreted as a path. The solution: use `netstat` + `taskkill` with MSYS double-slash syntax.

## Pattern: Kill ALL processes on a port

```bash
netstat -ano | grep ":PORT" | grep LISTENING | awk '{print $NF}' | sort -u | while read pid; do taskkill //F //PID "$pid" 2>/dev/null; done
```

Replace `PORT` with the actual port number. This:
1. Finds all PIDs listening on the port
2. Kills each one using MSYS-safe double-slash syntax
3. Works even when 10+ zombie processes have accumulated

## Verify port is clear

```bash
sleep 2 && netstat -ano | grep ":PORT" | grep LISTENING | wc -l
```

Should output `0`. If not, repeat the kill loop.

## Why single-slash fails

In git-bash (MSYS), `taskkill /PID X /F` passes the literal string `/PID X /F` which `taskkill.exe` interprets differently than in cmd.exe. MSYS attempts to convert paths, but fails on args that look like flags. Double-slash `//PID` bypasses this by making it a path-safe string that MSYS doesn't convert.

## Alternative: cmd.exe wrapper

When double-slash still fails:

```bash
cmd.exe //c "for /f "tokens=5" %a in ('netstat -ano ^| findstr ":PORT"') do @taskkill /F /PID %a"
```

This delegates to Windows native cmd.exe, bypassing MSYS entirely. Note: escaping quotes inside the cmd.exe string is fragile — prefer the awk pipe pattern above.

## Python subprocess (for watchdog scripts)

In Python, use `subprocess.run` with `shell=True`:

```python
import subprocess, os
# Kill all on port
os.system(f'netstat -ano | grep ":PORT" | grep LISTENING | awk "{{print $NF}}" | sort -u | while read pid; do taskkill //F //PID "$pid"; done')
```

Or use the cmd.exe approach from Python:

```python
subprocess.run(
    ['cmd.exe', '/c', 'for /f "tokens=5" %a in (\'netstat -ano ^| findstr ":5555.*LISTENING"\') do @taskkill /F /PID %a'],
    capture_output=True, timeout=10
)
```

## When to use this pattern

- Dashboard servers that stack zombie processes on restart (common with `http.server` in background)
- Any long-lived Python server where `terminal(background=true)` leaves orphaned processes
- After VPS reboot where previous server instances survived in a broken state

## Verification

After kill loop, always verify:
1. Port is clear: `netstat -ano | grep ":PORT" | wc -l` → `0`
2. No orphan python processes: `ps aux | grep -c "server.py"` → `0` (or 1 if you restarted)
3. New instance responds: `curl -s -o /dev/null -w "%{http_code}" http://localhost:PORT/` → `200`

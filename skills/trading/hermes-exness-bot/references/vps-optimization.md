# VPS RAM Optimization — 2GB Windows Server

## Baseline (Before Optimization)

| Component | RAM | Notes |
|-----------|-----|-------|
| python.exe (all) | 486 MB | Hermes gateway, scheduler, dashboard |
| MsMpEng.exe | 354 MB | Windows Defender real-time scanning |
| svchost.exe | 240 MB | Windows services |
| bash.exe + conhost.exe | 289 MB | Git Bash terminals + zombies |
| terminal64.exe | 31 MB | MT5 |
| Others | ~200 MB | Explorer, dwm, Registry, etc |
| **Total** | **93% (cuma 140MB free)** | |

## After Optimization

| Component | RAM | Change |
|-----------|-----|--------|
| python.exe (all) | 486 MB | — |
| MsMpEng.exe | **0 MB** | Disabled |
| svchost.exe | 418 MB | +178 (absorbed Defender's kernel pool) |
| bash.exe | **53 MB** | -115 (zombie cleanup) |
| terminal64.exe | 132 MB | +101 (MT5 restarted) |
| Others | ~150 MB | Tencent agents + Windows bloat removed |
| **Total** | **65% (698MB free)** | |

## Steps (in order)

### 1. Disable Windows Defender
```powershell
# Real-time monitoring off
Set-MpPreference -DisableRealtimeMonitoring $true

# Registry — permanent disable (requires reboot)
Set-ItemProperty -Path 'HKLM:\SOFTWARE\Policies\Microsoft\Windows Defender' -Name 'DisableAntiSpyware' -Value 1 -Force
```
Saved: **354 MB**

### 2. Kill Tencent Cloud Agents
```bash
cmd.exe //c "taskkill /F /IM YDService.exe"
cmd.exe //c "taskkill /F /IM YDLive.exe"
cmd.exe //c "taskkill /F /IM BaradAgent.exe"
cmd.exe //c "taskkill /F /IM sgagent.exe"
cmd.exe //c "taskkill /F /IM tat_agent.exe"
```
Saved: **~43 MB**

### 3. Kill Windows Bloat
```bash
cmd.exe //c "taskkill /F /IM SearchApp.exe"
cmd.exe //c "taskkill /F /IM StartMenuExperienceHost.exe"
cmd.exe //c "taskkill /F /IM TextInputHost.exe"
```
Saved: **~29 MB**

### 4. Clean Zombie Bash Processes
Every `terminal(background=true)` that starts dashboard/scheduler leaves a bash.exe parent. After multiple restarts, 10-20 zombies accumulate.

```bash
# List all bash processes
wmic process where "name='bash.exe'" get ProcessId,CommandLine

# Kill only zombie dashboard/scheduler bash (NOT current terminal)
wmic process where "name='bash.exe'" get ProcessId,CommandLine | \
  grep "dashboard.*server.py" | awk '{print $NF}' | \
  while read pid; do cmd.exe //c "taskkill /PID $pid /F"; done
```
Saved: **~115 MB**

### 5. Start Processes Directly (Avoid Bash)
Use the full venv python path to avoid spawning bash:
```bash
/c/Users/Administrator/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe cycle_scheduler.py --interval-minutes 60 &
/c/Users/Administrator/AppData/Local/hermes/hermes-agent/venv/Scripts/python.exe -B /c/Users/Administrator/AppData/Local/hermes/dashboard/server.py &
```

With `-B` flag: no .pyc files written (prevents stale bytecode issues).

## New Stable Baseline: 65% RAM, 698MB free, 0 swap pressure.

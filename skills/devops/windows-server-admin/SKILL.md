---
name: windows-server-admin
description: Check and manage Windows Server health from MSYS/Git Bash — CPU, RAM, disk, processes, services via wmic/powershell-compatible commands.
tags: [windows, vps, server, health-check, wmic, devops]
triggers:
  - "check vps or check server when the host is Windows"
  - "system status or resource usage on Windows"
  - "CPU/RAM/disk/process info on a Windows machine"
---

# Windows Server Administration (from MSYS/Git Bash)

On Windows hosts where the terminal runs through Git Bash (MSYS), standard Linux tools (`top`, `free`, `uptime`, `lscpu`, `df`) are often missing or unreliable. Use `wmic` and PowerShell-compatible commands instead.

## Quick Health Check

**Reusable script:** `scripts/health-check.sh` — run it directly for an instant overview.

Or run the inline version below in a single terminal call:

```bash
echo "=== OS ===" && systeminfo 2>/dev/null | grep -E "Host Name|OS Name|OS Version|System Boot Time" && \
echo -e "\n=== CPU ===" && wmic cpu get Name,NumberOfCores,NumberOfLogicalProcessors /format:list 2>/dev/null | grep -v "^$" && \
echo -e "\n=== MEMORY ===" && wmic OS get FreePhysicalMemory,TotalVisibleMemorySize /format:list 2>/dev/null | grep -v "^$" && \
echo -e "\n=== DISK ===" && wmic logicaldisk get Size,FreeSpace,DeviceID /format:list 2>/dev/null | grep -v "^$"
```

### Memory math
`wmic` returns values in **KB**. Convert:
- `TotalVisibleMemorySize` / 1024 / 1024 = GB total
- `FreePhysicalMemory` / 1024 / 1024 = GB free
- Free % = `FreePhysicalMemory / TotalVisibleMemorySize * 100`

### Disk math
`wmic` returns values in **bytes**. Convert:
- Size / 1024 / 1024 / 1024 = GB total
- FreeSpace / 1024 / 1024 / 1024 = GB free

## Common Commands

| Task | Command |
|------|---------|
| CPU info | `wmic cpu get Name,NumberOfCores,NumberOfLogicalProcessors /format:list` |
| RAM info | `wmic OS get FreePhysicalMemory,TotalVisibleMemorySize /format:list` |
| Disk space | `wmic logicaldisk get Size,FreeSpace,DeviceID /format:list` |
| OS info | `systeminfo \| grep -E "Host Name\|OS Name\|OS Version"` |
| Running processes (top by mem) | `tasklist /FI "MEMUSAGE gt 100000" /FO TABLE` |
| Specific process | `tasklist /FI "IMAGENAME eq python.exe" /FO TABLE` |
| Kill process | `taskkill /PID <pid> /F` |
| Services status | `sc query` or `Get-Service` via powershell |
| Network interfaces | `ipconfig /all` |
| Open ports | `netstat -an \| findstr LISTEN` |
| Uptime | `systeminfo \| grep "System Boot Time"` |
| Windows updates | `wmic qfe list brief` |

## Pitfalls

- **`top`, `free`, `uptime`, `df` do NOT exist** — don't try them, go straight to `wmic`.
- **`lscpu` does NOT exist** — use `wmic cpu get` instead.
- **`/format:list`** is cleaner than default table format for parsing.
- **`grep -v "^$"`** filters the blank lines wmic outputs between entries.
- **Disk D: may appear empty** — this is common on cloud VPS (Tencent/QCloud etc.) where D: is a temp/swap disk.
- **RAM pressure** — Windows Server often shows high RAM usage by design (SuperFetch, cached pages). Check if the user's actual apps are the bottleneck or just the OS caching.
- **`wmic` is deprecated** in newer Windows — still works on Server 2022 but may be removed in future. PowerShell `Get-CimInstance` is the modern alternative.
- **Python dual-process on MSYS**: On this host, `python` commands spawn TWO processes — one under the Hermes venv python and one under uv's cpython. Each has its own PID. When filtering `tasklist` or `wmic` output, expect 2 PIDs per logical Python process. Use `wmic process where "name='python.exe'" get ProcessId,CommandLine` with grep on CommandLine to distinguish them.
- **taskkill in MSYS**: Use double-slash syntax `taskkill //PID <pid> //F` — single slash is interpreted as a path and fails silently in git-bash.
- **Stuck `.git/index.lock` — kill git process first**: On MSYS, `git add -A` can leave a stale `index.lock` file. `rm` fails with "Device or resource busy" because a zombie git process holds it. Fix: `ps aux | grep -i git` → `kill -9 <PID>` → `rm -rf .git` → `git init && git branch -m main`. If the kill doesn't work, try `cmd //c "rmdir /s /q .git"` after killing the process. If a `.git/objects` directory persists, the process wasn't actually killed — check `ps aux` again. This pattern also applies to any local repo: stalled `git add -A`, `git commit`, or `git push` can leave lock files.

## References
- `references/msys-port-kill-pattern.md` — Kill ALL processes on a port (netstat + taskkill) when zombie processes accumulate from background restarts. Pattern for handling http.server stacking, dashboard zombies, and orphaned python processes.

```powershell
# CPU
Get-CimInstance Win32_Processor | Select-Object Name, NumberOfCores, NumberOfLogicalProcessors
# RAM
Get-CimInstance Win32_OperatingSystem | Select-Object FreePhysicalMemory, TotalVisibleMemorySize
# Disk
Get-CimInstance Win32_LogicalDisk | Select-Object DeviceID, Size, FreeSpace
```

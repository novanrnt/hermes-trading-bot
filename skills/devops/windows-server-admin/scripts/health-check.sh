#!/bin/bash
# Windows VPS Quick Health Check
# Usage: bash health-check.sh
# Works in MSYS/Git Bash on Windows Server

echo "=== OS ==="
systeminfo 2>/dev/null | grep -E "Host Name|OS Name|OS Version|System Boot Time"

echo -e "\n=== CPU ==="
wmic cpu get Name,NumberOfCores,NumberOfLogicalProcessors /format:list 2>/dev/null | grep -v "^$"

echo -e "\n=== MEMORY (KB) ==="
wmic OS get FreePhysicalMemory,TotalVisibleMemorySize /format:list 2>/dev/null | grep -v "^$"

echo -e "\n=== DISK (bytes) ==="
wmic logicaldisk get Size,FreeSpace,DeviceID /format:list 2>/dev/null | grep -v "^$"

echo -e "\n=== TOP MEMORY CONSUMERS ==="
tasklist /FO TABLE 2>/dev/null | head -15

echo -e "\n=== LISTENING PORTS ==="
netstat -an 2>/dev/null | findstr LISTEN

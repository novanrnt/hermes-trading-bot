#!/usr/bin/env python3
"""
[DAY] Cron trigger for the full 5-agent day trade swarm pipeline.
Runs every 2 hours during trading hours (07:00-22:00 WIB weekdays).
Calls: agent_swarm.py --mode day --symbol EURUSDm
"""
import subprocess, sys
from pathlib import Path

HERMES = Path(r"C:\Users\Administrator\AppData\Local\hermes")

print("[DAY] ⏰ Running day trade pipeline...")
r = subprocess.run(
    [sys.executable, str(HERMES / "agent_swarm.py"), "--mode", "day", "--symbol", "EURUSDm"],
    capture_output=True, text=True, timeout=240, cwd=str(HERMES)
)
out = r.stdout + r.stderr
print(out.strip())
print(f"[DAY] ✅ Pipeline exit code: {r.returncode}")

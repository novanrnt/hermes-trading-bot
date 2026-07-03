#!/usr/bin/env python3
"""Monte Carlo milestone reporter — only prints when we cross a 100-trade threshold."""
import json, sys
from pathlib import Path

HERMES = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERMES))

from monte_carlo import load_trades, run_monte_carlo, format_report

STATE_FILE = HERMES / "data" / "mc_milestone.json"

# Load state
state = {"last_milestone": 0}
if STATE_FILE.exists():
    try:
        state = json.load(open(STATE_FILE))
    except:
        pass

last = state.get("last_milestone", 0)

# Get current trade count
trades = load_trades()
n = len(trades)

# Find current milestone (100, 200, 300...)
current_milestone = (n // 100) * 100

if current_milestone > last and n >= 10:
    # Milestone crossed — run Monte Carlo and report
    results = run_monte_carlo(trades)
    report = format_report(trades, results)
    report += f"\n\n📌 _Milestone: {current_milestone} trades reached_"
    print(report)
    
    # Update state
    state["last_milestone"] = current_milestone
    json.dump(state, open(STATE_FILE, "w"))
    sys.exit(0)

# No milestone crossed — silent
sys.exit(0)

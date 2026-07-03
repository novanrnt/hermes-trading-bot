"""Full flow: run scanner to save candidate, then run pipeline."""
import sys, json, subprocess
from pathlib import Path

HERMES = Path(r"C:\Users\Administrator\AppData\Local\hermes")
sys.path.insert(0, str(HERMES))

from scripts.scalping_scanner import check_pair, ENABLED_SYMBOLS, now_wib

env = {}
for line in open(HERMES / ".env"):
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip("'\" ")

# Step 1: Find candidates
for sym in ENABLED_SYMBOLS:
    r = check_pair(sym, env)
    if r:
        print(f"✅ Candidate: {sym} {r['side']}")
        # Save candidate
        class NpEncoder(json.JSONEncoder):
            def default(self, obj):
                if hasattr(obj, 'item'):
                    return obj.item()
                return super().default(obj)
        with open(HERMES / "scalp_candidate.json", "w") as f:
            json.dump(r, f, indent=2, cls=NpEncoder)
        print(f"   Saved to scalp_candidate.json ✅")
        
        # Step 2: Run pipeline
        print(f"\n   Running pipeline...")
        r2 = subprocess.run(
            [sys.executable, str(HERMES / "agent_swarm.py"), "--mode", "scalp", "--symbol", sym],
            capture_output=True, text=True, timeout=180,
            cwd=str(HERMES)
        )
        out = r2.stdout + r2.stderr
        for line in out.split("\n")[-10:]:
            print(f"     {line.strip()}")
        break
else:
    print("❌ No candidates found")

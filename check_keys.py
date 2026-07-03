"""Check what's in the .env for agent keys."""
from pathlib import Path

HERMES = Path(r"C:\Users\Administrator\AppData\Local\hermes")
env = {}
for line in open(HERMES / ".env"):
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip("'\" ")

keys_to_check = [
    "AGENT_TECH_API_KEY",
    "AGENT_FUND_API_KEY",
    "AGENT_SENT_API_KEY",
    "AGENT_RISK_API_KEY",
    "AGENT_MANAGER_API_KEY",
]

for k in keys_to_check:
    v = env.get(k, "")
    print(f"{k}: len={len(v)} start={v[:15]}... end={v[-5:]}")

# Now test the main API key from config.yaml
import yaml
cfg = yaml.safe_load(open(HERMES / "config.yaml"))
main_key = cfg.get("model", {}).get("api_key", "")
print(f"\nMain API key from config.yaml: len={len(main_key)} start={main_key[:15]}...")

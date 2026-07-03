"""Test each agent API key with qwen3.7-plus."""
import requests, json, time
from pathlib import Path

HERMES = Path(r"C:\Users\Administrator\AppData\Local\hermes")
env = {}
for line in open(HERMES / ".env"):
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip("'\" ")

agents = {
    "technical": env.get("AGENT_TECH_API_KEY", ""),
    "fundamental": env.get("AGENT_FUND_API_KEY", ""),
    "sentiment": env.get("AGENT_SENT_API_KEY", ""),
    "risk": env.get("AGENT_RISK_API_KEY", ""),
    "manager": env.get("AGENT_MANAGER_API_KEY", ""),
}

base_url = "https://ai.sumopod.com/v1"

for name, key in agents.items():
    if not key:
        print(f"{name}: MISSING KEY ❌")
        continue
    t0 = time.time()
    try:
        r = requests.post(f"{base_url.rstrip('/')}/chat/completions", json={
            "model": "qwen3.7-plus",
            "messages": [{"role": "user", "content": f"Say hi as {name} agent in 5 words."}],
            "max_tokens": 50
        }, headers={
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json"
        }, timeout=15)
        t = time.time() - t0
        if r.status_code == 200:
            reply = r.json()["choices"][0]["message"]["content"]
            print(f"{name}: ✅ ({t:.1f}s) — {reply}")
        else:
            print(f"{name}: HTTP {r.status_code} ({t:.1f}s) — {r.text[:80]}")
    except Exception as e:
        t = time.time() - t0
        print(f"{name}: {type(e).__name__} ({t:.1f}s) ❌")

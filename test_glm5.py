"""Test glm-5 on SumoPod with various prompt sizes."""
import requests, json, time
from pathlib import Path

HERMES = Path(r"C:\Users\Administrator\AppData\Local\hermes")
env = {}
for line in open(HERMES / ".env"):
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip("'\" ")

api_key = env.get("AGENT_TECH_API_KEY", "")
base_url = "https://ai.sumopod.com/v1"

# Test 1: Tiny prompt
print("=== Tiny prompt ===")
for model in ["glm-5", "qwen3.7-plus", "deepseek-v4-flash"]:
    t0 = time.time()
    try:
        r = requests.post(f"{base_url.rstrip('/')}/chat/completions", json={
            "model": model,
            "messages": [{"role": "user", "content": "Say hello."}],
            "max_tokens": 30
        }, headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }, timeout=10)
        t = time.time() - t0
        if r.status_code == 200:
            print(f"  {model}: ✅ ({t:.1f}s)")
        else:
            print(f"  {model}: HTTP {r.status_code} ({t:.1f}s)")
    except Exception as e:
        t = time.time() - t0
        print(f"  {model}: {type(e).__name__} ({t:.1f}s)")

# Test 2: Medium prompt (like pipeline)
print("\n=== Medium prompt ===")
medium = "Analyze EURUSDm using EMA20 and ADX. Give entry levels.\n\n**Akun:** Balance: $10029\n**Harga:** EURUSDm Bid 1.08450 / Ask 1.08480\n**M15:** Close=1.08455 EMA20=1.08420\n**H1:** Close=1.08450 EMA20=1.08380"

for model in ["glm-5", "qwen3.7-plus"]:
    t0 = time.time()
    try:
        r = requests.post(f"{base_url.rstrip('/')}/chat/completions", json={
            "model": model,
            "messages": [
                {"role": "system", "content": "You are Technical Agent."},
                {"role": "user", "content": medium}
            ],
            "max_tokens": 500,
            "temperature": 0.7
        }, headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }, timeout=30)
        t = time.time() - t0
        if r.status_code == 200:
            reply = r.json()["choices"][0]["message"]["content"]
            print(f"  {model}: ✅ ({t:.1f}s) — {reply[:80]}...")
        else:
            print(f"  {model}: HTTP {r.status_code} ({t:.1f}s)")
    except Exception as e:
        t = time.time() - t0
        print(f"  {model}: {type(e).__name__} ({t:.1f}s)")

"""Test SumoPod with a realistic prompt size."""
import requests, yaml, json, time
from pathlib import Path

HERMES = Path(r"C:\Users\Administrator\AppData\Local\hermes")

env = {}
for line in open(HERMES / ".env"):
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip("'\" ")

api_key = env.get("LARGE_MODEL_API_KEY", env.get("API_KEY", ""))
cfg = yaml.safe_load(open(HERMES / "config.yaml"))
api_key = cfg.get("model", {}).get("api_key", api_key)
base_url = cfg.get("model", {}).get("base_url", "https://ai.sumopod.com/v1")

# Build a realistic prompt (like the pipeline sends)
system = "You are Technical Agent, a highly logical analyst."
user = "Analyze EURUSDm using EMA20, ADX, S/D zones. Give entry/exit levels with confidence.\n\n**Akun:** 415880976 | Balance: $10029.24 | Equity: $10016.19\n\n**Harga Saat Ini:**\nEURUSDm: Bid 1.08450 / Ask 1.08480 | Spread: 3\n\n**M15:** Close=1.08455 | EMA20=1.08420 | Hi20=1.08500 | Lo20=1.08400\n**H1:** Close=1.08450 | EMA20=1.08380 | Hi20=1.08600 | Lo20=1.08300\n**H4:** Close=1.08460 | EMA20=1.08200 | Hi20=1.08800 | Lo20=1.08000\n\n**Mode:** [DAY] | Timeframe: H4->H1->M15 | Symbol: EURUSDm\n**Min RR:** 1.8 | Risk per Trade: 0.5%"

for model in ["qwen3.7-plus", "deepseek-v4-flash"]:
    t0 = time.time()
    try:
        r = requests.post(f"{base_url.rstrip('/')}/chat/completions", json={
            "model": model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
            "max_tokens": 800,
            "temperature": 0.7
        }, headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }, timeout=60)
        t = time.time() - t0
        print(f"{model}: HTTP {r.status_code} ({t:.1f}s)")
        if r.status_code == 200:
            content = r.json()["choices"][0]["message"]["content"]
            print(f"  Response: {content[:120]}...")
            print(f"  Total tokens: {len(content.split())}")
        else:
            print(f"  Body: {r.text[:150]}")
    except Exception as e:
        t = time.time() - t0
        print(f"{model}: {type(e).__name__} ({t:.1f}s)")

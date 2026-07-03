"""Test SumoPod with main config key right now."""
import requests, yaml, json, time
from pathlib import Path

HERMES = Path(r"C:\Users\Administrator\AppData\Local\hermes")

# Main key from config
cfg = yaml.safe_load(open(HERMES / "config.yaml"))
api_key = cfg.get("model", {}).get("api_key", "")
base_url = cfg.get("model", {}).get("base_url", "https://ai.sumopod.com/v1")

print(f"Main API key: len={len(api_key)}")
print(f"Base URL: {base_url}")

for model in ["qwen3.7-plus", "deepseek-v4-flash"]:
    t0 = time.time()
    try:
        r = requests.post(f"{base_url.rstrip('/')}/chat/completions", json={
            "model": model,
            "messages": [{"role": "user", "content": "Say hello in 3 words."}],
            "max_tokens": 30
        }, headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }, timeout=15)
        t = time.time() - t0
        if r.status_code == 200:
            reply = r.json()["choices"][0]["message"]["content"]
            print(f"\n{model}: ✅ ({t:.1f}s) — {reply}")
        else:
            print(f"\n{model}: HTTP {r.status_code} ({t:.1f}s) — {r.text[:100]}")
    except Exception as e:
        t = time.time() - t0
        print(f"\n{model}: {type(e).__name__} ({t:.1f}s)")

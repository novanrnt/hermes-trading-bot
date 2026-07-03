"""Test if SumoPod API works right now (same params as call_llm)."""
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
print(f"Key: {api_key[:15]}...")
print(f"URL: {base_url}")

t0 = time.time()
r = requests.post(f"{base_url.rstrip('/')}/chat/completions", json={
    "model": "qwen3.7-plus",
    "messages": [
        {"role": "system", "content": "Be brief."},
        {"role": "user", "content": "Analyze EURUSDm in 2 sentences."}
    ],
    "max_tokens": 500,
    "temperature": 0.7
}, headers={
    "Authorization": f"Bearer {api_key}",
    "Content-Type": "application/json"
}, timeout=15)

t = time.time() - t0
print(f"Status: {r.status_code} ({t:.1f}s)")
print(f"Body[:300]: {r.text[:300]}")

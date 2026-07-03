import requests, yaml, json
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
model_cfg = cfg.get("model", {})
api_key = model_cfg.get("api_key", api_key)
base_url = model_cfg.get("base_url", "https://ai.sumopod.com/v1")

print(f"Base URL: {base_url}")
print(f"API Key: {api_key[:12]}..." if api_key else "API Key: MISSING!")

models_to_try = ["qwen3.7-plus", "mimo-v2.5-pro", "deepseek-v4-pro"]

for model in models_to_try:
    try:
        r = requests.post(f"{base_url.rstrip('/')}/chat/completions", json={
            "model": model,
            "messages": [{"role": "user", "content": "Say hello in 3 words."}],
            "max_tokens": 30
        }, headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }, timeout=20)
        print(f"\n{model}: HTTP {r.status_code}")
        if r.status_code == 200:
            print(f"  OK: {r.json()['choices'][0]['message']['content']}")
        else:
            print(f"  Body: {r.text[:200]}")
    except Exception as e:
        print(f"\n{model}: {type(e).__name__}: {e}")

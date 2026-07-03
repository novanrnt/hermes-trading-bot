import requests, yaml, json, time, concurrent.futures
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

def test_call(name):
    t0 = time.time()
    try:
        r = requests.post(f"{base_url.rstrip('/')}/chat/completions", json={
            "model": "qwen3.7-plus",
            "messages": [{"role": "user", "content": f"Analyze EURUSD in 2 sentences. This is {name}."}],
            "max_tokens": 200
        }, headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }, timeout=30)
        t = time.time() - t0
        if r.status_code == 200:
            return f"{name}: OK ({t:.1f}s) — {r.json()['choices'][0]['message']['content'][:60]}..."
        else:
            return f"{name}: HTTP {r.status_code} ({t:.1f}s) — {r.text[:80]}"
    except Exception as e:
        t = time.time() - t0
        return f"{name}: {type(e).__name__} ({t:.1f}s) — {e}"

# First test: sequential
print("=== SEQUENTIAL (3 calls) ===")
t0 = time.time()
for i in range(3):
    print(f"  {test_call(f'seq-{i+1}')}")
print(f"Total: {time.time()-t0:.1f}s")

# Then test: parallel 3
print("\n=== PARALLEL (3 calls) ===")
t0 = time.time()
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as exc:
    futs = [exc.submit(test_call, f"par-{i+1}") for i in range(3)]
    for f in concurrent.futures.as_completed(futs):
        print(f"  {f.result()}")
print(f"Total: {time.time()-t0:.1f}s")

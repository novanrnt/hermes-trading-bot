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
api_key = cfg.get("model", {}).get("api_key", api_key)
base_url = cfg.get("model", {}).get("base_url", "https://ai.sumopod.com/v1")

def test_call(name):
    t0 = time.time()
    try:
        r = requests.post(f"{base_url.rstrip('/')}/chat/completions", json={
            "model": "qwen3.7-plus",
            "messages": [{"role": "user", "content": f"Say a 1-line analysis of EURUSD."}],
            "max_tokens": 100
        }, headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }, timeout=15)
        t = time.time() - t0
        if r.status_code == 200:
            return f"{name}: OK ({t:.1f}s)"
        else:
            return f"{name}: HTTP {r.status_code} ({t:.1f}s)"
    except Exception as e:
        t = time.time() - t0
        return f"{name}: {type(e).__name__} ({t:.1f}s)"

print("=== SEQUENTIAL x3 ===")
t0 = time.time()
for i in range(3):
    print(f"  {test_call(f'seq-{i+1}')}")
print(f"Total: {time.time()-t0:.1f}s\n")

print("=== PARALLEL x2 ===")
t0 = time.time()
with concurrent.futures.ThreadPoolExecutor(max_workers=2) as exc:
    futs = [exc.submit(test_call, f"par-{i+1}") for i in range(2)]
    for f in concurrent.futures.as_completed(futs):
        print(f"  {f.result()}")
print(f"Total: {time.time()-t0:.1f}s\n")

print("=== PARALLEL x3 ===")
t0 = time.time()
with concurrent.futures.ThreadPoolExecutor(max_workers=3) as exc:
    futs = [exc.submit(test_call, f"par3-{i+1}") for i in range(3)]
    for f in concurrent.futures.as_completed(futs):
        print(f"  {f.result()}")
print(f"Total: {time.time()-t0:.1f}s")

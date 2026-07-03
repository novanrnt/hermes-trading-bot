"""Test gpt-5-mini vs glm-5 for agent analysis speed."""
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

# Realistic agent prompt (routing scale)
system = "Kamu adalah Technical Agent RNT Autotrade. IQ 160, logis, dingin, anti-FOMO. Analisis teknikal berdasarkan data. Wajib Bahasa Indonesia."
user = """Analisis EURUSDm untuk DAY TRADE:

**Data Pasar:**
EURUSDm: Bid 1.08450 / Ask 1.08480
M15: Close=1.08455, EMA20=1.08420, ADX=22
H1: Close=1.08450, EMA20=1.08380, ADX=28
H4: Close=1.08460, EMA20=1.08200, ADX=35

**Posisi Terbuka:** Tidak ada
**Balance:** $10,029 | **Equity:** $10,016

Beri analisis teknikal 3-4 kalimat dan TRADE SETUP dengan entry, SL, TP, RR, confidence."""

models_to_test = [
    "glm-5",
    "gpt-5-mini",
    "deepseek-v4-flash",
]

for model in models_to_test:
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
        if r.status_code == 200:
            content = r.json()["choices"][0]["message"]["content"]
            print(f"\n=== {model} === ✅ ({t:.1f}s, {len(content.split())} kata)")
            print(content[:200])
        else:
            print(f"\n=== {model} === HTTP {r.status_code} ({t:.1f}s)")
            print(r.text[:100])
    except Exception as e:
        t = time.time() - t0
        print(f"\n=== {model} === {type(e).__name__} ({t:.1f}s)")

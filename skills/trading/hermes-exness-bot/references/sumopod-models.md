# SumoPod Model Configuration

Base URL: `https://ai.sumopod.com/v1`
Provider type: `custom` (OpenAI-compatible)

## Models in Hermes Config

```
deepseek-v4-pro     ← default
deepseek-v4-flash
mimo-v2.5-pro
glm-5
gpt-5.4-mini
kimi-k2.7
qwen3.6-flash
qwen3.7-max
```

## How to Switch Models

```bash
hermes model
```

Interactive picker shows all available_models from config.yaml.

## Full SumoPod Catalog (42 models)

**Anthropic Claude:** haiku-4-5, sonnet-4-6, opus-4-6/4-7/4-8
**OpenAI GPT:** 4.1/mini/nano, 5/mini/nano, 5.4/mini/nano
**Google Gemini:** 2.5-flash/lite, 3-flash, 3.1-flash-lite/pro, 3.5-flash
**DeepSeek:** v4-flash, v4-pro
**Qwen:** 3.6-flash/plus, 3.7-max/plus
**MiMo:** v2.5, v2.5-pro
**GLM:** 5, 5-turbo, 5.1, 5.2
**Kimi:** k2.6, k2.7
**MiniMax:** M2.7-highspeed, M3
**ByteDance Seed:** 2-0-code/lite/mini/pro
**Embeddings:** text-embedding-3-small/large, gemini-embedding-001

User favorites: deepseek-v4-pro, deepseek-v4-flash, qwen3.6-flash, qwen3.7-max.

## Model Performance Notes

| Model | Speed (small prompt) | Speed (medium prompt, ~2K chars) | Notes |
|-------|-------|-------|-------------|
| deepseek-v4-pro | ~50s/call | N/A | Default. Best balance for orchestrator. |
| deepseek-v4-flash | ~1s/call | ~1s/call | Fastest. Good for pipeline agents. |
| mimo-v2.5-pro | ~55s/call | N/A | Reliable but slower total cycle (~185s) |
| qwen3.7-max | ~60s/call | N/A | Large context. Handles big payloads. |
| **qwen3.7-plus** | **~8s** | **>30s timeout ❌** | Degrades badly with larger context. NOT suitable for pipeline agents. |
| **glm-5** | **~3s** | **~14s ✅** | Best balance for pipeline agents. Default in agent_swarm.py. |

**Parallel request limitation:** SumoPod CANNOT handle concurrent requests from the same IP. 3 parallel requests → all ReadTimeout. Sequential with same calls → all succeed. Pipeline agents MUST run sequentially, even with per-agent API keys.

**Orchestrator timeout:** Set to 600s in `run_decision_cycle.py`. Each agent call takes 50-60s, 5 agents = 250-300s + overhead. Don't reduce below 600s.

**Empty content errors:** Some models (especially deepseek-v4-pro) occasionally return empty content. The orchestrator retries 2x with 2s delay. If all retries fail, pipeline aborts with "Empty content in LLM response". This is transient — next cycle usually works.

**Transient read timeouts (multiagent_pipeline.py):** The multi-agent bot pipeline (`multiagent_pipeline.py`, used for parallel 5-bot posting to Topics 969-974) originally had NO retry logic — a single timeout posted `[ERROR]` directly. Fixed 2026-07-03: added 2 retries with 3s delay, timeout increased from 90s to 120s. SumoPod sometimes has sustained slow periods lasting 15-30 min (especially 01:00-02:00 WIB). The retry handles short blips; longer outages just need to pass.

**JSON parsing errors:** Models sometimes return malformed JSON (missing commas, trailing commas). The `_extract_json()` function handles ```json fences but can't fix malformed JSON. Retries usually resolve this.

## Config Workaround (YAML List Bug)

Direct `hermes config set model.available_models` creates a dict with string keys instead of a YAML list. Fix with Python:

```python
import yaml
with open('config.yaml') as f:
    cfg = yaml.safe_load(f)
am = cfg['model'].get('available_models', {})
if isinstance(am, dict):
    cfg['model']['available_models'] = list(am.values())
with open('config.yaml', 'w') as f:
    yaml.dump(cfg, f, default_flow_style=False, allow_unicode=True, sort_keys=False)
```

## Credential Debugging (401 / Auth Errors)

When SumoPod returns `401 Authentication Error` or `Read timed out`:

### Step 1: Check if host is reachable
```bash
curl -s -o /dev/null -w "http_code=%{http_code} time=%{time_total}s\n" \
  --connect-timeout 10 --max-time 30 https://ai.sumopod.com/v1/models
```
- HTTP 401 → host is up, KEY is the problem
- Connection timeout → network/firewall issue (rare on VPS)
- HTTP 200 → key works, problem is elsewhere (model name, proxy config)

### Step 2: Test chat endpoint directly
```bash
curl -s --connect-timeout 10 --max-time 90 -X POST \
  "https://ai.sumopod.com/v1/chat/completions" \
  -H "Authorization: Bearer <key>" \
  -H "Content-Type: application/json" \
  -d '{"model":"qwen3.7-plus","messages":[{"role":"user","content":"hi"}],"max_tokens":10}'
```

### Step 3: Trace credential chain
`agent_swarm.py` (and other pipeline scripts) load API keys in this priority:
1. `LARGE_MODEL_API_KEY` from `.env`
2. `API_KEY` from `.env`
3. `model.api_key` from `config.yaml`

Check ALL three sources:
```bash
# config.yaml
grep "api_key:" ~/AppData/Local/hermes/config.yaml
# .env
grep -E "^(LARGE_MODEL_API_KEY|API_KEY|CUSTOM_API_KEY)=" ~/AppData/Local/hermes/.env
```

### Step 4: Detect truncated keys
A real SumoPod API key is **much longer than 25 characters**. Keys stored literally as `sk-iJy...B1zA` (with `...` in the string) are placeholders — the real key was replaced during a config edit or credential redactor pass. Verify length:
```bash
python3 -c "
import yaml
with open(r'C:\Users\Administrator\AppData\Local\hermes\config.yaml') as f:
    cfg = yaml.safe_load(f)
k = cfg.get('model', {}).get('api_key', '')
print(f'Key length: {len(k)}')
print(f'Contains \"...\": {\"...\" in k}')
"
```
If length < 40 or contains `...`, the key is truncated. Replace with the full key from your SumoPod dashboard.

### Step 5: Check credential pool
Hermes stores credentials in `auth.json` with its own credential pool. The `custom` provider's pool may be empty even when config.yaml has a key. Verify:
```bash
python3 -c "
import json
with open(r'C:\Users\Administrator\AppData\Local\hermes\auth.json') as f:
    auth = json.load(f)
cp = auth.get('credential_pool', {})
for prov, creds in cp.items():
    print(f'{prov}: {len(creds) if isinstance(creds, list) else \"non-list\"} credentials')
"
```

### Common causes of 401 errors
| Symptom | Likely Cause | Fix |
|---------|-------------|-----|
| `Invalid proxy server token passed` | Key expired/revoked/replaced | Get new key from SumoPod admin |
| Key shows `sk-iJy...B1zA` (25 chars) | Config saved truncated placeholder | Replace with full key |
| Key shows `sk-t1D...3Q1A` (25 chars) | .env saved truncated placeholder | Replace in BOTH config.yaml AND .env |
| Key was working yesterday | Key rotated without updating config | Same fix — replace with new key |

### Pitfall: agent_swarm.py vs Hermes credential chain
The `agent_swarm.py` pipeline reads credentials **independently** from Hermes' own credential pool. Even if Duleh (Hermes chat) works fine with SumoPod, the pipeline can fail with 401 if its credential path (`config.yaml` key) is stale. Always fix BOTH:
1. `config.yaml` → `model.api_key` (used by pipeline scripts)
2. `.env` → `CUSTOM_API_KEY` (may be read by some scripts as fallback)

### Per-Agent API Keys (since 2026-07-03)
Since the pipeline was refactored to use per-agent keys, each agent now reads its own API key from `.env`:
- `AGENT_TECH_API_KEY` → Technical Agent
- `AGENT_FUND_API_KEY` → Fundamental Agent
- `AGENT_SENT_API_KEY` → Sentiment Agent
- `AGENT_RISK_API_KEY` → Risk Agent
- `AGENT_MANAGER_API_KEY` → Manager Agent

If one agent shows `[Analysis unavailable — agent_name]` while others work, that specific agent's key is the problem — not the shared credential chain. Test with:
```bash
python -c "
import requests, json
key = open('.env').read().split('AGENT_TECH_API_KEY=')[1].split(chr(10))[0].strip().strip(chr(39)).strip(chr(34))
r = requests.post('https://ai.sumopod.com/v1/chat/completions', json={'model':'glm-5','messages':[{'role':'user','content':'hi'}]}, headers={'Authorization':f'Bearer {key}'}, timeout=15)
print(r.status_code, r.json()['choices'][0]['message']['content'][:50] if r.ok else r.text[:100])
"
```

## Prompt Size Caution

deepseek-v4-pro handles ~8K input well but fails on 25K+ char prompts. Keep news events to high/medium this-week only (~27 events). For extra safety on complex weeks, switch to qwen3.7-max (larger context) or gpt-5.4-mini.

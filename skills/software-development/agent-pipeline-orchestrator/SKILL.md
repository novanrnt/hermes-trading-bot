---
name: agent-pipeline-orchestrator
description: >
  Build and test multi-agent LLM pipelines where specialized agents run in
  stages, each reading prior outputs, with a manager agent synthesizing the
  final decision. Use for domain-specific analysis workflows (trading, content
  review, research, compliance) where multiple perspectives feed into one
  judgment.
---

# Agent Pipeline Orchestrator

## When to load
- Building or debugging a multi-agent pipeline with 3+ agents and a manager
- Testing individual agent prompts with dummy/partial data before full run
- Wrapping agent calls in a Python orchestrator with safety gates
- The user says "test agent", "jalanin pipeline", "cek agent", "orchestrator"

## Architecture

```
Stage 1: Primary Analysis Agent (e.g. Technical)
   ↓
Stage 2: Sequential Filter Agents (e.g. Fundamental → Sentiment → Risk)
   ↓
Stage 3: Manager Agent → final decision (entry/skip/etc.)
   ↓
Stage 4: Review Agent (optional, e.g. Boss) → audit & improvement proposals
   ↓
Safety Gate → validate manager output before accepting
```

**Note:** Run Stage 2 agents SEQUENTIALLY, not in parallel. Parallel execution makes debugging harder — you can't see which agent's output caused a downstream issue. Sequential allows you to trace the full decision chain.

## Prompt file convention
- One `.txt` per agent in a `prompts/active/` directory
- Naming: `<role>_agent_prompt.txt` (snake_case, english)
- Each prompt declares: role, tugas, larangan, gaya keputusan, format JSON wajib
- Prompts written in user's preferred language (e.g. Indonesian for metski)

## Testing agents (no live data)

> **Detailed testing workflow absorbed from `multi-agent-pipeline-testing` skill.** See `references/trading-pipeline-test-example.md` for a worked example with trading agents.

### Method: delegate_task with dummy payload
Use `delegate_task` with tasks array (max 3 per batch). Each task:
- Inject the full agent prompt as system instruction
- Provide compact dummy payload inline
- Require JSON-only output, no markdown, no explanation
- Verify output matches expected JSON schema

```
delegate_task tasks=[
  {goal: "PROMPT TEXT\n\nTEST DATA: ...\nRespond ONLY JSON."},
  ...
]
```

### What to check per agent
- Output is valid JSON (no markdown fences, no prose)
- All required fields present
- Agent is conservative when data is missing (returns "limited"/"conditional", not fake data)
- Agent does not overstep role (e.g. Technical doesn't execute trades)

## Orchestrator script pattern
Python script (`agent_orchestrator.py`) with these sections:

1. **Config loader** — read API key/model from YAML, agent registry from JSON
2. **MT5/data loader** — read payload file or fallback to dummy for testing
3. **Prompt builders** — load base prompt, inject payload, append "Respond ONLY JSON"
4. **LLM API call** — OpenAI-compatible `/chat/completions`, extract JSON with regex
5. **Safety Gate** — hard-check manager output: RR, confidence, SL/TP logic
6. **Pipeline runner** — stages in sequence, save output to `output/cycle_TIMESTAMP.json`
7. **CLI** — argparse with `--mode`, `--mt5-file`, `--status`, `--skip-boss`

## LLM API Call with Retry Logic

Every `_call_llm()` in a pipeline orchestrator MUST include retry logic. LLM APIs return empty `content`, malformed JSON, or timeout under load — a single bare call will crash the entire pipeline.

### Required retry coverage (2 retries, 2s delay):
1. **HTTP errors** (HTTPError) — retry on 5xx, non-retryable on 4xx (except 429)
2. **Connection/timeout** (URLError, socket.timeout, TimeoutError, ConnectionError)
3. **Empty response body** — API returned 200 but body is `""`
4. **Malformed JSON** — `json.loads()` fails on the response body
5. **Empty content** — `choices[0].message.content` exists but is `""` or whitespace-only
6. **JSON extraction failure** — `_extract_json()` raises ValueError (no `{...}` found)

### Pattern (see `references/llm-retry-pattern.py` for the full function):

```python
MAX_RETRIES = 2
RETRY_DELAY = 2

for attempt in range(MAX_RETRIES + 1):
    try:
        # ... urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) ...
        raw = resp.read().decode("utf-8")
    except HTTPError as e:       # retry on last attempt
    except (URLError, socket.timeout, TimeoutError, ConnectionError) as e:  # retry
    except Exception as e:       # retry generic failures

    if not raw or not raw.strip():  # empty body → retry
    result = json.loads(raw)        # malformed → retry
    content = result["choices"][0]["message"]["content"]
    if not content or not content.strip():  # empty content → retry
    return _extract_json(content)   # JSON extraction fails → retry
```

**Log format:** `[RETRY X/2] <reason>, waiting 2s...`

### Testing retry logic
Run with `--mode test` and watch for `[RETRY` in output. If you see it and the pipeline still completes, the retry saved the run. If the pipeline succeeds without any retry log, that's also fine — the mechanism is defensive.

## Pitfalls
- `read_file` caches results; use `terminal cat` to force re-read when file may have changed
- Subagents (delegate_task) have no session memory — inject all context inline
- `max_concurrent_children` may limit parallel batch size (default 3); split into batches
- `web_extract` may truncate large pages — use `browser_navigate` for interactive content
- **Data key casing mismatch** — When passing structured data (JSON payloads) to agent prompts, verify that the key casing in your extraction/compaction logic matches the source data. Common bug: code uses `data.get("h4", {})` but source has `"H4"`. Result: all extracted data is empty `{}`, downstream agents reject everything. Fix: normalize keys with fallback: `data.get(k) or data.get(k.upper()) or data.get(k.lower()) or {}`
- **Prompt builders must receive source data** — If downstream agents need context (news, account info, risk parameters), the prompt builder functions must receive the full source data dict, not just the technical output. Otherwise agents operate blind and return "conditional" for everything.

## Master Runner Pattern

Chain multiple pipeline steps in 1 Python script (`run_decision_cycle.py`):

```python
# Step 1: Data collector (MT5, API, etc.)
step1 = subprocess.run([python, "collector.py", "--output", "payload.json"])
if step1.returncode != 0: abort

# Step 2: Orchestrator (all agents)
step2 = subprocess.run([python, "orchestrator.py", "--mt5-file", "payload.json", "--mode", "test"])
if step2.returncode != 0: abort

# Step 3: Dry-run executor (simulates execution)
step3 = subprocess.run([python, "dryrun_executor.py"])
```

Rules:
- If step N fails, skip step N+1, write error to cycle report
- Save cycle report to `logs/cycles/cycle_run_TIMESTAMP.json`
- Support `--skip-collector` flag for environments without data source
- Each step has its own timeout
- Final output: FINAL ACTION + REPORT path

## Dry-Run Executor Pattern

Reads `final_decision.json` and simulates without real execution:

```python
def validate_entry(decision: dict) -> tuple[bool, list[str]]:
    # Check required fields, RR >= 1.8, confidence >= 75, price logic
    # Return (valid, list_of_errors)

def run_dry_run():
    decision = load_final_decision()
    if decision["action"] == "skip":
        # Print SKIP reason, save report
    elif decision["action"] == "entry":
        valid, errors = validate_entry(decision)
        if valid:
            # Print "WOULD EXECUTE" + details, save report
        else:
            # Print "BLOCKED" + errors, save report
```

Reports saved to `logs/dry_run/dryrun_TIMESTAMP.json`.

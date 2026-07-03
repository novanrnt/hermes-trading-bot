# Orchestrator Architecture

## Core Classes

### `AgentPipeline`
Main pipeline runner. Constructor takes `mt5_payload`, `api_config`, `mode`, `skip_boss`.

Flow:
1. `_run_stages()` runs agents sequentially
2. Each `_run_agent()` calls `_call_llm()` and wraps in `AgentResult`
3. On any failure → `_abort()` forces skip
4. Safety Gate validates Manager output
5. `_save_log()` writes to `logs/agent_debates/cycle_YYYYMMDD_HHMMSS.json`

### `SafetyGate`
Static validator. `validate(manager_output)` returns `(passed: bool, reason: str, corrected_output: dict)`.

Hard checks:
- RR >= 1.8
- Confidence >= 75
- Price logic: buy requires sl < entry < tp, sell requires sl > entry > tp
- Required fields: best_symbol, side, entry_type, planned_entry, sl_price, tp_price, rr, confidence

## LLM Call Pattern

Uses `urllib.request` to call OpenAI-compatible API. Reads `model.base_url` and `model.api_key` from `config.yaml`. Temperature fixed at 0.3 for consistency.

JSON extraction handles:
- ```json fences
- Leading/trailing text
- First { to last } extraction

## Log Format

Each cycle writes `cycle_YYYYMMDD_HHMMSS.json` to `logs/agent_debates/`:
```json
{
  "timestamp": "ISO8601",
  "mode": "test|live|cron",
  "model": "model-name",
  "mt5_payload": { ... },
  "agent_results": {
    "technical_agent": {"status": "completed|failed", "output_json": {...}, "error": null},
    ...
  },
  "manager_output_raw": { ... },
  "safety_gate_result": {"passed": true|false, "reason": "..."},
  "final_decision": { ... },
  "duration_per_agent": {"technical_agent": 1234.5, ...},
  "total_duration_ms": 5000.0
}
```

No API keys, tokens, or secrets are ever written to logs.

## agent_order

```python
AGENT_ORDER = [
    "technical_agent",
    "fundamental_agent",
    "sentiment_agent",
    "risk_agent",
    "manager_agent",
]
```

Boss agent is optional (`--skip-boss` flag) and not in the static order.

## Dependencies

- Python 3.11+
- `yaml` (pyyaml) — for config.yaml parsing
- `urllib` (stdlib) — for API calls
- No MT5 library dependency — payload comes from external JSON file

## Adding MT5 Integration

To connect real MT5 with Exness:
1. Create a script that reads MT5 terminal data and exports to `data/mt5_payload.json`
2. Format must match the `symbols` structure in `_dummy_mt5_payload()`
3. Run orchestrator with `--mt5-file data/mt5_payload.json --mode live`

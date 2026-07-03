# ADX Gate — Pre-Analysis Trend Filter

Blocks symbols from entering the Technical Agent if H1 ADX < 20 (ranging/choppy market). Runs BEFORE Stage 1, saving LLM tokens and preventing low-quality entries.

## How It Works

```
agent_orchestrator._run_stages():
  → Load MT5 payload (symbols + indicators)
  → ADX Gate: for each symbol, check H1 ADX
    - H1 ADX < 20 → BLOCK (remove from symbols dict)
    - H1 ADX ≥ 20 → PASS (pass to Technical Agent)
  → If ALL symbols blocked → skip pipeline with reason
  → Otherwise → proceed to Stage 1 (Technical)
```

## Location

`agent_orchestrator.py` → `_run_stages()` → right before `# ── Stage 1: Technical ──`

## Threshold

- **ADX minimum:** 20 (standard threshold: < 20 = ranging, 20-25 = borderline, > 25 = trending)
- **Timeframe:** H1 (if missing, symbol passes — no block without data)

## Why H1?

H1 ADX captures the medium-term trend regime without being too noisy (M5) or too slow (H4). A pair with H1 ADX < 20 has no directional momentum — entries are coin flips.

## Edge Cases

- H1 data missing → symbol PASSES (no false negatives)
- All 8 symbols blocked → pipeline SKIP with reason "All symbols filtered by ADX gate"
- Blocked symbols logged in `cycle_log.agent_results["adx_gate"]`

## Example Output

```
[ADX Gate] Blocked 4 symbol(s):
  ✗ GBPUSDm: H1 ADX 13.7 < 20 — ranging/choppy
  ✗ USDJPYm: H1 ADX 10.9 < 20 — ranging/choppy
  ✗ USDCADm: H1 ADX 4.2 < 20 — ranging/choppy
  ✗ NZDUSDm: H1 ADX 13.8 < 20 — ranging/choppy
```

## Tuning

If too many symbols get blocked, lower ADX minimum to 15. If entries are still choppy, raise to 25. Current value (20) is conservative-optimal for the bot's moderate profile.

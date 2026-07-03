# Cron Timeout Diagnosis & Fix (no_agent scripts)

## Symptom
Cron job (no_agent=true) fails with: `Script timed out after 120s`

## Root Cause
The cron scheduler has a **120s default timeout** for `no_agent=true` scripts. The Day Trade Pipeline (`54151c37162a`) calls `agent_swarm.py --mode day` which runs 5 sequential LLM API calls. With SumoPod's variable response times (10-45s per call), the total can exceed 120s.

**Key insight:** The script's own `subprocess.run(timeout=240)` doesn't matter — the outer cron scheduler kills at 120s regardless.

## Current Solution (2026-07-03)

### Architecture
- **Sequential agents** (not parallel): SumoPod cannot handle concurrent requests from the same IP. Testing confirmed: 3 parallel calls → all ReadTimeout at 90s. Sequential with same calls → all succeed.
- **Per-agent API keys**: Each agent has its own SumoPod key in `.env` (`AGENT_TECH_API_KEY` etc.), loaded from `AGENTS_LLM` dict. This isolates credential issues per agent.
- **Model: glm-5**: ~14s per medium prompt. Much faster than qwen3.7-plus (>30s timeout on same prompts).
- **Timeout: 45s per call**: 1-shot, no retries, fast fallback text on failure.
- **Fallback**: `[Analysis unavailable — agent_name]` — pipeline continues even when an agent fails.

### Typical Runtime
- 5 agents × ~14s/call (glm-5) = ~70s
- MT5 loading + overhead = ~15s
- **Total: ~85s** — under 120s ✅
- Worst case (API slow): ~140s → may timeout → **convert to agent-driven cron**

### When the Pipeline Still Exceeds 120s
If SumoPod is having a slow period and the pipeline exceeds 120s:
1. Convert cron from `no_agent=true` to agent-driven:
   ```
   cronjob action=update job_id=54151c37162a no_agent=false prompt="Run: cd ... && python agent_swarm.py --mode day --symbol EURUSDm" script=""
   ```
2. The Hermes agent runs the script via `terminal()` with a 240s timeout
3. Downsides: consumes ~2K tokens every 2h just for orchestration

## History of Fixes

| Date | Approach | Outcome |
|------|----------|---------|
| 2026-07-03 10:00 | Parallelize Phase 1 (3 agents) + 15s timeout | Failed: SumoPod rejects parallel requests |
| 2026-07-03 10:20 | Sequential + deepseek-v4-flash + 20s timeout | Fast but user wanted qwen3.7-plus |
| 2026-07-03 10:30 | Per-agent keys + qwen3.7-plus + parallel | qwen3.7-plus too slow (>30s) on large prompts |
| 2026-07-03 10:35 | Sequential + glm-5 + 45s timeout ✅ | ~85s typical, agent-driven cron fallback for slow days |

## Diagnosis Checklist
1. Check the script — is it calling LLM APIs? If yes, 120s cron limit is the bottleneck.
2. Check `call_llm()` current timeout and retry settings.
3. Verify which model is configured — qwen3.7-plus is too slow (>30s) for pipeline use.
4. Test with `timeout 120 python script.py` to reproduce the cron kill signal.
5. If consistently >120s, convert to agent-driven cron (see above).

## Related Files
- `agent_swarm.py` — `call_llm()` with 45s timeout, no retries, sequential agents
- `scripts/day_trade_cron.py` — cron wrapper (currently unused — cron is agent-driven)
- Cron job: `54151c37162a` — Day Trade Pipeline (2h), currently agent-driven

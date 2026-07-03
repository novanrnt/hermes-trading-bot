# Model Benchmarks — 2026-07-03

Real-world agent pipeline benchmark on SumoPod (https://ai.sumopod.com/v1).
Prompt: Technical Agent analysis with full market context (EURUSDm, MT5 data, 3 timeframes).

## Results

| Model | Speed | Response Quality | Verdict |
|-------|-------|-----------------|---------|
| deepseek-v4-flash | **9.4s** | ✅ 120 words, structured analysis | **BEST** |
| glm-5 | 29.9s | ✅ 158 words, detailed | OK but slow |
| qwen3.7-plus | >30s timeout | Fallback on pipeline prompts | Too slow |
| gpt-5-mini | 8.3s | ❌ Empty/0-word response | Unusable |

## Key Findings

1. deepseek-v4-flash is the optimal pipeline model — 9s/call, quality structured output
2. qwen3.7-plus times out (30s+) on prompts with full market context
3. glm-5 works but is 3x slower than deepseek-v4-flash (30s vs 9s)
4. gpt-5-mini returns empty responses for agent prompts — unusable

## Sequence Timing (5 agents, deepseek-v4-flash)

- 5 sequential calls x ~9s = ~45s
- MT5 data loading: ~10s  
- Telegram sends + overhead: ~15s
- Total: ~70s — well under 120s cron limit

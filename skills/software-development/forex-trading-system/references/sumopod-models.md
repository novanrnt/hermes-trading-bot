# SumoPod Model Catalog (as of June 2026)

API: `https://ai.sumopod.com/v1` (OpenAI-compatible)
Auth: Bearer token via `api_key` in config.yaml

## Anthropic (Claude)
| Model ID | Context | Cost (in/out) | Reasoning |
|----------|---------|---------------|-----------|
| `claude-haiku-4-5` | 200K | 1/5 | ✅ |
| `claude-sonnet-4-6` | 1M | 3/15 | ✅ |
| `claude-opus-4-6` | 1M | 5/25 | ✅ |
| `claude-opus-4-7` | 1M | 5/25 | ✅ |
| `claude-opus-4-8` | 1M | 5/25 | ✅ |

## OpenAI (GPT)
| Model ID | Context | Cost (in/out) | Reasoning |
|----------|---------|---------------|-----------|
| `gpt-4.1` | 1M | 2/8 | ❌ |
| `gpt-4.1-mini` | 1M | 0.4/1.6 | ❌ |
| `gpt-4.1-nano` | 1M | 0.1/0.4 | ❌ |
| `gpt-4o` | 128K | 2.5/10 | ❌ |
| `gpt-4o-mini` | 128K | 0.15/0.6 | ❌ |
| `gpt-5` | 272K | 1.25/10 | ✅ |
| `gpt-5-mini` | 272K | 0.25/2 | ✅ |
| `gpt-5-nano` | 272K | 0.05/0.4 | ✅ |
| `gpt-5.1` | 272K | 1.25/10 | ✅ |
| `gpt-5.1-codex` | 272K | 1.25/10 | ✅ |
| `gpt-5.1-codex-mini` | 272K | 0.25/2 | ✅ |
| `gpt-5.2` | 272K | 1.75/14 | ✅ |
| `gpt-5.2-codex` | 272K | 1.75/14 | ✅ |
| `gpt-5.3-codex` | 272K | 1.75/14 | ✅ |
| `gpt-5.4` | 1.05M | 2.5/15 | ✅ |
| `gpt-5.4-mini` | 272K | 0.75/4.5 | ✅ |
| `gpt-5.4-nano` | 272K | 0.2/1.25 | ✅ |

## Google Gemini
| Model ID | Context | Cost (in/out) | Reasoning |
|----------|---------|---------------|-----------|
| `gemini/gemini-2.5-flash` | 1M | 0.3/2.5 | ✅ |
| `gemini/gemini-2.5-flash-lite` | 1M | 0.1/0.4 | ✅ |
| `gemini/gemini-2.5-pro` | 1M | 1.25/10 | ✅ |
| `gemini/gemini-3-flash-preview` | 1M | 0.5/3 | ✅ |
| `gemini/gemini-3.1-flash-lite` | 1M | 0.25/1.5 | ✅ |
| `gemini/gemini-3.1-pro-preview` | 1M | 2/12 | ✅ |
| `gemini/gemini-3.5-flash` | 1M | 1.5/9 | ✅ |

## DeepSeek
| Model ID | Context | Cost (in/out) | Reasoning |
|----------|---------|---------------|-----------|
| `deepseek-v4-flash` | 1M | 0.14/0.28 | ✅ |
| `deepseek-v4-pro` | 1M | 0.435/0.87 | ✅ |

## Qwen (Alibaba)
| Model ID | Context | Cost (in/out) | Reasoning |
|----------|---------|---------------|-----------|
| `qwen3.6-flash` | 991K | 0.125/0.75 | ✅ |
| `qwen3.6-plus` | 991K | 0.25/1.5 | ✅ |
| `qwen3.7-max` | 991K | varies | ✅ |

## Xiaomi
| Model ID | Context | Cost (in/out) | Reasoning |
|----------|---------|---------------|-----------|
| `mimo-v2.5-pro` | varies | varies | ✅ |

## Recommended for Trading Agents

- **Technical / Sentiment (fast, cheap):** `deepseek-v4-flash`, `qwen3.6-flash`, `gpt-5-nano`
- **Fundamental / Risk (balanced):** `deepseek-v4-pro`, `qwen3.6-plus`, `gpt-5-mini`
- **Manager (strong reasoning):** `qwen3.7-max`, `gpt-5.1`, `gemini/gemini-2.5-pro`
- **Boss (review, heavy reasoning):** `claude-sonnet-4-6`, `gpt-5.2`

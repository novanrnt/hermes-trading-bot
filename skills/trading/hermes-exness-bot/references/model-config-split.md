# Model Config Split: Bot vs Duleh

## Architecture
The Hermes bot uses TWO separate config keys for models — they are NOT connected:

| Config key | Controls | Location in .yaml |
|------------|----------|-------------------|
| `model.default` | Duleh/Hermes chat responses (this agent) | Top-level under `model:` |
| `trading_model` | Bot orchestrator agents (scanner/reviewer) | Top-level, separate from `model:` |

## How Each One Works

### Bot (`trading_model`)
- Read by: `agent_orchestrator.py`, `kai_interactive.py`, `review_agent.py`
- Code path: `cfg.get("trading_model", model.get("default", "qwen3.7-max"))`
- If missing → falls back to `model.default`

### Duleh Chat (`model.default`)
- Read by: Hermes gateway directly
- Set via: `hermes config set model.default <name>` OR edit `config.yaml` directly
- Affects ALL chat interactions with this profile

## Switching Models

### Change Bot Scan Model (no impact on chat)
```bash
cd ~/AppData/Local/hermes
sed -i 's/trading_model: qwen3.7-plus/trading_model: deepseek-v4-pro/' config.yaml
grep trading_model config.yaml  # verify
```

### Change Chat Model (no impact on bot)
```bash
# Via CLI
hermes config set model.default deepseek-v4-flash
# Or direct edit
sed -i 's/default: qwen3.7-plus/default: deepseek-v4-flash/' config.yaml
grep "default:" config.yaml  # verify top-level default only
```

## Current Config (2026-07-01 update)
| Component | Model | Purpose |
|-----------|-------|---------|
| Bot Scan | `qwen3.7-plus` | Deep reasoning for market analysis |
| Kai Review | `qwen3.7-plus` (via `trading_model`) | Same reasoning tier as bot |
| Duleh Chat | `deepseek-v4-flash` | Fast, cheap casual responses |

## Why Split Matters
- Chat is chatty and happens frequently → needs cheapest/fastest model
- Bot scan runs ~every 2 hours but processes large payloads → benefits from deeper reasoning
- Changing `model.default` does NOT affect the bot if `trading_model` is explicitly set
- Changing `trading_model` does NOT affect chat at all

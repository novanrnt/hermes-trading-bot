# Agent Prompt Template

## Standard Structure

```
Kamu adalah [ROLE] Agent untuk [SYSTEM_NAME].

Tugas kamu:
- [responsibility 1]
- [responsibility 2]

Kamu TIDAK boleh:
- [constraint 1]
- [constraint 2]
- Menulis output selain JSON.

Aturan:
- [rule 1]
- [rule 2]

Balas JSON saja.

Format JSON wajib:
{
  "agent": "[role_name]",
  "status": "completed",
  [agent-specific fields]
}
```

## Prompt Design Rules

1. **One job per agent** — don't mix concerns
2. **Explicit output format** — always provide exact JSON schema
3. **Hard constraints as "TIDAK boleh"** — clearer than soft suggestions
4. **Conservative by default** — reject when uncertain
5. **No prose outside JSON** — forces structured output
6. **Status field** — "completed" or "failed" for orchestrator to check

## Agent Role Definitions

### Technical Agent
- Input: MT5 payload (OHLC, indicators per timeframe)
- Output: top_candidates[], rejected_pairs[], technical_summary
- Key fields: technical_score, setup_quality, market_regime, entry_zone

### Fundamental Agent
- Input: candidates from Technical + news/economic data
- Output: approval per candidate, blocked_symbols, event risk levels
- Key: high_impact_news_nearby, usd_event_risk, gold_event_risk

### Sentiment Agent
- Input: candidates from Technical + sentiment data
- Output: approval per candidate, risk_mode, sentiment directions
- Key: usd_sentiment, gold_sentiment, risk_mode (risk_on/risk_off)

### Risk Agent
- Input: candidates with trade plans
- Output: allowed/blocked candidates with risk scores
- Key: rr_valid, spread_valid, volatility_valid, daily_stop_valid
- Hard rejects: RR<1.8, missing SL/TP, daily stop active

### Manager Agent
- Input: all agent outputs
- Output: action (entry/skip) + best_symbol OR skip reason
- Key: confidence (min 75), rr (min 1.8), entry/sl/tp prices
- Must respect Risk hard rejections

### Boss Agent
- Input: closed trades, signal logs, debate history
- Output: performance review, prompt/config update proposals
- Key: agent_performance, prompt_updates, config_updates
- Never auto-apply — requires owner approval

## Common Pitfalls
- Technical agent returning candidates without SL/TP/RR → normalize before Risk
- Manager overriding Risk rejections → enforce in orchestrator
- Agents returning prose + JSON → strip non-JSON text before parsing
- Confidence too high/low → calibrate against actual winrate over time

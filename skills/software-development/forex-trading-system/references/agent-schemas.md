# Agent JSON Schemas — Hermes Exness Trading System v1.2

## Technical Agent
```json
{
  "agent": "technical",
  "status": "completed",
  "top_candidates": [{
    "symbol": "EURUSD",
    "side": "buy",
    "technical_score": 0.0,
    "setup_quality": "weak|medium|strong",
    "h4_bias": "bullish|bearish|neutral",
    "h1_structure": "bullish|bearish|neutral",
    "m15_setup": "desc",
    "m5_timing": "desc",
    "market_regime": "trending|ranging|volatile|unclear",
    "planned_entry_zone": "desc",
    "technical_reason": "reason"
  }],
  "rejected_pairs": [{"symbol": "GBPUSD", "reason": "reason"}],
  "technical_summary": "summary"
}
```

## Fundamental Agent
```json
{
  "agent": "fundamental",
  "status": "completed",
  "research_status": "completed|limited|failed",
  "approval": "approve|conditional|reject",
  "high_impact_news_nearby": true,
  "blocked_symbols": ["XAUUSD"],
  "usd_event_risk": "low|medium|high|unknown",
  "gold_event_risk": "low|medium|high|unknown",
  "candidate_reviews": [{"symbol": "EURUSD", "approval": "approve|conditional|reject", "reason": "reason"}],
  "fundamental_summary": "summary"
}
```

## Sentiment Agent
```json
{
  "agent": "sentiment",
  "status": "completed",
  "sentiment_status": "completed|limited|failed",
  "approval": "approve|conditional|reject",
  "usd_sentiment": "bullish|bearish|neutral|unknown",
  "gold_sentiment": "bullish|bearish|neutral|unknown",
  "risk_mode": "risk_on|risk_off|neutral|unknown",
  "candidate_reviews": [{"symbol": "EURUSD", "approval": "approve|conditional|reject", "reason": "reason"}],
  "sentiment_summary": "summary"
}
```

## Risk Agent
```json
{
  "agent": "risk",
  "status": "completed",
  "risk_status": "allowed|blocked|conditional",
  "allowed_candidates": [{
    "symbol": "EURUSD",
    "risk_score": 0,
    "approval": "approve|conditional|reject",
    "rr_valid": true,
    "spread_valid": true,
    "volatility_valid": true,
    "daily_stop_valid": true,
    "xauusd_stop_valid": true,
    "risk_note": "note"
  }],
  "blocked_candidates": [{"symbol": "XAUUSD", "reason": "reason"}],
  "risk_summary": "summary"
}
```

## Manager Agent — Entry
```json
{
  "action": "entry",
  "best_symbol": "EURUSD",
  "side": "buy|sell",
  "entry_type": "market|buy_limit|sell_limit",
  "planned_entry": 1.0852,
  "sl_price": 1.0832,
  "tp_price": 1.0892,
  "sl_points": 200,
  "tp_points": 400,
  "rr": 2.0,
  "confidence": 84,
  "technical_summary": "", "fundamental_summary": "", "sentiment_summary": "", "risk_summary": "",
  "manager_summary": "", "entry_reason": "", "sl_reason": "", "tp_reason": "",
  "why_best_pair": "", "risk_note": "",
  "rejected_pairs": [{"symbol": "GBPUSD", "reason": "reason"}]
}
```

## Manager Agent — Skip
```json
{
  "action": "skip",
  "reason": "reason",
  "technical_summary": "", "fundamental_summary": "", "sentiment_summary": "", "risk_summary": "",
  "manager_summary": "",
  "rejected_pairs": [{"symbol": "EURUSD", "reason": "reason"}]
}
```

## Boss Agent
```json
{
  "agent": "boss",
  "status": "completed",
  "review_batch": 1,
  "closed_trades": 0,
  "winrate": 0,
  "net_result": "positive|negative|breakeven|unknown",
  "main_findings": ["finding"],
  "agent_performance": {
    "technical_agent": "summary",
    "fundamental_agent": "summary",
    "sentiment_agent": "summary",
    "risk_agent": "summary",
    "manager_agent": "summary"
  },
  "prompt_updates": [{"target_agent": "agent", "change_type": "add_rule|tighten_rule|clarify_rule", "proposal": "proposal"}],
  "config_updates": [{"key": "config", "old_value": "old", "new_value": "new", "reason": "reason"}],
  "risk_warning": "warning",
  "approval_required": true
}
```

## Prompt Locations

All agent prompts stored at:
```
C:\Users\Administrator\AppData\Local\hermes\prompts\active\{agent_name}_agent_prompt.txt
```

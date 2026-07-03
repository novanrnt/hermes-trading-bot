# Sentiment Payload — Template & Integration Guide

## Static Template (Manual v1)

```json
{
  "status": "available",
  "source": "manual_static_v1",
  "timezone": "UTC",
  "updated_at": "2026-06-14T17:50:00+00:00",
  "market_mood": "neutral",
  "usd_bias": "neutral",
  "risk_mode": "neutral",
  "gold_sentiment": "neutral",
  "jpy_safe_haven_flow": "neutral",
  "equity_mood": "neutral",
  "us10y_yield_bias": "unknown",
  "dxy_bias": "neutral",
  "blocked_symbols": [],
  "caution_symbols": [],
  "notes": "Manual static sentiment payload. No strong risk-on/risk-off pressure loaded."
}
```

## Field Reference

| Field | Values | Description |
|-------|--------|-------------|
| `status` | `available`, `missing`, `error` | Payload availability |
| `source` | `manual_static_v1`, `api_<provider>` | Data source identifier |
| `market_mood` | `neutral`, `risk_on`, `risk_off`, `extreme_fear`, `panic` | Overall market sentiment |
| `usd_bias` | `bullish`, `bearish`, `neutral` | USD directional bias |
| `risk_mode` | `risk_on`, `risk_off`, `neutral` | Risk appetite |
| `gold_sentiment` | `bullish`, `bearish`, `neutral` | Gold (XAUUSD) sentiment |
| `jpy_safe_haven_flow` | `active`, `inactive`, `neutral` | JPY safe-haven demand |
| `equity_mood` | `bullish`, `bearish`, `neutral` | Equity market mood |
| `us10y_yield_bias` | `rising`, `falling`, `unknown` | US 10Y yield direction |
| `dxy_bias` | `bullish`, `bearish`, `neutral` | Dollar Index direction |
| `blocked_symbols` | `["XAUUSD", "USDJPY"]` | Symbols Sentiment Agent MUST reject |
| `caution_symbols` | `["EURUSD"]` | Symbols to flag but not hard-reject |

## Orchestrator Integration Code

```python
# Constants
SENTIMENT_PAYLOAD_PATH = HERMES_DIR / "sentiment_payload.json"

# Loader function
def load_sentiment_payload() -> dict:
    if not SENTIMENT_PAYLOAD_PATH.exists():
        return {"status": "missing", "source": "not_found"}
    try:
        with open(SENTIMENT_PAYLOAD_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        blocked = data.get("blocked_symbols", [])
        data["_has_blocked_symbols"] = len(blocked) > 0
        mood = data.get("market_mood", "unknown")
        data["_is_extreme_risk_off"] = mood.lower() in ("extreme_fear", "risk_off", "panic")
        return data
    except Exception as e:
        return {"status": "error", "source": "load_failed"}

# In _run_stages(), before Sentiment Agent:
sentiment_payload = load_sentiment_payload()
self.cycle_log.sentiment_payload = sentiment_payload
sent = self._run_agent("sentiment_agent", build_sentiment_prompt(tech_out, sentiment_payload))

# Updated prompt builder:
def build_sentiment_prompt(technical_output: dict, sentiment_payload: dict = None) -> str:
    prompt = load_prompt("sentiment_agent")
    candidates = technical_output.get("top_candidates", [])
    if sentiment_payload and sentiment_payload.get("status") != "missing":
        sent_str = json.dumps(sentiment_payload, indent=2)
    else:
        sent_str = "No sentiment payload provided."
    return (
        f"{prompt}\n\n"
        f"SENTIMENT PAYLOAD:\n{sent_str}\n\n"
        f"TECHNICAL CANDIDATES:\n{json.dumps(candidates, indent=2)}\n\n"
        f"Respond ONLY with the required JSON. No markdown, no explanation."
    )
```

## Telegram Reporter Integration

```python
def _load_sentiment_payload():
    sent_path = BASE_DIR / "sentiment_payload.json"
    if not sent_path.exists():
        return None
    try:
        with open(sent_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        blocked = data.get("blocked_symbols", [])
        data["_has_blocked_symbols"] = len(blocked) > 0
        return data
    except Exception:
        return None
```

Report section output:
```
Sentiment Status:
  Status: available
  Market Mood: neutral
  USD Bias: neutral
  Risk Mode: neutral
  Blocked Symbols: none
```

## Future Upgrades

- CFTC COT data (net speculative positions)
- Fear & Greed Index (CNN/alternative.me)
- VIX level for risk-on/off detection
- News sentiment scoring (NLP on headlines)
- Social media sentiment (Twitter/X, Reddit)

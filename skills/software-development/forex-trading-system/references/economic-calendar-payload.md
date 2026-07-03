# Economic Calendar Payload Reference

## Template (copy as `economic_calendar_payload.json`)

```json
{
  "status": "available",
  "source": "manual_static_v1",
  "timezone": "UTC",
  "updated_at": "",
  "events": [
    {
      "date": "YYYY-MM-DD",
      "time_utc": "HH:MM",
      "currency": "USD",
      "impact": "low|medium|high",
      "event": "Event name",
      "actual": null,
      "forecast": null,
      "previous": null,
      "risk_window_before_minutes": 60,
      "risk_window_after_minutes": 60
    }
  ],
  "rules": {
    "block_high_impact_before_minutes": 60,
    "block_high_impact_after_minutes": 60,
    "allow_if_no_high_impact": true,
    "unknown_news_policy": "conditional_not_reject"
  }
}
```

## Field Reference

| Field | Required | Description |
|-------|----------|-------------|
| status | yes | `available`, `missing`, or `error` |
| source | yes | `manual_static_v1`, `forexfactory_scrape`, `api`, etc. |
| timezone | yes | Timezone of event times (usually `UTC`) |
| updated_at | yes | ISO timestamp of last update |
| events[].date | yes | Event date `YYYY-MM-DD` |
| events[].time_utc | yes | Event time `HH:MM` in UTC |
| events[].currency | yes | 3-letter currency code (`USD`, `EUR`, `JPY`, etc.) |
| events[].impact | yes | `low`, `medium`, `high` |
| events[].event | yes | Human-readable event name |
| events[].actual | no | Actual value (null if not yet released) |
| events[].forecast | no | Forecast/consensus value |
| events[].previous | no | Previous release value |
| events[].risk_window_before_minutes | no | Minutes before event to block entry (default: 60) |
| events[].risk_window_after_minutes | no | Minutes after event to block entry (default: 60) |

## Computed Fields (added by orchestrator at runtime)

These are NOT in the file — they're computed by `load_economic_calendar()`:

| Field | Type | Description |
|-------|------|-------------|
| _high_impact_nearby | bool | True if any event has `impact == "high"` |
| _blocked_currencies | list | Unique currencies from high-impact events |

## Orchestrator Code Pattern

```python
def load_economic_calendar() -> dict:
    if not NEWS_CALENDAR_PATH.exists():
        return {"status": "missing", "source": "not_found", "events": [], "rules": {}}
    try:
        with open(NEWS_CALENDAR_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        events = data.get("events", [])
        high_impact = [e for e in events if e.get("impact", "").lower() == "high"]
        data["_high_impact_nearby"] = len(high_impact) > 0
        data["_blocked_currencies"] = list(set(
            e.get("currency", "") for e in high_impact
        ))
        return data
    except Exception as e:
        return {"status": "error", "source": "load_failed", "events": [], "rules": {}}
```

## Integration Points

- **Orchestrator**: Load before Fundamental Agent, pass to `build_fundamental_prompt()`
- **CycleLog**: Store in `news_payload` field, saved to debate log
- **Telegram Reporter**: `_load_news_payload()` helper reads same file for News Status section
- **Debate Log**: Full `news_payload` dict saved for audit trail

## Future: Auto-Refresh Sources

| Source | Pros | Cons |
|--------|------|------|
| ForexFactory scrape | Free, comprehensive | HTML structure changes often |
| Trading Economics API | Reliable, structured | Paid for full access |
| Investing.com calendar | Free, detailed | Aggressive anti-scraping |
| MQL5 economic calendar | Native MT5 integration | Limited API access |

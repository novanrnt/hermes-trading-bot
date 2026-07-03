# Telegram Bot API Patterns for Trading Reports

## Parse Mode Decision

**2026-06-14: parse_mode REMOVED entirely.**

### Problem
Telegram's Markdown parse mode breaks on special characters in dynamic agent output:
- Parentheses `()` in text like `EMA50(1.0842)`
- Underscores `_` in variable names or technical terms
- Asterisks `*` in bullet points or emphasis
- Square brackets `[]` in log references
- Tildes `~` in strikethrough or approximations

Results in `HTTP Error 400: Bad Request` — message never delivers.

### Solution
Remove `parse_mode` entirely from the API payload. Plain text delivers reliably.

```python
payload = json.dumps({
    "chat_id": chat_id,
    "text": message,
    "disable_web_page_preview": True
}).encode("utf-8")
```

### If formatting is needed later
Use `parse_mode: "HTML"` which only requires escaping `<`, `>`, `&`:
```python
import html
safe_text = html.escape(raw_text)
message = f"<b>Action:</b> {safe_text}"
```

## Message Length Limit
Telegram messages max 4096 chars. Trading reports with full agent summaries can exceed this.
- Truncate each agent summary to 150 chars
- Truncate entry/reason fields to 250 chars
- If still too long, split into multiple messages or shorten further

## Bot Token Security
- NEVER print, log, or return the bot token
- Read from `.env` silently
- If token missing, print "Token: MISSING" without revealing partial values
- The notifier bot (@SignalFxNotif_bot) is SEPARATE from the main Hermes bot

## Reliable Delivery Pattern
```python
try:
    with urllib.request.urlopen(req, timeout=30) as resp:
        result = json.loads(resp.read().decode("utf-8"))
        return result.get("ok", False)
except urllib.error.URLError as e:
    # Save report locally even if Telegram fails
    save_report_text(report_text)
    return False
```

## Testing
```bash
python telegram_reporter.py --test          # Verify bot connectivity
python telegram_reporter.py --send-latest   # Send latest decision report
```

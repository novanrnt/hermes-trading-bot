# Telegram Forum Topic Routing

## Problem

When both the main Hermes command bot and @SignalFxNotif_bot live in the same Telegram group with forum topics, all bot messages land in the General topic by default. This clutters the main thread and mixes bot commands with trading notifications.

## Solution

Route every message type to its own forum topic using `message_thread_id`. Each topic gets a stable ID assigned by Telegram at creation time.

### Topic Layout (RNT AUTOTRADE)

| Topic Name | Thread ID | Env Var | Purpose |
|-----------|-----------|---------|---------|
| 📊 Trading Report | 2 | `TELEGRAM_TOPIC_TRADING_REPORT` | Cycle results, scheduler armed/started, dry-run outcomes |
| 🤖 Duleh Command | 3 | `TELEGRAM_TOPIC_DULEH_COMMAND` | Bot command responses (handled by Hermes gateway) |
| 🧠 Agent Debate | 4 | `TELEGRAM_TOPIC_AGENT_DEBATE` | Detailed agent reasoning (future) |
| 🚨 Error & Alert | 5 | `TELEGRAM_TOPIC_ERROR_ALERT` | Cycle errors, scheduler crashes, MT5 failures |
| 👑 Owner Room | 6 | `TELEGRAM_TOPIC_OWNER_ROOM` | Private owner channel |
| 🧪 Demo Execution | 15 | `TELEGRAM_TOPIC_DEMO_EXECUTION` | Demo order executed/blocked/error |

### .env Variables

```
TELEGRAM_GROUP_CHAT_ID=-1004396608984
TELEGRAM_TOPIC_TRADING_REPORT=2
TELEGRAM_TOPIC_DULEH_COMMAND=3
TELEGRAM_TOPIC_AGENT_DEBATE=4
TELEGRAM_TOPIC_ERROR_ALERT=5
TELEGRAM_TOPIC_OWNER_ROOM=6
TELEGRAM_TOPIC_DEMO_EXECUTION=15
```

### Implementation Pattern

```python
def send_to_topic(topic_name: str, message: str) -> bool:
    """Send message to a specific forum topic. Falls back to main chat."""
    env = load_env()
    token = env["TELEGRAM_NOTIFY_BOT_TOKEN"]
    chat_id = env.get("TELEGRAM_GROUP_CHAT_ID") or env.get("TELEGRAM_NOTIFY_CHAT_ID")
    thread_id = env.get(f"TELEGRAM_TOPIC_{topic_name.upper()}", "")
    
    payload = {"chat_id": chat_id, "text": message, "disable_web_page_preview": True}
    if thread_id:
        payload["message_thread_id"] = int(thread_id)
    
    # POST to https://api.telegram.org/bot{token}/sendMessage
```

### Discovering Thread IDs

1. Owner sends a test message in each topic
2. Run `python telegram_reporter.py --debug-updates`
3. Captures: chat_id, message_thread_id, sample text
4. Maps thread_id to topic by matching test message content
5. Populate .env variables

**Pitfall**: `--debug-updates` may show empty "Sample" text if messages were sent too long ago or the update offset window missed them.

**Fallback — direct API probe**: If `--debug-updates` doesn't capture all threads (e.g., messages have empty text field, or some threads aren't in the update list), probe each candidate thread_id via direct API call. Send a test message to each unknown thread_id and check if the API accepts it:

```python
import json, urllib.request

# For each unknown candidate thread_id:
for tid in [1, 3, 7, 8, 9, 10, 11, 12, 13, 14, 16]:
    data = json.dumps({
        'chat_id': GROUP_CHAT_ID,
        'message_thread_id': tid,
        'text': f'[CHECK] testing thread {tid}'
    }).encode()
    req = urllib.request.Request(url, data=data, headers={'Content-Type': 'application/json'}, method='POST')
    resp = json.loads(urllib.request.urlopen(req, timeout=5).read())
    if resp.get('ok'):
        print(f'Thread {tid}: EXISTS')
    else:
        print(f'Thread {tid}: {resp.get("description", "")}')
```

**Note**: Telegram thread_id 1 (General) may return HTTP 400 for bots — this is normal. Thread IDs skip around (e.g., 2, 3, 4, 5, 6, 15) because deleted topics leave gaps in the ID sequence.

**Critical**: NEVER print the bot token in debug output. The `--debug-updates` command strips it automatically.

### `load_env()` Caching Pitfall

When `load_env()` uses `if key not in os.environ`, variables set to empty strings during a previous load are SKIPPED on subsequent calls — `os.environ` contains them with value `""`, so `key not in os.environ` is `False`. This causes the reporter to show "Chat ID: MISSING" even after `.env` has been properly populated.

**Fix**: Change the guard from `if key not in os.environ` to `if key not in os.environ or not os.environ[key]`. This allows overwriting empty/None values. Apply to both `telegram_reporter.py` and `trade_executor_demo.py`.

```python
# BROKEN — skips re-read on cached empty strings
if key not in os.environ:
    os.environ[key] = value

# FIXED — overwrites empty values
if key not in os.environ or not os.environ[key]:
    os.environ[key] = value
```

### Routing Map (who sends where)

| Source File | Message Type | Topic |
|------------|-------------|-------|
| `run_decision_cycle.py` | Cycle complete + decision report | 📊 Trading Report |
| `cycle_scheduler.py` | Scheduler armed / waiting | 📊 Trading Report |
| `cycle_scheduler.py` | Cycle error | 🚨 Error & Alert |
| `cycle_scheduler.py` | Scheduler crash | 🚨 Error & Alert |
| `cycle_scheduler.py` | Demo executor BLOCKED | 🧪 Demo Execution |
| `trade_executor_demo.py` | CHECK PASSED / BLOCKED | 🧪 Demo Execution |
| `trade_executor_demo.py` | DEMO EXECUTED / ERROR | 🧪 Demo Execution |
| `telegram_reporter.py` | Decision report (final) | 📊 Trading Report |

### Integration Points

- `telegram_reporter.py`: exports `send_to_topic(topic_name, message)` and `send_trading_alert(message)` for backward compat
- `trade_executor_demo.py`: calls `send_demo_execution_report()` → routes to demo_execution topic
- `cycle_scheduler.py`: `send_telegram(msg, topic)` → routes based on message type
- `run_decision_cycle.py`: calls `telegram_reporter.py --send-latest` → routes to trading_report

### Testing

```bash
python telegram_reporter.py --test-topic trading_report
python telegram_reporter.py --test-topic error_alert
python telegram_reporter.py --test-topic demo_execution
```

## Message Tracking & Auto-Cleanup

Bot messages sent via `sendMessage` API are NOT retrievable via `getUpdates` — `getUpdates` only returns incoming messages (users sending TO the bot), not the bot's own outgoing messages. This means bot messages cannot be retroactively found or deleted unless their `message_id` is saved at send time.

### Solution: Save on Send, Delete on Demand

`telegram_reporter.py` maintains `logs/sent_message_ids.json` — a JSON array of `{chat_id, message_id, thread_id, time}` appended on every successful send.

**Send** (`send_telegram` is patched):
```python
if ok:
    msg_id = result.get("result", {}).get("message_id")
    if msg_id:
        _save_sent_id(chat_id, msg_id, thread_id)
```

**Delete** (`--clear-recent`):
```bash
python telegram_reporter.py --clear-recent
```

Iterates `sent_message_ids.json`, calls `deleteMessage` API for each entry. 200-entry ring buffer. After deletion, file is cleared.

### Why Not getUpdates

```python
# getUpdates only returns messages FROM users TO the bot
# The bot's own sent messages are INVISIBLE here
url = f"https://api.telegram.org/bot{token}/getUpdates"
# → returns user messages, never bot messages
```

Always save the `message_id` from the `sendMessage` response. There is no other way to delete bot-sent messages via API.

### Broader Pattern

Any function that calls `send_telegram` automatically tracks IDs. Cleanup is one command. For testing/simulation sessions, send → verify → clear in one flow:

```bash
python telegram_reporter.py --test-topic trading_report
python telegram_reporter.py --test-topic error_alert
python telegram_reporter.py --clear-recent
```

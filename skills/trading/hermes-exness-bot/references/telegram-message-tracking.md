# Telegram Message Tracking & Auto-Cleanup

## Problem
Bot sends messages to forum topics during testing/debugging. Those messages clutter the topics. We need a way to auto-delete them after testing.

## The `getUpdates` trap
`getUpdates` only returns **incoming** messages (from users TO the bot). It does NOT return the bot's own outgoing messages. So you can't retroactively find bot messages to delete.

## Solution: Save message_id on send, delete by ID

### 1. Save message_id on send
```python
# In send_telegram(), capture the message_id from the API response
if ok:
    msg_id = result.get("result", {}).get("message_id")
    if msg_id:
        _save_sent_id(chat_id, msg_id, thread_id)
```

### 2. Store in JSON
```python
def _save_sent_id(chat_id, msg_id, thread_id):
    # Append to logs/sent_message_ids.json
    # Keep last 200 entries only
```

### 3. Delete via --clear-recent
```python
# Read logs/sent_message_ids.json
# For each entry: DELETE https://api.telegram.org/bot{token}/deleteMessage
# Clear the file after deletion
```

## Usage
```bash
python telegram_reporter.py --clear-recent   # Deletes last 100 tracked messages
```

## Note
Messages sent BEFORE tracking was added cannot be deleted by the bot. Those must be manually removed by the user.

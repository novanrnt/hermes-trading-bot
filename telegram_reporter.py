#!/usr/bin/env python3
"""
Telegram Reporter for Hermes Exness Trading System v1.2
=======================================================
Supports forum topic routing for group-based organization.
Topics: trading_report, error_alert, demo_execution, agent_debate, owner_room, kai_room
"""
import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime
from pathlib import Path
from typing import Optional

# === PATHS ===
BASE_DIR = Path(os.environ.get("HERMES_HOME", r"C:\Users\Administrator\AppData\Local\hermes"))
FINAL_DECISION_FILE = BASE_DIR / "final_decision.json"
LOGS_DIR = BASE_DIR / "logs"
CYCLES_DIR = LOGS_DIR / "cycles"
DRYRUN_DIR = LOGS_DIR / "dry_run"
DEBATES_DIR = LOGS_DIR / "agent_debates"
TELEGRAM_REPORTS_DIR = LOGS_DIR / "telegram_reports"

# === TOPIC KEY → ENV VAR MAPPING ===
TOPIC_KEYS = {
    "trading_report": "TELEGRAM_TOPIC_TRADING_REPORT",
    "duleh_command": "TELEGRAM_TOPIC_DULEH_COMMAND",
    "error_alert": "TELEGRAM_TOPIC_ERROR_ALERT",
    "demo_execution": "TELEGRAM_TOPIC_DEMO_EXECUTION",
    "agent_debate": "TELEGRAM_TOPIC_AGENT_DEBATE",
    "owner_room": "TELEGRAM_TOPIC_OWNER_ROOM",
    "kai_room": "TELEGRAM_TOPIC_KAI_ROOM",
    "learning": "TELEGRAM_TOPIC_LEARNING",
}


def load_env():
    """Load .env file variables into os.environ (simple parser, no dependency)."""
    env_path = BASE_DIR / ".env"
    if not env_path.exists():
        return
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key, _, value = line.partition("=")
                key = key.strip()
                value = value.strip()
                if key and (key not in os.environ or not os.environ[key]):
                    os.environ[key] = value


def get_token():
    return os.environ.get("TELEGRAM_NOTIFY_BOT_TOKEN", "")

def get_group_chat_id():
    return os.environ.get("TELEGRAM_GROUP_CHAT_ID",
                          os.environ.get("TELEGRAM_NOTIFY_CHAT_ID", ""))

def get_topic_id(topic_key: str) -> Optional[str]:
    """Get message_thread_id for a topic from .env."""
    env_var = TOPIC_KEYS.get(topic_key, "")
    if not env_var:
        return None
    val = os.environ.get(env_var, "").strip()
    return val if val else None

def is_enabled():
    return os.environ.get("TELEGRAM_NOTIFY_ENABLED", "false").lower() == "true"


# === HELPERS ===
def get_latest_file(directory, pattern="*.json"):
    if not directory.exists():
        return None
    files = sorted(directory.glob(pattern), key=lambda f: f.stat().st_mtime, reverse=True)
    return files[0] if files else None

def load_json(path):
    if not path or not path.exists():
        return None
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return None

def _load_news_payload():
    from datetime import datetime as _dt, timezone as _tz, timedelta as _td
    news_path = BASE_DIR / "economic_calendar_payload.json"
    if not news_path.exists():
        return None
    try:
        with open(news_path, "r", encoding="utf-8") as f:
            data = json.load(f)
        events = data.get("events", [])
        # Only block currencies from BIG news events within ±2 hours
        _now = _dt.now(_tz.utc)
        _blocked = []
        for e in events:
            if e.get("impact", "").lower() != "high" or not e.get("big_news", False):
                continue
            _edate = e.get("date", "")
            _etime = e.get("time_utc", "00:00")
            try:
                _evt_dt = _dt.strptime(f"{_edate} {_etime}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=_tz.utc)
            except Exception:
                continue
            if abs((_evt_dt - _now).total_seconds()) <= 7200:
                _blocked.append(e.get("currency", ""))
        data["_high_impact_nearby"] = len(_blocked) > 0
        data["_blocked_currencies"] = list(set(_blocked))
        return data
    except Exception:
        return None

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


# === CORE SEND ===
SENT_IDS_FILE = BASE_DIR / "logs" / "sent_message_ids.json"


def _save_sent_id(chat_id: str, msg_id: int, thread_id: str = ""):
    """Save sent message ID so it can be deleted later."""
    SENT_IDS_FILE.parent.mkdir(parents=True, exist_ok=True)
    ids = []
    if SENT_IDS_FILE.exists():
        try:
            with open(SENT_IDS_FILE, "r") as f:
                ids = json.load(f)
        except Exception:
            ids = []
    ids.append({
        "chat_id": str(chat_id),
        "message_id": msg_id,
        "thread_id": str(thread_id) if thread_id else "",
        "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    # keep last 200 only
    if len(ids) > 200:
        ids = ids[-200:]
    with open(SENT_IDS_FILE, "w") as f:
        json.dump(ids, f, indent=2)


def send_telegram(token: str, chat_id: str, message: str, thread_id: Optional[str] = None) -> bool:
    """Send message via Bot API. If thread_id provided, sends to that forum topic."""
    payload_dict = {
        "chat_id": chat_id,
        "text": message,
        "disable_web_page_preview": True,
        "parse_mode": "HTML",
    }
    if thread_id:
        try:
            payload_dict["message_thread_id"] = int(thread_id)
        except (ValueError, TypeError):
            pass

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps(payload_dict).encode("utf-8")

    req = urllib.request.Request(url, data=data,
                                  headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            ok = result.get("ok", False)
            if ok:
                msg_id = result.get("result", {}).get("message_id")
                if msg_id:
                    _save_sent_id(chat_id, msg_id, thread_id)
            return ok
    except urllib.error.URLError as e:
        print(f"[ERROR] Telegram API error: {e}")
        return False
    except Exception as e:
        print(f"[ERROR] Failed to send: {e}")
        return False


def send_to_topic(topic_key: str, message: str) -> bool:
    """Send message to a specific forum topic. Falls back to main chat if no topic ID."""
    load_env()
    if not is_enabled():
        print(f"[INFO] Notifier disabled — message not sent to '{topic_key}'")
        return False

    token = get_token()
    chat_id = get_group_chat_id()
    thread_id = get_topic_id(topic_key)

    if not token or not chat_id:
        print(f"[ERROR] Token or chat_id missing — cannot send to '{topic_key}'")
        return False

    dest = f"topic {thread_id}" if thread_id else "main chat"
    print(f"[TG] → {topic_key} ({dest})")
    return send_telegram(token, chat_id, message, thread_id)


def get_kai_token():
    return os.environ.get("TELEGRAM_KAI_BOT_TOKEN", "")


def send_kai_message(topic_key: str, message: str) -> bool:
    """Send message using Kai's own bot token. Falls back to main bot if not set."""
    load_env()
    token = get_kai_token()
    if not token:
        # Fallback to main bot
        return send_to_topic(topic_key, message)

    chat_id = get_group_chat_id()
    thread_id = get_topic_id(topic_key)

    if not chat_id:
        print(f"[Kai] Chat ID missing — cannot send to '{topic_key}'")
        return False

    dest = f"topic {thread_id}" if thread_id else "main chat"
    print(f"[Kai Bot] → {topic_key} ({dest})")
    return send_telegram(token, chat_id, message, thread_id)


# === REPORTS ===
def format_report(final_decision, cycle_log=None, dryrun_log=None, debate_log=None):
    action = final_decision.get("action", "unknown").upper()
    mode = final_decision.get("mode", "UNKNOWN").upper()
    safety_gate = final_decision.get("safety_gate", "unknown")
    timestamp = final_decision.get("timestamp", datetime.now().isoformat())

    lines = ["📊 Hermes Exness v1.2 Decision Report", ""]
    lines.append(f"Final Action: {action}")
    lines.append(f"Mode: {mode}")
    lines.append(f"Time: {timestamp}")

    # News
    news_payload = _load_news_payload()
    lines.append(""); lines.append("News Status:")
    if news_payload and news_payload.get("status") != "missing":
        lines.append(f"  Status: {news_payload.get('status', 'unknown')}")
        lines.append(f"  High Impact Nearby: {'YES' if news_payload.get('_high_impact_nearby') else 'No'}")
        blocked = news_payload.get("_blocked_currencies", [])
        lines.append(f"  Blocked Currencies: {', '.join(blocked) if blocked else 'none'}")
    else:
        lines.append(f"  Status: missing")

    # Sentiment
    sentiment_payload = _load_sentiment_payload()
    lines.append(""); lines.append("Sentiment Status:")
    if sentiment_payload and sentiment_payload.get("status") != "missing":
        lines.append(f"  Status: {sentiment_payload.get('status', 'unknown')}")
        lines.append(f"  Market Mood: {sentiment_payload.get('market_mood', 'unknown')}")
        lines.append(f"  USD Bias: {sentiment_payload.get('usd_bias', 'unknown')}")
        lines.append(f"  Risk Mode: {sentiment_payload.get('risk_mode', 'unknown')}")
        blocked_syms = sentiment_payload.get("blocked_symbols", [])
        lines.append(f"  Blocked Symbols: {', '.join(blocked_syms) if blocked_syms else 'none'}")
    else:
        lines.append(f"  Status: missing")

    # Candidate
    if action == "ENTRY":
        lines.append(""); lines.append("Candidate:")
        lines.append(f"  Symbol: {final_decision.get('best_symbol', 'N/A')}")
        lines.append(f"  Side: {final_decision.get('side', 'N/A')}")
        lines.append(f"  Entry: {final_decision.get('planned_entry', 'N/A')}")
        lines.append(f"  SL: {final_decision.get('sl_price', 'N/A')}")
        lines.append(f"  TP: {final_decision.get('tp_price', 'N/A')}")
        lines.append(f"  RR: {final_decision.get('rr', 'N/A')}")
        lines.append(f"  Confidence: {final_decision.get('confidence', 'N/A')}")
    elif action == "SKIP":
        lines.append(f"  Reason: {final_decision.get('reason', 'N/A')[:200]}")

    # Agent summaries
    lines.append(""); lines.append("Agent Summary:")
    for label, key in [("Technical", "technical_summary"), ("Fundamental", "fundamental_summary"),
                         ("Sentiment", "sentiment_summary"), ("Risk", "risk_summary"),
                         ("Manager", "manager_summary")]:
        val = final_decision.get(key, final_decision.get("reason", "N/A"))
        lines.append(f"  {label}: {val[:150]}")

    entry_reason = final_decision.get("entry_reason", "")
    if entry_reason:
        lines.append(""); lines.append("Entry Reason:")
        lines.append(f"  {entry_reason[:250]}")

    lines.append(""); lines.append("Safety:")
    lines.append(f"  Safety Gate: {safety_gate}")
    lines.append(f"  Execution Allowed: {final_decision.get('execution_allowed', False)}")
    lines.append(f"  Real Execution: OFF")

    lines.append(""); lines.append("Logs:")
    if debate_log: lines.append(f"  Debate: {debate_log.name}")
    if dryrun_log: lines.append(f"  Dry-run: {dryrun_log.name}")
    if cycle_log: lines.append(f"  Cycle: {cycle_log.name}")

    return "\n".join(lines)


def save_report_text(report_text):
    TELEGRAM_REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"telegram_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    filepath = TELEGRAM_REPORTS_DIR / filename
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(report_text)
    return filepath


def send_latest():
    """Load latest decision and send to TRADING_REPORT topic."""
    load_env()
    if not is_enabled():
        print("[INFO] Telegram reporter disabled")
        return False

    token = get_token()
    chat_id = get_group_chat_id()
    if not token or not chat_id:
        print("[ERROR] Token or chat_id not set")
        return False

    final_decision = load_json(FINAL_DECISION_FILE)
    if not final_decision:
        print("[ERROR] No final_decision.json")
        return False

    cycle_log = get_latest_file(CYCLES_DIR)
    dryrun_log = get_latest_file(DRYRUN_DIR)
    debate_log = get_latest_file(DEBATES_DIR)
    report_text = format_report(final_decision, cycle_log, dryrun_log, debate_log)

    report_path = save_report_text(report_text)
    print(f"[REPORT] Saved: {report_path}")

    # Send to TRADING_REPORT topic
    thread_id = get_topic_id("trading_report")
    ok = send_telegram(token, chat_id, report_text, thread_id)
    dest = f"topic {thread_id}" if thread_id else "main chat"
    if ok:
        print(f"[OK] Report sent to {dest}")
    else:
        print(f"[WARN] Failed to send to {dest}")
    return ok


def send_error(message: str):
    """Send error message to ERROR_ALERT topic."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S WIB")
    text = f"🚨 Hermes Exness Error\n\nTime: {ts}\n{message}"
    return send_to_topic("error_alert", text)


def send_demo_report(text: str):
    """Send demo execution report to DEMO_EXECUTION topic."""
    return send_to_topic("demo_execution", text)


def send_trading_alert(message: str):
    """Send trading-related message to TRADING_REPORT topic."""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S WIB")
    text = f"⏰ {message}\n\nTime: {ts}"
    return send_to_topic("trading_report", text)


# === DEBUG: Fetch Updates ===
def cmd_debug_updates():
    """Fetch recent updates from Telegram and display chat/thread info."""
    load_env()
    token = get_token()
    if not token:
        print("[ERROR] Token not set")
        return

    url = f"https://api.telegram.org/bot{token}/getUpdates"
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[ERROR] Failed to fetch updates: {e}")
        return

    if not data.get("ok"):
        print(f"[ERROR] API returned: {data}")
        return

    updates = data.get("result", [])
    if not updates:
        print("[INFO] No recent updates. Send a message in the group/topics first.")
        return

    print(f"\n{'='*70}")
    print(f"  Recent Telegram Updates ({len(updates)} total)")
    print(f"{'='*70}\n")

    seen_chats = {}
    for upd in updates[-20:]:  # last 20
        msg = upd.get("message", {})
        if not msg:
            continue

        chat = msg.get("chat", {})
        chat_id = chat.get("id", "")
        chat_title = chat.get("title", chat.get("first_name", ""))
        chat_type = chat.get("type", "")
        thread_id = msg.get("message_thread_id", msg.get("is_topic_message", False))
        text = (msg.get("text", msg.get("caption", "")) or "")[:80]
        author = msg.get("from", {}).get("first_name", msg.get("author_signature", ""))

        key = f"{chat_id}:{thread_id}" if thread_id else str(chat_id)
        if key not in seen_chats:
            seen_chats[key] = {
                "chat_id": chat_id,
                "chat_title": chat_title,
                "chat_type": chat_type,
                "thread_id": thread_id if thread_id else None,
                "sample_text": text,
            }

    for key, info in seen_chats.items():
        print(f"Chat ID:    {info['chat_id']}")
        print(f"Title:      {info['chat_title']}")
        print(f"Type:       {info['chat_type']}")
        if info['thread_id']:
            print(f"Thread ID:  {info['thread_id']}")
        print(f"Sample:     {info['sample_text'][:60]}")
        print("-" * 50)

    # Summary for .env
    print(f"\n{'='*70}")
    print("  For .env — copy these:")
    print(f"{'='*70}")
    group_id = ""
    for key, info in seen_chats.items():
        if info['chat_type'] in ("supergroup", "group"):
            group_id = str(info['chat_id'])
            print(f"\nTELEGRAM_GROUP_CHAT_ID={info['chat_id']}")
            print(f"# Group: {info['chat_title']}")
            if info['thread_id']:
                print(f"# Topic thread_id: {info['thread_id']}")
                print(f"# Sample: {info['sample_text'][:50]}")
    print()


def cmd_test_topic(topic_key: str):
    """Send a test message to a specific topic."""
    if topic_key not in TOPIC_KEYS:
        print(f"Unknown topic: {topic_key}")
        print(f"Valid topics: {', '.join(TOPIC_KEYS.keys())}")
        return

    load_env()
    if not is_enabled():
        print("[INFO] Notifier disabled")
        return

    thread_id = get_topic_id(topic_key)
    chat_id = get_group_chat_id()
    token = get_token()

    print(f"Token: {'SET' if token else 'MISSING'}")
    print(f"Chat ID: {chat_id or 'MISSING'}")
    print(f"Topic '{topic_key}' thread_id: {thread_id or 'NOT SET (main chat)'}")

    emoji_map = {
        "trading_report": "📊",
        "duleh_command": "🤖",
        "error_alert": "🚨",
        "demo_execution": "🧪",
        "agent_debate": "🧠",
        "owner_room": "👑",
        "kai_room": "🎯",
    }
    emoji = emoji_map.get(topic_key, "📌")
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S WIB")
    text = f"{emoji} Test message for topic: <b>{topic_key}</b>\n\nTime: {ts}\nStatus: OK"

    if thread_id:
        print(f"Sending to thread {thread_id}...")
    else:
        print("No thread_id set, sending to main chat...")

    ok = send_telegram(token, chat_id, text, thread_id)
    if ok:
        print(f"[OK] Test sent to '{topic_key}'")
    else:
        print(f"[FAIL] Could not send to '{topic_key}'")


# === CLI ===
def cmd_clear_recent():
    """Delete recently sent bot messages using saved message IDs."""
    load_env()
    token = get_token()
    if not token:
        print("[ERROR] Token not set")
        return

    if not SENT_IDS_FILE.exists():
        print("[INFO] No sent messages tracked yet")
        return

    try:
        with open(SENT_IDS_FILE, "r") as f:
            ids = json.load(f)
    except Exception:
        print("[ERROR] Cannot read sent IDs")
        return

    if not ids:
        print("[INFO] No messages to clear")
        return

    deleted = 0
    failed = 0
    for entry in ids[-100:]:  # last 100
        msg_id = entry.get("message_id")
        chat_id = entry.get("chat_id")
        tid = entry.get("thread_id", "")
        if not msg_id or not chat_id:
            continue

        url = f"https://api.telegram.org/bot{token}/deleteMessage"
        payload = json.dumps({"chat_id": chat_id, "message_id": msg_id}).encode()
        req = urllib.request.Request(url, data=payload,
                                      headers={"Content-Type": "application/json"})
        try:
            result = json.loads(urllib.request.urlopen(req, timeout=5).read())
            if result.get("ok"):
                deleted += 1
            else:
                failed += 1
        except Exception:
            failed += 1

    print(f"\n[DONE] Deleted: {deleted}, Failed: {failed}")
    # clear the file after deletion
    SENT_IDS_FILE.unlink(missing_ok=True)


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python telegram_reporter.py --test               Send test message")
        print("  python telegram_reporter.py --send-latest        Send latest decision report")
        print("  python telegram_reporter.py --debug-updates      Show chat/thread IDs from updates")
        print("  python telegram_reporter.py --test-topic <name>  Test-send to a topic")
        print("")
        print("Topics: trading_report, duleh_command, error_alert, demo_execution, agent_debate, owner_room")
        sys.exit(1)

    cmd = sys.argv[1]

    if cmd == "--test":
        load_env()
        token = get_token()
        chat_id = os.environ.get("TELEGRAM_NOTIFY_CHAT_ID", "")
        enabled = os.environ.get("TELEGRAM_NOTIFY_ENABLED", "false").lower()

        print(f"[STATUS] Enabled: {enabled}")
        print(f"[STATUS] Token: {'SET' if token else 'MISSING'}")

        if enabled != "true":
            print("[INFO] Telegram reporter disabled")
            return
        if not token or not chat_id:
            print("[ERROR] Missing token or chat_id")
            return

        msg = "✅ Hermes Exness Notifier aktif.\nMode: TEST\nReal execution: OFF"
        ok = send_telegram(token, chat_id, msg)
        print(f"[{'OK' if ok else 'FAIL'}] Test message {'sent' if ok else 'failed'}")

    elif cmd == "--send-latest":
        send_latest()

    elif cmd == "--debug-updates":
        cmd_debug_updates()

    elif cmd == "--test-topic":
        if len(sys.argv) < 3:
            print("[ERROR] Usage: python telegram_reporter.py --test-topic <name>")
            sys.exit(1)
        cmd_test_topic(sys.argv[2])

    elif cmd == "--clear-recent":
        cmd_clear_recent()

    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()

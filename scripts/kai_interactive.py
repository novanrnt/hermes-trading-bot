#!/usr/bin/env python3
"""
Kai Interactive — Chat mode untuk OwnerRoom (Topic 6)
======================================================
Listens for user messages in Topic 6 and responds as Kai.
Runs as a lightweight poller via cron (every 30s).
"""

import json
import os
import sys
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE_DIR = Path(os.environ.get("HERMES_HOME", r"C:\Users\Administrator\AppData\Local\hermes"))
WIB = timezone(timedelta(hours=7))

STATE_FILE = BASE_DIR / "data" / "kai_interactive_state.json"
# Ensure hermes root is on path for imports
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
PROMPTS_DIR = BASE_DIR / "prompts" / "review"
OWNER_ROOM_THREAD_ID = "6"


def load_env():
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    k = k.strip()
                    v = v.strip()
                    if k and k not in os.environ:
                        os.environ[k] = v


def get_token():
    return os.environ.get("TELEGRAM_KAI_BOT_TOKEN", "")


def get_chat_id():
    return os.environ.get("TELEGRAM_GROUP_CHAT_ID", "")


def load_state():
    if STATE_FILE.exists():
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"last_update_id": 0, "last_message_id": 0, "messages_handled": 0}


def save_state(state):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def load_kai_personality() -> str:
    prompt_path = PROMPTS_DIR / "kai_system.txt"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    return (
        "Kamu adalah Kai, Trade Review & Coach Agent untuk Hermes Exness Trading System v1.2.\n"
        "Personality: Tegas, berwibawa, tapi bahasa santai — kayak coach sepakbola top.\n"
        "Kamu ngomong pake bahasa Indonesia casual (lo-gue), tapi tetap profesional.\n"
        "Kamu review performa agent, kasih saran trading, dan bisa diskusi santai.\n"
    )


def load_trade_context() -> str:
    """Gather recent trade data for Kai's context."""
    ctx = []

    # Recent closed trades from kai state
    kai_state_path = BASE_DIR / "data" / "kai_state.json"
    if kai_state_path.exists():
        with open(kai_state_path, "r") as f:
            ks = json.load(f)
        ctx.append(f"Reviews done: {ks.get('total_reviews', 0)}")
        ctx.append(f"Trades reviewed: {ks.get('total_trades_reviewed', 0)}")

    # Latest final decision
    fd_path = BASE_DIR / "final_decision.json"
    if fd_path.exists():
        with open(fd_path, "r") as f:
            fd = json.load(f)
        ctx.append(f"Last decision: {fd.get('action', '?')} | {fd.get('mode', '?')}")
        ctx.append(f"Best symbol: {fd.get('best_symbol', 'N/A')} | Side: {fd.get('side', 'N/A')}")
        ctx.append(f"Confidence: {fd.get('confidence', 'N/A')} | RR: {fd.get('rr', 'N/A')}")
        ctx.append(f"Safety gate: {fd.get('safety_gate', '?')}")

    # Health check summary
    health_path = BASE_DIR / "logs" / "health" / "health_log.json"
    if health_path.exists():
        with open(health_path, "r") as f:
            lines = f.readlines()
        if lines:
            try:
                last = json.loads(lines[-1].strip())
                ctx.append(f"Health: MT5={last.get('mt5_connected','?')} | RAM={last.get('ram_pct','?')}% | Scheduler={last.get('scheduler_ok','?')}")
            except Exception:
                pass

    # Recent trades from MT5 (quick summary)
    try:
        import MetaTrader5 as mt5
        if mt5.initialize():
            from datetime import datetime as dt
            deals = mt5.history_deals_get(dt.now() - timedelta(days=7), dt.now())
            if deals:
                out_deals = [d for d in deals if d.entry == 1]
                wins = [d for d in out_deals if d.profit + d.commission + d.swap > 0]
                total_pnl = sum(d.profit + d.commission + d.swap for d in out_deals)
                ctx.append(f"Week trades: {len(out_deals)} closed | {len(wins)}W/{len(out_deals)-len(wins)}L | P/L: ${total_pnl:.2f}")
            mt5.shutdown()
    except Exception:
        pass

    return "\n".join(f"- {c}" for c in ctx)


def get_recent_owner_room_messages(limit: int = 10) -> list:
    """Fetch recent messages from OwnerRoom (Topic 6) for context."""
    token = get_token()
    chat_id = get_chat_id()
    if not token or not chat_id:
        return []

    state = load_state()
    url = f"https://api.telegram.org/bot{token}/getUpdates?"
    if state["last_update_id"]:
        url += f"offset={state['last_update_id'] + 1}&"
    url += "timeout=5&limit=20"

    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"[Kai] getUpdates failed: {e}")
        return []

    if not data.get("ok"):
        return []

    updates = data.get("result", [])
    messages = []

    for upd in updates:
        msg = upd.get("message", {})
        if not msg:
            continue

        # Filter: only Topic 6 (OwnerRoom)
        thread_id = str(msg.get("message_thread_id", ""))
        if thread_id != OWNER_ROOM_THREAD_ID:
            continue

        # Skip bot messages
        if msg.get("from", {}).get("is_bot", False):
            state["last_update_id"] = max(state["last_update_id"], upd["update_id"])
            continue

        text = msg.get("text", msg.get("caption", "")).strip()
        if not text:
            state["last_update_id"] = max(state["last_update_id"], upd["update_id"])
            continue

        messages.append({
            "message_id": msg["message_id"],
            "update_id": upd["update_id"],
            "text": text,
            "from": msg.get("from", {}).get("first_name", "User"),
            "date": msg.get("date", 0),
        })

        state["last_update_id"] = max(state["last_update_id"], upd["update_id"])

    save_state(state)
    return messages


def call_llm(personality: str, trade_ctx: str, user_message: str, history: list) -> str:
    """Call Kai's LLM for interactive response."""
    import requests

    cfg_path = BASE_DIR / "config.yaml"
    if not cfg_path.exists():
        return "[Error] config.yaml not found"

    import yaml
    with open(cfg_path, "r") as f:
        cfg = yaml.safe_load(f)

    model_cfg = cfg.get("model", {})
    api_key = model_cfg.get("api_key", "")
    base_url = model_cfg.get("base_url", "https://api.openai.com/v1")
    model = cfg.get("trading_model", model_cfg.get("default", "qwen3.7-max"))

    messages = [
        {"role": "system", "content": f"{personality}\n\n=== CURRENT SYSTEM STATE ===\n{trade_ctx}\n\nJawab dengan gaya casual tapi berwibawa. Maks 500 kata. Jangan pake format JSON — kamu lagi ngobrol santai di chat."},
    ]

    # Add recent history (last 6 exchanges for context)
    for h in history[-6:]:
        messages.append({"role": "user", "content": h["user_msg"]})
        messages.append({"role": "assistant", "content": h["kai_reply"]})

    messages.append({"role": "user", "content": user_message})

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": messages,
        "temperature": 0.8,
        "max_tokens": 800,
    }

    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=120,
        )
        if resp.status_code != 200:
            return f"[Error] LLM: {resp.status_code}"
        return resp.json()["choices"][0]["message"]["content"]
    except Exception as e:
        return f"[Error] {e}"


def send_reply(text: str, reply_to_msg_id: int = None):
    """Send Kai's reply to OwnerRoom (Topic 6)."""
    token = get_token()
    chat_id = get_chat_id()
    if not token or not chat_id:
        print("[Kai] No token/chat_id")
        return False

    payload = {
        "chat_id": chat_id,
        "text": text,
        "message_thread_id": int(OWNER_ROOM_THREAD_ID),
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_to_msg_id:
        payload["reply_to_message_id"] = reply_to_msg_id

    url = f"https://api.telegram.org/bot{token}/sendMessage"
    data = json.dumps(payload).encode("utf-8")

    req = urllib.request.Request(url, data=data,
                                  headers={"Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            result = json.loads(resp.read().decode("utf-8"))
            return result.get("ok", False)
    except Exception as e:
        print(f"[Kai] Send failed: {e}")
        return False


def run_interactive():
    """Main poll cycle — check for new messages in OwnerRoom and respond."""
    load_env()
    token = get_token()
    if not token:
        print("[Kai] No bot token — exiting")
        return

    messages = get_recent_owner_room_messages()
    if not messages:
        return  # nothing to do

    personality = load_kai_personality()
    trade_ctx = load_trade_context()
    state = load_state()

    # Load conversation history
    history_file = BASE_DIR / "data" / "kai_chat_history.json"
    history = []
    if history_file.exists():
        with open(history_file, "r") as f:
            history = json.load(f)
    history = history[-20:]

    for msg in messages:
        # Skip already handled messages
        if msg["message_id"] <= state.get("last_message_id", 0):
            continue

        print(f"[Kai] New message: {msg['from']}: {msg['text'][:60]}...")

        # Check if user is approving Kai's review → log to Learning Topic (156)
        is_approval = any(w in msg["text"].lower() for w in ["setujui", "gas", "ok set", "approve", "jalan", "lanjut", "apply", "terapkan"])

        if is_approval:
            # Load latest Kai review
            reviews_dir = BASE_DIR / "logs" / "kai_reviews"
            if reviews_dir.exists():
                reviews = sorted(reviews_dir.glob("kai_review_*.json"), key=lambda f: f.stat().st_mtime, reverse=True)
                if reviews:
                    with open(reviews[0], "r") as f:
                        latest_review = json.load(f)
                    r = latest_review.get("review", {})
                    tuning = r.get("parameter_tuning", {})
                    feedback = r.get("agent_feedback", [])

                    # Build learning log
                    lines = ["🧠 **Kai Learning Log — APPROVED**", ""]
                    lines.append(f"Grade: **{r.get('overall_grade', '?')}** | P/L: ${r.get('total_pnl', 0):.2f} | WR: {r.get('win_rate', 0):.1f}%")
                    lines.append(f"Priority: {r.get('priority_action', '')[:100]}")
                    lines.append("")

                    # Agent grades
                    lines.append("**Agent Scores:**")
                    for fb in feedback:
                        agent = fb.get("agent", "?").replace("_agent", "").title()
                        score = fb.get("score", "?")
                        obs = fb.get("observation", "")[:80]
                        lines.append(f"  • {agent}: {score} — {obs}")
                    lines.append("")

                    # Parameter tuning (changes only)
                    changes = []
                    for param, val in tuning.items():
                        curr = val.get("current")
                        sugg = val.get("suggested")
                        reason = val.get("reason", "")
                        if sugg is not None and sugg != curr:
                            changes.append(f"  • {param}: {curr} → **{sugg}** ({reason[:60]})")
                    if changes:
                        lines.append("**Applied Tuning:**")
                        lines.extend(changes)
                        lines.append("")

                    lines.append(f"_{latest_review.get('timestamp', '')}_")

                    try:
                        send_to_learning = getattr(sys.modules.get('telegram_reporter', None), 'send_kai_message', None)
                        if not send_to_learning:
                            from telegram_reporter import send_kai_message as send_to_learning
                        send_to_learning("learning", "\n".join(lines))
                        print(f"[Kai] ✅ Learning log → Topic 156")
                        send_reply("✅ Siap bro! Tuning udah gw catat di learning log (Topic 156).", msg["message_id"])
                    except Exception as e:
                        print(f"[Kai] Learning log error: {e}")
                        send_reply(f"Udah gw approve, tp error log: {e}", msg["message_id"])

                    state["messages_handled"] += 1
                    state["last_message_id"] = max(state["last_message_id"], msg["message_id"])
                    save_state(state)
                    continue  # Skip normal reply

        # Normal chat reply
        try:
            reply = call_llm(personality, trade_ctx, msg["text"], history)
        except Exception as e:
            reply = f"Wah error bro: {e}"

        # Send reply
        ok = send_reply(reply, msg["message_id"])
        if ok:
            history.append({
                "user_msg": msg["text"],
                "kai_reply": reply,
                "time": datetime.now(WIB).isoformat(),
            })
            state["messages_handled"] += 1
            state["last_message_id"] = max(state["last_message_id"], msg["message_id"])
            print(f"[Kai] Replied OK ({len(reply)} chars)")

    # Save state & history
    save_state(state)
    history_file.parent.mkdir(parents=True, exist_ok=True)
    with open(history_file, "w", encoding="utf-8") as f:
        json.dump(history, f, indent=2, ensure_ascii=False)


if __name__ == "__main__":
    run_interactive()

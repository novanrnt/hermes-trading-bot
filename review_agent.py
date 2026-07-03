#!/usr/bin/env python3
"""
|Kai — Trade Review & Agent Coach
|=================================
|Trigger: Every 20 closed trades
|Function: Review performance, give feedback to each agent, tune parameters
|Personality: Tegas, berwibawa, bahasa santai, perfeksionis
|Strategies: DAY trade (full 5-agent) + SCALP (Risk+Manager only) in 1 account
"""

import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

BASE_DIR = Path(os.environ.get("HERMES_HOME", r"C:\Users\Administrator\AppData\Local\hermes"))
WIB = timezone(timedelta(hours=7))

REVIEW_LOG_DIR = BASE_DIR / "logs" / "kai_reviews"
REVIEW_LOG_DIR.mkdir(parents=True, exist_ok=True)

STATE_FILE = BASE_DIR / "data" / "kai_state.json"
PROMPTS_DIR = BASE_DIR / "prompts" / "review"
PROMPTS_DIR.mkdir(parents=True, exist_ok=True)

TRADES_PER_REVIEW = 20
MIN_TRADES_TO_START = 20  # First review after 20 trades


# ─── Load Config ──────────────────────────────────────────────────────────
def _load_env() -> dict:
    env = {}
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
    return env


def _load_config() -> dict:
    """Load review config from config.yaml."""
    import yaml
    cfg_path = BASE_DIR / "config.yaml"
    if cfg_path.exists():
        with open(cfg_path, "r") as f:
            return yaml.safe_load(f)
    return {}


# ─── Trade Tracker ────────────────────────────────────────────────────────
def get_closed_trades_since(since_ticket: int = 0) -> list:
    """Get all closed trades (OUT deals) since a given ticket ID."""
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            print("[Kai] MT5 init failed")
            return []

        from_date = datetime.now() - timedelta(days=30)
        deals = mt5.history_deals_get(from_date, datetime.now())
        if not deals:
            mt5.shutdown()
            return []

        # Build position map for direction
        pos_types = {}
        for d in deals:
            if d.entry == 0:  # IN deal
                pos_types[d.position_id] = "BUY" if d.type == 0 else "SELL"

        # Get OUT deals (closing trades)
        trades = []
        for d in deals:
            if d.entry == 1 and d.ticket > since_ticket:  # OUT deal, new
                actual_type = pos_types.get(d.position_id, "SELL" if d.type == 0 else "BUY")
                trades.append({
                    "ticket": d.ticket,
                    "position_id": d.position_id,
                    "symbol": d.symbol,
                    "type": actual_type,
                    "volume": d.volume,
                    "price": d.price,
                    "profit": d.profit,
                    "commission": d.commission,
                    "swap": d.swap,
                    "net_pnl": d.profit + d.commission + d.swap,
                    "time": datetime.fromtimestamp(d.time, tz=WIB).strftime("%Y-%m-%d %H:%M"),
                    "comment": d.comment,
                })

        mt5.shutdown()
        return sorted(trades, key=lambda t: t["ticket"])
    except Exception as e:
        print(f"[Kai] Error reading trades: {e}")
        return []


def load_kai_state() -> dict:
    """Load Kai's review state."""
    if STATE_FILE.exists():
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {
        "last_review_ticket": 0,
        "total_reviews": 0,
        "total_trades_reviewed": 0,
        "applied_recommendations": [],
    }


def save_kai_state(state: dict):
    """Save Kai's review state."""
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


# ─── Kai Prompt Builder ───────────────────────────────────────────────────
def load_kai_system_prompt() -> str:
    """Load Kai's base personality prompt."""
    prompt_path = PROMPTS_DIR / "kai_system.txt"
    if prompt_path.exists():
        return prompt_path.read_text(encoding="utf-8")
    return "Kamu adalah Kai, Trade Review Agent. Tegas, berwibawa, bahasa santai, perfeksionis."


def build_review_prompt(trades: list, agent_prompts: dict, perf_stats: dict) -> str:
    """Build the full review prompt with trade data and agent context."""
    system = load_kai_system_prompt()

    trades_text = ""
    for i, t in enumerate(trades, 1):
        emoji = "🟢" if t["net_pnl"] > 0 else "🔴"
        trades_text += (
            f"{i}. {emoji} {t['symbol']} {t['type']} | "
            f"P/L: ${t['net_pnl']:.2f} | "
            f"Vol: {t['volume']} | "
            f"Price: {t['price']} | "
            f"Time: {t['time']} | "
            f"Comment: {t['comment']}\n"
        )

    total_pnl = sum(t["net_pnl"] for t in trades)
    wins = [t for t in trades if t["net_pnl"] > 0]
    losses = [t for t in trades if t["net_pnl"] < 0]
    win_rate = len(wins) / len(trades) * 100 if trades else 0

    # Current agent prompt excerpts
    agent_summary = ""
    for name, prompt in agent_prompts.items():
        # Get first 200 chars of each agent prompt
        preview = prompt[:200].replace("\n", " ") if prompt else "(not found)"
        agent_summary += f"\n  **{name}**: {preview}...\n"

    prompt = f"""{system}

## 📊 Batch Review — {len(trades)} Trades

### Trade Details:
{trades_text}

### Summary:
- **Total P/L:** ${total_pnl:.2f}
- **Wins:** {len(wins)} | **Losses:** {len(losses)}
- **Win Rate:** {win_rate:.1f}%
- **Avg Win:** ${(sum(t['net_pnl'] for t in wins)/len(wins)) if wins else 0:.2f}
- **Avg Loss:** ${(abs(sum(t['net_pnl'] for t in losses))/len(losses)) if losses else 0:.2f}

### Current Agent Configurations:
{agent_summary}

### Your Task:
1. Analisa setiap trade — apa yang bikin win, apa yang bikin loss?
2. Identifikasi pola: agent mana yang terlalu ketat/longgar? Pair mana yang problem?
3. Beri rekomendasi spesifik ke masing-masing agent (Technical, Fundamental, Sentiment, Risk, Manager)
4. Sarankan parameter tuning (confidence, RR, risk %, ADX threshold) kalau perlu
5. Beri nilai performa overall: A+/A/B/C/D

Format JSON response:
{{
  "review_id": {len(trades)},
  "batch_size": {len(trades)},
  "overall_grade": "B+",
  "total_pnl": {total_pnl:.2f},
  "win_rate": {win_rate:.1f},
  "trade_analysis": [
    {{
      "ticket": 123,
      "symbol": "XAUUSDm",
      "verdict": "good_entry_bad_exit",
      "what_worked": "Entry timing tepat di support",
      "what_failed": "SL terlalu ketat, kena noise",
      "suggestion": "Perlebar SL ke 1.5x ATR"
    }}
  ],
  "agent_feedback": [
    {{
      "agent": "technical_agent",
      "score": "B",
      "observation": "Filter terlalu ketat, banyak setup bagus kelewat",
      "recommendation": "Turunkan min score dari 65 ke 60, longgarkan ADX gate ke 18",
      "urgency": "medium"
    }}
  ],
  "parameter_tuning": {{
    "confidence": {{"current": 70, "suggested": 65, "reason": "..."}},
    "min_rr": {{"current": 1.8, "suggested": null, "reason": "..."}},
    "adx_min": {{"current": 20, "suggested": null, "reason": "..."}}
  }},
  "priority_action": "Hal paling penting yang harus diperbaiki segera",
  "coach_note": "Pesan motivasi singkat buat tim agent"
}}"""

    return prompt


# ─── Agent Prompt Loader/Updater ──────────────────────────────────────────
def load_agent_prompts() -> dict:
    """Load all active agent prompts."""
    prompts = {}
    agents_dir = BASE_DIR / "prompts" / "active"
    if agents_dir.exists():
        for f in agents_dir.glob("*_prompt.txt"):
            name = f.stem.replace("_prompt", "")
            prompts[name] = f.read_text(encoding="utf-8")
    return prompts


def apply_agent_feedback(feedback_list: list) -> list:
    """Apply Kai's feedback to agent prompts. Returns list of changes made."""
    changes = []
    agents_dir = BASE_DIR / "prompts" / "active"

    for fb in feedback_list:
        agent_name = fb.get("agent", "")
        recommendation = fb.get("recommendation", "")
        if not agent_name or not recommendation:
            continue

        prompt_path = agents_dir / f"{agent_name}_prompt.txt"
        if not prompt_path.exists():
            changes.append({"agent": agent_name, "status": "not_found"})
            continue

        # Append Kai's note to the prompt
        current = prompt_path.read_text(encoding="utf-8")
        kai_note = f"\n\n<!-- KAI REVIEW NOTE (auto-appended): {recommendation} -->"
        if "KAI REVIEW NOTE" not in current:
            new_content = current + kai_note
            prompt_path.write_text(new_content, encoding="utf-8")
            changes.append({"agent": agent_name, "status": "appended", "note": recommendation[:80]})
        else:
            changes.append({"agent": agent_name, "status": "skipped", "reason": "already has Kai note"})

    return changes


# ─── Kai Review Runner ─────────────────────────────────────────────────────
def run_kai_review(force: bool = False) -> Optional[dict]:
    """Main review cycle. Returns review dict or None if not enough trades."""
    # Import audit trail (scripts/ dir is already on path via kai_cron or standalone)
    try:
        from scripts import audit_trail as audit
    except ImportError:
        import importlib.util
        spec = importlib.util.spec_from_file_location("audit_trail", BASE_DIR / "scripts" / "audit_trail.py")
        audit = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(audit)
    
    state = load_kai_state()
    since_ticket = state.get("last_review_ticket", 0)

    trades = get_closed_trades_since(since_ticket)

    if not trades:
        print("[Kai] No new closed trades since last review")
        return None

    if len(trades) < TRADES_PER_REVIEW and not force:
        print(f"[Kai] Only {len(trades)} new trades (need {TRADES_PER_REVIEW}) — waiting")
        return None

    print(f"[Kai] 🔍 Reviewing {len(trades)} trades...")

    # Load agent prompts for context
    agent_prompts = load_agent_prompts()

    # Build perf stats
    perf_stats = {
        "total_pnl": sum(t["net_pnl"] for t in trades),
        "win_rate": len([t for t in trades if t["net_pnl"] > 0]) / len(trades) * 100 if trades else 0,
    }

    # Build review prompt
    review_prompt = build_review_prompt(trades[-TRADES_PER_REVIEW:], agent_prompts, perf_stats)

    # Call LLM
    review_result = _call_kai_llm(review_prompt)

    if not review_result:
        print("[Kai] ❌ LLM call failed")
        return None

    # Save review
    ts = datetime.now(WIB).strftime("%Y%m%d_%H%M%S")
    review_file = REVIEW_LOG_DIR / f"kai_review_{ts}.json"
    review_data = {
        "timestamp": datetime.now(WIB).isoformat(),
        "trades_reviewed": len(trades),
        "since_ticket": since_ticket,
        "latest_ticket": max(t["ticket"] for t in trades),
        "review": review_result,
    }
    with open(review_file, "w", encoding="utf-8") as f:
        json.dump(review_data, f, indent=2, default=str)

    # Apply feedback to agents — save as pending to audit trail instead of auto-apply
    agent_feedback = review_result.get("agent_feedback", [])
    for fb in agent_feedback:
        agent_name = fb.get("agent", "")
        observation = fb.get("observation", "")
        recommendation = fb.get("recommendation", "")
        score = fb.get("score", "?")
        urgency = fb.get("urgency", "medium")
        if agent_name and recommendation:
            audit.record_suggestion(
                review_id=len(trades),
                category="agent_prompt",
                param=f"{agent_name}_prompt",
                old_value=f"score: {agent_feedback.index(fb)+1 if agent_feedback else 0}",  # placeholder, just for audit
                new_value=recommendation[:200],
                reason=f"{urgency.upper()}: {observation[:200]}",
                source="kai"
            )
    
    # Save parameter tuning to audit trail
    tuning = review_result.get("parameter_tuning", {})
    for param, val in tuning.items():
        curr = val.get("current")
        sugg = val.get("suggested")
        reason = val.get("reason", "")
        if sugg is not None and sugg != curr:
            audit.record_suggestion(
                review_id=len(trades),
                category="parameter",
                param=param,
                old_value=curr,
                new_value=sugg,
                reason=reason[:200],
                source="kai"
            )
    review_data["pending_changes"] = len(agent_feedback) + len([v for v in tuning.values() if v.get("suggested") != v.get("current") and v.get("suggested") is not None])

    # Update state
    state["last_review_ticket"] = max(t["ticket"] for t in trades)
    state["total_reviews"] += 1
    state["total_trades_reviewed"] += len(trades)
    save_kai_state(state)

    print(f"[Kai] ✅ Review saved: {review_file}")
    print(f"[Kai] ⏳ {review_data['pending_changes']} change(s) pending user approval")

    return review_data


# ─── LLM Call ─────────────────────────────────────────────────────────────
def _call_kai_llm(prompt: str) -> Optional[dict]:
    """Call LLM for Kai's review using config.yaml settings."""
    import yaml
    import requests

    cfg_path = BASE_DIR / "config.yaml"
    if not cfg_path.exists():
        print("[Kai] config.yaml not found")
        return None

    with open(cfg_path, "r") as f:
        cfg = yaml.safe_load(f)

    model_cfg = cfg.get("model", {})
    api_key = model_cfg.get("api_key", "")
    base_url = model_cfg.get("base_url", "https://api.openai.com/v1")
    # Use trading_model for Kai (same tier as bot)
    model = cfg.get("trading_model", model_cfg.get("default", "qwen3.7-max"))

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "user", "content": prompt}
        ],
        "temperature": 0.7,
        "max_tokens": 4000,
    }

    try:
        resp = requests.post(
            f"{base_url}/chat/completions",
            headers=headers,
            json=payload,
            timeout=180,
        )
        if resp.status_code != 200:
            print(f"[Kai] LLM error: {resp.status_code} {resp.text[:200]}")
            return None

        content = resp.json()["choices"][0]["message"]["content"]

        # Extract JSON
        import re
        content = re.sub(r"```(?:json)?\s*", "", content).strip()
        start = content.find("{")
        end = content.rfind("}")
        if start == -1 or end == -1:
            print(f"[Kai] No JSON in response: {content[:200]}")
            return None
        return json.loads(content[start:end + 1])

    except Exception as e:
        print(f"[Kai] LLM exception: {e}")
        return None


# ─── Report Formatter ─────────────────────────────────────────────────────
def format_kai_report(review_data: dict) -> str:
    """Format Kai's review into a Telegram-friendly message."""
    r = review_data.get("review", {})
    trades = review_data.get("trades_reviewed", 0)
    grade = r.get("overall_grade", "?")

    lines = [
        f"📋 **Kai Review #{review_data.get('total_reviews', 0) + 1}**",
        f"",
        f"📊 **{trades} Trades** | Grade: **{grade}**",
        f"💰 P/L: ${r.get('total_pnl', 0):.2f} | Win Rate: {r.get('win_rate', 0):.1f}%",
        f"",
    ]

    # Priority action
    priority = r.get("priority_action", "")
    if priority:
        lines.append(f"⚠️ **Prioritas:** {priority}")
        lines.append("")

    # Agent feedback summary
    feedback = r.get("agent_feedback", [])
    if feedback:
        lines.append("**Feedback Agent:**")
        for fb in feedback:
            agent = fb.get("agent", "?").replace("_agent", "").title()
            score = fb.get("score", "?")
            obs = fb.get("observation", "")[:100]
            lines.append(f"  • {agent} ({score}): {obs}")
        lines.append("")

    # Parameter tuning
    tuning = r.get("parameter_tuning", {})
    if tuning:
        changes = []
        for param, val in tuning.items():
            curr = val.get("current")
            sugg = val.get("suggested")
            if sugg is not None and sugg != curr:
                changes.append(f"  • {param}: {curr} → **{sugg}**")
        if changes:
            lines.append("**🔧 Tuning Suggestion:**")
            lines.extend(changes)
            lines.append("")

    # Coach note
    coach = r.get("coach_note", "")
    if coach:
        lines.append(f"💬 *\"{coach}\"*")
        lines.append("")

    lines.append(f"📁 `kai_review_{{ts}}.json`")

    return "\n".join(lines)


# ─── CLI ──────────────────────────────────────────────────────────────────
def main():
    import argparse
    parser = argparse.ArgumentParser(description="Kai — Trade Review Agent")
    parser.add_argument("--force", action="store_true", help="Force review even if < 5 trades")
    parser.add_argument("--status", action="store_true", help="Show Kai status")
    args = parser.parse_args()

    if args.status:
        state = load_kai_state()
        print(f"📋 Kai Status:")
        print(f"   Reviews done: {state['total_reviews']}")
        print(f"   Trades reviewed: {state['total_trades_reviewed']}")
        print(f"   Last ticket: {state['last_review_ticket']}")
        print(f"   Pending trades: {len(get_closed_trades_since(state['last_review_ticket']))}")
        return

    result = run_kai_review(force=args.force)
    if result:
        report = format_kai_report(result)
        print(report)

        # Try to send to Telegram via Kai's own bot
        try:
            from telegram_reporter import send_to_topic, send_kai_message
            send_kai_message("kai_room", report)
            print(f"\n[Kai] Report sent to Kai Room via @Kaiagentt_bot")
        except Exception as e:
            print(f"\n[Kai] Telegram send failed: {e}")
    else:
        print("[Kai] No review generated (not enough trades or error)")


if __name__ == "__main__":
    main()

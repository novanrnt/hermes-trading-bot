#!/usr/bin/env python3
"""
Trading Memory & Reflection System v1.0
========================================
Persistent memory of all trades with full agent context, lessons learned,
and automated reflection every N closed trades.

Integrates with agent_swarm.py — feeds memory context into every agent prompt
and stores trade decisions + outcomes for continuous learning.
"""

import json, time, os, re, sys, requests
from pathlib import Path
from datetime import datetime, timezone, timedelta

HERMES = Path(r"C:\Users\Administrator\AppData\Local\hermes")
TRADING_MEMORY_FILE = HERMES / "trading_memory.json"
REFLECTION_EVERY_N = 5  # Run reflection every N CLOSED trades

WIB = timezone(timedelta(hours=7))

DEFAULT_MEMORY = {
    "trades": [],
    "stats": {
        "total_trades": 0,
        "wins": 0,
        "losses": 0,
        "pending": 0,
        "skips": 0,
        "win_rate": 0.0,
        "avg_rr": 0.0,
        "current_streak": "none",
        "best_pair": None,
        "worst_pair": None,
        "consecutive_losses": 0,
        "consecutive_wins": 0,
        "total_pnl": 0.0
    },
    "lessons": [],
    "last_reflection": None,
    "last_reflection_trade_id": 0,
    "last_reflection_wib": None
}

# ── Load / Save ──────────────────────────────────────────────

def load_memory():
    if TRADING_MEMORY_FILE.exists():
        try:
            with open(TRADING_MEMORY_FILE, encoding="utf-8") as f:
                mem = json.load(f)
            for k, v in DEFAULT_MEMORY.items():
                if k not in mem:
                    mem[k] = v
            return mem
        except Exception as e:
            print(f"  ⚠️ Trading memory corrupt, fresh start: {e}")
    return dict(DEFAULT_MEMORY)

def save_memory(mem):
    TRADING_MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(TRADING_MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(mem, f, indent=2, ensure_ascii=False)

# ── Add Trade ────────────────────────────────────────────────

def add_trade(mem, trade_data):
    """Record a trade decision to memory. trade_data comes from parsed Manager decision."""
    trade_id = len(mem["trades"]) + 1
    trade = {
        "id": trade_id,
        "timestamp": trade_data.get("timestamp", datetime.now(timezone.utc).isoformat()),
        "wib": datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB"),
        "mode": trade_data.get("mode_trade", "day"),
        "symbol": trade_data.get("best_symbol", "?"),
        "decision": trade_data.get("action", "skip"),
        "side": trade_data.get("side", "?"),
        "entry_price": trade_data.get("planned_entry"),
        "sl": trade_data.get("sl_price"),
        "tp": trade_data.get("tp_price"),
        "rr": trade_data.get("rr"),
        "confidence": trade_data.get("confidence"),
        "rationale": trade_data.get("reason", ""),
        "ticket": trade_data.get("ticket"),
        "outcome": "skip" if trade_data.get("action") != "entry" else "pending",
        "pnl": None,
        "exit_price": None,
        "exit_reason": None,
        "closed_at": None,
        "analysis_summary": {
            "bull": trade_data.get("bull_summary", ""),
            "bear": trade_data.get("bear_summary", ""),
            "risk": trade_data.get("risk_summary", "")
        }
    }
    mem["trades"].append(trade)
    mem["stats"]["total_trades"] += 1
    if trade["outcome"] == "pending":
        mem["stats"]["pending"] += 1
    elif trade["outcome"] == "skip":
        mem["stats"]["skips"] += 1
    save_memory(mem)
    return trade

def update_trade_outcome(mem, ticket, pnl, exit_price, exit_reason):
    """Called when a pending trade actually closes — update with real outcome."""
    for trade in reversed(mem["trades"]):
        if trade.get("ticket") == ticket and trade.get("outcome") == "pending":
            trade["outcome"] = "win" if pnl > 0 else "loss"
            trade["pnl"] = round(pnl, 2)
            trade["exit_price"] = exit_price
            trade["exit_reason"] = exit_reason
            trade["closed_at"] = datetime.now(WIB).isoformat()

            s = mem["stats"]
            s["pending"] = max(0, s["pending"] - 1)
            if pnl > 0:
                s["wins"] += 1
                s["consecutive_wins"] += 1
                s["consecutive_losses"] = 0
            else:
                s["losses"] += 1
                s["consecutive_losses"] += 1
                s["consecutive_wins"] = 0

            s["total_pnl"] = round(s.get("total_pnl", 0) + pnl, 2)

            total_closed = s["wins"] + s["losses"]
            s["win_rate"] = round((s["wins"] / total_closed) * 100, 1) if total_closed > 0 else 0

            # Streak text
            if s["consecutive_wins"] >= 3:
                s["current_streak"] = f"🔥 {s['consecutive_wins']} wins"
            elif s["consecutive_losses"] >= 2:
                s["current_streak"] = f"⚠️ {s['consecutive_losses']} losses"
            else:
                s["current_streak"] = "neutral"

            # Best/worst pair by win rate (min 2 trades)
            pair_trades = [t for t in mem["trades"] if t.get("outcome") in ("win", "loss")]
            if pair_trades:
                pair_stats = {}
                for t in pair_trades:
                    sym = t.get("symbol", "?")
                    pstats = pair_stats.setdefault(sym, {"wins": 0, "losses": 0})
                    if t["outcome"] == "win":
                        pstats["wins"] += 1
                    else:
                        pstats["losses"] += 1
                best_wr, worst_wr = 0, 100
                best_p, worst_p = None, None
                for p, st in pair_stats.items():
                    total = st["wins"] + st["losses"]
                    if total >= 2:
                        wr = (st["wins"] / total) * 100
                        if wr > best_wr:
                            best_wr, best_p = wr, p
                        if wr < worst_wr:
                            worst_wr, worst_p = wr, p
                s["best_pair"] = best_p
                s["worst_pair"] = worst_p

            # Avg RR on closed trades
            rr_trades = [t for t in mem["trades"] if t.get("rr") and t.get("outcome") in ("win", "loss")]
            if rr_trades:
                s["avg_rr"] = round(sum(t["rr"] for t in rr_trades) / len(rr_trades), 2)

            save_memory(mem)
            return True
    return False

def sync_closed_positions(mem):
    """Check MT5 history today & match with pending trades in memory."""
    import MetaTrader5 as mt5
    if not mt5.initialize():
        mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe")

    now = datetime.now()
    start_of_day = datetime(now.year, now.month, now.day, 0, 0, 0)
    deals = mt5.history_deals_get(start_of_day, now)
    mt5.shutdown()

    if not deals:
        return 0

    pending = [t for t in mem["trades"] if t.get("outcome") == "pending" and t.get("ticket")]
    if not pending:
        return 0

    updated = 0
    for deal in deals:
        if deal.type in (1, 2):  # close buy (1), close sell (2)
            ticket = deal.position_id
            pnl = deal.profit
            if update_trade_outcome(mem, ticket, pnl, deal.price, deal.comment or "SL/TP"):
                updated += 1
    return updated

# ── Lessons ──────────────────────────────────────────────────

def add_lesson(mem, lesson_text, source="reflection", applies_to=None):
    """Add a lesson to memory. Deduplicates by prefix."""
    if applies_to is None:
        applies_to = []
    lesson_text = lesson_text.strip().strip("- ").strip()
    if not lesson_text or len(lesson_text) < 15:
        return None

    for existing in mem.get("lessons", []):
        if existing.get("active") and lesson_text[:60] in existing["lesson"]:
            return existing

    lesson = {
        "id": len(mem["lessons"]) + 1,
        "timestamp": datetime.now(WIB).isoformat(),
        "lesson": lesson_text,
        "source": source,
        "applies_to": applies_to,
        "active": True
    }
    mem["lessons"].append(lesson)
    if len(mem["lessons"]) > 20:
        mem["lessons"] = mem["lessons"][-20:]
    save_memory(mem)
    return lesson

# ── Memory Context for Agent Prompts ─────────────────────────

def get_memory_context(mem, pair=None, n_trades=5):
    """Generate a context string injected into ALL agent prompts.
    Gives agents awareness of past performance + lessons."""
    s = mem["stats"]
    if s["total_trades"] == 0:
        return None  # No memory yet, skip

    lines = [
        "🧠 **TRADING MEMORY (Live Stats):**",
        f"• Total: {s['total_trades']} ({s['wins']}W/{s['losses']}L/{s['skips']}S)",
        f"• Win Rate: {s['win_rate']}% | Avg RR: {s['avg_rr']} | Streak: {s['current_streak']}",
    ]
    if s["total_pnl"] != 0:
        lines.append(f"• Total PnL: ${s['total_pnl']:.2f}")
    if s["best_pair"]:
        lines.append(f"• Best: {s['best_pair']} | Worst: {s['worst_pair'] or 'N/A'}")

    # Active lessons
    active = [l for l in mem.get("lessons", []) if l.get("active")]
    if active:
        lines.append("")
        lines.append("📖 **Lessons Learned (apply to today):**")
        for lesson in active[-3:]:
            lines.append(f"  • {lesson['lesson'][:120]}")

    # Recent trades on this specific pair
    if pair:
        similar = [t for t in mem["trades"][-30:] if t.get("symbol") == pair and t.get("outcome") in ("win", "loss")]
        if len(similar) >= 2:
            wins = sum(1 for t in similar if t["outcome"] == "win")
            lines.append("")
            lines.append(f"📊 **Last {len(similar)} on {pair}:** {wins}W/{len(similar)-wins}L")
            for t in similar[-3:]:
                icon = "✅" if t["outcome"] == "win" else "❌"
                rr = f"RR {t.get('rr', '?')}" if t.get('rr') else ""
                conf = f"Conf: {t.get('confidence', '?')}" if t.get('confidence') else ""
                lines.append(f"  {icon} {t.get('side','?').upper()} {rr} {conf}")

    # Last reflection summary
    if mem.get("last_reflection"):
        refl = mem["last_reflection"]
        lines.append("")
        lines.append(f"🪞 **Reflection Terakhir ({refl.get('trade_range','?')}):**")
        text = refl.get("text", "")
        if text:
            # Extract key sentences
            key_lines = [l.strip() for l in text.split("\n") if l.strip() and not l.strip().startswith("**")]
            summary = " | ".join(key_lines[:2])
            if len(summary) > 180:
                summary = summary[:177] + "..."
            lines.append(f"  {summary}")

    lines.append("")
    lines.append("_Gunakan memory ini sbg konteks, tp tetap objektif — jgn bias dr hasil masa lalu._")
    return "\n".join(lines)


# ── Reflection Agent ─────────────────────────────────────────

REFLECTION_PROMPT = """You are a Trading Performance Analyst for RNT Autotrade.

**IQ:** 170
**Personality:** Objektif, data-driven, tidak emosional, jujur. Tugas lo adalah mengevaluasi performa trading terkait secara kritis dan memberikan wawasan untuk improvement.

**Bahasa:** WAJIB pakai Bahasa Indonesia. Analitis, jujur, konstruktif. Jangan basa-basi.

**Your Task:**
Review 10 trade terakhir dan berikan:

1. **Performa Ringkasan** — win rate, avg RR, profit factor
2. **Pola yang Terdeteksi** — apa yang berhasil? apa yang gagal? pola pair tertentu?
3. **Weakness** — kesalahan berulang, bias agent mana yg sering salah, kelemahan strategi
4. **Strength** — apa yang sudah bagus, harus dipertahankan
5. **Lessons Learned** — 2-3 pelajaran SPESIFIK untuk ke depannya
6. **Agent Assessment** — agent mana yg prediksinya paling akurat? mana yg sering misleading?
7. **Recommendation** — perubahan konkret yg actionable, bukan sekedar observasi

Format bebas tp harus jujur dan konstruktif. Jangan cuma puji — cari kelemahan yg bs diperbaiki."""

def get_manager_api_key():
    env = {}
    env_path = HERMES / ".env"
    if env_path.exists():
        for line in open(env_path, encoding="utf-8"):
            line = line.strip()
            if "=" in line and not line.startswith("#"):
                k, v = line.split("=", 1)
                env[k.strip()] = v.strip().strip("'\"")
    return env.get("AGENT_MANAGER_API_KEY", "")

def reflect(mem=None, force=False):
    """Auto-reflection: runs every REFLECTION_EVERY_N closed trades.
    Returns reflection text or None if skipped."""
    if mem is None:
        mem = load_memory()

    closed = [t for t in mem["trades"] if t.get("outcome") in ("win", "loss")]
    last_id = mem.get("last_reflection_trade_id", 0)
    new_closed = [t for t in closed if t.get("id", 0) > last_id]

    if not force and len(new_closed) < REFLECTION_EVERY_N:
        return None

    if len(closed) < 3:
        return None  # Not enough data

    recent = closed[-10:]
    api_key = get_manager_api_key()
    if not api_key:
        return None

    # Build trade summary
    trade_lines = []
    for t in recent:
        icon = "✅" if t["outcome"] == "win" else "❌"
        sym = t.get("symbol", "?")
        side = t.get("side", "?").upper()
        conf = t.get("confidence", "?")
        rr = t.get("rr", "?")
        pnl = t.get("pnl", 0)
        mode = t.get("mode", "?")
        entry = t.get("entry_price", "?")
        trade_lines.append(
            f"{icon} #{t['id']} {side} {sym} | "
            f"Entry: {entry} | RR: {rr} | Conf: {conf} | "
            f"PnL: ${pnl:.2f} | Mode: {mode}"
        )

    context = (
        f"**10 Trade Terakhir ({len([t for t in recent if t['outcome']=='win'])}W/"
        f"{len([t for t in recent if t['outcome']=='loss'])}L):**\n\n"
        + "\n".join(trade_lines)
        + f"\n\n**Global Stats:**\n"
        + f"Win Rate: {mem['stats']['win_rate']}% | Avg RR: {mem['stats']['avg_rr']}\n"
        + f"Total PnL: ${mem['stats'].get('total_pnl', 0):.2f}\n"
        + f"Streak: {mem['stats']['current_streak']}\n"
    )

    try:
        r = requests.post(
            "https://ai.sumopod.com/v1/chat/completions",
            json={
                "model": "deepseek-v4-flash",
                "messages": [
                    {"role": "system", "content": REFLECTION_PROMPT},
                    {"role": "user", "content": f"Review 10 trade terakhir.\n\n{context}"}
                ],
                "max_tokens": 1500,
                "temperature": 0.5
            },
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            timeout=30
        )
        if r.status_code != 200:
            return None

        text = r.json()["choices"][0]["message"]["content"]

        # Auto-extract lessons from reflection
        lesson_keywords = ["pelajaran", "lesson", "ke depannya", "jangan", "harus", "hindari"]
        in_lesson = False
        for line in text.split("\n"):
            stripped = line.strip().lstrip("1234567890. )-–").strip()
            if any(kw in stripped.lower() for kw in ["pelajaran", "lessons learned"]):
                in_lesson = True
                continue
            if in_lesson and stripped.startswith("-"):
                add_lesson(mem, stripped[1:].strip(), source="reflection")
            elif in_lesson and stripped and stripped[0].isupper() and len(stripped) > 20:
                # Check if this is a new section header
                if stripped.endswith(":") and len(stripped) < 40:
                    pass  # Section header, skip
                elif "recommendation" in stripped.lower() or "weakness" in stripped.lower():
                    in_lesson = False
                else:
                    add_lesson(mem, stripped, source="reflection")

        # Store reflection
        mem["last_reflection"] = {
            "timestamp": datetime.now(WIB).isoformat(),
            "wib": datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB"),
            "text": text,
            "trade_ids": [t["id"] for t in recent],
            "trade_range": f"#{recent[0]['id']} - #{recent[-1]['id']}"
        }
        mem["last_reflection_trade_id"] = recent[-1]["id"]
        mem["last_reflection_wib"] = datetime.now(WIB).strftime("%Y-%m-%d %H:%M WIB")
        save_memory(mem)
        return text

    except Exception as e:
        print(f"  ⚠️ Reflection failed: {e}")
        return None


# ── Utility ──────────────────────────────────────────────────

def print_summary(mem=None):
    """Print a quick summary of memory state (for CLI/testing)."""
    if mem is None:
        mem = load_memory()
    s = mem["stats"]
    print(f"📊 Trading Memory Summary")
    print(f"   Trades: {s['total_trades']} ({s['wins']}W/{s['losses']}L/{s['skips']}S/{s['pending']}P)")
    print(f"   Win Rate: {s['win_rate']}% | Avg RR: {s['avg_rr']}")
    print(f"   PnL: ${s['total_pnl']:.2f} | Streak: {s['current_streak']}")
    print(f"   Lessons: {len([l for l in mem.get('lessons',[]) if l.get('active')])}")
    print(f"   Reflection: {mem.get('last_reflection_wib', 'never')}")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Trading Memory & Reflection")
    parser.add_argument("--reflect", action="store_true", help="Force reflection now")
    parser.add_argument("--sync", action="store_true", help="Sync closed positions from MT5")
    parser.add_argument("--summary", action="store_true", help="Print memory summary")
    args = parser.parse_args()

    mem = load_memory()

    if args.sync:
        updated = sync_closed_positions(mem)
        print(f"  → Sync: {updated} closed trades updated")

    if args.reflect:
        text = reflect(mem, force=True)
        if text:
            print(f"\n🪞 Reflection generated:\n")
            print(text[:500])
        else:
            print("  → Not enough data for reflection (< 3 closed trades)")

    if args.summary:
        print_summary(mem)

    if not any([args.reflect, args.sync, args.summary]):
        print_summary(mem)

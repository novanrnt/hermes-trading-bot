#!/usr/bin/env python3
"""
Hermes Exness Bot V1 — Self-Learning Auto-Tuner
================================================
Daily performance analysis + adaptive parameter tuning.
Runs via cron, adjusts bot parameters based on actual trade outcomes.
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any

BASE_DIR = Path(os.environ.get("HERMES_HOME", r"C:\Users\Administrator\AppData\Local\hermes"))
ENV_PATH = BASE_DIR / ".env"
PERF_DB = BASE_DIR / "logs" / "performance" / "perf_db.json"
DEMO_DIR = BASE_DIR / "logs" / "demo_execution"
CYCLES_DIR = BASE_DIR / "logs" / "cycles"
PERF_DB.parent.mkdir(parents=True, exist_ok=True)

WIB = timezone(timedelta(hours=7))

# ─── Default tunable parameters ──────────────────────────────────────────
DEFAULT_PARAMS = {
    "TRADING_SESSION_START_WIB": "07:00",
    "TRADING_SESSION_END_WIB": "00:00",
    "MIN_CONFIDENCE": 70,
    "MIN_RR": 1.8,
    "RISK_PER_TRADE_PERCENT": 1.0,
    "MAX_OPEN_POSITIONS": 3,
    "XAUUSD_DAILY_MAX_LOSS": 1,
}

# ─── Adaptive tuning ranges ─────────────────────────────────────────────
TUNE_RANGES = {
    "MIN_CONFIDENCE": (55, 85),
    "MIN_RR": (1.3, 2.5),
    "RISK_PER_TRADE_PERCENT": (0.5, 2.0),
}


def load_env() -> dict:
    env = {}
    if not ENV_PATH.exists():
        return env
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, _, v = line.partition("=")
            env[k.strip()] = v.strip()
    return env


def save_env(env: dict):
    lines = []
    if ENV_PATH.exists():
        with open(ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

    updated_keys = set(env.keys())
    new_lines = []
    seen = set()
    for line in lines:
        stripped = line.strip()
        if stripped and not stripped.startswith("#") and "=" in stripped:
            k = stripped.split("=", 1)[0].strip()
            if k in updated_keys:
                new_lines.append(f"{k}={env[k]}\n")
                seen.add(k)
                continue
        new_lines.append(line)

    for k, v in env.items():
        if k not in seen:
            new_lines.append(f"{k}={v}\n")

    with open(ENV_PATH, "w", encoding="utf-8") as f:
        f.writelines(new_lines)


def load_perf_db() -> dict:
    if PERF_DB.exists():
        with open(PERF_DB, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"trades": [], "daily_snapshots": [], "tuning_log": []}


def save_perf_db(db: dict):
    with open(PERF_DB, "w", encoding="utf-8") as f:
        json.dump(db, f, indent=2, default=str)


def fetch_mt5_closed_trades() -> list:
    """Fetch closed positions from MT5 history (last 30 days)."""
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            return []

        now = datetime.now(WIB)
        days_ago = now - timedelta(days=30)
        from_ts = int(days_ago.timestamp())
        to_ts = int(now.timestamp())

        history = mt5.history_deals_get(from_ts, to_ts)
        if not history:
            mt5.shutdown()
            return []

        # Get closed positions
        positions = mt5.history_orders_get(from_ts, to_ts)
        mt5.shutdown()

        trades = []
        if positions:
            for pos in positions:
                if pos.type in (0, 1):  # BUY/SELL orders that opened positions
                    trades.append({
                        "ticket": pos.ticket,
                        "symbol": pos.symbol,
                        "type": "buy" if pos.type == 0 else "sell",
                        "volume": pos.volume_current if pos.volume_current else pos.volume_initial,
                        "open_time": datetime.fromtimestamp(pos.time_setup, WIB).isoformat(),
                        "open_price": pos.price_open,
                        "sl": pos.sl,
                        "tp": pos.tp,
                        "state": str(pos.state),
                    })

        # Match deals to find closed PnL
        if history:
            for deal in history:
                if deal.entry in (0, 1):  # DEAL_ENTRY_IN / OUT
                    for t in trades:
                        if deal.position_id == t["ticket"] or deal.order == t["ticket"]:
                            if deal.entry == 0:  # IN
                                t["deal_in_price"] = deal.price
                            elif deal.entry == 1:  # OUT
                                t["deal_out_price"] = deal.price
                                t["profit"] = deal.profit
                                t["close_time"] = datetime.fromtimestamp(deal.time, WIB).isoformat()
                                t["pnl"] = deal.profit

        return trades
    except Exception as e:
        print(f"[MT5] Error: {e}")
        return []


def analyze_demo_logs() -> dict:
    """Analyze all demo execution logs + cycle logs."""
    if not DEMO_DIR.exists():
        return {"executed": [], "blocked": [], "skipped_cycles": []}

    executed = []
    blocked = []
    skipped_cycles = []

    for f in sorted(DEMO_DIR.glob("demo_exec_*.json")):
        try:
            with open(f, "r") as fh:
                d = json.load(fh)
            status = d.get("status", "unknown")
            if status == "executed":
                executed.append(d)
            elif status == "blocked":
                blocked.append(d)
        except Exception:
            pass

    # Count skipped cycles
    if CYCLES_DIR.exists():
        for f in sorted(CYCLES_DIR.glob("cycle_run_*.json")):
            try:
                with open(f, "r") as fh:
                    d = json.load(fh)
                if d.get("final_action") == "SKIP":
                    skipped_cycles.append({"timestamp": d.get("timestamp", ""), "reason": d.get("final_decision", {}).get("reason", "?")})
            except Exception:
                pass

    return {"executed": executed, "blocked": blocked, "skipped_cycles": skipped_cycles}


def compute_metrics(analysis: dict, mt5_trades: list) -> dict:
    """Compute performance metrics."""
    executed = analysis["executed"]
    blocked = analysis["blocked"]
    skipped = analysis["skipped_cycles"]

    metrics = {
        "period": datetime.now(WIB).isoformat(),
        "total_executed": len(executed),
        "total_blocked": len(blocked),
        "total_skipped_cycles": len(skipped),
        "total_decisions": len(executed) + len(blocked) + len(skipped),
        "win_rate": None,
        "avg_rr_planned": 0,
        "avg_rr_actual": 0,
        "total_pnl": 0.0,
        "per_pair": {},
        "per_session_hour": {},
        "top_block_reasons": {},
    }

    # Executed trades analysis
    wins = 0
    losses = 0
    total_rr_planned = 0
    total_rr_actual = 0
    total_pnl = 0.0

    for ex in executed:
        symbol = ex.get("symbol", "?")
        side = ex.get("side", "?")
        rr = ex.get("planned_rr", 0)
        actual_rr = ex.get("actual_rr", 0)
        confidence = ex.get("confidence", 0)
        ticket = ex.get("order_ticket")

        # Per pair stats
        if symbol not in metrics["per_pair"]:
            metrics["per_pair"][symbol] = {"executed": 0, "blocked": 0, "wins": 0, "losses": 0, "pnl": 0.0}
        metrics["per_pair"][symbol]["executed"] += 1

        # Per hour stats
        try:
            ts = datetime.fromisoformat(ex.get("timestamp", "").replace("Z", "+00:00"))
            hour = ts.astimezone(WIB).hour
            if hour not in metrics["per_session_hour"]:
                metrics["per_session_hour"][hour] = {"executed": 0, "wins": 0}
            metrics["per_session_hour"][hour]["executed"] += 1
        except Exception:
            pass

        total_rr_planned += rr
        if actual_rr:
            total_rr_actual += actual_rr

        # Match with MT5 to find PnL
        if ticket and mt5_trades:
            for mt in mt5_trades:
                if mt.get("ticket") == ticket and "pnl" in mt:
                    pnl = mt["pnl"]
                    total_pnl += pnl
                    metrics["per_pair"][symbol]["pnl"] += pnl
                    if pnl > 0:
                        wins += 1
                        metrics["per_pair"][symbol]["wins"] += 1
                        metrics["per_session_hour"][hour]["wins"] += 1
                    else:
                        losses += 1
                        metrics["per_pair"][symbol]["losses"] += 1

    n = len(executed)
    if n > 0:
        metrics["win_rate"] = round(wins / n * 100, 1) if (wins + losses) > 0 else None
        metrics["avg_rr_planned"] = round(total_rr_planned / n, 2)
        metrics["avg_rr_actual"] = round(total_rr_actual / n, 2) if total_rr_actual else 0
    metrics["total_pnl"] = round(total_pnl, 2)

    # Block reasons
    for blk in blocked:
        reason = blk.get("reason", "?").split(":")[0].strip()
        metrics["top_block_reasons"][reason] = metrics["top_block_reasons"].get(reason, 0) + 1

    # Per-pair blocked count
    for blk in blocked:
        sym = blk.get("symbol", "?")
        if sym and sym != "?":
            if sym not in metrics["per_pair"]:
                metrics["per_pair"][sym] = {"executed": 0, "blocked": 0, "wins": 0, "losses": 0, "pnl": 0.0}
            metrics["per_pair"][sym]["blocked"] += 1

    return metrics


def recommend_tuning(metrics: dict, current_params: dict) -> list:
    """Generate adaptive tuning recommendations."""
    recs = []
    executed = metrics["total_executed"]

    # 1. Win rate based tuning
    wr = metrics.get("win_rate")
    if wr is not None and executed >= 10:
        if wr < 40:
            # Too many losses — tighten
            recs.append({"param": "MIN_CONFIDENCE", "direction": "increase",
                         "current": int(current_params.get("MIN_CONFIDENCE", 70)),
                         "reason": f"Win rate {wr}% below 40% — tighten entry"})
            recs.append({"param": "MIN_RR", "direction": "increase",
                         "current": float(current_params.get("MIN_RR", 1.8)),
                         "reason": f"Low win rate ({wr}%) — demand better RR"})
        elif wr > 65:
            # Good win rate — can loosen slightly for more entries
            recs.append({"param": "MIN_CONFIDENCE", "direction": "decrease",
                         "current": int(current_params.get("MIN_CONFIDENCE", 70)),
                         "reason": f"Win rate {wr}% strong — allow more entries"})

    # 2. Activity based tuning
    total_cycles = metrics["total_decisions"]
    if total_cycles > 20 and executed < 3:
        # Too many skips, not enough trades
        recs.append({"param": "MIN_CONFIDENCE", "direction": "decrease",
                     "current": int(current_params.get("MIN_CONFIDENCE", 70)),
                     "reason": f"Only {executed} trades in {total_cycles} cycles — loosen up"})
        recs.append({"param": "MIN_RR", "direction": "decrease",
                     "current": float(current_params.get("MIN_RR", 1.8)),
                     "reason": "Increase trade frequency"})

    # 3. Per-pair analysis
    for pair, stats in metrics.get("per_pair", {}).items():
        pair_exec = stats.get("executed", 0)
        pair_loss = stats.get("losses", 0)
        if pair_exec >= 5 and pair_loss == pair_exec:
            # All trades on this pair lost
            recs.append({"param": f"PAIR_{pair}", "direction": "disable_or_review",
                         "current": "enabled",
                         "reason": f"{pair}: {pair_loss}/{pair_exec} losses — consider pause"})

    return recs


def apply_tuning(recommendations: list, env: dict) -> dict:
    """Apply tuning recommendations to env, respecting safe ranges."""
    changes = {}
    for rec in recommendations:
        param = rec["param"]
        if param.startswith("PAIR_"):
            # Pair-level action — log for now, manual review
            pair = param.replace("PAIR_", "")
            print(f"[TUNE] ⚠ {pair}: {rec['reason']} (manual review)")
            continue

        if param not in TUNE_RANGES:
            continue

        current = rec["current"]
        low, high = TUNE_RANGES[param]
        step = 5 if param == "MIN_CONFIDENCE" else 0.1

        if rec["direction"] == "increase":
            new_val = min(current + step, high)
        else:
            new_val = max(current - step, low)

        if new_val != current:
            changes[param] = {"old": current, "new": new_val, "reason": rec["reason"]}

    # Apply to env
    applied = {}
    for k, v in changes.items():
        env[k] = str(v["new"])
        applied[k] = v
        print(f"[TUNE] {k}: {v['old']} → {v['new']} ({v['reason']})")

    return applied


def main():
    print("=" * 60)
    print("  Hermes Auto-Tuner — Daily Performance Analysis")
    print("=" * 60)

    # 1. Collect data
    print("\n[1/4] Collecting trade data...")
    mt5_trades = fetch_mt5_closed_trades()
    print(f"  MT5 closed trades: {len(mt5_trades)}")

    analysis = analyze_demo_logs()
    print(f"  Demo executed: {len(analysis['executed'])}")
    print(f"  Demo blocked: {len(analysis['blocked'])}")
    print(f"  Skipped cycles: {len(analysis['skipped_cycles'])}")

    # 2. Compute metrics
    print("\n[2/4] Computing metrics...")
    metrics = compute_metrics(analysis, mt5_trades)

    print(f"  Total decisions: {metrics['total_decisions']}")
    print(f"  Win rate: {metrics['win_rate']}%" if metrics["win_rate"] else "  Win rate: N/A (insufficient data)")
    print(f"  Total PnL: ${metrics['total_pnl']}")
    print(f"  Avg planned RR: {metrics['avg_rr_planned']}")

    for pair, stats in metrics.get("per_pair", {}).items():
        print(f"  {pair}: {stats['executed']} trades, {stats['wins']}W/{stats['losses']}L, PnL=${stats['pnl']}")

    # 3. Generate recommendations
    print("\n[3/4] Generating tuning recommendations...")
    env = load_env()
    current_params = {}
    for k in TUNE_RANGES:
        val = env.get(k, DEFAULT_PARAMS.get(k, 0))
        current_params[k] = val

    recs = recommend_tuning(metrics, current_params)
    if recs:
        for r in recs:
            print(f"  → {r['param']}: {r['direction']} (current: {r['current']}) — {r['reason']}")
    else:
        print("  No tuning needed (insufficient data)")

    # 4. Apply if enough data
    print("\n[4/4] Applying tuning...")
    applied = {}
    if metrics["total_executed"] >= 10:
        applied = apply_tuning(recs, env)
        if applied:
            save_env(env)
            print(f"  ✅ {len(applied)} parameter(s) adjusted")
        else:
            print("  No parameter changes needed")
    else:
        print(f"  Skipped — need ≥10 executed trades (have {metrics['total_executed']})")

    # Save performance snapshot
    db = load_perf_db()
    db["daily_snapshots"].append(metrics)
    if applied:
        db["tuning_log"].append({
            "timestamp": datetime.now(WIB).isoformat(),
            "changes": applied,
            "metrics_snapshot": {
                "win_rate": metrics.get("win_rate"),
                "total_executed": metrics["total_executed"],
                "total_pnl": metrics["total_pnl"],
            }
        })
    save_perf_db(db)

    print(f"\n📊 Performance DB: {PERF_DB}")
    print("=" * 60)

    # Summary for Telegram
    wr_str = f"{metrics['win_rate']}%" if metrics.get("win_rate") else "N/A"
    changes_str = ", ".join([f"{k}: {v['old']}→{v['new']}" for k, v in applied.items()]) if applied else "none"
    print(f"\n📈 DAILY REPORT | Win: {wr_str} | Trades: {metrics['total_executed']} | PnL: ${metrics['total_pnl']}")
    print(f"🔧 Tuning: {changes_str}")


if __name__ == "__main__":
    main()

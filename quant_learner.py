#!/usr/bin/env python3
"""
Quant Learner v1.0 — Adaptive parameter tuning for scalping scanner
====================================================================
Reads trading_memory.json, analyzes quant signal performance across
multiple dimensions, and produces optimized parameters.

Runs:
  - After each closed trade (lightweight stat update)
  - Every 10 closed scalping trades (full analysis + parameter tuning)
  - Before scanner runs (load latest optimized params)
"""

import json, os, math
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional

HERMES = Path(r"C:\Users\Administrator\AppData\Local\hermes")
TRADING_MEMORY_FILE = HERMES / "trading_memory.json"
QUANT_CONFIG_FILE = HERMES / "quant_config.json"
MIN_TRADES_FOR_ANALYSIS = 5
TUNE_EVERY_N_TRADES = 10

WIB = timezone(timedelta(hours=7))

# ── Default Parameters ──────────────────────────────────────

DEFAULT_CONFIG = {
    "adx_min": 18,
    "rsi_oversold": 25,
    "rsi_overbought": 75,
    "volume_multiplier": 0.7,
    "max_scalp_trades_day": 5,
    "min_rr_scalp": 1.5,
    "trend_cont_vol": 0.6,
    "pullback_zone_atr": 2.0,
    "momentum_range_ratio": 0.6,
    "pullback_range_ratio": 0.5,
    "blacklisted_pairs": [],
    "trigger_bias": "none",  # "momentum", "pullback", or "none"
    "confidence_boost_adx": True,
    "confidence_boost_volume": True,
    "last_tuned": None,
    "tune_count": 0
}

# ── Load/Save Config ────────────────────────────────────────

def load_config() -> dict:
    if QUANT_CONFIG_FILE.exists():
        try:
            with open(QUANT_CONFIG_FILE) as f:
                cfg = json.load(f)
            for k, v in DEFAULT_CONFIG.items():
                cfg.setdefault(k, v)
            return cfg
        except:
            pass
    return dict(DEFAULT_CONFIG)

def save_config(cfg: dict):
    cfg["last_tuned"] = datetime.now(WIB).isoformat()
    cfg["tune_count"] = cfg.get("tune_count", 0) + 1
    QUANT_CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(QUANT_CONFIG_FILE, "w") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)

def reset_config():
    save_config(DEFAULT_CONFIG)
    return dict(DEFAULT_CONFIG)

# ── Analysis Engine ─────────────────────────────────────────

def load_trades() -> list:
    """Load scalping trades from trading memory."""
    if not TRADING_MEMORY_FILE.exists():
        return []
    try:
        with open(TRADING_MEMORY_FILE) as f:
            mem = json.load(f)
        # Filter scalping trades with outcomes
        trades = [t for t in mem.get("trades", [])
                  if t.get("mode") == "scalp"
                  and t.get("outcome") in ("win", "loss")]
        return trades
    except:
        return []

def analyze_trigger_type(trades: list) -> dict:
    """Win rate by trigger type (momentum vs pullback)."""
    by_type = {}
    for t in trades:
        rationale = t.get("rationale", t.get("reason", ""))
        # Extract trigger type from reason string
        trig = "momentum" if "MOMENTUM" in rationale.upper() else "pullback"
        by_type.setdefault(trig, {"wins": 0, "losses": 0, "total": 0, "pnl": 0.0})
        outcome = t["outcome"]
        by_type[trig]["total"] += 1
        if outcome == "win":
            by_type[trig]["wins"] += 1
        else:
            by_type[trig]["losses"] += 1
        by_type[trig]["pnl"] += t.get("pnl", 0) or 0

    for trig, stat in by_type.items():
        stat["win_rate"] = round((stat["wins"] / stat["total"]) * 100, 1) if stat["total"] > 0 else 0

    return by_type

def analyze_by_pair(trades: list) -> dict:
    """Win rate by pair."""
    by_pair = {}
    for t in trades:
        sym = t.get("symbol", "?")
        by_pair.setdefault(sym, {"wins": 0, "losses": 0, "total": 0, "pnl": 0.0})
        outcome = t["outcome"]
        by_pair[sym]["total"] += 1
        if outcome == "win":
            by_pair[sym]["wins"] += 1
        else:
            by_pair[sym]["losses"] += 1
        by_pair[sym]["pnl"] += t.get("pnl", 0) or 0

    for sym, stat in by_pair.items():
        stat["win_rate"] = round((stat["wins"] / stat["total"]) * 100, 1) if stat["total"] > 0 else 0

    return by_pair

def analyze_rsi_range(trades: list) -> dict:
    """Win rate by RSI range at entry."""
    ranges = {
        "oversold (<25)": {"wins": 0, "losses": 0, "total": 0},
        "low (25-40)": {"wins": 0, "losses": 0, "total": 0},
        "mid (40-60)": {"wins": 0, "losses": 0, "total": 0},
        "high (60-75)": {"wins": 0, "losses": 0, "total": 0},
        "overbought (>75)": {"wins": 0, "losses": 0, "total": 0},
    }
    for t in trades:
        # Try to extract RSI from reason
        rationale = t.get("rationale", t.get("reason", ""))
        rsi_val = None
        for part in rationale.split():
            try:
                if "RSI" in part:
                    # "RSI" or "RSI45" etc
                    rsi_str = part.replace("RSI", "").replace(",", "").replace(".", "")
                    if rsi_str.strip().isdigit():
                        rsi_val = float(rsi_str)
            except:
                pass

        if rsi_val is None:
            continue

        outcome = t["outcome"]
        if rsi_val < 25:
            key = "oversold (<25)"
        elif rsi_val < 40:
            key = "low (25-40)"
        elif rsi_val < 60:
            key = "mid (40-60)"
        elif rsi_val < 75:
            key = "high (60-75)"
        else:
            key = "overbought (>75)"

        ranges[key]["total"] += 1
        if outcome == "win":
            ranges[key]["wins"] += 1
        else:
            ranges[key]["losses"] += 1

    for key, stat in ranges.items():
        stat["win_rate"] = round((stat["wins"] / stat["total"]) * 100, 1) if stat["total"] > 0 else 0

    return ranges

def analyze_adx_range(trades: list) -> dict:
    """Win rate by ADX range at entry."""
    ranges = {
        "weak (18-25)": {"wins": 0, "losses": 0, "total": 0},
        "moderate (25-35)": {"wins": 0, "losses": 0, "total": 0},
        "strong (35-50)": {"wins": 0, "losses": 0, "total": 0},
        "very strong (>50)": {"wins": 0, "losses": 0, "total": 0},
    }
    for t in trades:
        rationale = t.get("rationale", t.get("reason", ""))
        adx_val = None
        parts = rationale.split()
        for i, p in enumerate(parts):
            if "ADX" in p:
                try:
                    # Next word might be number
                    for j in range(i, min(i+3, len(parts))):
                        cleaned = parts[j].replace(",", "").replace(".", "")
                        if cleaned.replace(".", "").isdigit():
                            val = float(parts[j].replace(",", ""))
                            if 0 < val < 100:
                                adx_val = val
                                break
                except:
                    pass

        if adx_val is None:
            continue

        if adx_val < 25:
            key = "weak (18-25)"
        elif adx_val < 35:
            key = "moderate (25-35)"
        elif adx_val < 50:
            key = "strong (35-50)"
        else:
            key = "very strong (>50)"

        ranges[key]["total"] += 1
        outcome = t["outcome"]
        if outcome == "win":
            ranges[key]["wins"] += 1
        else:
            ranges[key]["losses"] += 1

    for key, stat in ranges.items():
        stat["win_rate"] = round((stat["wins"] / stat["total"]) * 100, 1) if stat["total"] > 0 else 0

    return ranges

def analyze_session_time(trades: list) -> dict:
    """Win rate by trading session."""
    sessions = {
        "Asia (7-11 WIB)": {"wins": 0, "losses": 0, "total": 0},
        "London (13-18 WIB)": {"wins": 0, "losses": 0, "total": 0},
        "US Overlap (19-22 WIB)": {"wins": 0, "losses": 0, "total": 0},
    }
    for t in trades:
        wib_str = t.get("wib", "")
        if not wib_str:
            continue
        try:
            hour = int(wib_str.split(":")[0].split()[-1])
        except:
            continue

        outcome = t["outcome"]
        if 7 <= hour < 11:
            key = "Asia (7-11 WIB)"
        elif 13 <= hour < 18:
            key = "London (13-18 WIB)"
        elif 19 <= hour < 22:
            key = "US Overlap (19-22 WIB)"
        else:
            continue

        sessions[key]["total"] += 1
        if outcome == "win":
            sessions[key]["wins"] += 1
        else:
            sessions[key]["losses"] += 1

    for key, stat in sessions.items():
        stat["win_rate"] = round((stat["wins"] / stat["total"]) * 100, 1) if stat["total"] > 0 else 0

    return sessions

# ── Parameter Optimization ──────────────────────────────────

def optimize_parameters(trades: list, current_cfg: dict) -> dict:
    """Analyze trade data and suggest optimized parameters."""
    cfg = dict(current_cfg)
    total = len(trades)
    wins = sum(1 for t in trades if t["outcome"] == "win")
    losses = sum(1 for t in trades if t["outcome"] == "loss")
    wr = (wins / total) * 100 if total > 0 else 0
    pnl = sum(t.get("pnl", 0) or 0 for t in trades)

    by_type = analyze_trigger_type(trades)
    by_pair = analyze_by_pair(trades)
    by_rsi = analyze_rsi_range(trades)
    by_adx = analyze_adx_range(trades)
    by_session = analyze_session_time(trades)

    changes = []

    # ── 1. ADX_MIN optimization ──
    weak_adx = by_adx.get("weak (18-25)", {})
    if weak_adx.get("total", 0) >= 3:
        if weak_adx["win_rate"] < 35:
            cfg["adx_min"] = 25
            changes.append(f"ADX_MIN raised to 25 (weak ADX WR {weak_adx['win_rate']}% < 35%)")
        elif weak_adx["win_rate"] >= 55:
            cfg["adx_min"] = 18
            changes.append(f"ADX_MIN kept at 18 (weak ADX WR {weak_adx['win_rate']}% >= 55%)")

    # ── 2. Trigger bias optimization ──
    mom = by_type.get("momentum", {})
    pul = by_type.get("pullback", {})
    if mom.get("total", 0) >= 3 and pul.get("total", 0) >= 3:
        diff = mom["win_rate"] - pul["win_rate"]
        if abs(diff) > 15:
            if mom["win_rate"] > pul["win_rate"]:
                cfg["trigger_bias"] = "momentum"
                changes.append(f"Bias → MOMENTUM ({mom['win_rate']}% vs pullback {pul['win_rate']}%)")
            else:
                cfg["trigger_bias"] = "pullback"
                changes.append(f"Bias → PULLBACK ({pul['win_rate']}% vs momentum {mom['win_rate']}%)")
        else:
            cfg["trigger_bias"] = "none"
    elif mom.get("total", 0) >= 3:
        if mom["win_rate"] >= 60:
            cfg["trigger_bias"] = "momentum"
            changes.append(f"Bias → MOMENTUM (WR {mom['win_rate']}%)")
    elif pul.get("total", 0) >= 3:
        if pul["win_rate"] >= 60:
            cfg["trigger_bias"] = "pullback"
            changes.append(f"Bias → PULLBACK (WR {pul['win_rate']}%)")

    # ── 3. Blacklist poor performing pairs ──
    blacklist = []
    for sym, stat in sorted(by_pair.items(), key=lambda x: x[1]["win_rate"]):
        if stat["total"] >= 5 and stat["win_rate"] < 30:
            blacklist.append(sym)
            changes.append(f"⛔ {sym} blacklisted (WR {stat['win_rate']}% over {stat['total']} trades)")
    cfg["blacklisted_pairs"] = blacklist

    # ── 4. RSI range optimization ──
    ob = by_rsi.get("overbought (>75)", {})
    os_ = by_rsi.get("oversold (<25)", {})
    if ob.get("total", 0) >= 3 and ob["win_rate"] < 30:
        cfg["rsi_overbought"] = 70
        changes.append(f"RSI_OVERBOUGHT → 70 (overbought WR {ob['win_rate']}%)")
    if os_.get("total", 0) >= 3 and os_["win_rate"] < 30:
        cfg["rsi_oversold"] = 30
        changes.append(f"RSI_OVERSOLD → 30 (oversold WR {os_['win_rate']}%)")

    # ── 5. Volume optimization ──
    # Volume impact is tracked via win rate by session
    # If Asia session has very low WR, be more selective there
    asia = by_session.get("Asia (7-11 WIB)", {})
    if asia.get("total", 0) >= 3 and asia["win_rate"] < 30:
        cfg["volume_multiplier"] = 1.0  # stricter volume in asia
        changes.append(f"Volume multiplier → 1.0 (Asia WR low {asia['win_rate']}%)")

    # ── 6. Pullback zone adjustment ──
    pul_trades = [t for t in trades if "PULLBACK" in (t.get("rationale", t.get("reason", ""))).upper()]
    pul_wins = sum(1 for t in pul_trades if t["outcome"] == "win")
    if len(pul_trades) >= 5:
        pul_wr = (pul_wins / len(pul_trades)) * 100
        if pul_wr < 35:
            cfg["pullback_zone_atr"] = 1.5  # tighter
            changes.append(f"Pullback zone → 1.5 ATR (WR {round(pul_wr,1)}%)")

    cfg["_changes"] = changes
    cfg["_analysis"] = {
        "total_trades": total,
        "win_rate": round(wr, 1),
        "total_pnl": round(pnl, 2),
        "by_trigger": by_type,
        "by_pair": by_pair,
        "by_rsi": by_rsi,
        "by_adx": by_adx,
        "by_session": by_session,
    }

    return cfg


def tune(force=False) -> dict:
    """Main tuning function — analyzes trades and optimizes parameters."""
    trades = load_trades()
    cfg = load_config()

    if len(trades) < MIN_TRADES_FOR_ANALYSIS:
        if force:
            print(f"  ⚠️ Hanya {len(trades)} trade scalping — butuh min {MIN_TRADES_FOR_ANALYSIS}")
        return cfg

    # Only tune every N trades
    tunable_trades = len(trades) - (cfg.get("tune_count", 0) * TUNE_EVERY_N_TRADES)
    if not force and tunable_trades < TUNE_EVERY_N_TRADES and cfg.get("last_tuned"):
        return cfg  # Not enough new trades to tune

    print(f"\n🧠 Quant Learner — Analyzing {len(trades)} scalping trades...")
    new_cfg = optimize_parameters(trades, cfg)
    save_config(new_cfg)

    changes = new_cfg.get("_changes", [])
    analysis = new_cfg.get("_analysis", {})

    if changes:
        print(f"  📊 WR: {analysis.get('win_rate','?')}% | PnL: ${analysis.get('total_pnl',0):.2f}")
        print(f"  🔧 Changes ({len(changes)}):")
        for c in changes:
            print(f"    • {c}")
    else:
        print(f"  ✅ No changes needed (WR: {analysis.get('win_rate','?')}%, {analysis.get('total_trades',0)} trades)")

    return new_cfg

# ── Analyse-only (no save) ──────────────────────────────────

def analyze_only() -> dict:
    """Just analyze and print report, don't change config."""
    trades = load_trades()
    if not trades:
        return {"status": "no_data", "trades": 0}

    by_type = analyze_trigger_type(trades)
    by_pair = analyze_by_pair(trades)
    by_rsi = analyze_rsi_range(trades)
    by_adx = analyze_adx_range(trades)
    by_session = analyze_session_time(trades)

    wins = sum(1 for t in trades if t["outcome"] == "win")
    total = len(trades)
    pnl = sum(t.get("pnl", 0) or 0 for t in trades)

    return {
        "status": "ok",
        "total_trades": total,
        "wins": wins,
        "losses": total - wins,
        "win_rate": round((wins/total)*100, 1) if total > 0 else 0,
        "total_pnl": round(pnl, 2),
        "by_trigger": by_type,
        "by_pair": by_pair,
        "by_rsi": by_rsi,
        "by_adx": by_adx,
        "by_session": by_session,
    }

def print_report(report: dict):
    """Print analysis report to stdout."""
    if report.get("status") == "no_data":
        print("📊 Quant Learner — No scalping trade data yet")
        return

    print(f"\n{'='*45}")
    print(f"📊 Quant Learner Report")
    print(f"{'='*45}")
    print(f"Total: {report['total_trades']} ({report['wins']}W/{report['losses']}L)")
    print(f"Win Rate: {report['win_rate']}% | PnL: ${report['total_pnl']:.2f}")

    print(f"\n🔹 By Trigger Type:")
    for trig, stat in sorted(report["by_trigger"].items(), key=lambda x: x[1]["total"], reverse=True):
        print(f"  {trig.title():10} {stat['total']:3} trades | WR {stat['win_rate']:5.1f}% | PnL ${stat['pnl']:+.2f}")

    print(f"\n🔹 By Pair:")
    for sym, stat in sorted(report["by_pair"].items(), key=lambda x: x[1]["total"], reverse=True):
        wr_color = "🟢" if stat["win_rate"] >= 55 else "🟡" if stat["win_rate"] >= 40 else "🔴"
        print(f"  {wr_color} {sym:10} {stat['total']:3} trades | WR {stat['win_rate']:5.1f}% | PnL ${stat['pnl']:+.2f}")

    print(f"\n🔹 By RSI Range:")
    for rng, stat in sorted(report["by_rsi"].items(), key=lambda x: x[1]["total"], reverse=True):
        if stat["total"] > 0:
            print(f"  {rng:20} {stat['total']:3} trades | WR {stat['win_rate']:5.1f}%")

    print(f"\n🔹 By ADX Range:")
    for rng, stat in sorted(report["by_adx"].items(), key=lambda x: x[1]["total"], reverse=True):
        if stat["total"] > 0:
            print(f"  {rng:20} {stat['total']:3} trades | WR {stat['win_rate']:5.1f}%")

    print(f"\n🔹 By Session:")
    for sess, stat in sorted(report["by_session"].items(), key=lambda x: x[1]["total"], reverse=True):
        if stat["total"] > 0:
            print(f"  {sess:22} {stat['total']:3} trades | WR {stat['win_rate']:5.1f}%")

    print()


# ── CLI ─────────────────────────────────────────────────────

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Quant Learner — adaptive parameter tuning")
    parser.add_argument("--tune", action="store_true", help="Analyze + optimize parameters")
    parser.add_argument("--report", action="store_true", help="Print analysis report only")
    parser.add_argument("--reset", action="store_true", help="Reset config to defaults")
    args = parser.parse_args()

    if args.reset:
        cfg = reset_config()
        print("✅ Config reset to defaults")

    if args.report:
        report = analyze_only()
        print_report(report)

    if args.tune:
        cfg = tune(force=True)
        print(f"✅ Tuned — config saved to {QUANT_CONFIG_FILE}")
        changes = cfg.get("_changes", [])
        if changes:
            print(f"   Changes: {len(changes)}")
            for c in changes:
                print(f"   • {c}")

    if not any([args.reset, args.report, args.tune]):
        # Default: show report
        report = analyze_only()
        print_report(report)

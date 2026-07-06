"""
Hermes Exness Trading System v1.2 — Dashboard
===============================================
Dark-themed monitoring dashboard for the trading bot.
Shows: Balance, Equity, PNL, Win Rate, Trade History, Decision Logs.
"""

import json
import os
import sys
import glob
from datetime import datetime, timezone, timedelta
from pathlib import Path
from flask import Flask, render_template, jsonify

# Add parent directory to path
HERMES_DIR = Path(__file__).parent.parent.resolve()
sys.path.insert(0, str(HERMES_DIR))

app = Flask(__name__)

WIB = timezone(timedelta(hours=7))


def get_mt5_connection():
    """Initialize MT5 connection and return account info."""
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            return None
        info = mt5.account_info()
        if info is None:
            return None
        return {
            "login": info.login,
            "server": info.server,
            "balance": info.balance,
            "equity": info.equity,
            "margin": info.margin,
            "free_margin": info.margin_free,
            "margin_level": info.margin_level,
            "profit": info.profit,
            "currency": info.currency,
            "leverage": info.leverage,
            "trade_allowed": info.trade_allowed,
        }
    except Exception as e:
        return {"error": str(e)}


def get_open_positions():
    """Get all open positions from MT5."""
    try:
        import MetaTrader5 as mt5
        positions = mt5.positions_get()
        if positions is None:
            return []
        result = []
        for p in positions:
            result.append({
                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": "BUY" if p.type == 0 else "SELL",
                "volume": p.volume,
                "open_price": p.price_open,
                "current_price": p.price_current,
                "sl": p.sl,
                "tp": p.tp,
                "profit": p.profit,
                "swap": p.swap,
                "time": datetime.fromtimestamp(p.time, tz=WIB).strftime("%Y-%m-%d %H:%M"),
                "magic": p.magic,
                "comment": p.comment,
            })
        return result
    except Exception as e:
        return []


def get_trade_history(days=30):
    """Get trade history from MT5."""
    try:
        import MetaTrader5 as mt5
        from_date = datetime.now() - timedelta(days=days)
        to_date = datetime.now()
        deals = mt5.history_deals_get(from_date, to_date)
        if deals is None:
            return []
        result = []
        for d in deals:
            if d.entry == 0:  # Skip entry deals, only show exits
                continue
            result.append({
                "ticket": d.ticket,
                "order": d.order,
                "symbol": d.symbol,
                "type": "BUY" if d.type == 0 else "SELL",
                "volume": d.volume,
                "price": d.price,
                "profit": d.profit,
                "swap": d.swap,
                "commission": d.commission,
                "net_pnl": round(d.profit + d.swap + d.commission, 2),
                "time": datetime.fromtimestamp(d.time, tz=WIB).strftime("%Y-%m-%d %H:%M"),
                "magic": d.magic,
                "comment": d.comment,
            })
        # Sort by time descending
        result.sort(key=lambda x: x["time"], reverse=True)
        return result
    except Exception as e:
        return []


def get_decision_logs(limit=20):
    """Get recent decision cycle logs."""
    debate_dir = HERMES_DIR / "logs" / "agent_debates"
    if not debate_dir.exists():
        return []
    
    files = sorted(debate_dir.glob("cycle_*.json"), reverse=True)[:limit]
    logs = []
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            
            final = data.get("final_decision", {})
            tech = data.get("agent_results", {}).get("technical_agent", {})
            tech_out = tech.get("output_json", {})
            candidates = tech_out.get("top_candidates", [])
            rejected = tech_out.get("rejected_pairs", [])
            
            logs.append({
                "file": f.name,
                "timestamp": data.get("timestamp", ""),
                "mode": data.get("mode", "?"),
                "model": data.get("model", "?"),
                "action": final.get("action", "?"),
                "reason": final.get("reason", ""),
                "symbol": final.get("best_symbol", "-"),
                "side": final.get("side", "-"),
                "rr": final.get("rr", 0),
                "confidence": final.get("confidence", 0),
                "candidates_count": len(candidates),
                "rejected_count": len(rejected),
                "safety_gate": final.get("safety_gate", "?"),
                "duration_ms": data.get("total_duration_ms", 0),
            })
        except Exception:
            continue
    return logs


def get_dryrun_logs(limit=20):
    """Get recent dry-run execution logs."""
    dryrun_dir = HERMES_DIR / "logs" / "dry_run"
    if not dryrun_dir.exists():
        return []
    
    files = sorted(dryrun_dir.glob("dryrun_*.json"), reverse=True)[:limit]
    logs = []
    for f in files:
        try:
            with open(f, "r", encoding="utf-8") as fh:
                data = json.load(fh)
            logs.append({
                "file": f.name,
                "timestamp": data.get("timestamp", ""),
                "action": data.get("final_action", data.get("action", "?")),
                "symbol": data.get("symbol", "-"),
                "side": data.get("side", "-"),
                "lot": data.get("lot_size", 0),
                "entry": data.get("planned_entry", 0),
                "sl": data.get("sl_price", 0),
                "tp": data.get("tp_price", 0),
                "rr": data.get("rr", 0),
                "confidence": data.get("confidence", 0),
                "result": data.get("result", "?"),
                "reason": data.get("reason", ""),
            })
        except Exception:
            continue
    return logs


def get_scheduler_state():
    """Get current scheduler state."""
    state_file = HERMES_DIR / "logs" / "scheduler" / "scheduler_state.json"
    if not state_file.exists():
        return {"status": "unknown"}
    try:
        with open(state_file, "r") as f:
            return json.load(f)
    except Exception:
        return {"status": "error"}


def get_stats(history):
    """Calculate trading statistics from history."""
    if not history:
        return {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "win_rate": 0,
            "total_pnl": 0,
            "avg_win": 0,
            "avg_loss": 0,
            "best_trade": 0,
            "worst_trade": 0,
            "profit_factor": 0,
        }
    
    wins = [t for t in history if t["net_pnl"] > 0]
    losses = [t for t in history if t["net_pnl"] < 0]
    total_pnl = sum(t["net_pnl"] for t in history)
    total_wins = sum(t["net_pnl"] for t in wins) if wins else 0
    total_losses = abs(sum(t["net_pnl"] for t in losses)) if losses else 0
    
    return {
        "total_trades": len(history),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(len(wins) / len(history) * 100, 1) if history else 0,
        "total_pnl": round(total_pnl, 2),
        "avg_win": round(total_wins / len(wins), 2) if wins else 0,
        "avg_loss": round(total_losses / len(losses), 2) if losses else 0,
        "best_trade": max((t["net_pnl"] for t in history), default=0),
        "worst_trade": min((t["net_pnl"] for t in history), default=0),
        "profit_factor": round(total_wins / total_losses, 2) if total_losses > 0 else 0,
    }


# ─── Routes ────────────────────────────────────────────────────────────

@app.route("/")
def index():
    return render_template("index.html")


@app.route("/api/account")
def api_account():
    data = get_mt5_connection()
    if data is None:
        return jsonify({"error": "MT5 not connected"})
    return jsonify(data)


@app.route("/api/positions")
def api_positions():
    return jsonify(get_open_positions())


@app.route("/api/history")
def api_history():
    return jsonify(get_trade_history(30))


@app.route("/api/decisions")
def api_decisions():
    return jsonify(get_decision_logs(20))


@app.route("/api/dryrun")
def api_dryrun():
    return jsonify(get_dryrun_logs(20))


@app.route("/api/stats")
def api_stats():
    history = get_trade_history(30)
    return jsonify(get_stats(history))


@app.route("/api/scheduler")
def api_scheduler():
    return jsonify(get_scheduler_state())


@app.route("/api/dashboard")
def api_dashboard():
    """Single endpoint for all dashboard data."""
    account = get_mt5_connection()
    positions = get_open_positions()
    history = get_trade_history(30)
    decisions = get_decision_logs(10)
    dryrun = get_dryrun_logs(10)
    stats = get_stats(history)
    scheduler = get_scheduler_state()
    
    return jsonify({
        "account": account,
        "positions": positions,
        "history": history[:20],
        "decisions": decisions,
        "dryrun": dryrun,
        "stats": stats,
        "scheduler": scheduler,
        "updated_at": datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S WIB"),
    })


if __name__ == "__main__":
    print("=" * 50)
    print("  Hermes Exness Dashboard v1.2")
    print("  http://localhost:5555")
    print("=" * 50)
    app.run(host="0.0.0.0", port=5555, debug=False)

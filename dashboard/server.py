"""
Hermes Dashboard — Ultra Light Server
======================================
~5MB RAM vs Flask's ~200MB.
Generates data JSON + serves static HTML.
Refreshes data every 60 seconds automatically.
"""

import json
import os
import sys
import threading
import time
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, SimpleHTTPRequestHandler
from pathlib import Path

HERMES_DIR = Path(__file__).parent.parent.resolve()
DASHBOARD_DIR = Path(__file__).parent.resolve()
DATA_FILE = DASHBOARD_DIR / "static" / "dashboard_data.json"
WIB = timezone(timedelta(hours=7))

sys.path.insert(0, str(HERMES_DIR))


def collect_data():
    """Collect all dashboard data from MT5 + log files."""
    data = {
        "account": None,
        "positions": [],
        "history": [],
        "decisions": [],
        "dryrun": [],
        "stats": {},
        "scheduler": {},
        "updated_at": datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S WIB"),
    }

    # MT5 Account
    try:
        import MetaTrader5 as mt5
        if mt5.initialize():
            info = mt5.account_info()
            if info:
                data["account"] = {
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
                }

            # Open positions
            positions = mt5.positions_get()
            if positions:
                for p in positions:
                    data["positions"].append({
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
                    })

            # Trade history (30 days) — match IN/OUT deals to get real direction
            from_date = datetime.now() - timedelta(days=30)
            deals = mt5.history_deals_get(from_date, datetime.now())
            if deals:
                # Build position_id → type map from IN deals
                pos_types = {}
                for d in deals:
                    if d.entry == 0:  # DEAL_ENTRY_IN
                        pos_types[d.position_id] = "BUY" if d.type == 0 else "SELL"

                for d in deals:
                    if d.entry != 1:  # Only OUT deals (closing)
                        continue
                    # Get real direction from matching IN deal
                    real_type = pos_types.get(d.position_id, "BUY" if d.type == 0 else "SELL")
                    data["history"].append({
                        "ticket": d.ticket,
                        "position_id": d.position_id,
                        "symbol": d.symbol,
                        "type": real_type,
                        "volume": d.volume,
                        "price": d.price,
                        "profit": d.profit,
                        "swap": d.swap,
                        "commission": d.commission,
                        "net_pnl": round(d.profit + d.swap + d.commission, 2),
                        "time": datetime.fromtimestamp(d.time, tz=WIB).strftime("%Y-%m-%d %H:%M"),
                        "comment": d.comment,
                    })
                data["history"].sort(key=lambda x: x["time"], reverse=True)
    except Exception as e:
        data["account"] = {"error": str(e)}

    # Decision logs
    debate_dir = HERMES_DIR / "logs" / "agent_debates"
    if debate_dir.exists():
        files = sorted(debate_dir.glob("cycle_*.json"), reverse=True)[:30]
        for f in files:
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    d = json.load(fh)
                final = d.get("final_decision", {})
                tech = d.get("agent_results", {}).get("technical_agent", {})
                tech_out = tech.get("output_json", {})
                data["decisions"].append({
                    "timestamp": d.get("timestamp", ""),
                    "mode": d.get("mode", "?"),
                    "model": d.get("model", "?"),
                    "action": final.get("action", "?"),
                    "reason": final.get("reason", ""),
                    "symbol": final.get("best_symbol", "-"),
                    "side": final.get("side", "-"),
                    "rr": final.get("rr", 0),
                    "confidence": final.get("confidence", 0),
                    "candidates": len(tech_out.get("top_candidates", [])),
                    "rejected": len(tech_out.get("rejected_pairs", [])),
                    "duration_s": round(d.get("total_duration_ms", 0) / 1000, 1),
                })
            except Exception:
                continue

    # Dry-run logs
    dryrun_dir = HERMES_DIR / "logs" / "dry_run"
    if dryrun_dir.exists():
        files = sorted(dryrun_dir.glob("dryrun_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:30]
        for f in files:
            try:
                with open(f, "r", encoding="utf-8") as fh:
                    d = json.load(fh)
                data["dryrun"].append({
                    "timestamp": d.get("timestamp", ""),
                    "action": d.get("final_action", d.get("action", "?")),
                    "symbol": d.get("symbol", "-"),
                    "side": d.get("side", "-"),
                    "lot": d.get("lot_size", d.get("lot", 0)),
                    "entry": d.get("planned_entry", d.get("entry", d.get("entry_price", 0))),
                    "sl": d.get("sl_price", d.get("sl", 0)),
                    "tp": d.get("tp_price", d.get("tp", 0)),
                    "rr": d.get("rr", 0),
                    "result": d.get("result", d.get("reason", "")),
                })
            except Exception:
                continue

    # Update the positions with comment-based type
    for pos in data["positions"]:
        # We don't have comment from positions_get, but we can check via demo_exec logs
        pass
    
    # Also read final_decision.json for current mode info
    fd_path = HERMES_DIR / "final_decision.json"
    if fd_path.exists():
        try:
            with open(fd_path) as f:
                fd = json.load(f)
            data["current_decision"] = {
                "action": fd.get("action", "?"),
                "symbol": fd.get("best_symbol", "-"),
                "side": fd.get("side", "-"),
                "mode_trade": fd.get("mode_trade", "day"),
            }
        except Exception:
            data["current_decision"] = {}
    
    # ── Read Demo Execution Logs for mode_trade ──
    exec_dir = HERMES_DIR / "logs" / "demo_execution"
    mode_map = {}  # ticket -> mode
    if exec_dir.exists():
        files = sorted(exec_dir.glob("demo_exec_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:100]
        for f in files:
            try:
                with open(f) as fh:
                    ed = json.load(fh)
                if ed.get("status") == "executed" and ed.get("order_ticket"):
                    ticket = str(ed["order_ticket"])
                    mode_map[ticket] = ed.get("trade_mode", "day")
            except Exception:
                pass
    
    # Tag history trades with mode
    for t in data["history"]:
        ticket_str = str(t.get("ticket", ""))
        pos_id = t.get("position_id", "")
        # Match by ticket or position_id
        mode_from_exec = mode_map.get(ticket_str) or mode_map.get(str(pos_id))
        # Also check MT5 comment field
        comment = t.get("comment", "").upper()
        if "SCALP" in comment:
            t["mode"] = "scalp"
        elif mode_from_exec:
            t["mode"] = mode_from_exec
        else:
            # Try by position_id
            t["mode"] = mode_map.get(f"pos_{pos_id}", "day")
    
    # Stats for scalping vs day trade
    history = data["history"]
    if history:
        scalp_trades = [t for t in history if t.get("mode") == "scalp"]
        day_trades = [t for t in history if t.get("mode", "day") == "day"]
        
        def calc_stats(trades, label):
            if not trades:
                return {"total": 0, "wins": 0, "losses": 0, "win_rate": 0, "total_pnl": 0, "total_pips": 0, "pf": 0}
            wins = [t for t in trades if t["net_pnl"] > 0]
            losses = [t for t in trades if t["net_pnl"] < 0]
            total_wins = sum(t["net_pnl"] for t in wins)
            total_losses = abs(sum(t["net_pnl"] for t in losses))
            total_pips = sum(t.get("pips", 0) for t in trades)
            return {
                "total": len(trades),
                "wins": len(wins),
                "losses": len(losses),
                "win_rate": round(len(wins) / len(trades) * 100, 1) if trades else 0,
                "total_pnl": round(sum(t["net_pnl"] for t in trades), 2),
                "total_pips": round(total_pips, 1),
                "avg_win": round(total_wins / len(wins), 2) if wins else 0,
                "avg_loss": round(total_losses / len(losses), 2) if losses else 0,
                "pf": round(total_wins / total_losses, 2) if total_losses > 0 else 0,
            }
        
        data["stats_scalp"] = calc_stats(scalp_trades, "SCALP")
        data["stats_day"] = calc_stats(day_trades, "DAY")
    else:
        data["stats_scalp"] = {"total": 0}
        data["stats_day"] = {"total": 0}
    if history:
        wins = [t for t in history if t["net_pnl"] > 0]
        losses = [t for t in history if t["net_pnl"] < 0]
        total_wins = sum(t["net_pnl"] for t in wins)
        total_losses = abs(sum(t["net_pnl"] for t in losses))

        # Calculate pips for each trade
        total_pips = 0.0
        for t in history:
            sym = t.get("symbol", "").upper()
            profit = t.get("net_pnl", 0)
            vol = t.get("volume", 0) or 0.01
            if "XAU" in sym:
                pips = profit / (vol * 10) if vol else 0
            elif "JPY" in sym:
                pips = profit / (vol * 10) if vol else 0
            else:
                pips = profit / (vol * 10) if vol else 0
            t["pips"] = round(pips, 1)
            total_pips += pips

        data["stats"] = {
            "total": len(history),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": round(len(wins) / len(history) * 100, 1) if history else 0,
            "total_pnl": round(sum(t["net_pnl"] for t in history), 2),
            "total_pips": round(total_pips, 1),
            "avg_win": round(total_wins / len(wins), 2) if wins else 0,
            "avg_loss": round(total_losses / len(losses), 2) if losses else 0,
            "best": max(t["net_pnl"] for t in history),
            "worst": min(t["net_pnl"] for t in history),
            "pf": round(total_wins / total_losses, 2) if total_losses > 0 else 0,
        }
    else:
        data["stats"] = {"total": 0, "wins": 0, "losses": 0, "win_rate": 0, "total_pnl": 0, "total_pips": 0, "pf": 0}

    # Scheduler state
    state_file = HERMES_DIR / "logs" / "scheduler" / "scheduler_state.json"
    if state_file.exists():
        try:
            with open(state_file, "r") as f:
                data["scheduler"] = json.load(f)
        except Exception:
            pass

    # Health check (pass account data so it doesn't re-init MT5)
    try:
        from health_check import collect_health
        data["health"] = collect_health(mt5_account=data.get("account"))
    except Exception:
        data["health"] = {"overall": "unknown", "detail": "health_check module failed"}

    return data


def save_data(data):
    """Save data to static JSON file."""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, default=str)


def data_refresh_loop():
    """Background thread: refresh data every 60 seconds."""
    while True:
        try:
            data = collect_data()
            save_data(data)
            print(f"[{datetime.now(WIB).strftime('%H:%M:%S')}] Data refreshed", flush=True)
        except Exception as e:
            print(f"[ERROR] Data refresh failed: {e}", flush=True)
        time.sleep(60)


class QuietHandler(SimpleHTTPRequestHandler):
    """Serve files from the static/ directory."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=str(DASHBOARD_DIR / "static"), **kwargs)

    def log_message(self, format, *args):
        pass  # Suppress request logs


def main():
    port = int(os.environ.get("DASHBOARD_PORT", 5555))

    # Generate initial data
    print("[INIT] Collecting initial data...", flush=True)
    data = collect_data()
    save_data(data)
    print(f"[INIT] Data saved ({len(data.get('decisions',[]))} decisions, {len(data.get('history',[]))} trades)", flush=True)

    # Copy index.html to static/
    src_html = DASHBOARD_DIR / "templates" / "index.html"
    dst_html = DASHBOARD_DIR / "static" / "index.html"
    if src_html.exists():
        import shutil
        shutil.copy2(src_html, dst_html)

    # Start server — NO data refresh loop, handled by cron dashboard_data_provider.py
    server = HTTPServer(("0.0.0.0", port), QuietHandler)
    print(f"[OK] Dashboard running at http://0.0.0.0:{port}", flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n[STOP] Dashboard stopped.", flush=True)
        server.server_close()


if __name__ == "__main__":
    main()

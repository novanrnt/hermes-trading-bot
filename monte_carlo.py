#!/usr/bin/env python3
"""
Monte Carlo Trade Simulator — stress-test trading strategy robustness.
Usage: python monte_carlo.py           # full report
       python monte_carlo.py --quick   # compact summary
"""
import json, random, statistics, sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

WIB = timezone(timedelta(hours=7))
HERMES = Path(__file__).parent.resolve()
SIMULATIONS = 10_000

def load_trades():
    """Load executed trades — prioritize MT5 history (accurate PnL), fallback to demo logs."""
    # Try MT5 history first (most accurate PnL)
    mt5_trades = _load_mt5_history()
    if mt5_trades and len(mt5_trades) >= 3:
        return mt5_trades
    
    # Fallback to demo execution logs
    trades = []
    exec_dir = HERMES / "logs" / "demo_execution"
    if not exec_dir.exists():
        return trades
    
    for f in sorted(exec_dir.glob("*.json")):
        try:
            d = json.load(open(f))
            status = d.get("status", "")
            if status in ("entry", "executed"):
                pnl = d.get("net_pnl") or d.get("realized_pnl") or 0
                if pnl == 0:
                    pnl = d.get("profit", 0)
                trades.append({
                    "symbol": d.get("symbol", "?"),
                    "side": d.get("side", "?"),
                    "pnl": float(pnl),
                    "rr": d.get("planned_rr", d.get("rr", 0)),
                    "time": d.get("timestamp", "")[:19],
                })
        except Exception:
            pass
    
    return trades

def _load_mt5_history():
    """Load closed trades from MT5 history (most accurate PnL)."""
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            return []
        
        from datetime import datetime
        # Get history from last 30 days
        from_date = datetime.now() - timedelta(days=30)
        deals = mt5.history_deals_get(from_date, datetime.now())
        if not deals:
            mt5.shutdown()
            return []
        
        # Build position_id -> entry deal map
        pos_types = {}
        for d in deals:
            if d.entry == 0:  # Entry
                pos_types[d.position_id] = "BUY" if d.type == 0 else "SELL"
        
        # Collect closed positions with profit
        trades = []
        seen_positions = set()
        for d in deals:
            if d.entry == 1 and d.position_id not in seen_positions:  # Exit
                seen_positions.add(d.position_id)
                side = pos_types.get(d.position_id, "?")
                trades.append({
                    "symbol": d.symbol,
                    "side": side,
                    "pnl": float(d.profit),
                    "rr": 0,
                    "time": str(d.time),
                })
        
        mt5.shutdown()
        return sorted(trades, key=lambda t: t["time"])
    except Exception:
        return []


def run_monte_carlo(pnls, simulations=SIMULATIONS):
    """Run Monte Carlo simulation: randomly shuffle trade sequence N times."""
    n = len(pnls)
    if n < 3:
        return None
    
    results = {
        "final_equity": [],
        "max_drawdown_pct": [],
        "max_drawdown_abs": [],
        "win_streak_max": [],
        "loss_streak_max": [],
        "ruined": 0,  # equity drops below 50% of peak
    }
    
    start_equity = 10000  # normalize to $10K
    
    for _ in range(simulations):
        shuffled = random.sample(pnls, n)
        equity = start_equity
        peak = start_equity
        max_dd_pct = 0
        max_dd_abs = 0
        curr_win_streak = 0
        max_win_streak = 0
        curr_loss_streak = 0
        max_loss_streak = 0
        
        for pnl in shuffled:
            equity += pnl
            
            if equity > peak:
                peak = equity
                curr_win_streak = 0
                curr_loss_streak = 0
            
            if pnl > 0:
                curr_win_streak += 1
                curr_loss_streak = 0
                max_win_streak = max(max_win_streak, curr_win_streak)
            elif pnl < 0:
                curr_loss_streak += 1
                curr_win_streak = 0
                max_loss_streak = max(max_loss_streak, curr_loss_streak)
            
            dd_pct = (peak - equity) / peak * 100
            max_dd_pct = max(max_dd_pct, dd_pct)
            max_dd_abs = max(max_dd_abs, peak - equity)
            
            if equity < start_equity * 0.5:
                results["ruined"] += 1
        
        results["final_equity"].append(equity)
        results["max_drawdown_pct"].append(max_dd_pct)
        results["max_drawdown_abs"].append(max_dd_abs)
        results["win_streak_max"].append(max_win_streak)
        results["loss_streak_max"].append(max_loss_streak)
    
    return results


def percentile(data, p):
    """Calculate percentile from sorted data."""
    if not data:
        return 0
    data = sorted(data)
    idx = int(len(data) * p / 100)
    return data[min(idx, len(data)-1)]


def format_report(trades, results):
    """Generate readable Monte Carlo report."""
    n = len(trades)
    wins = [t for t in trades if t["pnl"] > 0]
    losses = [t for t in trades if t["pnl"] < 0]
    
    win_rate = len(wins) / n * 100 if n else 0
    avg_win = statistics.mean([t["pnl"] for t in wins]) if wins else 0
    avg_loss = statistics.mean([abs(t["pnl"]) for t in losses]) if losses else 0
    total_pnl = sum(t["pnl"] for t in trades)
    
    lines = []
    lines.append("🎲 **Monte Carlo Analysis**")
    lines.append("")
    lines.append(f"📊 **Sample:** {n} trades | Win: {len(wins)} ({win_rate:.0f}%) | Loss: {len(losses)}")
    lines.append(f"💰 **Real PnL:** ${total_pnl:.2f} | Avg Win: ${avg_win:.2f} | Avg Loss: ${avg_loss:.2f}")
    if avg_loss > 0:
        lines.append(f"📐 **Profit Factor:** {sum(t['pnl'] for t in wins)/abs(sum(t['pnl'] for t in losses)):.2f}" if wins and losses else "📐 Profit Factor: N/A")
    lines.append("")
    lines.append(f"🔄 **Simulations:** {SIMULATIONS:,}x random shuffle")
    lines.append("")
    
    # Equity curve range
    final_eq = results["final_equity"]
    lines.append("📈 **Final Equity Range ($10K start):**")
    lines.append(f"  • Best case (95%):  ${percentile(final_eq, 95):,.0f}")
    lines.append(f"  • Median (50%):     ${percentile(final_eq, 50):,.0f}")
    lines.append(f"  • Worst case (5%):  ${percentile(final_eq, 5):,.0f}")
    lines.append("")
    
    # Drawdown
    dd = results["max_drawdown_pct"]
    ruin_pct = results["ruined"] / SIMULATIONS * 100
    lines.append("📉 **Max Drawdown Risk:**")
    lines.append(f"  • 95% of runs:      ≤{percentile(dd, 95):.1f}%")
    lines.append(f"  • 50% of runs:      ≤{percentile(dd, 50):.1f}%")
    lines.append(f"  • Worst 5% runs:    ≤{percentile(dd, 5):.1f}%")
    lines.append(f"  • Ruin risk (50%):  {ruin_pct:.1f}%")
    lines.append("")
    
    # Streak analysis
    ws = results["win_streak_max"]
    ls = results["loss_streak_max"]
    lines.append("🎯 **Streak Analysis:**")
    lines.append(f"  • Max win streak:   {max(ws)} (typical)")
    lines.append(f"  • Max loss streak:  {max(ls)} (typical)")
    lines.append(f"  • 95% win streak ≤: {percentile(ws, 95)}")
    lines.append(f"  • 95% loss streak ≤:{percentile(ls, 95)}")
    lines.append("")
    
    # Verdict
    lines.append("🏆 **Verdict:**")
    if ruin_pct < 1 and percentile(dd, 95) < 20:
        lines.append("  ✅ Strategy is ROBUST — low ruin risk, manageable drawdown")
    elif ruin_pct < 5 and percentile(dd, 95) < 30:
        lines.append("  ⚠️ Strategy is OK — moderate risk, monitor closely")
    else:
        lines.append("  ❌ Strategy is FRAGILE — high ruin risk, needs improvement")
    
    if n < 20:
        lines.append(f"  ℹ️ Only {n} trades — need 20+ for statistical confidence")
    
    lines.append(f"\n⏰ _{datetime.now(WIB).strftime('%Y-%m-%d %H:%M')} WIB_")
    
    return "\n".join(lines)


def format_quick(trades, results):
    """Compact one-line summary."""
    n = len(trades)
    dd = results["max_drawdown_pct"]
    ruin = results["ruined"] / SIMULATIONS * 100
    
    wins = len([t for t in trades if t["pnl"] > 0])
    wr = wins / n * 100 if n else 0
    total = sum(t["pnl"] for t in trades)
    
    return (
        f"🎲 Monte Carlo ({n} trades): "
        f"WR {wr:.0f}% | PnL ${total:.0f} | "
        f"DD ≤{percentile(dd, 95):.1f}% | "
        f"Ruin {ruin:.1f}% → "
        f"{'✅ ROBUST' if ruin < 1 and percentile(dd, 95) < 20 else '⚠️ OK' if ruin < 5 else '❌ FRAGILE'}"
    )


if __name__ == "__main__":
    random.seed(42)
    
    trades = load_trades()
    if len(trades) < 3:
        print(f"Need 3+ trades for Monte Carlo (found {len(trades)})")
        sys.exit(1)
    
    pnls = [t["pnl"] for t in trades]
    results = run_monte_carlo(pnls)
    
    if results is None:
        print("Simulation failed")
        sys.exit(1)
    
    quick = "--quick" in sys.argv
    
    if quick:
        print(format_quick(trades, results))
    else:
        print(format_report(trades, results))
    
    # Save to log
    log_dir = HERMES / "logs" / "monte_carlo"
    log_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(WIB).strftime("%Y%m%d_%H%M%S")
    with open(log_dir / f"mc_{ts}.json", "w") as f:
        json.dump({
            "timestamp": datetime.now(WIB).isoformat(),
            "trades": len(trades),
            "total_pnl": sum(pnls),
            "simulation_count": SIMULATIONS,
            "percentiles": {
                "equity_p95": percentile(results["final_equity"], 95),
                "equity_p50": percentile(results["final_equity"], 50),
                "equity_p5": percentile(results["final_equity"], 5),
                "drawdown_p95": percentile(results["max_drawdown_pct"], 95),
                "drawdown_p50": percentile(results["max_drawdown_pct"], 50),
            },
            "ruin_risk_pct": results["ruined"] / SIMULATIONS * 100,
        }, f, indent=2)

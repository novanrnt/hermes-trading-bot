#!/usr/bin/env python3
"""
Hermes Exness Bot V1 — Adaptive Trailing Stop Manager
=======================================================
ATR-based trailing: activation threshold + dynamic trail distance per pair.
Runs as part of the scheduler cycle or standalone.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Any, Optional

BASE_DIR = Path(os.environ.get("HERMES_HOME", r"C:\Users\Administrator\AppData\Local\hermes"))
WIB = timezone(timedelta(hours=7))
LOG_DIR = BASE_DIR / "logs" / "trailing"
LOG_DIR.mkdir(parents=True, exist_ok=True)

# ─── Trailing config ──────────────────────────────────────────────────────
TRAIL_CONFIG = {
    "activation_pct": 0.5,       # Activate when profit >= 50% of risk
    "trail_atr_mult": 2.0,       # Trail distance = 2x M15 ATR (was 1.5x)
    "fallback_min": {
        "XAU": 2.00,             # $2.00 for gold (only if ATR unavailable)
        "JPY": 0.15,             # 15 pips for JPY
        "default": 0.0010,       # 10 pips for majors
    },
}


def get_atr(symbol: str) -> float:
    """Get M15 ATR from MT5 live data. Falls back to H1 ATR."""
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            return None

        # Try to get from symbol info or compute
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_M15, 0, 15)
        if rates is None or len(rates) < 2:
            mt5.shutdown()
            return None

        # Simple ATR calculation from recent candles
        tr_sum = 0.0
        for i in range(1, len(rates)):
            high = rates[i]["high"]
            low = rates[i]["low"]
            prev_close = rates[i-1]["close"]
            tr = max(high - low, abs(high - prev_close), abs(low - prev_close))
            tr_sum += tr
        atr = tr_sum / (len(rates) - 1)
        mt5.shutdown()
        return atr
    except Exception:
        return None


def get_fallback_distance(symbol: str) -> float:
    """Fallback trail distance when ATR unavailable."""
    sym = symbol.upper()
    if "XAU" in sym:
        return TRAIL_CONFIG["fallback_min"]["XAU"]
    if "JPY" in sym:
        return TRAIL_CONFIG["fallback_min"]["JPY"]
    return TRAIL_CONFIG["fallback_min"]["default"]


def calculate_trail_distance(symbol: str, atr: Optional[float] = None) -> float:
    """Calculate trailing distance = ATR * multiplier. Fallback if ATR missing."""
    if atr is None:
        atr = get_atr(symbol)
    if atr is None or atr <= 0:
        return get_fallback_distance(symbol)
    return atr * TRAIL_CONFIG["trail_atr_mult"]


def should_activate(entry_price: float, current_price: float, side: str,
                    risk_amount: float, volume: float) -> bool:
    """Check if trailing should activate (profit >= activation_pct * risk)."""
    if side == "buy":
        profit = (current_price - entry_price) * volume * _pip_value("XAUUSDm" if "XAU" in "XAU" else "EURUSDm")
    else:
        profit = (entry_price - current_price) * volume * _pip_value("XAUUSDm" if "XAU" in "XAU" else "EURUSDm")

    return profit >= risk_amount * TRAIL_CONFIG["activation_pct"]


def _pip_value(symbol: str) -> float:
    """Rough pip value multiplier for cent account."""
    sym = symbol.upper()
    if "XAU" in sym:
        return 100.0  # Gold: price change * lot * 100
    elif "JPY" in sym:
        return 1000.0
    else:
        return 100000.0


def run_trailing_check(env: dict = None) -> dict:
    """
    Check all open positions and apply trailing stop + breakeven.
    Returns summary dict.
    """
    if env is None:
        env = {}

    breakeven_enabled = env.get("BREAKEVEN_ENABLED", "false").lower() == "true"

    result = {
        "timestamp": datetime.now(WIB).isoformat(),
        "positions_checked": 0,
        "trail_activated": 0,
        "sl_updated": 0,
        "breakeven_applied": 0,
        "details": [],
    }

    # Track breakeven state to avoid re-applying
    be_state_file = BASE_DIR / "data" / "breakeven_state.json"
    be_applied = set()
    if be_state_file.exists():
        try:
            with open(be_state_file, "r") as f:
                be_data = json.load(f)
                be_applied = set(be_data.get("applied_tickets", []))
        except (json.JSONDecodeError, KeyError):
            pass

    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            result["error"] = "MT5 init failed"
            return result

        positions = mt5.positions_get()
        if not positions:
            mt5.shutdown()
            return result

        result["positions_checked"] = len(positions)

        for pos in positions:
            detail = {
                "ticket": pos.ticket,
                "symbol": pos.symbol,
                "type": "BUY" if pos.type == 0 else "SELL",
                "open_price": pos.price_open,
                "current_price": pos.price_current,
                "current_sl": pos.sl,
                "profit": pos.profit,
            }

            side = "buy" if pos.type == 0 else "sell"

            # ── BREAKEVEN CHECK (runs first, before trailing) ──
            be_done = False
            if breakeven_enabled and pos.ticket not in be_applied:
                if side == "buy":
                    if pos.price_current > pos.price_open and ((pos.sl or 0) < pos.price_open):
                        # Move SL to entry (breakeven)
                        req = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": pos.ticket,
                            "sl": pos.price_open,
                            "tp": pos.tp,
                        }
                        sent = mt5.order_send(req)
                        if sent and sent.retcode == mt5.TRADE_RETCODE_DONE:
                            detail["breakeven"] = "applied"
                            detail["old_sl"] = pos.sl
                            detail["new_sl"] = pos.price_open
                            detail["note"] = f"Breakeven: SL → entry ({pos.price_open})"
                            result["breakeven_applied"] += 1
                            be_applied.add(pos.ticket)
                            be_done = True
                        else:
                            detail["breakeven"] = "failed"
                            detail["be_reason"] = f"MT5 retcode: {sent.retcode if sent else 'no response'}"
                else:  # sell
                    if pos.price_current < pos.price_open and ((pos.sl or float("inf")) > pos.price_open):
                        req = {
                            "action": mt5.TRADE_ACTION_SLTP,
                            "position": pos.ticket,
                            "sl": pos.price_open,
                            "tp": pos.tp,
                        }
                        sent = mt5.order_send(req)
                        if sent and sent.retcode == mt5.TRADE_RETCODE_DONE:
                            detail["breakeven"] = "applied"
                            detail["old_sl"] = pos.sl
                            detail["new_sl"] = pos.price_open
                            detail["note"] = f"Breakeven: SL → entry ({pos.price_open})"
                            result["breakeven_applied"] += 1
                            be_applied.add(pos.ticket)
                            be_done = True
                        else:
                            detail["breakeven"] = "failed"
                            detail["be_reason"] = f"MT5 retcode: {sent.retcode if sent else 'no response'}"

            # ── TRAILING STOP (skip if breakeven just applied — SL already moved) ──
            if be_done:
                detail["action"] = "breakeven_only"
                result["details"].append(detail)
                continue

            m15_atr = get_atr(pos.symbol)
            trail_dist = calculate_trail_distance(pos.symbol, m15_atr)
            detail["atr"] = round(m15_atr, 6) if m15_atr else None
            detail["trail_distance"] = round(trail_dist, 6)

            # Calculate new SL
            if side == "buy":
                new_sl = pos.price_current - trail_dist
                # Only move SL UP (never down)
                if new_sl <= (pos.sl or 0):
                    detail["action"] = "skip"
                    detail["reason"] = "SL already above proposed trail"
                elif pos.price_current <= pos.price_open:
                    detail["action"] = "skip"
                    detail["reason"] = "Not yet in sufficient profit"
                else:
                    sl_price = new_sl
                    old_sl = pos.sl
                    req = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "position": pos.ticket,
                        "sl": sl_price,
                        "tp": pos.tp,
                    }
                    sent = mt5.order_send(req)
                    if sent and sent.retcode == mt5.TRADE_RETCODE_DONE:
                        detail["action"] = "updated"
                        detail["old_sl"] = old_sl
                        detail["new_sl"] = sl_price
                        detail["locked_profit"] = round((sl_price - pos.price_open) * pos.volume * _pip_value(pos.symbol), 2)
                        result["sl_updated"] += 1
                    else:
                        detail["action"] = "failed"
                        detail["reason"] = f"MT5 retcode: {sent.retcode if sent else 'no response'}"
            else:  # sell
                new_sl = pos.price_current + trail_dist
                if new_sl >= (pos.sl or float("inf")):
                    detail["action"] = "skip"
                    detail["reason"] = "SL already below proposed trail"
                elif pos.price_current >= pos.price_open:
                    detail["action"] = "skip"
                    detail["reason"] = "Not yet in sufficient profit"
                else:
                    sl_price = new_sl
                    old_sl = pos.sl
                    req = {
                        "action": mt5.TRADE_ACTION_SLTP,
                        "position": pos.ticket,
                        "sl": sl_price,
                        "tp": pos.tp,
                    }
                    sent = mt5.order_send(req)
                    if sent and sent.retcode == mt5.TRADE_RETCODE_DONE:
                        detail["action"] = "updated"
                        detail["old_sl"] = old_sl
                        detail["new_sl"] = sl_price
                        detail["locked_profit"] = round((pos.price_open - sl_price) * pos.volume * _pip_value(pos.symbol), 2)
                        result["sl_updated"] += 1
                    else:
                        detail["action"] = "failed"
                        detail["reason"] = f"MT5 retcode: {sent.retcode if sent else 'no response'}"

            result["details"].append(detail)

        mt5.shutdown()

    except Exception as e:
        result["error"] = str(e)

    # Save breakeven state
    be_state_file.parent.mkdir(parents=True, exist_ok=True)
    with open(be_state_file, "w") as f:
        json.dump({"applied_tickets": list(be_applied), "updated": datetime.now(WIB).isoformat()}, f, indent=2)

    # Save trailing log
    ts = datetime.now(WIB).strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"trail_{ts}.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(result, f, indent=2, default=str)

    return result


def print_summary(result: dict):
    """Print human-readable trailing summary."""
    print("=" * 60)
    print("  Adaptive Trailing Stop — Check")
    print("=" * 60)
    print(f"  Positions: {result['positions_checked']} | Updated: {result['sl_updated']}")
    for d in result.get("details", []):
        symbol = d["symbol"]
        action = d.get("action", "?")
        trail = d.get("trail_distance", "?")
        atr = d.get("atr", "?")
        if action == "updated":
            print(f"  ✅ {symbol}: SL {d['old_sl']:.2f} → {d['new_sl']:.2f} (trail: {trail}, ATR: {atr})")
            print(f"     Locked: ${d.get('locked_profit', 0):.2f}")
        elif action == "skip":
            print(f"  ⊘  {symbol}: {d.get('reason','?')} (trail: {trail}, ATR: {atr})")
        elif action == "failed":
            print(f"  ❌ {symbol}: {d.get('reason','?')}")
    print("=" * 60)


def main():
    env = {}
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()

    result = run_trailing_check(env)
    print_summary(result)

    # Return exit code based on activity
    return 0 if result.get("error") is None else 1


def main_silent():
    """Run trailing check — only print if SL was updated or breakeven applied."""
    env = {}
    result = run_trailing_check(env)

    if result.get("sl_updated", 0) > 0 or result.get("breakeven_applied", 0) > 0:
        updates = []
        for d in result.get("details", []):
            if d.get("breakeven") == "applied":
                updates.append(f"  🛡 {d['symbol']}: Breakeven! SL → entry ({d['open_price']:.2f})")
                updates.append(f"     Old SL: {d.get('old_sl', '?')}")
            elif d.get("action") == "updated":
                updates.append(f"  🔒 {d['symbol']}: SL {d['old_sl']:.2f} → {d['new_sl']:.2f}")
                updates.append(f"     Locked profit: ${d.get('locked_profit', 0):.2f}")

        if updates:
            print(f"⚙️ Trailing Stop Update")
            for u in updates:
                print(u)
            last_trail = [d for d in result.get("details", []) if d.get("action") == "updated"]
            if last_trail:
                print(f"  Trail distance: {last_trail[-1].get('trail_distance', '?')} (ATR: {last_trail[-1].get('atr', '?')})")

    return 0 if result.get("error") is None else 1


if __name__ == "__main__":
    sys.exit(main())

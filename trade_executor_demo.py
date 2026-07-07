#!/usr/bin/env python3
"""
Hermes Exness Bot V1 — DEMO CENT Controlled Execution
======================================================
Demo cent order executor. ALL validations must pass before any order.

MODE: DEMO CENT ONLY — REAL EXECUTION OFF TOTAL
"""
import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional, Tuple

# --- Paths ---
BASE_DIR = Path(os.environ.get("HERMES_HOME", r"C:\Users\Administrator\AppData\Local\hermes"))
ENV_PATH = BASE_DIR / ".env"
FINAL_DECISION_FILE = BASE_DIR / "final_decision.json"
LOGS_DIR = BASE_DIR / "logs" / "demo_execution"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# --- ENV ---
def load_env() -> dict:
    """Load .env to dict."""
    env = {}
    if not ENV_PATH.exists():
        return env
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                k = k.strip()
                v = v.strip()
                if k and (k not in env or not env[k]):
                    env[k] = v
    return env


def parse_enabled_symbols(env: dict) -> list:
    raw = env.get("ENABLED_SYMBOLS", "")
    return [s.strip() for s in raw.split(",") if s.strip()]


# --- MT5 ---
def _init_mt5():
    import MetaTrader5 as mt5
    if not mt5.initialize():
        if not mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe"):
            return None, f"MT5 init failed: {mt5.last_error()}"
    return mt5, None


def confirm_demo_account(mt5) -> Tuple[bool, str, dict]:
    """Confirm this is a demo/cent account. Returns (is_demo, reason, account_dict)."""
    acc = mt5.account_info()
    if acc is None:
        return False, "Cannot read account_info", {}
    server = acc.server.lower()
    is_demo = any(x in server for x in ["demo", "trial", "cent"])
    acc_dict = {
        "login": acc.login,
        "server": acc.server,
        "balance": acc.balance,
        "equity": acc.equity,
        "leverage": acc.leverage,
        "trade_allowed": acc.trade_allowed,
        "is_demo_server": is_demo,
    }
    if not is_demo:
        return False, f"Server '{acc.server}' is not demo/trial/cent", acc_dict
    if not acc.trade_allowed:
        return False, "trade_allowed is False", acc_dict
    return True, "Demo cent account confirmed", acc_dict


def is_trading_session_allowed(env: dict) -> Tuple[bool, str]:
    """Check if current WIB time is within trading session AND past start date."""
    start_date = env.get("START_FROM_DATE_WIB", "2026-06-15")
    start_time = env.get("START_FROM_TIME_WIB", "07:00")
    session_start = env.get("TRADING_SESSION_START_WIB", "07:00")
    session_end = env.get("TRADING_SESSION_END_WIB", "22:00")

    # WIB = UTC+7
    now_wib = datetime.now(timezone.utc) + timedelta(hours=7)
    start_dt = datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M")
    start_dt = start_dt.replace(tzinfo=timezone(timedelta(hours=7)))

    if now_wib < start_dt:
        return False, f"Scheduler armed. Waiting until {start_date} {start_time} WIB."

    current_time = now_wib.strftime("%H:%M")
    # Handle midnight wrap (e.g., 07:00-00:00 → 07:00 to midnight)
    if session_end <= session_start:
        in_session = current_time >= session_start or current_time < session_end
    else:
        in_session = session_start <= current_time < session_end
    if not in_session:
        return False, f"Outside trading session ({session_start}-{session_end} WIB, now {current_time})"

    return True, "Trading session active"


def get_open_positions_count(mt5) -> int:
    positions = mt5.positions_get()
    return len(positions) if positions else 0


def has_open_position_same_symbol(mt5, symbol: str) -> bool:
    positions = mt5.positions_get(symbol=symbol)
    return bool(positions)


def get_daily_loss_info(mt5) -> dict:
    """Get daily realized PnL and loss count from history."""
    now_wib = datetime.now(timezone.utc) + timedelta(hours=7)
    day_start = now_wib.replace(hour=0, minute=0, second=0, microsecond=0)
    day_start_utc = day_start - timedelta(hours=7)
    day_start_ts = int(day_start_utc.timestamp())

    history = mt5.history_deals_get(day_start_ts, int(time.time()))
    if history is None or len(history) == 0:
        return {"daily_realized_pnl": 0, "daily_loss_count": 0, "xauusd_loss_count": 0, "warn": "no_history"}

    total_pnl = 0.0
    loss_count = 0
    xauusd_loss_count = 0
    for deal in history:
        if deal.entry == 1:  # entry deals
            continue
        pnl = deal.profit + deal.commission + deal.swap
        total_pnl += pnl
        if pnl < 0:
            loss_count += 1
            if deal.symbol.upper().startswith("XAU"):
                xauusd_loss_count += 1

    return {
        "daily_realized_pnl": round(total_pnl, 2),
        "daily_loss_count": loss_count,
        "xauusd_loss_count": xauusd_loss_count,
    }


def get_daily_realized_loss_percent(mt5, env: dict, equity: float) -> float:
    """Daily realized loss as % of equity."""
    info = get_daily_loss_info(mt5)
    pnl = info.get("daily_realized_pnl", 0)
    if equity > 0:
        return round(abs(min(pnl, 0)) / equity * 100, 2)
    return 0


def get_daily_loss_count(mt5) -> int:
    info = get_daily_loss_info(mt5)
    return info.get("daily_loss_count", 0)


# ─── Daily Equity Drawdown ────────────────────────────────────────────────
def get_session_start_equity() -> Optional[float]:
    """Read session start equity from daily state file. Returns None if not set."""
    state_file = BASE_DIR / "data" / "daily_equity_state.json"
    if not state_file.exists():
        return None
    try:
        with open(state_file, "r") as f:
            data = json.load(f)
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        if data.get("date") == today:
            return data.get("session_start_equity")
    except (json.JSONDecodeError, KeyError):
        pass
    return None


def record_session_start_equity(equity: float):
    """Record equity at session start for drawdown tracking."""
    state_file = BASE_DIR / "data" / "daily_equity_state.json"
    state_file.parent.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    with open(state_file, "w") as f:
        json.dump({
            "date": today,
            "session_start_equity": round(equity, 2),
            "recorded_at": datetime.now(timezone.utc).isoformat(),
        }, f, indent=2)


def check_daily_drawdown(equity: float, env: dict) -> Tuple[bool, str, dict]:
    """
    Check if current equity drawdown from session start exceeds limit.
    Returns (passed, reason, details_dict).
    """
    dd_enabled = env.get("DAILY_DRAWDOWN_ENABLED", "false").lower() == "true"
    if not dd_enabled:
        return True, "Drawdown check disabled", {"drawdown_enabled": False}

    try:
        max_dd_pct = float(env.get("MAX_DAILY_DRAWDOWN_PCT", "5.0"))
    except ValueError:
        max_dd_pct = 5.0

    start_equity = get_session_start_equity()

    # First check of the session — record start equity
    if start_equity is None:
        record_session_start_equity(equity)
        return True, f"Session start recorded: equity ${equity:.2f}", {
            "drawdown_enabled": True,
            "max_drawdown_pct": max_dd_pct,
            "start_equity": equity,
            "current_drawdown_pct": 0.0,
        }

    drawdown_amt = start_equity - equity
    drawdown_pct = (drawdown_amt / start_equity) * 100 if start_equity > 0 else 0

    details = {
        "drawdown_enabled": True,
        "max_drawdown_pct": max_dd_pct,
        "start_equity": round(start_equity, 2),
        "current_equity": round(equity, 2),
        "drawdown_amount": round(drawdown_amt, 2),
        "current_drawdown_pct": round(drawdown_pct, 2),
    }

    if drawdown_pct >= max_dd_pct:
        return False, f"Daily drawdown {drawdown_pct:.2f}% >= {max_dd_pct}% (${drawdown_amt:.2f} from ${start_equity:.2f})", details

    return True, f"Drawdown OK: {drawdown_pct:.2f}% / {max_dd_pct}%", details


# ─── Pair Cooldown & Trade Limit ──────────────────────────────────────────
COOLDOWN_STATE_FILE = BASE_DIR / "data" / "cooldown_state.json"


def load_cooldown_state() -> dict:
    """Load per-pair last entry timestamps. Returns {symbol: iso_timestamp}."""
    if not COOLDOWN_STATE_FILE.exists():
        return {}
    try:
        with open(COOLDOWN_STATE_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError):
        return {}


def save_cooldown_state(state: dict):
    """Write cooldown state to disk."""
    COOLDOWN_STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(COOLDOWN_STATE_FILE, "w") as f:
        json.dump(state, f, indent=2)


def check_pair_cooldown(symbol: str, cooldown_minutes: int) -> Tuple[bool, str]:
    """Check if pair is still in cooldown. Returns (allowed, reason)."""
    if cooldown_minutes <= 0:
        return True, "Cooldown disabled"
    state = load_cooldown_state()
    last_ts = state.get(symbol)
    if not last_ts:
        return True, "No previous entry"
    try:
        last_dt = datetime.fromisoformat(last_ts)
    except ValueError:
        return True, "Invalid timestamp (cleared)"
    now = datetime.now(timezone.utc)
    elapsed = (now - last_dt).total_seconds() / 60
    if elapsed < cooldown_minutes:
        remaining = int(cooldown_minutes - elapsed)
        return False, f"Cooldown: {symbol} entered {int(elapsed)}m ago, need {remaining}m more"
    return True, f"Cooldown passed ({int(elapsed)}m since last entry)"


def record_pair_entry(symbol: str):
    """Record that a pair was entered (for cooldown tracking)."""
    state = load_cooldown_state()
    state[symbol] = datetime.now(timezone.utc).isoformat()
    save_cooldown_state(state)


def get_pair_closed_trades_today(mt5, symbol: str) -> int:
    """Count how many trades for this symbol have already closed today."""
    try:
        now_utc = datetime.now(timezone.utc)
        day_start = now_utc.replace(hour=0, minute=0, second=0, microsecond=0)
        from_ts = int(day_start.timestamp())
        to_ts = int(now_utc.timestamp())
        history = mt5.history_deals_get(from_ts, to_ts)
        if history is None:
            return 0
        closed_tickets = set()
        for deal in history:
            if deal.entry == 1 and deal.symbol == symbol:
                # DEAL_ENTRY_OUT — trade closed
                closed_tickets.add(deal.position_id)
        return len(closed_tickets)
    except Exception:
        return 0


def calculate_lot_by_risk(mt5, symbol: str, side: str, entry_price: float,
                          sl_price: float, risk_percent: float, equity: float,
                          symbol_info) -> Tuple[Optional[float], dict]:
    """Calculate lot size by risking risk_percent% of equity on SL distance.
    Returns (lot_final, calc_details) or (None, error_details) if blocked.
    """
    details = {}
    risk_amount = equity * (risk_percent / 100.0)
    details["risk_amount"] = round(risk_amount, 2)

    # Use order_calc_profit for 1 lot to find loss at SL
    # order_type: 0=BUY, 1=SELL
    order_type = 0 if side.lower() == "buy" else 1

    # For order_calc_profit we need to provide the order price and SL price
    # The function returns profit if price moves from entry to sl_price
    # We need the loss when SL is hit, so we pass sl_price as the target
    result = mt5.order_calc_profit(order_type, symbol, 1.0, entry_price, sl_price)
    if result is None:
        return None, {**details, "error": "order_calc_profit returned None"}

    loss_per_1_lot = result  # should be negative for a loss
    details["loss_per_1_lot"] = round(loss_per_1_lot, 2)

    if loss_per_1_lot >= 0:
        return None, {**details, "error": f"order_calc_profit returned positive {loss_per_1_lot}"}

    if abs(loss_per_1_lot) < 0.01:
        return None, {**details, "error": "loss_per_1_lot too small"}

    lot_raw = risk_amount / abs(loss_per_1_lot)
    details["lot_raw"] = round(lot_raw, 6)

    # Round down to volume_step
    vol_min = symbol_info.volume_min
    vol_max = symbol_info.volume_max
    vol_step = symbol_info.volume_step

    if vol_step <= 0:
        return None, {**details, "error": f"volume_step is {vol_step}"}

    steps = int(lot_raw / vol_step)
    lot_final = steps * vol_step
    lot_final = round(lot_final, 2)  # 2 decimals for most forex
    details["lot_final"] = lot_final

    if lot_final < vol_min:
        # Allow vol_min only if risk still within limit
        test_result = mt5.order_calc_profit(order_type, symbol, vol_min, entry_price, sl_price)
        if test_result is None:
            return None, {**details, "error": "order_calc_profit failed for vol_min"}
        projected_loss = abs(test_result)
        projected_loss_pct = projected_loss / equity * 100
        if projected_loss_pct > risk_percent * 1.05:
            return None, {**details, "error": f"vol_min exceeds risk limit ({projected_loss_pct:.2f}% > {risk_percent*1.05:.2f}%)"}
        lot_final = vol_min
        details["lot_final"] = lot_final
        details["used_vol_min"] = True

    if lot_final > vol_max:
        lot_final = vol_max
        details["lot_final"] = lot_final
        details["capped_at_vol_max"] = True

    # Recalculate projected loss with final lot
    final_result = mt5.order_calc_profit(order_type, symbol, lot_final, entry_price, sl_price)
    if final_result is None:
        return None, {**details, "error": "order_calc_profit failed for final lot"}

    projected_loss = abs(final_result)
    projected_loss_pct = projected_loss / equity * 100
    details["projected_loss"] = round(projected_loss, 2)
    details["projected_loss_percent"] = round(projected_loss_pct, 2)

    if projected_loss_pct > risk_percent * 1.05:
        return None, {**details, "error": f"projected loss {projected_loss_pct:.2f}% exceeds limit {risk_percent*1.05:.2f}%"}

    return lot_final, details


def validate_entry_sl_tp(symbol: str, side: str, planned_entry: float,
                         actual_entry: float, sl_price: float, tp_price: float,
                         min_rr: float) -> Tuple[bool, str, float]:
    """Validate entry/SL/TP and actual RR. Returns (valid, reason, actual_rr)."""
    # Check price deviation
    price_deviation = abs(actual_entry - planned_entry)

    # Determine max deviation based on symbol
    if symbol.upper().startswith("XAU"):
        max_dev = 20.0  # $20 for gold — normal volatility
    elif "JPY" in symbol.upper():
        max_dev = 0.05
        # Check in pips
        price_deviation = abs(actual_entry - planned_entry)
    else:
        max_dev = 0.0010  # 10 pips for majors (was 5, too tight for normal slippage)

    if price_deviation > max_dev:
        return False, f"Price deviation {price_deviation:.6f} exceeds max {max_dev}", 0

    # SL/TP logic
    side = side.lower()
    if side == "buy":
        if not (sl_price < actual_entry < tp_price):
            return False, f"Buy: SL({sl_price}) < Entry({actual_entry}) < TP({tp_price}) failed", 0
    elif side == "sell":
        if not (sl_price > actual_entry > tp_price):
            return False, f"Sell: SL({sl_price}) > Entry({actual_entry}) > TP({tp_price}) failed", 0
    else:
        return False, f"Unknown side: {side}", 0

    # RR — use planned entry for consistency (actual may drift slightly)
    sl_dist = abs(planned_entry - sl_price)
    tp_dist = abs(tp_price - planned_entry)
    if sl_dist <= 0:
        return False, "SL distance is zero", 0

    actual_rr = round(tp_dist / sl_dist, 2)
    if actual_rr < min_rr:
        return False, f"Actual RR {actual_rr} < min {min_rr}", actual_rr

    return True, "Entry/SL/TP valid", actual_rr


def validate_spread(mt5, symbol: str) -> Tuple[bool, str, dict]:
    """Validate spread is not abnormal. Returns (valid, reason, tick_dict)."""
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        return False, "No tick data", {}
    info = mt5.symbol_info(symbol)
    if info is None:
        return False, "No symbol info", {}

    spread = tick.ask - tick.bid
    spread_points = spread / info.point if info.point else spread

    tick_dict = {"bid": tick.bid, "ask": tick.ask, "spread": round(spread, info.digits + 1),
                 "spread_points": round(spread_points, 1)}

    # Abnormal spread check
    if symbol.upper().startswith("XAU"):
        if spread_points > 500:
            return False, f"XAUUSD spread {spread_points:.0f} points (abnormal)", tick_dict
    else:
        if spread_points > 20:
            return False, f"Spread {spread_points:.0f} points (abnormal)", tick_dict

    return True, "Spread valid", tick_dict


def execute_demo_order(mt5, symbol: str, side: str, lot: float,
                       sl_price: float, tp_price: float, mode: str = "DAY") -> Tuple[bool, int, str]:
    """Send MARKET order with SL/TP. No pending orders. Returns (success, ticket, message)."""
    order_type = mt5.ORDER_TYPE_BUY if side.lower() == "buy" else mt5.ORDER_TYPE_SELL
    tick = mt5.symbol_info_tick(symbol)
    price = tick.ask if side.lower() == "buy" else tick.bid

    request = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot,
        "type": order_type,
        "price": price,
        "sl": sl_price,
        "tp": tp_price,
        "deviation": 20,
        "magic": 1206,
        "comment": f"Hermes v1.2 {mode.upper()} DEMO CENT",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_IOC,
    }

    result = mt5.order_send(request)
    if result.retcode != mt5.TRADE_RETCODE_DONE:
        return False, 0, f"MT5 reject: retcode={result.retcode}, comment={result.comment}"

    return True, result.order, f"Order placed: ticket={result.order}"


def send_demo_execution_report(report_text: str):
    """Send report via telegram_reporter to DEMO_EXECUTION topic."""
    try:
        from telegram_reporter import send_demo_report
        return send_demo_report(report_text)
    except ImportError:
        print("[REPORT] telegram_reporter not found, skipping Telegram")
        return False


def write_demo_execution_log(log_data: dict) -> Path:
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_path = LOGS_DIR / f"demo_exec_{ts}.json"
    with open(log_path, "w", encoding="utf-8") as f:
        json.dump(log_data, f, indent=2, default=str)
    print(f"[LOG] Demo execution log: {log_path}")
    return log_path


def load_final_decision() -> Optional[dict]:
    if not FINAL_DECISION_FILE.exists():
        return None
    try:
        with open(FINAL_DECISION_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError:
        return None


def cmd_check():
    """Run all validations without executing. Full check report."""
    env = load_env()
    enabled_syms = parse_enabled_symbols(env)
    min_rr = float(env.get("MIN_RR", "1.8"))
    min_conf = int(env.get("MIN_CONFIDENCE", "75"))
    max_open = int(env.get("DEMO_MAX_OPEN_POSITIONS", "3"))
    risk_pct = float(env.get("RISK_PER_TRADE_PERCENT", "1.0"))
    risk_day_pct = float(env.get("RISK_PER_DAY_PERCENT", "20.0"))
    max_daily_losses = int(env.get("MAX_DAILY_LOSSES", "2"))
    max_xau_losses = int(env.get("MAX_XAUUSD_DAILY_LOSSES", "1"))
    demo_exec_enabled = env.get("DEMO_EXECUTION_ENABLED", "false").lower() == "true"
    real_exec_enabled = env.get("REAL_EXECUTION_ENABLED", "false").lower() == "true"

    log = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "check",
        "real_execution_enabled": real_exec_enabled,
        "demo_execution_enabled": demo_exec_enabled,
        "account_mode": env.get("ACCOUNT_MODE", "unknown"),
        "enabled_symbols": enabled_syms,
        "risk_per_trade_percent": risk_pct,
        "risk_per_day_percent": risk_day_pct,
        "max_open_positions": max_open,
        "status": "blocked",
        "reason": "",
    }

    print("=" * 50)
    print("  TRADE EXECUTOR DEMO --CHECK")
    print("=" * 50)

    # 1. MT5 init
    mt5, err = _init_mt5()
    if mt5 is None:
        log["status"] = "blocked"
        log["reason"] = f"MT5 not connected: {err}"
        print(f"[BLOCKED] {err}")
        write_demo_execution_log(log)
        return log

    print("[OK] MT5 connected")

    # 2. Account check
    is_demo, reason, acc_dict = confirm_demo_account(mt5)
    log["account_server"] = acc_dict.get("server", "unknown")
    log["account_equity"] = acc_dict.get("equity", 0)
    log["account_balance"] = acc_dict.get("balance", 0)
    log["demo_confirmed"] = is_demo
    if not is_demo:
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = reason
        print(f"[BLOCKED] {reason}")
        write_demo_execution_log(log)
        return log
    print(f"[OK] {reason}")

    equity = acc_dict["equity"]

    # 3. Real execution blocked
    if real_exec_enabled:
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = "REAL_EXECUTION_ENABLED=true — BLOCKED"
        print("[BLOCKED] REAL_EXECUTION_ENABLED=true")
        write_demo_execution_log(log)
        return log
    print("[OK] Real execution OFF")

    # 4. Session check
    session_ok, session_reason = is_trading_session_allowed(env)
    log["session_allowed"] = session_ok
    if not session_ok:
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = session_reason
        print(f"[BLOCKED] {session_reason}")
        write_demo_execution_log(log)
        return log
    print(f"[OK] {session_reason}")

    # 5. Final decision
    fd = load_final_decision()
    if fd is None:
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = "No final_decision.json or invalid"
        print("[BLOCKED] No final_decision.json")
        write_demo_execution_log(log)
        return log

    log["final_decision_action"] = fd.get("action", "unknown")

    if fd.get("action") != "entry":
        mt5.shutdown()
        log["status"] = "checked"
        log["reason"] = f"Action is '{fd.get('action')}', not 'entry'"
        print(f"[SKIP] Action is '{fd.get('action')}'")
        write_demo_execution_log(log)
        return log

    if fd.get("safety_gate") != "passed":
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = "Safety gate not passed"
        print("[BLOCKED] Safety gate not passed")
        write_demo_execution_log(log)
        return log

    symbol = fd.get("best_symbol", "")
    # Normalize: orchestrator may return "EURUSDm" or "EURUSD" — always add "m" suffix if missing
    if symbol:
        # Strip existing "m" suffix to normalize base name
        base = symbol.rstrip("m") if symbol.endswith("m") else symbol
        candidate = f"{base}m"
        if candidate in enabled_syms:
            symbol = candidate
        elif symbol not in enabled_syms and base in enabled_syms:
            # orchestrator output is already correct (e.g. "EURUSDm")
            symbol = base
    side = fd.get("side", "")
    planned_entry = fd.get("planned_entry", 0)
    sl_price = fd.get("sl_price", 0)
    tp_price = fd.get("tp_price", 0)
    rr = fd.get("rr", 0)
    confidence = fd.get("confidence", 0)

    log["symbol"] = symbol
    log["side"] = side
    log["planned_entry"] = planned_entry
    log["sl_price"] = sl_price
    log["tp_price"] = tp_price
    log["planned_rr"] = rr
    log["confidence"] = confidence
    
    # ── Mode-specific thresholds ──
    trade_mode = fd.get("mode_trade", "day").lower()
    log["trade_mode"] = trade_mode
    if trade_mode == "scalp":
        # Scalping: tighter SL → lower RR is expected
        min_rr_scalp = float(env.get("MIN_RR_SCALP", "1.5"))
        min_conf_scalp = int(env.get("MIN_CONFIDENCE_SCALP", "70"))
        print(f"[SCALP] Using scalp thresholds: min_rr={min_rr_scalp}, min_conf={min_conf_scalp}")
    else:
        # Day trade: use general thresholds
        min_rr_scalp = min_rr  # same as general
        min_conf_scalp = min_conf
        print(f"[{trade_mode.upper()}] Using general thresholds: min_rr={min_rr}, min_conf={min_conf}")

    # Validate fields
    if not symbol or symbol not in enabled_syms:
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = f"Symbol '{symbol}' not in enabled symbols"
        print(f"[BLOCKED] Symbol '{symbol}' not in ENABLED_SYMBOLS")
        write_demo_execution_log(log)
        return log

    if side not in ("buy", "sell"):
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = f"Invalid side: {side}"
        print(f"[BLOCKED] Invalid side: {side}")
        write_demo_execution_log(log)
        return log

    if rr < min_rr_scalp:
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = f"RR {rr} < {min_rr_scalp}"
        print(f"[BLOCKED] RR {rr} < {min_rr_scalp}")
        write_demo_execution_log(log)
        return log

    # ── Supply/Demand Zone Touch Check ──
    try:
        sd_path = BASE_DIR / "data" / "sd_zones.json"
        if sd_path.exists():
            with open(sd_path, "r") as f:
                sd = json.load(f)
            sym_zones = sd.get("zones", {}).get(symbol, [])
            active = [z for z in sym_zones if not z.get("expired")]
            zone_penalty = 0
            zone_touches = 0
            for z in active:
                if (z["type"] == "demand" and side == "buy") or (z["type"] == "supply" and side == "sell"):
                    if z["touch_count"] > zone_touches:
                        zone_touches = z["touch_count"]
                        zone_penalty = z["touch_count"] * 10
            if zone_touches >= 3:
                mt5.shutdown()
                log["status"] = "blocked"
                log["reason"] = f"S/D zone exhausted ({zone_touches} touches)"
                print(f"[BLOCKED] S/D zone {zone_touches} touches — exhausted")
                write_demo_execution_log(log)
                return log
            if zone_penalty > 0:
                confidence -= zone_penalty
                log["sd_zone_penalty"] = zone_penalty
                log["sd_zone_touches"] = zone_touches
                log["confidence_adjusted"] = confidence
                print(f"[SD] {symbol} zone: {zone_touches} touches, confidence -{zone_penalty} → {confidence}")
    except Exception as e:
        print(f"[SD] Zone check error (non-fatal): {e}")

    if confidence < min_conf_scalp:
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = f"Confidence {confidence} < {min_conf_scalp}"
        print(f"[BLOCKED] Confidence {confidence} < {min_conf_scalp}")
        write_demo_execution_log(log)
        return log

    # 6. Position checks
    open_count = get_open_positions_count(mt5)
    log["current_open_positions"] = open_count
    if open_count >= max_open:
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = f"Max open positions reached ({open_count}/{max_open})"
        print(f"[BLOCKED] Max positions: {open_count}/{max_open}")
        write_demo_execution_log(log)
        return log

    if has_open_position_same_symbol(mt5, symbol):
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = f"Already have open position on {symbol}"
        print(f"[BLOCKED] Already open position on {symbol}")
        write_demo_execution_log(log)
        return log

    print(f"[OK] Open positions: {open_count}/{max_open}")

    # 7. Daily risk
    loss_info = get_daily_loss_info(mt5)
    daily_loss_pct = abs(min(loss_info["daily_realized_pnl"], 0)) / equity * 100 if equity > 0 else 0
    daily_losses = loss_info["daily_loss_count"]
    xau_losses = loss_info["xauusd_loss_count"]
    log["daily_realized_loss_percent"] = round(daily_loss_pct, 2)
    log["daily_loss_count"] = daily_losses

    print(f"[OK] Daily P&L: {loss_info['daily_realized_pnl']}, Losses: {daily_losses}/{max_daily_losses}")

    if daily_loss_pct >= risk_day_pct:
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = f"Daily loss {daily_loss_pct:.1f}% >= {risk_day_pct}%"
        print(f"[BLOCKED] Daily loss limit hit: {daily_loss_pct:.1f}%")
        write_demo_execution_log(log)
        return log

    if daily_losses >= max_daily_losses:
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = f"Daily losses {daily_losses} >= {max_daily_losses}"
        print(f"[BLOCKED] Daily loss count: {daily_losses}")
        write_demo_execution_log(log)
        return log

    if symbol.upper().startswith("XAU") and xau_losses >= max_xau_losses:
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = f"XAUUSD already lost {xau_losses}x today"
        print(f"[BLOCKED] XAUUSD daily losses: {xau_losses}/{max_xau_losses}")
        write_demo_execution_log(log)
        return log

    # 7b. Daily equity drawdown check
    dd_ok, dd_reason, dd_details = check_daily_drawdown(equity, env)
    log["daily_drawdown"] = dd_details
    if not dd_ok:
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = f"Drawdown: {dd_reason}"
        print(f"[BLOCKED] {dd_reason}")
        write_demo_execution_log(log)
        return log
    print(f"[OK] {dd_reason}")

    # 8. Spread check
    spread_ok, spread_reason, tick_dict = validate_spread(mt5, symbol)
    log["spread_check"] = spread_reason
    if not spread_ok:
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = f"Spread: {spread_reason}"
        print(f"[BLOCKED] {spread_reason}")
        write_demo_execution_log(log)
        return log

    actual_entry = tick_dict["ask"] if side == "buy" else tick_dict["bid"]
    log["actual_entry_price"] = actual_entry
    print(f"[OK] Spread valid, bid={tick_dict['bid']}, ask={tick_dict['ask']}")

    # 8b. Min SL distance check
    sl_dist = abs(planned_entry - sl_price)
    if symbol.upper().startswith("XAU"):
        min_sl_price = 10.00     # $10 for gold
    elif "JPY" in symbol.upper():
        min_sl_price = 0.30      # 30 pips (JPY 2-decimal)
    else:
        min_sl_price = 0.0020    # 20 pips (forex 4-decimal)
    if sl_dist < min_sl_price:
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = f"SL too tight: {sl_dist:.5f} < min {min_sl_price}"
        print(f"[BLOCKED] SL {sl_dist:.5f} < min {min_sl_price}")
        write_demo_execution_log(log)
        return log

    # 9. Entry validation
    entry_ok, entry_reason, actual_rr = validate_entry_sl_tp(
        symbol, side, planned_entry, actual_entry, sl_price, tp_price, min_rr
    )
    log["actual_rr"] = actual_rr
    if not entry_ok:
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = f"Entry validation: {entry_reason}"
        print(f"[BLOCKED] {entry_reason}")
        write_demo_execution_log(log)
        return log
    print(f"[OK] Entry valid, actual RR={actual_rr}")

    # 10. Lot calculation
    sym_info = mt5.symbol_info(symbol)
    lot, lot_details = calculate_lot_by_risk(
        mt5, symbol, side, actual_entry, sl_price, risk_pct, equity, sym_info
    )
    log["risk_amount"] = lot_details.get("risk_amount", 0)
    log["loss_per_1_lot"] = lot_details.get("loss_per_1_lot", 0)
    log["calculated_lot_raw"] = lot_details.get("lot_raw", 0)
    if lot is None:
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = f"Lot calculation: {lot_details.get('error', 'unknown')}"
        print(f"[BLOCKED] Lot calc: {lot_details.get('error')}")
        write_demo_execution_log(log)
        return log

    log["calculated_lot_final"] = lot
    log["projected_loss"] = lot_details.get("projected_loss", 0)
    log["projected_loss_percent"] = lot_details.get("projected_loss_percent", 0)
    print(f"[OK] Lot: {lot} (risk {risk_pct}%, projected loss {lot_details.get('projected_loss_percent')}%)")

    # 10b. Lot anomaly check — compare to recent trades average
    try:
        mt5.initialize()
        from datetime import datetime as _dt, timedelta as _td
        _deals = mt5.history_deals_get(_dt.now() - _td(days=7), _dt.now())
        if _deals:
            _closed = [d for d in _deals if d.entry == 1]
            if len(_closed) >= 3:
                _avg_lot = sum(d.volume for d in _closed) / len(_closed)
                log["recent_avg_lot"] = round(_avg_lot, 2)
                log["lot_vs_avg_ratio"] = round(lot / _avg_lot, 2) if _avg_lot > 0 else 1.0
                anom_max = env.get("MAX_LOT_ANOMALY_RATIO", "2.0")
                if lot > _avg_lot * float(anom_max) and lot > 0.1:
                    mt5.shutdown()
                    log["status"] = "blocked"
                    log["reason"] = f"Lot anomaly: {lot} vs avg {_avg_lot:.2f} ({lot/_avg_lot:.1f}x > {anom_max}x)"
                    print(f"[BLOCKED] Lot anomaly: {lot} vs avg {_avg_lot:.2f}")
                    write_demo_execution_log(log)
                    return log
                print(f"[OK] Lot vs avg: {lot} vs {_avg_lot:.2f} ({lot/_avg_lot:.1f}x)")
        mt5.shutdown()
    except Exception as e:
        print(f"[WARN] Lot anomaly check failed: {e}")
        try: mt5.shutdown()
        except: pass

    # ALL CHECKS PASSED
    mt5.shutdown()
    log["status"] = "checked"
    log["reason"] = "All validations passed — ready for --execute"
    log["validation_status"] = "passed"

    print("\n✅ ALL CHECKS PASSED — Ready for demo execution")
    print(f"   Symbol: {symbol} {side.upper()}")
    print(f"   Entry: {actual_entry} | SL: {sl_price} | TP: {tp_price}")
    print(f"   Lot: {lot} | RR: {actual_rr} | Loss: {lot_details.get('projected_loss_percent')}%")

    write_demo_execution_log(log)

    # Telegram report
    report = (
        f"🧪 Hermes Exness DEMO CENT Execution\n\n"
        f"Status: CHECK PASSED\n"
        f"Real Execution: OFF\n"
        f"Demo Execution Enabled: {demo_exec_enabled}\n"
        f"Account Mode: DEMO CENT\n"
        f"Symbol: {symbol}\n"
        f"Side: {side.upper()}\n"
        f"Lot: {lot}\n"
        f"Entry: {actual_entry}\n"
        f"SL: {sl_price}\n"
        f"TP: {tp_price}\n"
        f"Actual RR: {actual_rr}\n"
        f"Risk per Entry: {risk_pct}%\n"
        f"Risk per Day: {risk_day_pct}%\n"
        f"Projected Loss: {lot_details.get('projected_loss_percent')}%\n"
        f"Max Open Positions: {max_open}\n"
        f"Current Open Positions: {open_count}\n"
        f"Reason: All validations passed\n"
        f"Log: demo_exec_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    send_demo_execution_report(report)

    return log


def cmd_execute():
    """Run all validations AND execute demo order if all pass."""
    env = load_env()
    enabled_syms = parse_enabled_symbols(env)
    max_open = int(env.get("DEMO_MAX_OPEN_POSITIONS", "3"))
    risk_pct = float(env.get("RISK_PER_TRADE_PERCENT", "1.0"))
    risk_day_pct = float(env.get("RISK_PER_DAY_PERCENT", "20.0"))
    max_daily_losses = int(env.get("MAX_DAILY_LOSSES", "2"))
    max_xau_losses = int(env.get("MAX_XAUUSD_DAILY_LOSSES", "1"))
    demo_exec_enabled = env.get("DEMO_EXECUTION_ENABLED", "false").lower() == "true"
    real_exec_enabled = env.get("REAL_EXECUTION_ENABLED", "false").lower() == "true"
    max_trades_per_pair = int(env.get("MAX_TRADES_PER_PAIR", "0"))
    cooldown_minutes = int(env.get("TRADE_COOLDOWN_MINUTES", "0"))

    # ── Mode-specific thresholds (read from final_decision if exists) ──
    fd_mode = load_final_decision()
    trade_mode = (fd_mode.get("mode_trade", "day") or "day").lower() if fd_mode else "day"
    if trade_mode == "scalp":
        # Use scalp-specific risk (0.15% default instead of 0.5%)
        risk_pct = float(env.get("SCALP_RISK_PERCENT", "0.15"))
        min_rr = float(env.get("MIN_RR_SCALP", "1.5"))
        min_conf = int(env.get("MIN_CONFIDENCE_SCALP", "70"))
        print(f"[SCALP] Mode-specific thresholds: min_rr={min_rr}, min_conf={min_conf}")
    else:
        min_rr = float(env.get("MIN_RR", "1.8"))
        min_conf = int(env.get("MIN_CONFIDENCE", "75"))
        print(f"[{trade_mode.upper()}] General thresholds: min_rr={min_rr}, min_conf={min_conf}")

    log = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "mode": "execute",
        "real_execution_enabled": real_exec_enabled,
        "demo_execution_enabled": demo_exec_enabled,
        "account_mode": env.get("ACCOUNT_MODE", "unknown"),
        "enabled_symbols": enabled_syms,
        "risk_per_trade_percent": risk_pct,
        "risk_per_day_percent": risk_day_pct,
        "max_open_positions": max_open,
        "max_trades_per_pair": max_trades_per_pair,
        "cooldown_minutes": cooldown_minutes,
        "status": "blocked",
        "reason": "",
    }

    print("=" * 50)
    print("  TRADE EXECUTOR DEMO --EXECUTE")
    print("  ⚠ DEMO CENT ONLY — REAL OFF")
    print("=" * 50)

    # Block if demo execution disabled
    if not demo_exec_enabled:
        log["status"] = "blocked"
        log["reason"] = "DEMO_EXECUTION_ENABLED=false"
        print("[BLOCKED] DEMO_EXECUTION_ENABLED=false")
        write_demo_execution_log(log)
        return log

    # 1. MT5
    mt5, err = _init_mt5()
    if mt5 is None:
        log["status"] = "blocked"
        log["reason"] = f"MT5: {err}"
        print(f"[BLOCKED] {err}")
        write_demo_execution_log(log)
        return log

    # 2. Account
    is_demo, reason, acc_dict = confirm_demo_account(mt5)
    log["account_server"] = acc_dict.get("server", "unknown")
    log["account_equity"] = acc_dict.get("equity", 0)
    log["account_balance"] = acc_dict.get("balance", 0)
    log["demo_confirmed"] = is_demo
    if not is_demo:
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = reason
        print(f"[BLOCKED] {reason}")
        write_demo_execution_log(log)
        return log

    equity = acc_dict["equity"]

    # 3. Real blocked
    if real_exec_enabled:
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = "REAL_EXECUTION_ENABLED=true"
        print("[BLOCKED] Real execution blocked")
        write_demo_execution_log(log)
        return log

    # 4. Session
    session_ok, session_reason = is_trading_session_allowed(env)
    if not session_ok:
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = session_reason
        print(f"[BLOCKED] {session_reason}")
        write_demo_execution_log(log)
        return log

    # 5-10: Same validations as check
    fd = load_final_decision()
    if fd is None or fd.get("action") != "entry":
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = "No valid entry decision"
        print("[BLOCKED] No valid entry decision")
        write_demo_execution_log(log)
        return log

    if fd.get("safety_gate") != "passed":
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = "Safety gate not passed"
        print("[BLOCKED] Safety gate")
        write_demo_execution_log(log)
        return log

    symbol = fd.get("best_symbol", "")
    # Normalize: orchestrator may return "EURUSDm" or "EURUSD" — always add "m" suffix if missing
    if symbol:
        # Strip existing "m" suffix to normalize base name
        base = symbol.rstrip("m") if symbol.endswith("m") else symbol
        candidate = f"{base}m"
        if candidate in enabled_syms:
            symbol = candidate
        elif symbol not in enabled_syms and base in enabled_syms:
            # orchestrator output is already correct (e.g. "EURUSDm")
            symbol = base
    side = fd.get("side", "")
    planned_entry = fd.get("planned_entry", 0)
    sl_price = fd.get("sl_price", 0)
    tp_price = fd.get("tp_price", 0)
    rr = fd.get("rr", 0)
    confidence = fd.get("confidence", 0)
    trade_mode = fd.get("mode_trade", "day")

    log["symbol"] = symbol
    log["side"] = side
    log["planned_entry"] = planned_entry
    log["sl_price"] = sl_price
    log["tp_price"] = tp_price
    log["planned_rr"] = rr
    log["confidence"] = confidence
    log["trade_mode"] = trade_mode

    if not symbol or symbol not in enabled_syms:
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = f"Symbol {symbol} not enabled"
        print(f"[BLOCKED] Symbol not enabled")
        write_demo_execution_log(log)
        return log

    # ── Supply/Demand Zone Touch Check ──
    base_symbol = symbol.rstrip("m")  # EURUSDm → EURUSD
    zone_touch_count = 0
    zone_penalty = 0
    try:
        sd_path = BASE_DIR / "data" / "sd_zones.json"
        if sd_path.exists():
            with open(sd_path, "r") as f:
                sd = json.load(f)
            sym_zones = sd.get("zones", {}).get(symbol, [])
            active = [z for z in sym_zones if not z.get("expired")]
            # Find nearest zone matching our side
            for z in active:
                if (z["type"] == "demand" and side == "buy") or (z["type"] == "supply" and side == "sell"):
                    if z["touch_count"] > zone_touch_count:
                        zone_touch_count = z["touch_count"]
                        zone_penalty = z["touch_count"] * 10
            if zone_touch_count >= 3:
                mt5.shutdown()
                log["status"] = "blocked"
                log["reason"] = f"S/D zone exhausted ({zone_touch_count} touches)"
                print(f"[BLOCKED] S/D zone {zone_touch_count} touches — exhausted")
                write_demo_execution_log(log)
                return log
            if zone_penalty > 0:
                confidence -= zone_penalty
                log["sd_zone_penalty"] = zone_penalty
                log["sd_zone_touches"] = zone_touch_count
                log["confidence_adjusted"] = confidence
                print(f"[SD] {base_symbol} zone: {zone_touch_count} touches, confidence -{zone_penalty} → {confidence}")
    except Exception as e:
        print(f"[SD] Zone check error (non-fatal): {e}")

    if rr < min_rr or confidence < min_conf:
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = f"RR {rr} < {min_rr} or Conf {confidence} < {min_conf} ({trade_mode})"
        print(f"[BLOCKED] RR {rr} < {min_rr} or Conf {confidence} < {min_conf} ({trade_mode})")
        write_demo_execution_log(log)
        return log

    # Position checks
    open_count = get_open_positions_count(mt5)
    log["current_open_positions"] = open_count
    if open_count >= max_open or has_open_position_same_symbol(mt5, symbol):
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = "Position limit or duplicate"
        print("[BLOCKED] Position check")
        write_demo_execution_log(log)
        return log

    # Pair cooldown gate (TRADE_COOLDOWN_MINUTES)
    cooldown_ok, cooldown_reason = check_pair_cooldown(symbol, cooldown_minutes)
    log["cooldown_check"] = cooldown_reason
    if not cooldown_ok:
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = cooldown_reason
        print(f"[BLOCKED] {cooldown_reason}")
        write_demo_execution_log(log)
        return log

    # Max trades per pair gate (MAX_TRADES_PER_PAIR)
    if max_trades_per_pair > 0:
        closed_today = get_pair_closed_trades_today(mt5, symbol)
        log["pair_closed_trades_today"] = closed_today
        if closed_today >= max_trades_per_pair:
            mt5.shutdown()
            log["status"] = "blocked"
            log["reason"] = f"Pair limit: {symbol} has {closed_today}/{max_trades_per_pair} closed trades today"
            print(f"[BLOCKED] Pair limit: {closed_today}/{max_trades_per_pair}")
            write_demo_execution_log(log)
            return log

    # Daily risk
    loss_info = get_daily_loss_info(mt5)
    daily_loss_pct = abs(min(loss_info["daily_realized_pnl"], 0)) / equity * 100 if equity > 0 else 0
    log["daily_realized_loss_percent"] = round(daily_loss_pct, 2)
    log["daily_loss_count"] = loss_info["daily_loss_count"]

    if daily_loss_pct >= risk_day_pct or loss_info["daily_loss_count"] >= max_daily_losses:
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = "Daily risk limit"
        print("[BLOCKED] Daily risk")
        write_demo_execution_log(log)
        return log

    if symbol.upper().startswith("XAU") and loss_info["xauusd_loss_count"] >= max_xau_losses:
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = "XAUUSD loss limit"
        print("[BLOCKED] XAUUSD loss")
        write_demo_execution_log(log)
        return log

    # Daily equity drawdown check
    dd_ok, dd_reason, dd_details = check_daily_drawdown(equity, env)
    log["daily_drawdown"] = dd_details
    if not dd_ok:
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = f"Drawdown: {dd_reason}"
        print(f"[BLOCKED] Drawdown: {dd_reason}")
        write_demo_execution_log(log)
        return log

    # Spread
    spread_ok, spread_reason, tick_dict = validate_spread(mt5, symbol)
    if not spread_ok:
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = f"Spread: {spread_reason}"
        print(f"[BLOCKED] Spread")
        write_demo_execution_log(log)
        return log

    actual_entry = tick_dict["ask"] if side == "buy" else tick_dict["bid"]
    log["actual_entry_price"] = actual_entry

    # Entry validation
    entry_ok, entry_reason, actual_rr = validate_entry_sl_tp(
        symbol, side, planned_entry, actual_entry, sl_price, tp_price, min_rr
    )
    log["actual_rr"] = actual_rr
    if not entry_ok:
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = f"Entry: {entry_reason}"
        print(f"[BLOCKED] Entry validation")
        write_demo_execution_log(log)
        return log

    # Lot
    sym_info = mt5.symbol_info(symbol)
    lot, lot_details = calculate_lot_by_risk(
        mt5, symbol, side, actual_entry, sl_price, risk_pct, equity, sym_info
    )
    log["risk_amount"] = lot_details.get("risk_amount", 0)
    log["loss_per_1_lot"] = lot_details.get("loss_per_1_lot", 0)
    log["calculated_lot_raw"] = lot_details.get("lot_raw", 0)
    if lot is None:
        mt5.shutdown()
        log["status"] = "blocked"
        log["reason"] = f"Lot: {lot_details.get('error')}"
        print(f"[BLOCKED] Lot calc")
        write_demo_execution_log(log)
        return log

    log["calculated_lot_final"] = lot
    log["projected_loss"] = lot_details.get("projected_loss", 0)
    log["projected_loss_percent"] = lot_details.get("projected_loss_percent", 0)
    log["validation_status"] = "passed"

    # === EXECUTE ===
    print(f"\n⚡ EXECUTING DEMO ORDER: {symbol} {side.upper()} {lot} lot @ {actual_entry}")
    ok, ticket, msg = execute_demo_order(mt5, symbol, side, lot, sl_price, tp_price, trade_mode)
    log["mt5_retcode"] = msg

    if ok:
        log["status"] = "executed"
        log["reason"] = "Demo order executed"
        log["order_ticket"] = ticket
        # Record pair entry for cooldown tracking
        if cooldown_minutes > 0:
            record_pair_entry(symbol)
            print(f"[COOLDOWN] {symbol} locked for {cooldown_minutes}m")
        print(f"✅ DEMO ORDER EXECUTED: ticket={ticket}")
    else:
        log["status"] = "error"
        log["reason"] = f"Order failed: {msg}"
        print(f"❌ ORDER FAILED: {msg}")

    mt5.shutdown()
    write_demo_execution_log(log)

    # Telegram report
    report = (
        f"🧪 Hermes Exness DEMO CENT Execution\n\n"
        f"Status: {'DEMO EXECUTED' if ok else 'ERROR'}\n"
        f"Real Execution: OFF\n"
        f"Demo Execution Enabled: {demo_exec_enabled}\n"
        f"Account Mode: DEMO CENT\n"
        f"Symbol: {symbol}\n"
        f"Side: {side.upper()}\n"
        f"Lot: {lot}\n"
        f"Entry: {actual_entry}\n"
        f"SL: {sl_price}\n"
        f"TP: {tp_price}\n"
        f"Actual RR: {actual_rr}\n"
        f"Risk per Entry: {risk_pct}%\n"
        f"Risk per Day: {risk_day_pct}%\n"
        f"Projected Loss: {lot_details.get('projected_loss_percent')}%\n"
        f"Max Open Positions: {max_open}\n"
        f"Current Open Positions: {open_count + (1 if ok else 0)}\n"
        f"Reason: {'Executed' if ok else msg}\n"
        f"Ticket: {ticket if ok else 'N/A'}\n"
        f"Log: demo_exec_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    send_demo_execution_report(report)

    return log


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python trade_executor_demo.py --check")
        print("  python trade_executor_demo.py --execute")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "--check":
        cmd_check()
    elif cmd == "--execute":
        cmd_execute()
    else:
        print(f"Unknown command: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()

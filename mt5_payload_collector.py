#!/usr/bin/env python3
"""
MT5 Payload Collector — Hermes Exness Trading System v1.2
Read-only. No orders. No position modifications.
Connects to local MetaTrader5 terminal and builds compact payload JSON.
"""

import json
import sys
import os
from datetime import datetime
from pathlib import Path

# --- Config ---
HERMES_DIR = Path(__file__).resolve().parent
DEFAULT_SYMBOLS = [
    "EURUSDm", "GBPUSDm", "USDJPYm", "USDCHFm",
    "USDCADm", "AUDUSDm", "NZDUSDm", "XAUUSDm"
]


def _load_env() -> dict:
    """Load .env file returning key-value dict (no dependency)."""
    env = {}
    env_path = HERMES_DIR / ".env"
    if not env_path.exists():
        return env
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def get_enabled_symbols() -> list:
    """Read ENABLED_SYMBOLS from .env, fallback to defaults."""
    env = _load_env()
    raw = env.get("ENABLED_SYMBOLS", "")
    if raw:
        syms = [s.strip() for s in raw.split(",") if s.strip()]
        if syms:
            return syms
    return DEFAULT_SYMBOLS

TIMEFRAMES = {
    "H4": None,   # filled at runtime
    "H1": None,
    "M15": None,
    "M5": None,
}

OUTPUT_DIR = Path(__file__).resolve().parent


def _import_mt5():
    """Late import so --status works even if mt5 isn't installed."""
    try:
        import MetaTrader5 as mt5
        return mt5
    except ImportError:
        print("[ERROR] MetaTrader5 package not installed.")
        print("        Run: pip install MetaTrader5")
        sys.exit(1)


def resolve_suffix(mt5, symbol: str) -> str | None:
    """Try symbol as-is first, then strip suffix and try base + common suffixes."""
    candidates = [symbol]  # first try exactly as provided

    # strip trailing "c" or "m" and try base + other suffixes
    base = symbol.rstrip("cm")
    if base != symbol:
        candidates.append(base)
        # try all common suffixes
        for sfx in ["m", "c", "raw", ".c", ".m"]:
            candidates.append(base + sfx)

    for raw in candidates:
        info = mt5.symbol_info(raw)
        if info is not None:
            return raw

    # fallback: scan all symbols
    try:
        all_symbols = [s.name for s in mt5.symbols_get()]
        for raw in candidates:
            if raw in all_symbols:
                return raw
    except Exception:
        pass

    return None


def calc_ema(prices, period):
    """Simple EMA calculation."""
    if len(prices) < period:
        return None
    k = 2 / (period + 1)
    ema = sum(prices[:period]) / period
    for p in prices[period:]:
        ema = p * k + ema * (1 - k)
    return round(ema, 5)


def calc_rsi(prices, period=14):
    """Simple RSI calculation."""
    if len(prices) < period + 1:
        return None
    gains, losses = [], []
    for i in range(1, len(prices)):
        diff = prices[i] - prices[i - 1]
        gains.append(diff if diff > 0 else 0)
        losses.append(abs(diff) if diff < 0 else 0)
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return round(100 - (100 / (1 + rs)), 2)


def calc_atr(mt5, symbol, timeframe, period=14):
    """Calculate ATR from MT5 rates."""
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, period + 1)
    if rates is None or len(rates) < period + 1:
        return None
    tr_vals = []
    for i in range(1, len(rates)):
        h = rates[i]["high"]
        l = rates[i]["low"]
        c_prev = rates[i - 1]["close"]
        tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
        tr_vals.append(tr)
    return round(sum(tr_vals) / period, 5)


def calc_adx(mt5, symbol, timeframe, period=14):
    """Simple ADX calculation."""
    rates = mt5.copy_rates_from_pos(symbol, timeframe, 0, period * 2 + 1)
    if rates is None or len(rates) < period + 1:
        return None

    highs = [r["high"] for r in rates]
    lows = [r["low"] for r in rates]
    closes = [r["close"] for r in rates]

    tr_vals = []
    plus_dm = []
    minus_dm = []

    for i in range(1, len(rates)):
        tr = max(highs[i] - lows[i],
                 abs(highs[i] - closes[i - 1]),
                 abs(lows[i] - closes[i - 1]))
        tr_vals.append(tr)

        up = highs[i] - highs[i - 1]
        down = lows[i - 1] - lows[i]
        plus_dm.append(up if up > down and up > 0 else 0)
        minus_dm.append(down if down > up and down > 0 else 0)

    if len(tr_vals) < period:
        return None

    atr_period = sum(tr_vals[:period]) / period
    plus_di = (sum(plus_dm[:period]) / period / atr_period * 100) if atr_period else 0
    minus_di = (sum(minus_dm[:period]) / period / atr_period * 100) if atr_period else 0

    # smooth with previous value (simple approach)
    for i in range(period, len(tr_vals)):
        atr_period = (atr_period * (period - 1) + tr_vals[i]) / period
        pdi_cur = (sum(plus_dm[i - period + 1:i + 1]) / period / atr_period * 100) if atr_period else 0
        mdi_cur = (sum(minus_dm[i - period + 1:i + 1]) / period / atr_period * 100) if atr_period else 0
        plus_di = (plus_di * (period - 1) + pdi_cur) / period
        minus_di = (minus_di * (period - 1) + mdi_cur) / period

    dx = abs(plus_di - minus_di) / (plus_di + minus_di) * 100 if (plus_di + minus_di) else 0
    return round(dx, 2)


def assess_trend(ema20, ema50, rsi):
    """Simple trend assessment from indicators."""
    if ema20 is None or ema50 is None:
        return "unclear"
    if rsi is None:
        return "unclear"
    if ema20 > ema50 and rsi > 50:
        return "bullish"
    elif ema20 < ema50 and rsi < 50:
        return "bearish"
    else:
        return "neutral"


def collect_payload(mt5):
    """Build compact payload for orchestrator."""
    # resolve timeframe constants
    tf_map = {
        "H4": mt5.TIMEFRAME_H4,
        "H1": mt5.TIMEFRAME_H1,
        "M15": mt5.TIMEFRAME_M15,
        "M5": mt5.TIMEFRAME_M5,
    }

    symbols = get_enabled_symbols()

    payload = {
        "timestamp": datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
        "symbols": {},
    }

    for raw_symbol in symbols:
        symbol = resolve_suffix(mt5, raw_symbol)
        if symbol is None:
            payload["symbols"][raw_symbol] = {"error": "symbol_not_found"}
            continue

        enable = mt5.symbol_select(symbol, True)
        if not enable:
            payload["symbols"][raw_symbol] = {"error": "symbol_select_failed"}
            continue

        # bid / ask / spread
        tick = mt5.symbol_info_tick(symbol)
        info = mt5.symbol_info(symbol)
        if tick is None or info is None:
            payload["symbols"][raw_symbol] = {"error": "tick_or_info_failed"}
            continue

        bid = tick.bid
        ask = tick.ask
        spread = round((ask - bid) / info.point, 1)

        symbol_data = {
            "resolved": symbol,
            "bid": round(bid, info.digits),
            "ask": round(ask, info.digits),
            "spread_points": spread,
        }

        # candles + indicators per TF
        for tf_name, tf_val in tf_map.items():
            rates = mt5.copy_rates_from_pos(symbol, tf_val, 0, 60)
            if rates is None or len(rates) < 50:
                symbol_data[tf_name] = {"error": "insufficient_rates"}
                continue

            closes = [float(r["close"]) for r in rates]

            ema20 = calc_ema(closes, 20)
            ema50 = calc_ema(closes, 50)
            rsi = calc_rsi(closes, 14)
            atr = calc_atr(mt5, symbol, tf_val, 14)
            adx = calc_adx(mt5, symbol, tf_val, 14)

            trend = assess_trend(ema20, ema50, rsi)

            symbol_data[tf_name] = {
                "ema20": ema20,
                "ema50": ema50,
                "rsi": rsi,
                "atr": atr,
                "adx": adx,
                "trend": trend,
            }

        payload["symbols"][raw_symbol] = symbol_data

    return payload


def cmd_status(mt5):
    """Check MT5 connection and symbol availability."""
    if not mt5.initialize():
        # try with path
        if not mt5.initialize(path=r"C:\Program Files\MetaTrader 5	erminal64.exe"):
            print(f"[STATUS] MT5 initialize: FAILED — {mt5.last_error()}")
            return

    print("[STATUS] MT5 initialize: OK")
    terminal_info = mt5.terminal_info()
    if terminal_info:
        print(f"[STATUS] MT5 terminal: {terminal_info.name}")
        print(f"[STATUS] MT5 build: {terminal_info.build}")
        print(f"[STATUS] MT5 path: {terminal_info.path}")
        print(f"[STATUS] MT5 connected: {terminal_info.connected}")
        print(f"[STATUS] MT5 trade allowed: {terminal_info.trade_allowed}")

    account_info = mt5.account_info()
    if account_info:
        print(f"[STATUS] Account: {account_info.login}")
        print(f"[STATUS] Broker: {account_info.server}")
        print(f"[STATUS] Balance: {account_info.balance}")
        print(f"[STATUS] Leverage: {account_info.leverage}")

    print("\n[STATUS] Symbol resolution test:")
    symbols = get_enabled_symbols()
    found = 0
    missing = 0
    for raw in symbols:
        resolved = resolve_suffix(mt5, raw)
        if resolved:
            info = mt5.symbol_info(resolved)
            if info:
                print(f"  {raw} → {resolved} (digits={info.digits}, spread={info.spread})")
                found += 1
            else:
                print(f"  {raw} → {resolved} (no info)")
                found += 1
        else:
            print(f"  {raw} → NOT FOUND")
            missing += 1
    print(f"\n  Found: {found}, Missing: {missing}")

    mt5.shutdown()


def cmd_generate(mt5, output_path):
    """Generate payload and write to file."""
    if not mt5.initialize():
        if not mt5.initialize(path=r"C:\Program Files\MetaTrader 5	erminal64.exe"):
            print(f"[ERROR] MT5 initialize failed: {mt5.last_error()}")
            sys.exit(1)

    print("[INFO] Collecting market data...")
    payload = collect_payload(mt5)

    out = Path(output_path)
    with open(out, "w") as f:
        json.dump(payload, f, indent=2, default=str)

    symbol_count = sum(1 for v in payload["symbols"].values() if "error" not in v)
    error_count = sum(1 for v in payload["symbols"].values() if "error" in v)

    mt5.shutdown()

    print(f"[OK] Payload written to: {out}")
    print(f"[OK] Symbols collected: {symbol_count}")
    if error_count:
        print(f"[WARN] Symbols with errors: {error_count}")

    return payload


def main():
    args = sys.argv[1:]

    if "--status" in args:
        mt5 = _import_mt5()
        cmd_status(mt5)
        return

    if "--output" in args:
        idx = args.index("--output")
        output_path = args[idx + 1] if idx + 1 < len(args) else "mt5_payload.json"
        mt5 = _import_mt5()
        cmd_generate(mt5, output_path)
        return

    # default: show usage
    print("MT5 Payload Collector — Hermes Exness Trading System v1.2")
    print()
    print("Usage:")
    print("  python mt5_payload_collector.py --status")
    print("  python mt5_payload_collector.py --output mt5_payload.json")


if __name__ == "__main__":
    main()

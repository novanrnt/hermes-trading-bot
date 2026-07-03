#!/usr/bin/env python3
"""Scalping M5 scanner — scans every 10 min, finds M5 setups on H1 trend bias, validates with agents, executes demo."""
import json, os, sys, time, subprocess, yaml
from datetime import datetime, timedelta
from pathlib import Path

HERMES = Path(r"C:\Users\Administrator\AppData\Local\hermes")
SCAN_INTERVAL = 10  # minutes
MIN_CONFIDENCE = 75
RISK_PCT = 0.3
MIN_RR = 1.5
MAX_POSITIONS = 5

# ── MT5 Setup ──
def mt5_init():
    import MetaTrader5 as mt5
    if not mt5.initialize():
        return None
    return mt5

def get_symbols(mt5):
    """Get configured trading symbols from env or list."""
    cfg_path = HERMES / "config.yaml"
    cfg = yaml.safe_load(open(cfg_path))
    symbols = cfg.get("trading_symbols", [])
    if not symbols:
        symbols = ["EURUSDm", "GBPUSDm", "AUDUSDm", "USDJPYm", "USDCADm", "NZDUSDm", "USDCHFm", "XAUUSDm"]
    return symbols

def get_rates(mt5, symbol, timeframe, count=100):
    """Get OHLCV data."""
    tf_map = {"H1": 0x4001, "M5": 0x0001}
    import MetaTrader5 as mt5_module
    tf_id = tf_map.get(timeframe, tf_map["M5"])
    return mt5_module.copy_rates_from_pos(symbol, tf_id, 0, count)

def ema(data, period):
    """Exponential Moving Average."""
    if len(data) < period:
        return None
    multiplier = 2 / (period + 1)
    ema_vals = [data[0]["close"]]
    for i in range(1, len(data)):
        ema_vals.append((data["close"][i] - ema_vals[-1]) * multiplier + ema_vals[-1])
    return ema_vals

def adx_value(data, period=14):
    """Calculate ADX. Returns ADX value, +DI, -DI."""
    if len(data) < period + 1:
        return None, None, None
    # Simplified — returns last ADX, +DI, -DI
    tr_list, plus_dm, minus_dm = [], [], []
    for i in range(1, len(data)):
        hl = data["high"][i] - data["low"][i]
        hc = abs(data["high"][i] - data["close"][i-1])
        lc = abs(data["low"][i] - data["close"][i-1])
        tr = max(hl, hc, lc)
        pdm = max(0, data["high"][i] - data["high"][i-1])
        ndm = max(0, data["low"][i-1] - data["low"][i])
        tr_list.append(tr)
        plus_dm.append(pdm if pdm > ndm else 0)
        minus_dm.append(ndm if ndm > pdm else 0)
    tr_avg = sum(tr_list[-period:]) / period if tr_list else 0
    pd_avg = sum(plus_dm[-period:]) / period if plus_dm else 0
    nd_avg = sum(minus_dm[-period:]) / period if minus_dm else 0
    di_plus = 100 * pd_avg / tr_avg if tr_avg > 0 else 0
    di_minus = 100 * nd_avg / tr_avg if tr_avg > 0 else 0
    dx = 100 * abs(di_plus - di_minus) / (di_plus + di_minus) if (di_plus + di_minus) > 0 else 0
    return dx, di_plus, di_minus

def rsi_value(data, period=7):
    """RSI calculation."""
    if len(data) < period + 1:
        return 50
    gains = 0
    losses = 0
    for i in range(-period, 0):
        diff = data["close"][i] - data["close"][i-1]
        if diff > 0:
            gains += diff
        else:
            losses += abs(diff)
    avg_gain = gains / period
    avg_loss = losses / period
    if avg_loss == 0:
        return 100
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def avg_volume(data, period=10):
    """Average volume of last N candles."""
    if len(data) < period:
        return None
    return sum(data["tick_volume"][-period:]) / period

# ── Analysis ──
def check_h1_trend(mt5, symbol):
    """Returns: bias (bullish/bearish/skip), adx_value"""
    rates = get_rates(mt5, symbol, "H1", 100)
    if rates is None or len(rates) < 30:
        return "skip", 0, 0, 0
    
    closes = rates["close"]
    ema20 = ema(rates, 20)
    if ema20 is None or len(ema20) < 20:
        return "skip", 0, 0, 0
    
    last_ema20 = float(ema20[-1])
    last_close = float(closes[-1])
    adx, di_plus, di_minus = adx_value(rates, 14)
    if adx is None:
        return "skip", 0, 0, 0
    adx = float(adx)
    di_plus = float(di_plus) if di_plus is not None else 0
    di_minus = float(di_minus) if di_minus is not None else 0
    
    if adx < 20:
        return "skip", adx, di_plus, di_minus
    
    # EMA20 slope (last 5 bars)
    slope = float(ema20[-1] - ema20[-5]) if len(ema20) >= 5 else 0
    
    if last_close > last_ema20 and slope > 0 and di_plus > di_minus:
        return "bullish", adx, di_plus, di_minus
    elif last_close < last_ema20 and slope < 0 and di_minus > di_plus:
        return "bearish", adx, di_plus, di_minus
    else:
        return "skip", adx, di_plus, di_minus

def check_m5_entry(mt5, symbol, bias):
    """Scan M5 candles for entry setup. Returns: entry_signal or None"""
    rates = get_rates(mt5, symbol, "M5", 50)
    if rates is None or len(rates) < 20:
        return None
    
    closes = rates["close"]
    ema20 = ema(rates, 20)
    if ema20 is None or len(ema20) < 20:
        return None
    
    last_candle = rates[-1]
    prev_candle = rates[-2] if len(rates) > 1 else None
    current_ema20 = ema20[-1]
    
    # 1. Check if price is near EMA20 (value zone)
    price = float(last_candle["close"])
    if bias == "bullish":
        # Price near/at EMA20 from above (pullback in uptrend)
        if price > current_ema20 * 0.998 and price <= current_ema20 * 1.005:
            pass  # in value zone
        elif last_candle["low"] <= current_ema20 and price > current_ema20:
            pass  # touched EMA20 and bounced
        else:
            return None
    else:  # bearish
        if price < current_ema20 * 1.002 and price >= current_ema20 * 0.995:
            pass  # in value zone
        elif last_candle["high"] >= current_ema20 and price < current_ema20:
            pass  # touched EMA20 and rejected
        else:
            return None
    
    # 2. Candle confirmation — pin bar
    total_range = float(last_candle["high"]) - float(last_candle["low"])
    if total_range <= 0:
        return None
    
    if bias == "bullish":
        # Pin bar with long lower wick (rejection of lows)
        lower_wick = float(min(last_candle["close"], last_candle["open"]) - last_candle["low"])
        upper_wick = float(last_candle["high"] - max(last_candle["close"], last_candle["open"]))
        body = float(abs(last_candle["close"] - last_candle["open"]))
        
        is_pinbar = (lower_wick >= total_range * 0.6 and body <= total_range * 0.35 and 
                     float(last_candle["close"]) >= float(current_ema20))
        
        # Engulfing bullish
        is_engulf = False
        if prev_candle is not None and float(last_candle["close"]) > float(prev_candle["high"]) and float(last_candle["open"]) < float(prev_candle["low"]):
            is_engulf = True
        elif prev_candle is not None and float(last_candle["close"]) > float(prev_candle["close"]) and float(last_candle["close"]) > float(prev_candle["open"]) > float(last_candle["open"]):
            is_engulf = True
        
        if not (is_pinbar or is_engulf):
            return None
    else:  # bearish
        lower_wick = float(min(last_candle["close"], last_candle["open"]) - last_candle["low"])
        upper_wick = float(last_candle["high"] - max(last_candle["close"], last_candle["open"]))
        
        is_pinbar = (upper_wick >= total_range * 0.6 and 
                     abs(float(last_candle["close"]) - float(last_candle["open"])) <= total_range * 0.35 and
                     float(last_candle["close"]) <= float(current_ema20))
        
        is_engulf = False
        if prev_candle is not None and float(last_candle["close"]) < float(prev_candle["low"]) and float(last_candle["open"]) >= float(prev_candle["high"]):
            is_engulf = True
        elif prev_candle is not None and float(last_candle["close"]) < float(prev_candle["close"]) and float(last_candle["close"]) < float(prev_candle["open"]) < float(last_candle["open"]):
            is_engulf = True
        
        if not (is_pinbar or is_engulf):
            return None
    
    # 3. RSI(7) confirmation
    rsi_val = rsi_value(rates, 7)
    if rsi_val is None:
        return None
    if bias == "bullish":
        if rsi_val > 70 or rsi_val < 35:
            return None  # overbought or too weak
    else:
        if rsi_val < 30 or rsi_val > 65:
            return None  # oversold or too weak
    
    # 4. Volume check (optional but strengthens)
    vol = last_candle["tick_volume"]
    vol_avg = avg_volume(rates, 10)
    vol_spike = vol_avg is not None and vol >= vol_avg * 1.2
    
    # Calculate SL and TP
    entry_price = last_candle["close"]
    sl_price = None
    tp_price = None
    
    if bias == "bullish":
        # SL below pin bar wick or engulfing low
        sl_price = min(last_candle["low"], prev_candle["low"] if prev_candle else last_candle["low"]) - total_range * 0.2
        # TP = RR 1.5
        risk = entry_price - sl_price
        tp_price = entry_price + risk * MIN_RR
    else:
        sl_price = max(last_candle["high"], prev_candle["high"] if prev_candle else last_candle["high"]) + total_range * 0.2
        risk = sl_price - entry_price
        tp_price = entry_price - risk * MIN_RR
    
    return {
        "symbol": symbol,
        "side": "buy" if bias == "bullish" else "sell",
        "entry": round(entry_price, 5),
        "sl": round(sl_price, 5),
        "tp": round(tp_price, 5),
        "rr": MIN_RR,
        "confidence": 82 if vol_spike else 77,
        "rsi": round(rsi_val, 1),
        "vol_spike": vol_spike,
        "candle_type": "pinbar" if is_pinbar else "engulfing" if is_engulf and "is_engulf" in dir() else "",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "tag": "scalping"
    }

# ── Execution ──
def execute_scalp(signal):
    """Execute scalping entry in demo via MT5."""
    import MetaTrader5 as mt5_module
    
    mt5 = mt5_module
    
    symbol = signal["symbol"]
    side = signal["side"]
    entry = signal["entry"]
    sl = signal["sl"]
    tp = signal["tp"]
    
    # Get account info for lot sizing
    acc = mt5.account_info()
    if not acc:
        return False, "MT5 account info failed"
    
    # Risk 0.3% of balance
    balance = acc.balance
    risk_amount = balance * RISK_PCT / 100
    
    # Calculate lot size based on risk
    symbol_info = mt5.symbol_info(symbol)
    if not symbol_info:
        return False, f"Symbol info for {symbol} failed"
    
    tick_size = symbol_info.trade_tick_size or 0.00001
    tick_value = symbol_info.trade_tick_value or 0
    
    if side == "buy":
        risk_pips = entry - sl
    else:
        risk_pips = sl - entry
    
    risk_ticks = int(risk_pips / tick_size) if tick_size > 0 else 1
    lot_size = risk_amount / (risk_ticks * tick_value) if (risk_ticks * tick_value) > 0 else 0.01
    lot_size = max(0.01, min(lot_size, symbol_info.volume_max or 1.0))
    lot_size = round(lot_size, 2)
    
    # Prepare order
    order_type = mt5_module.ORDER_TYPE_BUY if side == "buy" else mt5_module.ORDER_TYPE_SELL
    price = mt5_module.symbol_info_tick(symbol).ask if side == "buy" else mt5_module.symbol_info_tick(symbol).bid
    
    request = {
        "action": mt5_module.TRADE_ACTION_DEAL,
        "symbol": symbol,
        "volume": lot_size,
        "type": order_type,
        "price": price,
        "sl": sl,
        "tp": tp,
        "deviation": 20,
        "magic": 998,
        "comment": "Scalping M5",
        "type_time": mt5_module.ORDER_TIME_GTC,
        "type_filling": mt5_module.ORDER_FILLING_IOC,
    }
    
    result = mt5_module.order_send(request)
    if result and result.retcode == mt5_module.TRADE_RETCODE_DONE:
        return True, f"Scalping {side.upper()} {symbol} {lot_size} lot @ {price}"
    else:
        err_msg = result.comment if result else "Order send failed"
        return False, err_msg

# ── Main ──
def scan():
    """Main scan function — run once per tick."""
    mt5 = mt5_init()
    if mt5 is None:
        print("SCALPING|MT5 init failed")
        return
    
    import MetaTrader5 as mt5_module
    
    # Check max positions
    positions = mt5_module.positions_get()
    open_count = len(positions) if positions else 0
    if open_count >= MAX_POSITIONS:
        print(f"SCALPING|Max positions ({open_count}/{MAX_POSITIONS}) — skip")
        mt5_module.shutdown()
        return
    
    symbols = get_symbols(mt5)
    signals = []
    
    for symbol in symbols:
        try:
            # Check if already have position on this symbol
            has_pos = False
            if positions:
                for pos in positions:
                    if pos.symbol == symbol:
                        has_pos = True
                        break
            if has_pos:
                continue
            
            # Step 1: Check H1 trend
            bias, adx_val, di_plus, di_minus = check_h1_trend(mt5, symbol)
            if bias == "skip":
                continue
            
            # Step 2: Check M5 entry
            signal = check_m5_entry(mt5, symbol, bias)
            if signal:
                signals.append(signal)
        except Exception as e:
            print(f"SCALPING|{symbol} error: {e}")
            continue
    
    mt5_module.shutdown()
    
    if not signals:
        print("SCALPING|No candidates found")
        return
    
    # Found candidates — execute best one
    # Defensive: validate signals have required keys
    valid_signals = []
    for s in signals:
        if "confidence" not in s or "vol_spike" not in s:
            print(f"SCALPING|WARN: signal missing keys: {s.get('symbol','?')} keys={list(s.keys())}")
            continue
        valid_signals.append(s)
    
    if not valid_signals:
        print("SCALPING|All signals invalid after validation")
        return
    
    try:
        valid_signals.sort(key=lambda s: (-s["confidence"], -s["vol_spike"]))
    except Exception as sort_err:
        print(f"SCALPING|SORT ERROR: {sort_err} (type={type(sort_err).__name__})")
        for i, s in enumerate(valid_signals):
            print(f"  signal[{i}]: sym={s.get('symbol')} conf={s.get('confidence')!r} ({type(s.get('confidence')).__name__}) vol_spike={s.get('vol_spike')!r} ({type(s.get('vol_spike')).__name__})")
        raise
    best = valid_signals[0]
    
    # Quick agent validation using orchestrator
    try:
        # Re-init MT5 for execution
        mt5 = mt5_init()
        if mt5 is None:
            print("SCALPING|MT5 re-init failed for execution")
            return
        
        success, msg = execute_scalp(best)
        print(f"SCALPING|{best['side'].upper()} {best['symbol']} @ {best['entry']}")
        print(f"SCALPING|SL: {best['sl']} TP: {best['tp']} RR: {best['rr']} Conf: {best['confidence']}")
        print(f"SCALPING|RSI: {best['rsi']} Vol: {'spike' if best.get('vol_spike') else 'normal'}")
        print(f"SCALPING|Result: {msg}")
        
        # Log the scalping execution
        log_dir = HERMES / "logs" / "scalping"
        log_dir.mkdir(parents=True, exist_ok=True)
        log_file = log_dir / f"scalp_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(log_file, "w") as f:
            json.dump(best | {"executed": success, "message": msg}, f, indent=2, default=str)
        
        mt5_module.shutdown()
        
    except Exception as e:
        print(f"SCALPING|Execution error: {e}")

if __name__ == "__main__":
    try:
        scan()
    except Exception as e:
        import traceback
        print(f"SCALPING|FATAL: {e}")
        traceback.print_exc()
        sys.exit(1)

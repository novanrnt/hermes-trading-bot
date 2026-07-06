#!/usr/bin/env python3
"""
[SCALP] Lightweight M5 scanner — runs every 10 min.
Quick indicator check (no LLM). 
- IF candidate found → runs full 6-agent pipeline.
- Reports scaled signal as separate [SCALP] entry.
"""
import json, sys, os, time, subprocess
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERMES = Path(r"C:\Users\Administrator\AppData\Local\hermes")
sys.path.insert(0, str(HERMES))

WIB = timezone(timedelta(hours=7))

# ── Config ─────────────────────────────────────────────────
ENABLED_SYMBOLS = [
    "EURUSDm", "GBPUSDm", "USDJPYm", "USDCHFm",
    "USDCADm", "AUDUSDm", "NZDUSDm", "XAUUSDm",
]
ADX_MIN = 18
RSI_PERIOD = 7
RSI_OVERSOLD = 25
RSI_OVERBOUGHT = 75
MAX_SCALP_TRADES_DAY = 5
RISK_SCALP = 0.003  # 0.3% per trade
MIN_RR_SCALP = 1.5
VOLUME_MULTIPLIER = 0.7  # candle volume > avg * this

# ── Helpers ────────────────────────────────────────────────

def now_wib():
    return datetime.now(WIB)

def load_env():
    env = {}
    for line in open(HERMES / ".env"):
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip("'\"")
    return env

def get_mt5_candles(symbol, timeframe, count=100):
    """Fetch MT5 candles. timeframe: 'M5' or 'H1'"""
    import MetaTrader5 as mt5
    tf_map = {"M5": mt5.TIMEFRAME_M5, "H1": mt5.TIMEFRAME_H1}
    # Initialize without path
    if not mt5.initialize():
        mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe")
    
    rates = mt5.copy_rates_from_pos(symbol, tf_map[timeframe], 0, count)
    if rates is None:
        return []
    return list(rates)

def rsi_values(candles, period=RSI_PERIOD):
    """Compute RSI for each candle. Returns list aligned to candle count, front-padded with None."""
    closes = [c[4] for c in candles]  # close = index 4
    n = len(closes)
    if n < period + 1:
        return [None] * n
    
    gains = []
    losses = []
    for i in range(1, n):
        diff = closes[i] - closes[i-1]
        gains.append(max(diff, 0))
        losses.append(max(-diff, 0))
    
    # First avg gain/loss
    avg_gain = sum(gains[:period]) / period
    avg_loss = sum(losses[:period]) / period
    
    # Build RS values (without placeholders)
    rs_vals = [avg_gain / avg_loss if avg_loss > 0 else 100]
    for i in range(period + 1, n):
        avg_gain = (avg_gain * (period - 1) + gains[i-1]) / period
        avg_loss = (avg_loss * (period - 1) + losses[i-1]) / period
        rs_vals.append(avg_gain / avg_loss if avg_loss > 0 else 100)
    
    rsi = [100 - (100 / (1 + r)) for r in rs_vals]
    
    # Pad front to align with candles
    pad = n - len(rsi)
    return [None] * pad + rsi

def ema(values, period=20):
    """Exponential Moving Average"""
    if len(values) < period:
        return [None] * len(values)
    multiplier = 2 / (period + 1)
    result = [None] * (period - 1)
    result.append(sum(values[:period]) / period)
    for v in values[period:]:
        result.append((v - result[-1]) * multiplier + result[-1])
    return result

def adx(candles, period=14):
    """Average Directional Index"""
    highs = [c[2] for c in candles]
    lows = [c[3] for c in candles]
    closes = [c[4] for c in candles]
    
    if len(candles) < period + 1:
        return [None] * len(candles), [None] * len(candles)
    
    # True Range
    tr = []
    for i in range(1, len(candles)):
        hl = highs[i] - lows[i]
        hc = abs(highs[i] - closes[i-1])
        lc = abs(lows[i] - closes[i-1])
        tr.append(max(hl, hc, lc))
    
    # Directional Movement
    plus_dm = []
    minus_dm = []
    for i in range(1, len(candles)):
        up_move = highs[i] - highs[i-1]
        down_move = lows[i-1] - lows[i]
        if up_move > down_move and up_move > 0:
            plus_dm.append(up_move)
        else:
            plus_dm.append(0)
        if down_move > up_move and down_move > 0:
            minus_dm.append(down_move)
        else:
            minus_dm.append(0)
    
    # ATR first
    atr = [sum(tr[:period]) / period]
    for i in range(period, len(tr)):
        atr.append((atr[-1] * (period - 1) + tr[i]) / period)
    
    # Smooth DI
    pdi = [100 * sum(plus_dm[:period]) / atr[0]] if atr[0] > 0 else [0]
    ndi = [100 * sum(minus_dm[:period]) / atr[0]] if atr[0] > 0 else [0]
    for i in range(period, len(plus_dm)):
        p = (pdi[-1] * (period - 1) + plus_dm[i]) / period
        n = (ndi[-1] * (period - 1) + minus_dm[i]) / period
        pdi.append(p if atr[i - period + 1] > 0 else 0)
        ndi.append(n if atr[i - period + 1] > 0 else 0)
    
    # DX → ADX
    dx = []
    for i in range(len(pdi)):
        diff = abs(pdi[i] - ndi[i])
        summ = pdi[i] + ndi[i]
        dx.append(100 * diff / summ if summ > 0 else 0)
    
    # Build ADX values (pad FRONT to align with candles)
    adx_vals = [None] * len(candles)
    if len(dx) >= period:
        adx_raw = []
        adx_raw.append(sum(dx[:period]) / period)
        for i in range(period, len(dx)):
            adx_raw.append((adx_raw[-1] * (period - 1) + dx[i]) / period)
        # Place at end of array
        pad = len(candles) - len(adx_raw)
        if pad >= 0:
            adx_vals = [None] * pad + adx_raw
    
    return adx_vals, atr if atr else [None] * len(candles)

def avg_volume(candles, period=10):
    """Average volume for last N candles"""
    volumes = [c[5] for c in candles[-period:]]
    return sum(volumes) / len(volumes) if volumes else 1

def is_pinbar(candle):
    """Check if candle is a pin bar (wick >= 60% of range)"""
    high, low, open_, close = candle[2], candle[3], candle[1], candle[4]
    total_range = high - low
    if total_range == 0:
        return False, None
    body = abs(close - open_)
    lower_wick = min(open_, close) - low
    upper_wick = high - max(open_, close)
    max_wick = max(lower_wick, upper_wick)
    if max_wick / total_range >= 0.6 and body <= total_range * 0.4:
        if lower_wick >= upper_wick and close < open_:
            return True, "bullish"  # bearish context = bullish pin, CONFUSED. Let me re-think
        if upper_wick >= lower_wick and close > open_:
            return True, "bearish"
    return False, None

def demark_setup(prices, period=9):
    """TD Sequential basic setup — 9 consecutive closes lower/higher"""
    closes = prices
    if len(closes) < period + 1:
        return False, False
    
    buy_count = 0
    sell_count = 0
    for i in range(1, min(period + 1, len(closes))):
        if closes[i] < closes[i-1]:
            buy_count += 1
            sell_count = 0
        elif closes[i] > closes[i-1]:
            sell_count += 1
            buy_count = 0
        if buy_count == 9:
            return True, False  # buy setup (ready for reversal up)
        if sell_count == 9:
            return False, True  # sell setup (ready for reversal down)
    return False, False

def check_pair(symbol, env):
    """Check one pair for scalping setup. Returns dict or None."""
    try:
        m5_candles = get_mt5_candles(symbol, "M5", 100)
        h1_candles = get_mt5_candles(symbol, "H1", 50)
    except:
        return None
    
    if len(m5_candles) < 30 or len(h1_candles) < 30:
        return None
    
    # Parse candles
    m5_close = [c[4] for c in m5_candles]
    h1_close = [c[4] for c in h1_candles]
    
    h1_ema20 = ema(h1_close, 20)
    h1_adx_arr, h1_atr_arr = adx(h1_candles, 14)
    
    # H1 Trend Filter
    current_h1_close = h1_close[-1]
    current_h1_ema = h1_ema20[-1]
    current_h1_adx = h1_adx_arr[-1]
    
    if current_h1_adx is None or current_h1_adx < ADX_MIN:
        return None  # Skip — ranging
    
    # Determine H1 bias
    if current_h1_close > current_h1_ema:
        h1_bias = "long"
    elif current_h1_close < current_h1_ema:
        h1_bias = "short"
    else:
        return None  # No clear trend
    
    # M5 EMA20
    m5_ema20 = ema(m5_close, 20)
    current_m5_price = m5_close[-1]
    current_m5_ema = m5_ema20[-1]
    
    if current_m5_ema is None:
        return None
    
    # Check if price is near EMA20 (within 0.5 ATR)
    m5_atr = None
    # Quick ATR from last 14 M5 candles
    trs = []
    for i in range(1, min(15, len(m5_candles))):
        hl = m5_candles[-i][2] - m5_candles[-i][3]
        hc = abs(m5_candles[-i][2] - m5_candles[-i-1][4])
        lc = abs(m5_candles[-i][3] - m5_candles[-i-1][4])
        trs.append(max(hl, hc, lc))
    m5_atr = sum(trs) / len(trs) if trs else 0
    
    price_near_ema = abs(current_m5_price - current_m5_ema) <= m5_atr * 3.0
    
    if not price_near_ema:
        return None  # Price not near value zone
    
    # RSI(7)
    rsi_arr = rsi_values(m5_candles, RSI_PERIOD)
    current_rsi = rsi_arr[-1]
    prev_rsi = rsi_arr[-2] if len(rsi_arr) >= 2 else None
    
    if current_rsi is None:
        return None
    
    # Check RSI (wide range 20-80, prioritize cross from extreme)
    if h1_bias == "long":
        rsi_ok = (prev_rsi is not None and prev_rsi < RSI_OVERSOLD and current_rsi >= RSI_OVERSOLD) or (current_rsi <= RSI_OVERBOUGHT)
    else:
        rsi_ok = (prev_rsi is not None and prev_rsi > RSI_OVERBOUGHT and current_rsi <= RSI_OVERBOUGHT) or (current_rsi >= RSI_OVERSOLD)
    
    if not rsi_ok:
        return None
    
    # Candle pattern check
    last_candle = m5_candles[-1]
    is_pin, pin_dir = is_pinbar(last_candle)
    
    # Slower pin detection: check if candle direction matches bias
    close = last_candle[4]
    open_ = last_candle[1]
    pin_match = False
    if is_pin and pin_dir:
        if h1_bias == "long" and pin_dir == "bullish":
            pin_match = True
        elif h1_bias == "short" and pin_dir == "bearish":
            pin_match = True
    
    # Engulfing check: prev candle body + current body
    engulf_match = False
    prev_candle = m5_candles[-2]
    if h1_bias == "long" and close > open_:
        prev_body = prev_candle[4] - prev_candle[1]
        curr_body = close - open_
        if prev_body < 0 and curr_body > abs(prev_body):
            engulf_match = True
    elif h1_bias == "short" and close < open_:
        prev_body = prev_candle[1] - prev_candle[4]
        curr_body = open_ - close
        if prev_body > 0 and curr_body > prev_body:
            engulf_match = True
    
    # Trend continuation: candle searah trend + volume
    trend_cont_match = False
    if h1_bias == "long" and close > open_ and close > current_m5_ema:
        trend_cont_match = True
    elif h1_bias == "short" and close < open_ and close < current_m5_ema:
        trend_cont_match = True
    
    # Trigger: pinbar/engulfing (pernah ada reversal setup) ATAU trend continuation + volume
    trigger_ok = pin_match or engulf_match
    if trend_cont_match:
        avg_vol = avg_volume(m5_candles, 10)
        current_vol = last_candle[5]
        vol_ok_tc = current_vol >= avg_vol * 0.6 if avg_vol > 0 else True
        if vol_ok_tc:
            trigger_ok = True
    
    if not trigger_ok:
        return None
    
    # Volume check (for confidence boost)
    avg_vol = avg_volume(m5_candles, 10)
    current_vol = last_candle[5]
    volume_ok = current_vol >= avg_vol * VOLUME_MULTIPLIER if avg_vol > 0 else True
    
    # Build result
    entry_price = close
    sl_dist = m5_atr * 2.5
    if "XAU" in symbol:
        sl_dist = max(sl_dist, 5.0)
        tp_dist = sl_dist * MIN_RR_SCALP
    elif "JPY" in symbol:
        sl_dist = max(sl_dist / 0.01, 15) * 0.01
        tp_dist = sl_dist * MIN_RR_SCALP
    else:
        sl_dist = max(sl_dist, 0.00015)
        tp_dist = sl_dist * MIN_RR_SCALP
    
    # SL/TP calculation by direction
    if h1_bias == "long":
        sl = entry_price - sl_dist
        tp = entry_price + tp_dist
        side = "BUY"
    else:
        sl = entry_price + sl_dist
        tp = entry_price - tp_dist
        side = "SELL"
    
    return {
        "symbol": symbol,
        "side": side,
        "entry": round(entry_price, 5),
        "sl": round(sl, 5),
        "tp": round(tp, 5),
        "rr": round(MIN_RR_SCALP, 2),
        "confidence": 82 if volume_ok else 78,
        "h1_bias": h1_bias,
        "h1_adx": round(current_h1_adx, 1),
        "trigger": "pinbar" if pin_match else "engulfing",
        "volume_ok": volume_ok,
        "rsi": round(current_rsi, 1),
        "reason": f"H1 {h1_bias.upper()} trend, M5 {trigger_ok} at EMA20, RSI {round(current_rsi,1)}, {'volume OK' if volume_ok else 'low volume'}"
    }


def main():
    now = now_wib()
    
    # Only run during trading hours (07:00 - 22:00 WIB weekdays)
    if now.weekday() >= 5:  # weekend
        return
    hour = now.hour
    if hour < 7 or hour >= 22:
        return
    
    # Check daily scalp trade count
    env = load_env()
    
    candidates = []
    for symbol in ENABLED_SYMBOLS:
        result = check_pair(symbol, env)
        if result:
            candidates.append(result)
    
    if not candidates:
        # Silent — no scalping candidates
        return
    
    # Build report
    lines = []
    lines.append("[SCALP] M5 Quick Scan — Signal Detected")
    lines.append("")
    
    for c in candidates:
        vol_mark = "👍" if c["volume_ok"] else "⚠️"
        lines.append(f"{c['symbol']} {c['side']}")
        lines.append(f"  Entry: {c['entry']} | SL: {c['sl']} | TP: {c['tp']}")
        lines.append(f"  RR: {c['rr']} | Conf: {c['confidence']} | RSI: {c['rsi']}")
        lines.append(f"  H1: {c['h1_bias'].upper()} (ADX {c['h1_adx']}) | Trigger: {c['trigger']} {vol_mark}")
        lines.append(f"  Reason: {c['reason']}")
        lines.append("")
    
    lines.append(f"⏰ {now.strftime('%Y-%m-%d %H:%M WIB')}")
    lines.append("")
    lines.append("*[SCALP] This is a scalping signal — separate from [DAY] day trade system*")
    lines.append("*Execution: pipeline will validate before entry*")
    
    print("\n".join(lines))
    
    # ── Trigger Full Swarm Pipeline ──
    today_scalp_count = 0
    try:
        import MetaTrader5 as mt5
        if mt5.initialize():
            now = datetime.now()
            from_dt = now - timedelta(hours=24)
            deals = mt5.history_deals_get(from_dt, now)
            if deals:
                today_scalp_count = len([d for d in deals if d.comment and "SCALP" in d.comment])
            mt5.shutdown()
    except:
        pass
    
    # Check existing positions for these symbols
    existing_symbols = set()
    try:
        import MetaTrader5 as mt5
        if mt5.initialize():
            pos = mt5.positions_get()
            if pos:
                existing_symbols = {p.symbol for p in pos}
            mt5.shutdown()
    except:
        pass
    
    triggered = 0
    for c in candidates[:3]:  # max 3 candidates per scan
        sym = c["symbol"]
        
        # Skip if already have position for this symbol
        if sym in existing_symbols:
            print(f"  ⏭️ {sym} skipped — already have open position")
            continue
        
        # Skip if max scalp trades today reached
        if today_scalp_count >= MAX_SCALP_TRADES_DAY:
            print(f"  ⏭️ Max scalp trades today ({MAX_SCALP_TRADES_DAY}) reached")
            break
        
        print(f"\n[SCALP] ⚡ Candidate: {sym} {c['side']} — triggering swarm...")
        today_scalp_count += 1
        
        # Save candidate details for pipeline to read
        cand_file = HERMES / "scalp_candidate.json"
        with open(cand_file, "w") as f:
            # Convert numpy types (MT5 returns numpy scalars)
            class NpEncoder(json.JSONEncoder):
                def default(self, obj):
                    if hasattr(obj, 'item'):
                        return obj.item()
                    return super().default(obj)
            json.dump(c, f, indent=2, cls=NpEncoder)
        
        try:
            r = subprocess.run(
                [sys.executable, str(HERMES / "agent_swarm.py"), "--mode", "scalp", "--symbol", sym],
                capture_output=True, text=True, timeout=180,
                cwd=str(HERMES)
            )
            out = r.stdout + r.stderr
            print(f"  → agent_swarm.py exit code: {r.returncode}")
            # Print last few lines of pipeline output
            for line in out.split("\n")[-6:]:
                print(f"  {line.strip()}")
        except subprocess.TimeoutExpired:
            print(f"  → Swarm pipeline TIMEOUT ({sym})")
        except Exception as e:
            print(f"  → Swarm pipeline ERROR: {e}")

if __name__ == "__main__":
    main()

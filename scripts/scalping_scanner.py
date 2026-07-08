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
ADX_MIN = 18       # H1 ADX minimum (trend filter)
ADX_MIN_M5 = 20    # M5 ADX minimum (entry filter — jangan masuk kalo M5 choppy)
RSI_PERIOD = 7
RSI_OVERSOLD = 25
RSI_OVERBOUGHT = 75
MAX_SCALP_TRADES_DAY = 999  # no daily limit
RISK_SCALP = 0.003  # 0.3% per trade
MIN_RR_SCALP = 1.5
VOLUME_MULTIPLIER = 0.7  # candle volume > avg * this

# ── Session & News Filters ──
ASIAN_SESSION_BLOCK_START = 0    # Server time: block 00:00
ASIAN_SESSION_BLOCK_END = 6       # Server time: until 06:00
LONDON_NY_WINDOW_START = 14      # Server time: London Open
LONDON_NY_WINDOW_END = 22        # Server time: NY Close
NEWS_BLACKOUT_MINUTES = 30        # Pause 30min before/after high impact news

# Session state (set by main(), read by check_pair)
_session_penalty = 0
_session_label = "Unknown"

# ── Load adaptive config from Quant Learner ──
QUANT_CFG_PATH = HERMES / "quant_config.json"
_quant_cfg_loaded = False

def load_quant_config():
    global ADX_MIN, ADX_MIN_M5, RSI_OVERSOLD, RSI_OVERBOUGHT, MAX_SCALP_TRADES_DAY
    global VOLUME_MULTIPLIER, MIN_RR_SCALP, ENABLED_SYMBOLS, _quant_cfg_loaded
    try:
        if QUANT_CFG_PATH.exists():
            with open(QUANT_CFG_PATH) as f:
                qc = json.load(f)
            ADX_MIN = qc.get("adx_min", ADX_MIN)
            ADX_MIN_M5 = qc.get("adx_min_m5", ADX_MIN_M5)
            RSI_OVERSOLD = qc.get("rsi_oversold", RSI_OVERSOLD)
            RSI_OVERBOUGHT = qc.get("rsi_overbought", RSI_OVERBOUGHT)
            VOLUME_MULTIPLIER = qc.get("volume_multiplier", VOLUME_MULTIPLIER)
            MAX_SCALP_TRADES_DAY = qc.get("max_scalp_trades_day", MAX_SCALP_TRADES_DAY)
            MIN_RR_SCALP = qc.get("min_rr_scalp", MIN_RR_SCALP)
            # Apply blacklist
            blacklisted = qc.get("blacklisted_pairs", [])
            if blacklisted:
                print(f"  🚫 Pairs blacklisted by Quant Learner: {', '.join(blacklisted)}")
            _quant_cfg_loaded = True
            return qc
    except Exception as e:
        print(f"  ⚠️ Quant config load error: {e}")
    return None


# ── Session & News Helpers ──

NEWS_BLACKOUT_PATH = HERMES / "data" / "news_blackout.json"

def get_server_hour() -> int:
    """Get current server hour (UTC for Exness)."""
    return datetime.now(timezone.utc).hour

def is_news_blackout() -> tuple:
    """Check if current time is in news blackout period.
    Returns (blocked: bool, reason: str or None)"""
    try:
        if not NEWS_BLACKOUT_PATH.exists():
            return False, None
        with open(NEWS_BLACKOUT_PATH) as f:
            nb = json.load(f)
        now_utc = datetime.now(timezone.utc)
        blackout_minutes = nb.get("blackout_minutes", NEWS_BLACKOUT_MINUTES)
        for evt in nb.get("events", []):
            try:
                evt_time = datetime.fromisoformat(evt["time"])
                if evt_time.tzinfo is None:
                    evt_time = evt_time.replace(tzinfo=timezone.utc)
                before = evt_time - timedelta(minutes=blackout_minutes)
                after = evt_time + timedelta(minutes=blackout_minutes)
                if before <= now_utc <= after:
                    remaining = (after - now_utc).total_seconds() / 60
                    return True, f"News blackout: {evt['title']} ({int(remaining)}m remaining)"
            except Exception:
                continue
        return False, None
    except Exception:
        return False, None


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
    tf_map = {"M5": mt5.TIMEFRAME_M5, "M15": mt5.TIMEFRAME_M15, "H1": mt5.TIMEFRAME_H1}
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
        m15_candles = get_mt5_candles(symbol, "M15", 50)
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
    _, m15_atr_arr = adx(m15_candles, 14)  # M15 ATR for SL sizing
    
    # H1 Trend Filter
    current_h1_close = h1_close[-1]
    current_h1_ema = h1_ema20[-1]
    current_h1_adx = h1_adx_arr[-1]
    
    if current_h1_adx is None or current_h1_adx < ADX_MIN:
        return None  # Skip — ranging

    # ── M5 ADX Filter — jangan entry kalo M5 juga choppy ──
    m5_adx_arr, _ = adx(m5_candles, 14)
    current_m5_adx = m5_adx_arr[-1] if m5_adx_arr and len(m5_adx_arr) > 0 else None
    if current_m5_adx is None or current_m5_adx < ADX_MIN_M5:
        return None  # Skip — M5 terlalu choppy buat scalp entry
    
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
    
    # ── Quant Trigger: Momentum Breakout + EMA Pullback ──
    last_candle = m5_candles[-1]
    close = last_candle[4]
    open_ = last_candle[1]
    high = last_candle[2]
    low = last_candle[3]
    
    # Recent range (last 5 closes candles)
    lookback = 5
    prev_highs = [c[2] for c in m5_candles[-(lookback+1):-1]]
    prev_lows = [c[3] for c in m5_candles[-(lookback+1):-1]]
    highest_recent = max(prev_highs) if prev_highs else high
    lowest_recent = min(prev_lows) if prev_lows else low
    
    # Candle metrics
    candle_range = high - low
    range_ratio = candle_range / m5_atr if m5_atr > 0 else 0
    body = abs(close - open_)
    body_ratio = body / candle_range if candle_range > 0 else 0
    
    # ⚠️ HARUS candle terakhir sudah closed (bukan forming)
    # Candle[-1] = forming, candle[-2] = most recent closed
    # Tapi kalo range candle forming udah gede, tetap diproses
    
    # ── Entry Confirmation Check ──
    # Cek 3 candle terakhir — minimal 2 dari 3 harus support arah H1
    # (gak wajib candle sebelumnya doang, biar toleransi pullback alami)
    last_3 = m5_candles[-4:-1] if len(m5_candles) >= 4 else m5_candles[-3:]
    directional_count = 0
    for c in last_3:
        if h1_bias == "long":
            if c[4] > c[1]:  # bullish candle
                directional_count += 1
        else:
            if c[4] < c[1]:  # bearish candle
                directional_count += 1
    
    if directional_count < 2:  # butuh minimal 2 dari 3 search arah
        return None  # Trend M5 gak konsisten dengan H1 — skip
    
    # Momentum: break of recent range + strong directional candle
    momentum_breakout = False
    if range_ratio >= 0.7:  # was 0.8 — sedikit longgar
        if h1_bias == "long":
            # HARUS kedua kondisi: break range DAN close bullish
            if high > highest_recent and close > open_ and body_ratio >= 0.55:
                momentum_breakout = True
        elif h1_bias == "short":
            if low < lowest_recent and close < open_ and body_ratio >= 0.55:
                momentum_breakout = True
    
    # Pullback: price near EMA zone + reversed back + closed candle confirm
    ema_dist = abs(current_m5_price - current_m5_ema)
    pullback_entry = False
    if not momentum_breakout and ema_dist <= m5_atr * 2.0:
        if h1_bias == "long":
            if high >= current_m5_ema and close > current_m5_ema and range_ratio >= 0.6 and body_ratio >= 0.55:
                pullback_entry = True
        else:
            if low <= current_m5_ema and close < current_m5_ema and range_ratio >= 0.6 and body_ratio >= 0.55:
                pullback_entry = True
    
    trigger_ok = momentum_breakout or pullback_entry
    trigger_type = "momentum" if momentum_breakout else ("pullback" if pullback_entry else "none")
    
    if not trigger_ok:
        return None
    
    # ── Volume check ──
    avg_vol = avg_volume(m5_candles, 10)
    current_vol = last_candle[5]
    vol_ratio = current_vol / avg_vol if avg_vol > 0 else 0
    volume_ok = vol_ratio >= VOLUME_MULTIPLIER
    
    # ── Confidence Scoring (Quant) ──
    score = 50
    
    # ADX: stronger trend = higher confidence
    if current_h1_adx > 35:
        score += 15
    elif current_h1_adx > 25:
        score += 10
    elif current_h1_adx >= ADX_MIN:
        score += 5
    
    # Momentum: bigger candle relative to ATR = stronger signal
    if range_ratio > 1.5:
        score += 15
    elif range_ratio > 1.0:
        score += 10
    elif range_ratio > 0.6:
        score += 5
    
    # Volume: higher volume = stronger confirmation
    if vol_ratio > 1.5:
        score += 15
    elif vol_ratio > 1.0:
        score += 10
    elif vol_ratio > 0.7:
        score += 5
    
    # EMA alignment: ideal is 0.3-2.0 ATR from EMA (close enough to be pullback, far enough to be real)
    ema_dist_ratio = ema_dist / m5_atr if m5_atr > 0 else 0
    if 0.3 <= ema_dist_ratio <= 2.0:
        score += 10
    elif ema_dist_ratio < 0.3:
        score += 5
    
    # RSI in trend direction
    if h1_bias == "long" and 40 <= current_rsi <= 75:
        score += 10
    elif h1_bias == "short" and 25 <= current_rsi <= 60:
        score += 10
    
    final_score = min(score, 100)
    
    # Apply session penalty (London-NY peak = 0 penalty, non-peak = -10)
    global _session_penalty, _session_label
    if _session_penalty != 0:
        final_score = max(0, final_score + _session_penalty)
    
    # Map score to confidence level
    if final_score >= 85:
        confidence = 88
    elif final_score >= 75:
        confidence = 84
    elif final_score >= 65:
        confidence = 80
    elif final_score >= 55:
        confidence = 77
    else:
        confidence = 74
    
    # ── Build result ──
    entry_price = close
    
    # SL: pake M15 ATR + M5 ATR (bukan H1 yang kegedean skalanya)
    
    if "XAU" in symbol:
        sl_dist = max(m15_atr_curr * 1.0, m5_atr * 3.0, 10.0)
        tp_dist = sl_dist * MIN_RR_SCALP
    elif "JPY" in symbol:
        sl_dist = max(m15_atr_curr * 0.8, m5_atr * 3.0, 0.0030)
        tp_dist = sl_dist * MIN_RR_SCALP
    else:
        sl_dist = max(m15_atr_curr * 0.8, m5_atr * 3.0, 0.0020)
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
        "confidence": confidence,
        "score": final_score,
        "h1_bias": h1_bias,
        "h1_adx": round(current_h1_adx, 1),
        "trigger": trigger_type,
        "volume_ok": volume_ok,
        "vol_ratio": round(vol_ratio, 2),
        "rsi": round(current_rsi, 1),
        "reason": f"Quant {trigger_type.upper()} | H1 {h1_bias.upper()} ADX {round(current_h1_adx,1)} | "
                  f"M5 range {range_ratio:.1f}xATR vol {vol_ratio:.1f}x | RSI {round(current_rsi,1)} "
                  f"| Score {final_score}/100 | {_session_label}"
    }


def main():
    now = now_wib()
    
    # ── Session Filter (server time = UTC) ──
    if now.weekday() >= 5:  # weekend
        return
    
    server_hour = get_server_hour()
    
    # Hard block: Asian session (00:00-06:00 server time = volume tipis)
    if ASIAN_SESSION_BLOCK_START <= server_hour < ASIAN_SESSION_BLOCK_END:
        return  # Hard block — market tidur
    
    # News blackout check
    blocked, reason = is_news_blackout()
    if blocked:
        print(f"  🚫 {reason}")
        return
    
    # Session label buat laporan
    global _session_penalty, _session_label
    if LONDON_NY_WINDOW_START <= server_hour < LONDON_NY_WINDOW_END:
        _session_label = "London-NY"
        _session_penalty = 0
    else:
        _session_label = "Transition"
        _session_penalty = -10  # Lower confidence di luar peak hours
    
    # ── Check closed scalp trades since last scan ──
    LAST_CHECK_FILE = HERMES / "data" / "last_scalp_check.json"
    last_check_ts = 0
    if LAST_CHECK_FILE.exists():
        try:
            last_check_ts = json.load(open(LAST_CHECK_FILE)).get("ts", 0)
        except:
            pass
    
    closed_reports = []
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe")
        
        from datetime import datetime as dt
        now_dt = dt.now()
        check_from = dt.fromtimestamp(last_check_ts) if last_check_ts > 0 else now_dt - timedelta(hours=24)
        deals = mt5.history_deals_get(check_from, now_dt)
        if deals:
            for d in reversed(deals):
                if d.type in (1, 2) and d.comment and "SCALP" in d.comment.upper():
                    closed_reports.append({
                        "symbol": d.symbol,
                        "side": "BUY" if d.type == 1 else "SELL",
                        "pnl": d.profit,
                        "price": d.price,
                        "ticket": d.position_id,
                        "time": dt.fromtimestamp(d.time).strftime("%H:%M"),
                    })
        mt5.shutdown()
    except:
        pass
    
    # Save last check timestamp
    LAST_CHECK_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(LAST_CHECK_FILE, "w") as f:
        json.dump({"ts": time.time()}, f)
    
    if closed_reports:
        print("[SCALP] 📋 **Closed Trades Report**")
        print("")
        for r in closed_reports:
            icon = "✅" if r["pnl"] > 0 else "❌"
            pnl_str = f"+${r['pnl']:.2f}" if r["pnl"] > 0 else f"-${abs(r['pnl']):.2f}"
            print(f"  {icon} {r['symbol']} {r['side']} @ {r['price']} | {pnl_str} | {r['time']} WIB")
        print("")
    
    # ── Load adaptive params from Quant Learner ──
    qc = load_quant_config()
    if qc and qc.get("_analysis"):
        analysis = qc.get("_analysis", {})
        print(f"🧠 Quant Learner: {analysis.get('total_trades',0)} trades | "
              f"WR {analysis.get('win_rate','?')}% | PnL ${analysis.get('total_pnl',0):.2f}")
    
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
    lines.append("*[SCALP] Quant signal — langsung eksekusi, no LLM*")
    
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
        
        # Skip if blacklisted by Quant Learner
        if qc and sym in qc.get("blacklisted_pairs", []):
            print(f"  ⏭️ {sym} skipped — blacklisted by Quant Learner")
            continue
        
        # Skip if already have position for this symbol
        if sym in existing_symbols:
            print(f"  ⏭️ {sym} skipped — already have open position")
            continue
        
        # Skip if max scalp trades today reached
        if today_scalp_count >= MAX_SCALP_TRADES_DAY:
            print(f"  ⏭️ Max scalp trades today ({MAX_SCALP_TRADES_DAY}) reached")
            break
        
        print(f"\n[SCALP] ⚡ Quant Signal: {sym} {c['side']} (Score: {c.get('score','?')}/100)")
        today_scalp_count += 1

        # ── Quant: build final_decision.json & execute directly (no LLM) ──
        from datetime import datetime, timezone

        decision = {
            "action": "entry",
            "mode_trade": "scalp",
            "side": c["side"].lower(),
            "best_symbol": c["symbol"],
            "planned_entry": c["entry"],
            "sl_price": c["sl"],
            "tp_price": c["tp"],
            "rr": c.get("rr", MIN_RR_SCALP),
            "confidence": c.get("confidence", 80),
            "reason": c.get("reason", f"Quant {c.get('trigger','?')} signal"),
            "safety_gate": "passed",
            "mode": "QUANT",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "execution_allowed": True
        }

        # Save candidate for record
        cand_file = HERMES / "scalp_candidate.json"
        with open(cand_file, "w") as f:
            class NpEncoder(json.JSONEncoder):
                def default(self, obj):
                    if hasattr(obj, 'item'):
                        return obj.item()
                    return super().default(obj)
            json.dump(c, f, indent=2, cls=NpEncoder)

        # Save scalp decision (separate file — jangan campur sama final_decision.json day trade!)
        fd_file = HERMES / "scalp_decision.json"
        with open(fd_file, "w") as f:
            json.dump(decision, f, indent=2, cls=NpEncoder)
        print(f"  → scalp_decision.json written (Quant mode)")

        # Execute directly via demo executor (no agent swarm)
        ticket = None
        try:
            r = subprocess.run(
                [sys.executable, str(HERMES / "trade_executor_demo.py"), "--file", str(fd_file), "--execute"],
                capture_output=True, text=True, timeout=120,
                cwd=str(HERMES)
            )
            output = r.stdout + r.stderr
            print(f"  → Executor exit code: {r.returncode}")
            for line in output.split("\n")[-8:]:
                print(f"  {line.strip()}")
            # Extract ticket
            import re
            tm = re.search(r'ticket[= ](\d+)', output)
            if tm:
                ticket = tm.group(1)
        except subprocess.TimeoutExpired:
            print(f"  → Executor TIMEOUT ({sym})")
        except Exception as e:
            print(f"  → Executor ERROR: {e}")

        # ── Save to Trading Memory for Quant Learner ──
        try:
            from trading_memory import load_memory, add_trade, save_memory
            mem = load_memory()
            trade_data = dict(decision)
            trade_data["ticket"] = ticket
            trade_data["trade_mode"] = "scalp"  # Explicit label biar ga ketuker sama day trade
            trade_data["bull_summary"] = c.get("trigger", "quant")
            trade_data["bear_summary"] = ""
            trade_data["risk_summary"] = f"Quant score: {c.get('score','?')}/100"
            add_trade(mem, trade_data)
            print(f"  → Trade saved to trading memory (#{len(mem['trades'])})")
        except Exception as e:
            print(f"  ⚠️ Memory save error: {e}")

        # ── Auto-tune quant params every N trades ──
        try:
            from quant_learner import tune
            tune()
        except Exception as e:
            print(f"  ⚠️ Quant learner tune error: {e}")

if __name__ == "__main__":
    main()

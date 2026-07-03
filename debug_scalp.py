"""Debug: which filter blocks each pair."""
import sys, MetaTrader5 as mt5
from pathlib import Path

HERMES = Path(r"C:\Users\Administrator\AppData\Local\hermes")
sys.path.insert(0, str(HERMES))

from scripts.scalping_scanner import (
    get_mt5_candles, ema, adx, rsi_values, avg_volume,
    is_pinbar, ENABLED_SYMBOLS, ADX_MIN, RSI_PERIOD,
    RSI_OVERSOLD, RSI_OVERBOUGHT, VOLUME_MULTIPLIER
)

for symbol in ENABLED_SYMBOLS:
    m5 = get_mt5_candles(symbol, "M5", 100)
    h1 = get_mt5_candles(symbol, "H1", 50)
    
    if len(m5) < 30 or len(h1) < 30:
        print(f"{symbol:10} ❌ Candle data insufficient")
        continue
    
    m5_close = [c[4] for c in m5]
    h1_close = [c[4] for c in h1]
    
    # H1 filters
    h1_ema20 = ema(h1_close, 20)
    h1_adx_arr, h1_atr_arr = adx(h1, 14)
    
    ch1 = h1_close[-1]
    chema = h1_ema20[-1]
    cadx = h1_adx_arr[-1]
    
    if cadx is None or cadx < ADX_MIN:
        print(f"{symbol:10} ❌ ADX={cadx} (min {ADX_MIN})")
        continue
    
    h1_bias = "long" if ch1 > chema else "short" if ch1 < chema else None
    if not h1_bias:
        print(f"{symbol:10} ❌ No clear H1 trend")
        continue
    
    # M5 EMA
    m5_ema20 = ema(m5_close, 20)
    cm5 = m5_close[-1]
    cm5_ema = m5_ema20[-1]
    if cm5_ema is None:
        print(f"{symbol:10} ❌ M5 EMA None")
        continue
    
    # M5 ATR
    trs = []
    for i in range(1, min(15, len(m5))):
        hl = m5[-i][2] - m5[-i][3]
        hc = abs(m5[-i][2] - m5[-i-1][4])
        lc = abs(m5[-i][3] - m5[-i-1][4])
        trs.append(max(hl, hc, lc))
    m5_atr = sum(trs)/len(trs) if trs else 0
    price_near = abs(cm5 - cm5_ema) <= m5_atr * 1.5
    
    if not price_near:
        print(f"{symbol:10} ❌ Price not near EMA (diff={abs(cm5-cm5_ema):.5f}, atr={m5_atr:.5f})")
        continue
    
    # RSI
    rsi_arr = rsi_values(m5, RSI_PERIOD)
    crsi = rsi_arr[-1]
    prsi = rsi_arr[-2] if len(rsi_arr) >= 2 else None
    if crsi is None:
        print(f"{symbol:10} ❌ RSI None")
        continue
    
    if h1_bias == "long":
        rsi_ok = (prsi is not None and prsi < RSI_OVERSOLD and crsi >= RSI_OVERSOLD) or (RSI_OVERSOLD <= crsi <= 50)
    else:
        rsi_ok = (prsi is not None and prsi > RSI_OVERBOUGHT and crsi <= RSI_OVERBOUGHT) or (50 <= crsi <= RSI_OVERBOUGHT)
    
    if not rsi_ok:
        print(f"{symbol:10} ❌ RSI={crsi:.1f} (needs {RSI_OVERSOLD}-50 for long / 50-{RSI_OVERBOUGHT} for short)")
        continue
    
    # Pinbar check  
    lc = m5[-1]
    is_pin, pin_dir = is_pinbar(lc)
    pin_match = False
    if is_pin and pin_dir:
        if h1_bias == "long" and pin_dir == "bullish":
            pin_match = True
        elif h1_bias == "short" and pin_dir == "bearish":
            pin_match = True
    
    # Engulfing check
    engulf_match = False
    pc = m5[-2]
    close, open_ = lc[4], lc[1]
    if h1_bias == "long" and close > open_:
        pb = pc[4] - pc[1]
        cb = close - open_
        if pb < 0 and cb > abs(pb):
            engulf_match = True
    elif h1_bias == "short" and close < open_:
        pb = pc[1] - pc[4]
        cb = open_ - close
        if pb > 0 and cb > pb:
            engulf_match = True
    
    # Trend continuation
    trend_cont = False
    if h1_bias == "long" and close > open_ and close > cm5_ema:
        trend_cont = True
    elif h1_bias == "short" and close < open_ and close < cm5_ema:
        trend_cont = True
    
    trigger_ok = pin_match or engulf_match
    if trend_cont:
        avg_vol = avg_volume(m5, 10)
        cv = lc[5]
        vol_ok = cv >= avg_vol * 0.8 if avg_vol > 0 else True
        if vol_ok:
            trigger_ok = True
    
    if not trigger_ok:
        print(f"{symbol:10} ❌ No trigger (pin={pin_match}, engulf={engulf_match}, trend_cont={trend_cont}) | last candle: O={lc[1]:.5f} C={lc[4]:.5f} H={lc[2]:.5f} L={lc[3]:.5f}")
        continue
    
    print(f"{symbol:10} ✅ {h1_bias.upper()} | ADX={cadx:.1f} | RSI={crsi:.1f} | EMA diff={abs(cm5-cm5_ema):.5f} | trigger={'pin' if pin_match else 'engulf' if engulf_match else 'trend'}")

mt5.shutdown()

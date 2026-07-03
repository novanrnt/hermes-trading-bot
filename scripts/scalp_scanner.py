#!/usr/bin/env python3
"""Scalp scanner — every 10 min. Silent when no signal. Prints [SCALP] when found."""
import MetaTrader5 as mt5
import pandas as pd
import numpy as np
import warnings
from datetime import datetime, timezone, timedelta

warnings.filterwarnings("ignore", category=DeprecationWarning)
warnings.filterwarnings("ignore", message="Passing more than 2 positional arguments")

WIB = timezone(timedelta(hours=7))
SYMBOLS = ["EURUSDm", "GBPUSDm", "USDJPYm", "USDCHFm", "USDCADm", "AUDUSDm", "NZDUSDm", "XAUUSDm"]

def tr(high, low, close):
    """True Range — avoid numpy.maximum deprecation."""
    hl = high - low
    hc = np.abs(high - close.shift(1))
    lc = np.abs(low - close.shift(1))
    result = hl.copy()
    mask = hc > result
    result[mask] = hc[mask]
    mask = lc > result
    result[mask] = lc[mask]
    return result

def rsi(series, period=7):
    delta = series.diff()
    gain = delta.clip(lower=0).rolling(period).mean()
    loss = (-delta.clip(upper=0)).rolling(period).mean()
    rs = gain / loss.replace(0, np.nan)
    return 100 - (100 / (1 + rs))

def analyze():
    if not mt5.initialize():
        return

    now_wib = datetime.now(WIB)
    # Skip weekend
    if now_wib.weekday() >= 5:
        mt5.shutdown()
        return

    results = []
    high_impact_zones = ["NFP", "CPI", "FOMC", "rate", "GDP", "non-farm", "employment", "retail sales", "inflation", "unemployment"]

    for sym in SYMBOLS:
        symbol_info = mt5.symbol_info(sym)
        if not symbol_info or not symbol_info.trade_mode:
            continue

        # H1 data — determine bias
        h1_rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 100)
        if h1_rates is None or len(h1_rates) < 50:
            continue
        h1 = pd.DataFrame(h1_rates)
        h1["ema20"] = h1["close"].ewm(span=20).mean()
        h1["ema50"] = h1["close"].ewm(span=50).mean()

        # ADX on H1
        h1["tr"] = np.maximum(h1["high"] - h1["low"],
                              np.abs(h1["high"] - h1["close"].shift(1)),
                              np.abs(h1["low"] - h1["close"].shift(1)))
        h1["atr14"] = h1["tr"].rolling(14).mean()
        h1["up"] = h1["high"] - h1["high"].shift(1)
        h1["down"] = h1["low"].shift(1) - h1["low"]
        h1["plus_dm"] = np.where((h1["up"] > h1["down"]) & (h1["up"] > 0), h1["up"], 0)
        h1["minus_dm"] = np.where((h1["down"] > h1["up"]) & (h1["down"] > 0), h1["down"], 0)
        h1["plus_di"] = 100 * (h1["plus_dm"].rolling(14).mean() / h1["atr14"])
        h1["minus_di"] = 100 * (h1["minus_dm"].rolling(14).mean() / h1["atr14"])
        h1["dx"] = 100 * np.abs(h1["plus_di"] - h1["minus_di"]) / (h1["plus_di"] + h1["minus_di"])
        h1_adx = h1["dx"].iloc[-1]

        # Trend bias
        last_ema20 = h1["ema20"].iloc[-1]
        last_ema50 = h1["ema50"].iloc[-1]
        if np.isnan(last_ema20) or np.isnan(last_ema50):
            continue
        if pd.isna(h1_adx):
            continue

        if last_ema20 > last_ema50 and h1_adx >= 20:
            bias = "long"
        elif last_ema20 < last_ema50 and h1_adx >= 20:
            bias = "short"
        else:
            continue  # No clear trend bias

        # M5 data — check entry conditions
        m5_rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 50)
        if m5_rates is None or len(m5_rates) < 20:
            continue
        m5 = pd.DataFrame(m5_rates)
        m5["ema20"] = m5["close"].ewm(span=20).mean()
        m5["rsi7"] = rsi(m5["close"], 7)
        m5["avg_vol"] = m5["tick_volume"].rolling(10).mean()

        last = m5.iloc[-1]
        prev = m5.iloc[-2] if len(m5) >= 2 else None
        current_open = last["open"]
        current_ema20 = last["ema20"]
        current_close = last["close"]
        current_high = last["high"]
        current_low = last["low"]
        current_rsi = last["rsi7"]
        current_vol = last["tick_volume"]
        avg_vol = last["avg_vol"]

        if np.isnan(current_ema20) or pd.isna(current_rsi):
            continue

        if bias == "long":
            # Harga dekat EMA20 (dalam 0.1% atau sentuh)
            pct_from_ema = (current_close - current_ema20) / current_ema20
            if pct_from_ema > 0.005:
                continue  # Too far above EMA

            # RSI baru cross naik dari 40-50
            if current_rsi < 40 or current_rsi > 65:
                continue
            if prev is not None:
                prev_rsi = m5.iloc[-2]["rsi7"]
                if prev_rsi is not None and not pd.isna(prev_rsi):
                    if not (prev_rsi < 50 and current_rsi >= 50):
                        continue
                else:
                    continue
            else:
                continue

            # Candle konfirmasi — pin bar (wick bawah >= 60% range)
            candle_range = current_high - current_low
            if candle_range <= 0:
                continue
            lower_wick = min(current_close, current_open) - current_low
            wick_pct = lower_wick / candle_range
            if wick_pct < 0.6:
                continue

            # Volume spike
            if avg_vol > 0 and current_vol < avg_vol:
                continue

            results.append((sym, bias, current_close, lower_wick, candle_range, current_rsi, current_vol, avg_vol))

        elif bias == "short":
            pct_from_ema = (current_ema20 - current_close) / current_ema20
            if pct_from_ema > 0.005:
                continue

            if current_rsi > 60 or current_rsi < 35:
                continue
            if prev is not None:
                prev_rsi = m5.iloc[-2]["rsi7"]
                if prev_rsi is not None and not pd.isna(prev_rsi):
                    if not (prev_rsi > 50 and current_rsi <= 50):
                        continue
                else:
                    continue
            else:
                continue

            candle_range = current_high - current_low
            if candle_range <= 0:
                continue
            upper_wick = current_high - max(current_close, current_open)
            wick_pct = upper_wick / candle_range
            if wick_pct < 0.6:
                continue

            if avg_vol > 0 and current_vol < avg_vol:
                continue

            results.append((sym, bias, current_close, upper_wick, candle_range, current_rsi, current_vol, avg_vol))

    mt5.shutdown()

    if results:
        wib_str = now_wib.strftime("%H:%M WIB")
        lines = [f"🔹 **[SCALP] — {wib_str}**"]
        for r in results:
            sym, bias, price, wick, c_range, rsi_val, vol, avg_v = r
            arrow = "🟢 BUY" if bias == "long" else "🔴 SELL"
            lines.append(f"  {arrow} {sym} @ {price:.3f}")
            lines.append(f"     RSI(7): {rsi_val:.1f} | Candle: {c_range*1000:.0f}p | Wick: {wick*1000:.0f}p")
            lines.append(f"     Vol: {vol:.0f} (avg {avg_v:.0f})")
        print("\n".join(lines))

if __name__ == "__main__":
    analyze()

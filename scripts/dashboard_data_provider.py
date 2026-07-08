#!/usr/bin/env python3
"""
Dashboard Data Provider — fetches live MT5 data for dashboard.
Updates dashboard_data.json with candles, indicators, and strategy info.
Runs every 1 minute via cron.
"""
import json, sys, os, time, math
from datetime import datetime, timezone, timedelta, date
from pathlib import Path

BASE = Path(r"C:\Users\Administrator\AppData\Local\hermes")
WIB = timezone(timedelta(hours=7))

SYMBOLS = ["EURUSDm","GBPUSDm","USDJPYm","USDCHFm","USDCADm","AUDUSDm","NZDUSDm","XAUUSDm"]

def now_wib():
    return datetime.now(WIB)

def ema(values, period=20):
    if len(values) < period:
        return [None]*len(values)
    m = 2/(period+1)
    r = [None]*(period-1)+[sum(values[:period])/period]
    for v in values[period:]:
        r.append((v-r[-1])*m+r[-1])
    return r

def rsi(values, period=7):
    if len(values) < period+1:
        return [None]*len(values)
    gains = [max(values[i]-values[i-1],0) for i in range(1,len(values))]
    losses = [max(-(values[i]-values[i-1]),0) for i in range(1,len(values))]
    ag = sum(gains[:period])/period
    al = sum(losses[:period])/period
    rs = [ag/al if al>0 else 100]
    for i in range(period+1, len(values)):
        ag = (ag*(period-1)+gains[i-1])/period
        al = (al*(period-1)+losses[i-1])/period
        rs.append(ag/al if al>0 else 100)
    rsi = [100-(100/(1+r)) for r in rs]
    return [None]*(len(values)-len(rsi))+rsi

def macd(values, fast=12, slow=26, signal=9):
    def _ema(vals, p):
        if len(vals) < p: return [None]*len(vals)
        m = 2/(p+1)
        r = [None]*(p-1)+[sum(vals[:p])/p]
        for v in vals[p:]:
            r.append((v-r[-1])*m+r[-1])
        return r
    ema_f = _ema(values, fast)
    ema_s = _ema(values, slow)
    macd_line = []
    for i in range(len(values)):
        if ema_f[i] is not None and ema_s[i] is not None:
            macd_line.append(ema_f[i]-ema_s[i])
        else:
            macd_line.append(None)
    signal_line = _ema([m for m in macd_line if m is not None], signal)
    # Pad signal
    pad = len([m for m in macd_line if m is None])
    return macd_line, [None]*pad+signal_line

def stoch(highs, lows, closes, k=14, d=3):
    stoch_k = []
    for i in range(len(closes)):
        if i < k-1:
            stoch_k.append(None)
        else:
            hh = max(highs[i-k+1:i+1])
            ll = min(lows[i-k+1:i+1])
            stoch_k.append(100*(closes[i]-ll)/(hh-ll) if hh!=ll else 50)
    # Smooth K
    sk = []
    for i in range(len(stoch_k)):
        if i < d-1 or stoch_k[i] is None:
            sk.append(None)
        else:
            vals = [v for v in stoch_k[i-d+1:i+1] if v is not None]
            sk.append(sum(vals)/len(vals) if vals else None)
    return stoch_k, sk

def main():
    import MetaTrader5 as mt5
    if not mt5.initialize():
        mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe")
    
    wib = now_wib()
    
    # ── Account ──
    acc = mt5.account_info()
    if not acc:
        print("No MT5 account")
        mt5.shutdown()
        return
    
    # ── Positions ──
    positions = mt5.positions_get() or []
    
    # ── History (last 24h) ──
    from_dt = datetime.now()-timedelta(hours=24)
    deals = mt5.history_deals_get(from_dt, datetime.now()) or []
    
    # ── Market Data + Indicators ──
    market_data = {}
    for sym in SYMBOLS:
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_M5, 0, 150)
        h1_rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 48)
        if rates is None: continue
        
        closes = [c[4] for c in rates]
        highs = [c[2] for c in rates]
        lows = [c[3] for c in rates]
        opens = [c[1] for c in rates]
        volumes = [int(c[5]) for c in rates]
        times = [c[0] for c in rates]
        
        # Indicators
        rsi_arr = rsi(closes, 7)
        macd_line, macd_signal = macd(closes)
        stoch_k, stoch_d = stoch(highs, lows, closes)
        ema20 = ema(closes, 20)
        ema50 = ema(closes, 50)
        
        # H1 trend
        h1_closes = [h[4] for h in h1_rates] if h1_rates is not None else []
        h1_ema20 = ema(h1_closes, 20) if h1_closes else []
        h1_trend = "NEUTRAL"
        if h1_closes and h1_ema20 and len(h1_ema20) > 0:
            h1c = h1_closes[-1]
            h1e = h1_ema20[-1] if h1_ema20[-1] is not None else h1c
            h1_trend = "BULLISH" if h1c > h1e else ("BEARISH" if h1c < h1e else "NEUTRAL")
        
        # Candle data (last 100 candles for chart)
        candles = []
        for i in range(max(0, len(rates)-100), len(rates)):
            t = time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(rates[i][0]))
            volume = int(rates[i][5])
            # Normalize volume to reasonable chart values
            vol_norm = min(volume // 10 + 1, 100) if 'XAU' not in sym else min(volume // 2, 100)
            candles.append({
                "time": t,
                "open": round(rates[i][1], 5),
                "high": round(rates[i][2], 5),
                "low": round(rates[i][3], 5),
                "close": round(rates[i][4], 5),
                "volume": vol_norm
            })
        
        # Oscillators (last 60 for chart)
        osc_len = min(60, len(rsi_arr))
        oscillators = []
        for i in range(len(rsi_arr)-osc_len, len(rsi_arr)):
            if rsi_arr[i] is not None:
                t = time.strftime('%Y-%m-%dT%H:%M:%S', time.gmtime(times[i]))
                ml = round(macd_line[i], 6) if macd_line[i] is not None else 0
                ms = round(macd_signal[i], 6) if i < len(macd_signal) and macd_signal[i] is not None else 0
                sk = round(stoch_k[i], 1) if stoch_k[i] is not None else 50
                sd = round(stoch_d[i], 1) if stoch_d[i] is not None else 50
                oscillators.append({
                    "time": t,
                    "rsi": round(rsi_arr[i], 1) if rsi_arr[i] is not None else 50,
                    "macd": ml,
                    "macd_signal": ms,
                    "macd_hist": round(ml-ms, 6),
                    "stoch_k": sk,
                    "stoch_d": sd
                })
        
        tick = mt5.symbol_info_tick(sym)
        spread = mt5.symbol_info(sym)
        
        market_data[sym] = {
            "bid": round(tick.bid, 5) if tick else 0,
            "ask": round(tick.ask, 5) if tick else 0,
            "spread": spread.spread if spread else 0,
            "trend": h1_trend,
            "candles": candles,
            "oscillators": oscillators,
            "last_rsi": round(rsi_arr[-1], 1) if rsi_arr and rsi_arr[-1] else 50,
            "last_macd": round(macd_line[-1], 6) if macd_line and macd_line[-1] else 0,
            "last_stoch_k": round(stoch_k[-1], 1) if stoch_k and stoch_k[-1] else 50,
        }
    
    # ── Recent trades (last 20) ──
    history = []
    for d in reversed((deals or [])[-50:]):
        t = datetime.fromtimestamp(d.time)
        history.append({
            "ticket": d.ticket,
            "time": t.strftime("%m-%d %H:%M"),
            "symbol": d.symbol,
            "type": "BUY" if d.type in (0,2) else "SELL",
            "volume": d.volume,
            "price": d.price,
            "profit": round(d.profit, 2),
        })
    
    # ── Strategy data from files ──
    day_trade = {"status": "idle", "last_scan": "-", "decision": "WAIT", "confidence": 0}
    fd_file = BASE / "final_decision.json"
    if fd_file.exists():
        try:
            fd = json.load(open(fd_file))
            if fd.get("mode_trade") == "day":
                day_trade = {
                    "status": "active",
                    "last_scan": fd.get("timestamp","")[:19] if fd.get("timestamp") else "-",
                    "decision": fd.get("action","skip").upper(),
                    "symbol": fd.get("best_symbol","-"),
                    "side": fd.get("side","-").upper(),
                    "confidence": fd.get("confidence", 0),
                    "rr": fd.get("rr", 0),
                }
        except: pass
    
    quant_data = {"status": "idle", "signals_today": 0, "trades_today": 0, "pnl_today": 0}
    
    # Count today's quant trades from history
    today_start = datetime.now().replace(hour=0, minute=0, second=0)
    for d in deals or []:
        if d.comment and "SCAL" in d.comment.upper():
            dt_deal = datetime.fromtimestamp(d.time)
            if dt_deal >= today_start and d.entry in (0, 1):
                if d.entry == 1:  # close
                    quant_data["pnl_today"] += round(d.profit, 2)
        if d.comment and "SCAL" in d.comment.upper() and d.entry == 0:
            dt_deal = datetime.fromtimestamp(d.time)
            if dt_deal >= today_start:
                quant_data["trades_today"] += 1
    
    # Check last scanner output
    scale_file = BASE / "data" / "last_scalp_check.json"
    if scale_file.exists():
        try:
            lsc = json.load(open(scale_file))
            quant_data["last_scan"] = lsc.get("ts","-")
        except: pass
    
    # Read quant config for learner stats
    qc_file = BASE / "quant_config.json"
    if qc_file.exists():
        try:
            qc = json.load(open(qc_file))
            quant_data["learner_trades"] = qc.get("_analysis",{}).get("total_trades", 0)
            quant_data["learner_wr"] = qc.get("_analysis",{}).get("win_rate", 0)
        except: pass
    
    # ── Build output ──
    output = {
        "updated_at": wib.strftime("%H:%M WIB"),
        "account": {
            "login": acc.login,
            "server": acc.server,
            "balance": round(acc.balance, 2),
            "equity": round(acc.equity, 2),
            "margin": round(acc.margin, 2),
            "free_margin": round(acc.margin_free, 2),
            "margin_level": round(acc.margin_level, 1) if acc.margin_level else 0,
            "profit": round(acc.profit, 2),
            "leverage": acc.leverage,
        },
        "positions": [
            {
                "ticket": p.ticket,
                "symbol": p.symbol,
                "type": "BUY" if p.type==0 else "SELL",
                "volume": p.volume,
                "open_price": round(p.price_open, 5),
                "current_price": round(p.price_current, 5),
                "sl": round(p.sl, 5) if p.sl else 0,
                "tp": round(p.tp, 5) if p.tp else 0,
                "profit": round(p.profit, 2),
                "time": datetime.fromtimestamp(p.time).strftime("%m-%d %H:%M"),
            }
            for p in positions
        ],
        "history": history[:20],
        "market": market_data,
        "day_trade": day_trade,
        "quant": quant_data,
    }
    
    out_file = BASE / "dashboard" / "static" / "dashboard_data.json"
    with open(out_file, "w") as f:
        json.dump(output, f, indent=2)
    print(f"✅ Dashboard data updated ({wib.strftime('%H:%M')}) | {len(market_data)} pairs | {len(positions)} positions")
    
    mt5.shutdown()

if __name__ == "__main__":
    main()

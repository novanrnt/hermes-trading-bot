#!/usr/bin/env python3
"""
[SCALP] Max Hold Time — tutup otomatis scalp > 2 jam.
Jalan tiap 5 menit via cron. No agent — silent kalo gak ada yang ditutup.
"""
import sys, json, os, time
from datetime import datetime, timezone, timedelta
from pathlib import Path

BASE = Path(r"C:\Users\Administrator\AppData\Local\hermes")
WIB = timezone(timedelta(hours=7))
MAX_HOLD_HOURS = 2

def now_wib():
    return datetime.now(WIB)

def main():
    import MetaTrader5 as mt5
    if not mt5.initialize():
        mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe")

    positions = mt5.positions_get()
    if not positions:
        mt5.shutdown()
        return  # silent — nothing to do

    now = datetime.now()
    closed = []

    for pos in positions:
        comment = (pos.comment or "").upper()
        if "SCAL" not in comment:
            continue  # hanya scalp

        open_time = datetime.fromtimestamp(pos.time)
        hours_held = (now - open_time).total_seconds() / 3600

        if hours_held < MAX_HOLD_HOURS:
            continue  # masih boleh

        # Close position
        close_type = mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY
        tick = mt5.symbol_info_tick(pos.symbol)
        price = tick.bid if close_type == mt5.ORDER_TYPE_SELL else tick.ask

        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": pos.symbol,
            "volume": pos.volume,
            "type": close_type,
            "position": pos.ticket,
            "price": price,
            "deviation": 20,
            "magic": 1206,
            "comment": "Hermes v1.2 SCALP TIME LIMIT",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_IOC,
        }

        result = mt5.order_send(request)
        if result is None:
            err = mt5.last_error()
            print(f"[SCALP] ❌ Gagal close {pos.symbol} ticket {pos.ticket}: {err}")
            continue
        if result.retcode == mt5.TRADE_RETCODE_DONE:
            pnl = pos.profit
            closed.append({
                "symbol": pos.symbol,
                "ticket": pos.ticket,
                "side": "BUY" if pos.type == 0 else "SELL",
                "hours_held": round(hours_held, 1),
                "pnl": round(pnl, 2),
                "entry": pos.price_open,
                "close_price": price,
            })
            print(f"[SCALP] 🕐 Force close {pos.symbol} {hours_held:.1f}h PnL ${pnl:.2f}")
        else:
            print(f"[SCALP] ❌ Gagal close {pos.symbol} ticket {pos.ticket}: retcode={result.retcode}")

        time.sleep(0.5)  # anti rate limit

    mt5.shutdown()

    if closed:
        wib = now_wib()
        lines = [
            f"🕐 **Scalp Time Limit — Auto Close** ({wib.strftime('%H:%M WIB')})",
            "",
        ]
        total_pnl = 0
        for c in closed:
            icon = "✅" if c["pnl"] >= 0 else "❌"
            lines.append(
                f"{icon} {c['symbol']} {c['side']} | "
                f"{c['hours_held']}h | "
                f"Entry: {c['entry']:.5f} → Close: {c['close_price']:.5f} | "
                f"PnL: ${c['pnl']:.2f}"
            )
            total_pnl += c["pnl"]
        lines.append("")
        lines.append(f"**Total PnL: ${total_pnl:.2f}**")
        lines.append(f"Max hold: {MAX_HOLD_HOURS} jam")
        lines.append("")
        lines.append("_Scalp >2 jam auto ditutup — next trade aja._")
        print("---REPORT---")
        print("\n".join(lines))

if __name__ == "__main__":
    main()

"""
Simple Backtest — replay historical candles through technical agent logic
=======================================================================
Feeds 2 weeks of MT5 H1 data, simulates candidate detection,
tracks what the bot *would have* done and the PNL result.
"""

import json
import sys
import os
from pathlib import Path
from datetime import datetime, timezone, timedelta
from typing import Optional

HERMES_DIR = Path(__file__).parent.resolve()
sys.path.insert(0, str(HERMES_DIR))

WIB = timezone(timedelta(hours=7))


def pull_history(symbol: str, days: int = 14) -> list[dict]:
    """Pull H1 candles from MT5."""
    import MetaTrader5 as mt5
    if not mt5.initialize():
        raise RuntimeError("MT5 not available")

    now = datetime.now()
    start = now - timedelta(days=days)
    rates = mt5.copy_rates_range(symbol, mt5.TIMEFRAME_H1, start, now)
    if rates is None or len(rates) == 0:
        return []

    return [
        {
            "time": datetime.fromtimestamp(r["time"], tz=WIB).isoformat(),
            "open": r["open"],
            "high": r["high"],
            "low": r["low"],
            "close": r["close"],
            "volume": r["tick_volume"],
        }
        for r in rates
    ]


def calculate_indicators(candles: list[dict]) -> dict:
    """Calculate basic TA: SMA, ADX proxy, RSI proxy."""
    if len(candles) < 50:
        return {"error": "not enough data"}

    closes = [c["close"] for c in candles]
    highs = [c["high"] for c in candles]
    lows = [c["low"] for c in candles]
    latest = candles[-1]

    # SMA 50
    sma50 = sum(closes[-50:]) / 50 if len(closes) >= 50 else None
    sma20 = sum(closes[-20:]) / 20 if len(closes) >= 20 else None

    # ADX proxy (simple: average directional movement vs ATR)
    tr_list = []
    pdm_list = []
    ndm_list = []
    for i in range(1, min(30, len(candles))):
        h, l, pc = highs[-i], lows[-i], closes[-i-1]
        tr = max(h - l, abs(h - pc), abs(l - pc))
        tr_list.append(tr)
        up = h - highs[-i-1] if i < len(highs)-1 else 0
        dn = lows[-i-1] - l if i < len(lows)-1 else 0
        pdm_list.append(up if up > dn and up > 0 else 0)
        ndm_list.append(dn if dn > up and dn > 0 else 0)

    atr = sum(tr_list) / len(tr_list) if tr_list else 0.001
    pdi = (sum(pdm_list) / len(pdm_list)) / atr * 100 if pdm_list else 0
    ndi = (sum(ndm_list) / len(ndm_list)) / atr * 100 if ndm_list else 0
    dx = abs(pdi - ndi) / (pdi + ndi) * 100 if (pdi + ndi) > 0 else 0

    # RSI proxy (14-period, simplified)
    gains = []
    losses = []
    for i in range(1, min(15, len(closes))):
        diff = closes[-i] - closes[-i-1]
        if diff > 0:
            gains.append(diff)
            losses.append(0)
        else:
            gains.append(0)
            losses.append(abs(diff))
    avg_gain = sum(gains) / len(gains) if gains else 0
    avg_loss = sum(losses) / len(losses) if losses else 0.001
    rs = avg_gain / avg_loss if avg_loss > 0 else 100
    rsi = 100 - (100 / (1 + rs))

    # Trend detection
    above_sma20 = latest["close"] > sma20 if sma20 else False
    above_sma50 = latest["close"] > sma50 if sma50 else False
    trend = "bullish" if above_sma20 and above_sma50 else "bearish" if not above_sma20 and not above_sma50 else "neutral"

    return {
        "close": latest["close"],
        "sma20": sma20,
        "sma50": sma50,
        "adx": dx,
        "rsi": rsi,
        "atr": atr,
        "trend": trend,
        "candle_count": len(candles),
    }


def evaluate_candidate(symbol: str, ind: dict) -> Optional[dict]:
    """Apply simplified technical filters (same as bot's Technical Agent)."""
    adx = ind.get("adx", 0)
    rsi = ind.get("rsi", 50)
    trend = ind.get("trend", "neutral")
    atr = ind.get("atr", 0)
    close = ind.get("close", 0)

    # Filters (matching the bot's criteria)
    if adx < 15:
        return {"symbol": symbol, "rejected": True, "reason": f"ADX too low ({adx:.1f})"}

    if trend == "neutral":
        return {"symbol": symbol, "rejected": True, "reason": "No clear trend"}

    if rsi > 85 or rsi < 15:
        return {"symbol": symbol, "rejected": True, "reason": f"RSI extreme ({rsi:.1f})"}

    if atr < close * 0.0005:
        return {"symbol": symbol, "rejected": True, "reason": f"ATR too tight ({atr:.5f})"}

    # Candidate found
    direction = "BUY" if trend == "bullish" else "SELL"
    sl_mult = 1.5
    tp_mult = 2.5
    sl = close - (atr * sl_mult) if direction == "BUY" else close + (atr * sl_mult)
    tp = close + (atr * tp_mult) if direction == "BUY" else close - (atr * tp_mult)
    rr = tp_mult / sl_mult if sl_mult > 0 else 0

    return {
        "symbol": symbol,
        "rejected": False,
        "direction": direction,
        "entry": close,
        "sl": round(sl, 5),
        "tp": round(tp, 5),
        "rr": round(rr, 2),
        "adx": round(adx, 1),
        "rsi": round(rsi, 1),
        "atr": round(atr, 5),
    }


def run_backtest(symbols: list[str], days: int = 14) -> dict:
    """Main backtest loop."""
    print(f"\n{'='*60}")
    print(f"  HERMES EXNESS BACKTEST")
    print(f"  Period: {days} days  |  Symbols: {len(symbols)}")
    print(f"  Time: {datetime.now(WIB).strftime('%Y-%m-%d %H:%M WIB')}")
    print(f"{'='*60}\n")

    results = {
        "timestamp": datetime.now(WIB).isoformat(),
        "days": days,
        "symbols": symbols,
        "candidates": [],
        "rejected": [],
        "summary": {},
    }

    for sym in symbols:
        print(f"  [{sym}] Pulling {days}d history...", end=" ")
        candles = pull_history(sym, days)
        if not candles:
            print("NO DATA")
            continue
        print(f"{len(candles)} candles")

        # Analyze at multiple points (every 24 candles = daily check)
        step = max(24, len(candles) // 10)
        for i in range(50, len(candles), step):
            window = candles[:i]
            ind = calculate_indicators(window)
            if "error" in ind:
                continue

            result = evaluate_candidate(sym, ind)
            result["check_time"] = candles[i-1]["time"]
            result["candle_idx"] = i

            if result.get("rejected"):
                results["rejected"].append(result)
            else:
                results["candidates"].append(result)
                print(f"    ✅ CANDIDATE at {candles[i-1]['time']}: "
                      f"{result['direction']} @ {result['entry']:.5f} "
                      f"| ADX={result['adx']} RSI={result['rsi']} RR={result['rr']}")

    # Summary
    total_checks = len(results["candidates"]) + len(results["rejected"])
    results["summary"] = {
        "total_checks": total_checks,
        "candidates_found": len(results["candidates"]),
        "rejected": len(results["rejected"]),
        "hit_rate": round(len(results["candidates"]) / total_checks * 100, 1) if total_checks > 0 else 0,
    }

    print(f"\n{'='*60}")
    print(f"  SUMMARY")
    print(f"  Total checks: {total_checks}")
    print(f"  Candidates:   {len(results['candidates'])}")
    print(f"  Rejected:     {len(results['rejected'])}")
    print(f"  Hit rate:     {results['summary']['hit_rate']}%")
    print(f"{'='*60}\n")

    return results


def save_results(results: dict):
    """Save to logs/backtest/."""
    out_dir = HERMES_DIR / "logs" / "backtest"
    out_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(WIB).strftime("%Y%m%d_%H%M%S")
    path = out_dir / f"backtest_{ts}.json"
    with open(path, "w") as f:
        json.dump(results, f, indent=2, default=str)
    print(f"  [OK] Saved: {path}")


# ── CLI ──────────────────────────────────────────────────────────
def main():
    import argparse
    p = argparse.ArgumentParser(description="Hermes Exness Backtest")
    p.add_argument("--symbols", nargs="+", default=[
        "EURUSDm", "GBPUSDm", "USDJPYm", "AUDUSDm",
        "USDCHFm", "USDCADm", "NZDUSDm", "XAUUSDm"
    ])
    p.add_argument("--days", type=int, default=14)
    p.add_argument("--save", action="store_true", default=True)
    args = p.parse_args()

    results = run_backtest(args.symbols, args.days)
    if args.save:
        save_results(results)


if __name__ == "__main__":
    main()

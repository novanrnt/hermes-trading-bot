#!/usr/bin/env python3
"""
Sentiment Feed Collector — Hermes Exness Bot V1
=================================================
Computes real market sentiment from MT5 price data.
No API key needed. Uses:
- DXY proxy from weighted USD pairs in MT5
- USD strength vs all majors
- Gold sentiment (XAUUSDm trend + volatility)
- Equity mood proxy (USDJPY as risk proxy)
- JPY safe-haven flow detection
Updates sentiment_payload.json for Sentiment Agent.
"""
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = BASE_DIR / "sentiment_payload.json"
LOGS_DIR = BASE_DIR / "logs" / "sentiment_collector"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

# DXY proxy weights (approximate)
DXY_WEIGHTS = {"EUR": 0.576, "JPY": 0.136, "GBP": 0.119, "CAD": 0.091, "SEK": 0.042, "CHF": 0.036}
# We have: EURUSDm, USDJPYm, GBPUSDm, USDCADm, USDCHFm
# EURUSD: EUR strength up = EURUSD up = DXY down (inverse)
# USDJPY: JPY strength down = USDJPY up = DXY up
# GBPUSD: GBP strength up = DXY down (inverse)
# USDCAD: CAD strength down = DXY up
# USDCHF: CHF strength down = DXY up


def _init_mt5():
    import MetaTrader5 as mt5
    if not mt5.initialize():
        if not mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe"):
            return None
    return mt5


def compute_dxy_proxy(mt5) -> dict:
    """Compute approximate DXY from USD pairs in MT5."""
    pairs = {
        "EURUSDm": ("EUR", -1),   # inverse: EURUSD up = USD down
        "USDJPYm":  ("JPY", 1),
        "GBPUSDm":  ("GBP", -1),
        "USDCADm":  ("CAD", 1),
        "USDCHFm":  ("CHF", 1),
    }

    dxy = 0
    for sym, (ccy, direction) in pairs.items():
        tick = mt5.symbol_info_tick(sym)
        if tick:
            price = (tick.bid + tick.ask) / 2
            weight = DXY_WEIGHTS.get(ccy, 0.1)
            # Normalize contribution
            if "JPY" in sym:
                contrib = (price / 100) * weight * direction
            else:
                contrib = price * weight * direction
            dxy += contrib

    # Scale to ~100 range
    dxy = round(dxy * 90, 2)

    # Assess bias
    if dxy > 105:
        usd_bias = "bullish"
    elif dxy < 95:
        usd_bias = "bearish"
    else:
        usd_bias = "neutral"

    return {"dxy_proxy": dxy, "usd_bias": usd_bias}


def compute_gold_sentiment(mt5) -> dict:
    """Assess gold sentiment from XAUUSDm data."""
    sym = "XAUUSDm"
    tick = mt5.symbol_info_tick(sym)
    if not tick:
        return {"gold_sentiment": "unknown"}

    # Get H4 trend
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H4, 0, 50)
    if rates is None or len(rates) < 20:
        return {"gold_sentiment": "neutral"}

    closes = [float(r["close"]) for r in rates]
    ma20 = sum(closes[-20:]) / 20
    current = closes[-1]
    pct_from_ma = round((current - ma20) / ma20 * 100, 2)

    if pct_from_ma > 2:
        sentiment = "bullish"
    elif pct_from_ma < -2:
        sentiment = "bearish"
    else:
        sentiment = "neutral"

    return {
        "gold_sentiment": sentiment,
        "xauusd_price": round(current, 2),
        "pct_from_h4_ma20": pct_from_ma,
    }


def compute_market_mood(mt5, dxy_info: dict) -> dict:
    """Infer overall market mood from major pairs trend alignment."""
    # Check USDJPY as risk proxy
    tick = mt5.symbol_info_tick("USDJPYm")
    usdjpy = (tick.bid + tick.ask) / 2 if tick else 0

    # Get H1 trends
    trends = {}
    for sym in ["EURUSDm", "GBPUSDm", "USDJPYm", "AUDUSDm"]:
        rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 30)
        if rates is not None and len(rates) >= 5:
            first = float(rates[0]["close"])
            last = float(rates[-1]["close"])
            trends[sym] = "up" if last > first else "down"

    # Count bull USD pairs
    usd_bull_count = 0
    if trends.get("EURUSDm") == "down":
        usd_bull_count += 1
    if trends.get("GBPUSDm") == "down":
        usd_bull_count += 1
    if trends.get("USDJPYm") == "up":
        usd_bull_count += 1
    if trends.get("AUDUSDm") == "down":
        usd_bull_count += 1

    if usd_bull_count >= 3:
        mood = "risk_off"  # strong USD = flight to safety
    elif usd_bull_count <= 1:
        mood = "risk_on"
    else:
        mood = "neutral"

    return {
        "market_mood": mood,
        "risk_mode": mood,
        "usdjpy_proxy": round(usdjpy, 5) if usdjpy else None,
        "trend_alignment": trends,
    }


def compute_jpy_flow(mt5) -> dict:
    """Detect JPY safe-haven flow."""
    sym = "USDJPYm"
    rates = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 20)
    if rates is None or len(rates) < 5:
        return {"jpy_safe_haven_flow": "neutral"}

    closes = [float(r["close"]) for r in rates]
    start = closes[0]
    end = closes[-1]
    pct = round((end - start) / start * 100, 2)

    if pct > 0.5:
        return {"jpy_safe_haven_flow": "risk_on"}  # JPY weakening
    elif pct < -0.5:
        return {"jpy_safe_haven_flow": "risk_off"}  # JPY strengthening
    return {"jpy_safe_haven_flow": "neutral"}


def collect() -> dict:
    """Main collection pipeline. Returns payload dict."""
    print("[SENTIMENT COLLECTOR] Starting...")

    mt5 = _init_mt5()
    if mt5 is None:
        print("[ERROR] Cannot connect to MT5")
        return build_fallback()

    try:
        dxy = compute_dxy_proxy(mt5)
        gold = compute_gold_sentiment(mt5)
        mood = compute_market_mood(mt5, dxy)
        jpy = compute_jpy_flow(mt5)

        payload = {
            "status": "available",
            "source": "mt5_computed_live",
            "timezone": "UTC",
            "updated_at": datetime.now(timezone.utc).isoformat(),
            "market_mood": mood["market_mood"],
            "usd_bias": dxy["usd_bias"],
            "risk_mode": mood["risk_mode"],
            "gold_sentiment": gold["gold_sentiment"],
            "jpy_safe_haven_flow": jpy.get("jpy_safe_haven_flow", "neutral"),
            "equity_mood": "unknown",
            "us10y_yield_bias": "unknown",
            "dxy_bias": dxy["usd_bias"],
            "blocked_symbols": [],
            "caution_symbols": [],
            "notes": f"Live MT5 computed. DXY proxy={dxy.get('dxy_proxy')}, "
                     f"XAUUSD={gold.get('xauusd_price')}, "
                     f"USDJPY={mood.get('usdjpy_proxy')}",
            "_raw": {
                "dxy": dxy,
                "gold": gold,
                "mood": mood,
                "jpy": jpy,
            },
        }

        mt5.shutdown()

        # Save
        with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        print(f"[OK] Sentiment: mood={payload['market_mood']}, USD={payload['usd_bias']}, "
              f"Gold={payload['gold_sentiment']}")
        print(f"[OK] Saved to {OUTPUT_FILE}")

        # Log
        log_path = LOGS_DIR / f"sentiment_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        with open(log_path, "w") as f:
            json.dump(payload, f, indent=2, default=str)

        return payload

    except Exception as e:
        print(f"[ERROR] {e}")
        if mt5:
            mt5.shutdown()
        return build_fallback()


def build_fallback() -> dict:
    """Static fallback with neutral sentiment."""
    return {
        "status": "available",
        "source": "static_fallback",
        "timezone": "UTC",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "market_mood": "neutral",
        "usd_bias": "neutral",
        "risk_mode": "neutral",
        "gold_sentiment": "neutral",
        "jpy_safe_haven_flow": "neutral",
        "equity_mood": "unknown",
        "us10y_yield_bias": "unknown",
        "dxy_bias": "neutral",
        "blocked_symbols": [],
        "caution_symbols": [],
        "notes": "MT5 not available. Static neutral fallback.",
    }


def main():
    if "--check" in sys.argv:
        if OUTPUT_FILE.exists():
            with open(OUTPUT_FILE) as f:
                p = json.load(f)
            print(f"Source: {p.get('source')}")
            print(f"Mood: {p.get('market_mood')}")
            print(f"USD: {p.get('usd_bias')}")
            print(f"Gold: {p.get('gold_sentiment')}")
        else:
            print("No payload yet")
    else:
        collect()


if __name__ == "__main__":
    main()

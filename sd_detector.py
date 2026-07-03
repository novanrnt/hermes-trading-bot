#!/usr/bin/env python3
"""
Supply/Demand Zone Detector — v1.0
===================================
Scans H1 candles via MT5, detects S/D zones, tracks touch count,
maintains persistent state in data/sd_zones.json.

Zone life:
  - 0 touch → fresh (full power)
  - 1 touch → confidence -10
  - 2 touch → confidence -20, still valid
  - 3+ touch → expire (reject)
  - Broken (price closes through zone) → remove immediately
  - >48h old → expire

Entry rules (applied downstream in executor):
  - Entry within 1 ATR of zone → eligible
  - Fresh zone → no confidence penalty
  - Tested zone → confidence deduction per touch count
"""

import json
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

BASE_DIR = Path(os.environ.get("HERMES_HOME", r"C:\Users\Administrator\AppData\Local\hermes"))
ENV_PATH = BASE_DIR / ".env"
STATE_FILE = BASE_DIR / "data" / "sd_zones.json"

# Detection params
H1_CANDLE_COUNT = 72       # 3 days of H1 candles
BASE_BODY_MIN_ATR = 2.0    # body > 2x H1 ATR = base candle
BASE_WICK_MAX_PCT = 0.30   # wick < 30% of body
MOMENTUM_CONFIRM = 3       # need 3 candles continuing direction after base
ZONE_MAX_AGE_HOURS = 48    # expire after 48h

WIB = timezone(timedelta(hours=7))


def load_env() -> dict:
    env = {}
    if not ENV_PATH.exists():
        return env
    with open(ENV_PATH, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def load_state() -> dict:
    if STATE_FILE.exists():
        with open(STATE_FILE, "r") as f:
            return json.load(f)
    return {"zones": {}, "updated_at": ""}


def save_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now(WIB).isoformat()
    with open(STATE_FILE, "w") as f:
        json.dump(state, f, indent=2, default=str)


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


def get_h1_candles(symbol: str) -> list:
    """Fetch H1 candles from MT5. Returns list of dicts with OHLC."""
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            return []
        rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, H1_CANDLE_COUNT)
        mt5.shutdown()
        if rates is None or len(rates) < 20:
            return []
        candles = []
        for r in rates:
            candles.append({
                "time": datetime.fromtimestamp(r["time"], tz=timezone.utc).isoformat(),
                "open": float(r["open"]),
                "high": float(r["high"]),
                "low": float(r["low"]),
                "close": float(r["close"]),
            })
        return candles
    except Exception as e:
        print(f"[SD] MT5 error for {symbol}: {e}", file=sys.stderr)
        return []


def compute_atr(candles: list, period: int = 14) -> float:
    """Compute ATR from candle list."""
    if len(candles) < period + 1:
        return 0.0
    trs = []
    for i in range(1, len(candles)):
        h, l, c_prev = candles[i]["high"], candles[i]["low"], candles[i - 1]["close"]
        tr = max(h - l, abs(h - c_prev), abs(l - c_prev))
        trs.append(tr)
    if len(trs) < period:
        return sum(trs) / len(trs) if trs else 0.0
    return sum(trs[-period:]) / period


def detect_zones(symbol: str, candles: list, atr: float) -> list:
    """Scan candles for S/D zones. Returns list of new zone dicts."""
    if atr <= 0 or len(candles) < MOMENTUM_CONFIRM + 2:
        return []

    zones = []
    avg_body = sum(abs(c["close"] - c["open"]) for c in candles[-20:]) / min(len(candles[-20:]), 20)
    min_body = max(BASE_BODY_MIN_ATR * atr, avg_body * 1.5)

    for i in range(len(candles) - MOMENTUM_CONFIRM - 1):
        c = candles[i]
        body = abs(c["close"] - c["open"])
        upper_wick = c["high"] - max(c["open"], c["close"])
        lower_wick = min(c["open"], c["close"]) - c["low"]
        wick = upper_wick if c["close"] > c["open"] else lower_wick

        # Base candle criteria
        if body < min_body:
            continue
        if body > 0 and wick / body > BASE_WICK_MAX_PCT:
            continue

        # Momentum confirmation: next 3 candles must continue direction
        bullish = c["close"] > c["open"]
        confirmed = True
        for j in range(1, MOMENTUM_CONFIRM + 1):
            if i + j >= len(candles):
                confirmed = False
                break
            nc = candles[i + j]
            if bullish and nc["close"] < c["close"]:
                confirmed = False
                break
            if not bullish and nc["close"] > c["close"]:
                confirmed = False
                break
        if not confirmed:
            continue

        # Define zone
        if bullish:
            # Demand zone: base candle low-wick to open
            zone_low = c["low"]
            zone_high = min(c["open"], c["low"] + atr * 0.5)
        else:
            # Supply zone: base candle open to high-wick
            zone_low = max(c["open"], c["high"] - atr * 0.5)
            zone_high = c["high"]

        if zone_high <= zone_low:
            continue

        zone = {
            "symbol": symbol,
            "type": "demand" if bullish else "supply",
            "zone_low": round(zone_low, 8),
            "zone_high": round(zone_high, 8),
            "base_time": candles[i]["time"],
            "base_price": round(c["close"], 8),
            "touch_count": 0,
            "last_touch": "",
            "status": "fresh",
            "expired": False,
        }
        zones.append(zone)

    return zones


def update_touches(zones: list, candles: list):
    """Check current price against zones, update touch count. Wick AND body count as touch."""
    if not candles:
        return
    latest = candles[-1]
    prev = candles[-2] if len(candles) >= 2 else latest

    for zone in zones:
        if zone.get("expired"):
            continue
        zl, zh = zone["zone_low"], zone["zone_high"]

        # Check if price touched zone this candle (wick or body)
        touched = False
        # Body in zone
        if (zl <= latest["open"] <= zh) or (zl <= latest["close"] <= zh):
            touched = True
        # Wick in zone
        if (zl <= latest["high"] <= zh) or (zl <= latest["low"] <= zh):
            touched = True
        # Zone inside candle range
        if latest["low"] <= zl and latest["high"] >= zh:
            touched = True

        # Check if zone was broken (price closed THROUGH zone — beyond it)
        if zone["type"] == "demand" and latest["close"] < zl:
            zone["expired"] = True
            zone["status"] = "broken"
        elif zone["type"] == "supply" and latest["close"] > zh:
            zone["expired"] = True
            zone["status"] = "broken"

        if touched and not zone.get("expired"):
            zone["touch_count"] += 1
            zone["last_touch"] = latest["time"]
            if zone["touch_count"] >= 3:
                zone["expired"] = True
                zone["status"] = "expired"
            elif zone["touch_count"] == 2:
                zone["status"] = "tested_2x"
            elif zone["touch_count"] == 1:
                zone["status"] = "tested_1x"


def expire_old_zones(zones: list):
    """Remove zones older than ZONE_MAX_AGE_HOURS."""
    cutoff = now_utc() - timedelta(hours=ZONE_MAX_AGE_HOURS)
    for zone in zones:
        if zone.get("expired"):
            continue
        try:
            zt = datetime.fromisoformat(zone["base_time"])
            if zt.tzinfo is None:
                zt = zt.replace(tzinfo=timezone.utc)
            if zt < cutoff:
                zone["expired"] = True
                zone["status"] = "expired_age"
        except Exception:
            pass


def merge_zones(existing: list, new_zones: list) -> list:
    """Merge newly detected zones into existing, avoiding duplicates."""
    for nz in new_zones:
        duplicate = False
        for ez in existing:
            if ez.get("expired"):
                continue
            # Same symbol + type + similar zone (within 0.3 ATR)
            if (ez["symbol"] == nz["symbol"] and ez["type"] == nz["type"]):
                avg_existing = (ez["zone_low"] + ez["zone_high"]) / 2
                avg_new = (nz["zone_low"] + nz["zone_high"]) / 2
                if abs(avg_existing - avg_new) < 0.0005:  # ~5 pips forex
                    duplicate = True
                    break
        if not duplicate:
            existing.append(nz)
    return existing


def scan_all_symbols(symbols: list) -> dict:
    """Main scan: fetch H1 candles, detect zones, update touches, save state."""
    state = load_state()
    zones = state.get("zones", {})

    for sym in symbols:
        print(f"[SD] Scanning {sym}...")
        candles = get_h1_candles(sym)

        if not candles:
            print(f"[SD] {sym}: no candles, skipping")
            continue

        atr = compute_atr(candles)
        if atr <= 0:
            print(f"[SD] {sym}: ATR=0, skipping")
            continue

        # Detect new zones
        new_zones = detect_zones(sym, candles, atr)

        # Get existing zones for this symbol
        sym_zones = zones.get(sym, [])

        # Update touches on existing zones
        update_touches(sym_zones, candles)

        # Expire old/broken zones
        expire_old_zones(sym_zones)

        # Merge new zones
        sym_zones = merge_zones(sym_zones, new_zones)

        # Clean: remove expired zones older than 7 days to prevent bloat
        cutoff = now_utc() - timedelta(days=7)
        sym_zones = [
            z for z in sym_zones
            if not z.get("expired") or
            datetime.fromisoformat(z["base_time"]).replace(tzinfo=timezone.utc) > cutoff
        ]

        zones[sym] = sym_zones

        fresh = sum(1 for z in sym_zones if not z.get("expired"))
        print(f"[SD] {sym}: {fresh} active zones (ATR={atr:.6f})")

    state["zones"] = zones
    save_state(state)

    # Build summary for agent consumption
    summary = build_summary(state)
    return summary


def build_summary(state: dict) -> dict:
    """Build a compact summary of active zones for agent prompts."""
    summary = {}
    for sym, zones in state.get("zones", {}).items():
        active = [z for z in zones if not z.get("expired")]
        if not active:
            continue
        nearest_demand = None
        nearest_supply = None
        for z in active:
            entry = {
                "zone_low": z["zone_low"],
                "zone_high": z["zone_high"],
                "status": z["status"],
                "touch_count": z["touch_count"],
                "base_time": z["base_time"],
            }
            if z["type"] == "demand":
                if nearest_demand is None or z["zone_high"] > nearest_demand["zone_high"]:
                    nearest_demand = entry
            else:
                if nearest_supply is None or z["zone_low"] < nearest_supply["zone_low"]:
                    nearest_supply = entry
        summary[sym] = {
            "total_active": len(active),
            "nearest_demand": nearest_demand,
            "nearest_supply": nearest_supply,
        }
    return summary


if __name__ == "__main__":
    env = load_env()
    enabled = env.get("ENABLED_SYMBOLS", "EURUSDm,GBPUSDm,USDJPYm,USDCHFm,USDCADm,AUDUSDm,NZDUSDm,XAUUSDm")
    symbols = [s.strip() for s in enabled.split(",") if s.strip()]

    print(f"[SD] Scanning {len(symbols)} symbols...")
    summary = scan_all_symbols(symbols)

    # Print brief summary
    for sym, info in summary.items():
        print(f"  {sym}: {info['total_active']} zones | "
              f"demand={info['nearest_demand']['zone_low']:.5f}-{info['nearest_demand']['zone_high']:.5f} ({info['nearest_demand']['status']}) | "
              f"supply={info['nearest_supply']['zone_low']:.5f}-{info['nearest_supply']['zone_high']:.5f} ({info['nearest_supply']['status']})"
              if info['nearest_demand'] and info['nearest_supply'] else f"  {sym}: {info['total_active']} zones")

    print(f"\n[SD] Saved to {STATE_FILE}")

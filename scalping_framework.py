#!/usr/bin/env python3
"""
Scalping Framework v1.0 — Hermes Exness Bot
=============================================
Strategi: Trend H1 → Entry M5 (parallel system to day trade)

CORE CONCEPT
────────────
H1 determines trend bias (BUY/SELL only in direction)
M5 pinpoints entry (pullback/breakout/momentum)
SL: below M5 swing low (BUY) or above M5 swing high (SELL)
TP: 2-3x M5 ATR (RR 1.5 target minimum)

RULES
─────
1. TREND FILTER (H1)
   - EMA 20/50 crossover or ADX > 20 & direction
   - H1 must have clear structure (higher highs for uptrend, lower lows for downtrend)
   - NO trade if H1 is choppy/range-bound

2. ENTRY (M5)
   - Pullback to M5 EMA 20/50 in H1 trend direction
   - M5 candle close beyond consolidation range
   - M5 momentum after pullback completes (3 consecutive candles same direction)
   - NO entry during H1 news window

3. EXIT
   - TP: 1.5x RR minimum (flexible up to 3x depending on ATR)
   - SL: below recent M5 swing (min 10 pips, max 18 pips for forex)
   - Trailing stop after TP attained: 2x M5 ATR

4. RISK
   - Risk per trade: 0.3%-0.5% (smaller than day trade)
   - Max 3 open scalping positions total
   - No more than 1 trade per pair simultaneously
   - Max 3 losses in a row before pause (no revenge trading)

5. SEPARATION FROM DAY TRADE
   - Day trade = H4→H1→M15 (existing)
   - Scalping = H1→M5
   - Never trade both systems on same pair at same time
   - Separate max position counts
   - Separate risk pools

CONFIGURATION
─────────────
"""
import json, sys, os
from pathlib import Path

HERMES = Path(os.environ.get("HERMES_DIR", r"C:\Users\Administrator\AppData\Local\hermes"))

# ── Scalping Config ───────────────────────────────────────────────────
SCALP_CONFIG = {
    "enabled": False,               # Master switch
    "max_positions": 3,             # Max scalping positions total
    "risk_per_trade": 0.3,          # % of equity per trade
    "min_rr": 1.5,                  # Minimum reward:risk
    "max_rr": 3.0,                  # Maximum reward:risk
    "min_confidence": 70,           # Confidence threshold
    "sl_min_pips": 10,              # Min SL in pips
    "sl_max_pips": 18,              # Max SL in pips
    "trailing_atr_multiple": 2.0,   # ATR multiple for trailing
    "max_consecutive_loss": 3,      # Pause after 3 losses
    "market_open_only": True,       # Only during liquid market hours
    "session_start_wib": "09:00",   # Scalping session start
    "session_end_wib": "21:00",     # Scalping session end
}

def show_framework():
    """Print the complete framework."""
    print("=" * 60)
    print("  SCALPING FRAMEWORK v1.0 — H1 → M5")
    print("=" * 60)
    print()
    print("📐 CORE IDEA")
    print("  • H1 = Trend filter (bias only)")
    print("  • M5 = Entry execution (precision)")
    print("  • Tighter SL = Higher win rate = Scalping profit")
    print()
    print("📊 H1 TREND FILTER")
    print("  1) Check trend direction:")
    print("     - BUY bias: H1 EMA20 > EMA50, higher highs, ADX > 20")
    print("     - SELL bias: H1 EMA20 < EMA50, lower lows, ADX > 20")
    print("  2) Reject if H1 is ranging (ADX < 20 or tight range)")
    print()
    print("⚡ M5 ENTRY TRIGGERS")
    print("  1) PULLBACK entry:")
    print("     - Price pulls back to M5 EMA 20 in H1 trend direction")
    print("     - Candle closes back in trend direction → ENTRY")
    print("  2) BREAKOUT entry:")
    print("     - M5 consolidation (tight range 5+ candles)")
    print("     - Breakout in H1 trend direction → ENTRY")
    print("  3) MOMENTUM entry:")
    print("     - 3 consecutive M5 candles same direction as H1")
    print("     - Each candle closes higher/lower than previous → ENTRY")
    print()
    print("🎯 EXIT RULES")
    print("  • TP = RR 1.5 (adjust to 2.0 if momentum strong)")
    print("  • SL = Below M5 swing low (BUY) / Above M5 swing high (SELL)")
    print("  • SL range: 10-18 pips forex, 30-50 pips JPY, $3-6 XAU")
    print("  • Trailing: 2x M5 ATR after TP hit")
    print()
    print("💰 RISK MANAGEMENT")
    print(f"  • Risk/trade: {SCALP_CONFIG['risk_per_trade']}%")
    print(f"  • Max positions: {SCALP_CONFIG['max_positions']}")
    print(f"  • Max loss streak: {SCALP_CONFIG['max_consecutive_loss']} → auto-pause")
    print(f"  • Session: {SCALP_CONFIG['session_start_wib']}-{SCALP_CONFIG['session_end_wib']} WIB")
    print()
    print("🔄 SEPARATION FROM DAY TRADE")
    print("  • Day trade (H4→H1→M15) runs as-is")
    print("  • Scalping (H1→M5) runs as separate pipeline")
    print("  • Different pairs recommended (e.g. EURUSD day, GBPUSD scalp)")
    print("  • Never same pair both systems simultaneously")
    print()
    print("⚙️ ENABLE WHEN READY:")
    print(f"  Edit scalping_framework.py → SCALP_CONFIG['enabled'] = True")
    print("  Or run: python scalping_framework.py --enable")
    print("=" * 60)

def save_config():
    """Save config to JSON for pipeline to read."""
    conf_file = HERMES / "scalping_config.json"
    with open(conf_file, "w") as f:
        json.dump(SCALP_CONFIG, f, indent=2)
    print(f"✅ Config saved to {conf_file}")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--enable":
        SCALP_CONFIG["enabled"] = True
        save_config()
        print("🟢 SCALPING ENABLED")
    else:
        show_framework()

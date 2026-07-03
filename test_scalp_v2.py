"""Test actual check_pair function with all fixes."""
import sys
from pathlib import Path

HERMES = Path(r"C:\Users\Administrator\AppData\Local\hermes")
sys.path.insert(0, str(HERMES))

from scripts.scalping_scanner import check_pair, ENABLED_SYMBOLS, now_wib

env = {}
for line in open(HERMES / ".env"):
    line = line.strip()
    if "=" in line and not line.startswith("#"):
        k, v = line.split("=", 1)
        env[k.strip()] = v.strip().strip("'\" ")

print(f"Scan: {now_wib().strftime('%H:%M WIB')}")
print("=" * 60)
found = 0
for sym in ENABLED_SYMBOLS:
    r = check_pair(sym, env)
    if r:
        found += 1
        print(f"\n✅ {r['symbol']} {r['side']}")
        print(f"   Entry: {r['entry']} | SL: {r['sl']} | TP: {r['tp']}")
        print(f"   RR: {r['rr']} | Conf: {r['confidence']} | Trigger: {r['trigger']}")
        print(f"   H1: {r['h1_bias'].upper()} ADX {r['h1_adx']} | RSI: {r['rsi']} | VolOK: {r['volume_ok']}")
    else:
        print(f"   {sym:10} ❌")

print(f"\n✅ Total: {found} kandidat" if found else "\n❌ Tidak ada kandidat")

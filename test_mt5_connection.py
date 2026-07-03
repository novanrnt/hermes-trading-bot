#!/usr/bin/env python3
"""
Test MetaTrader 5 Python connection.
Read-only. No orders. No position modifications.
"""

import sys
import os

def main():
    # --- Import ---
    try:
        import MetaTrader5 as mt5
    except ImportError:
        print("[FAIL] MetaTrader5 package not installed.")
        print("       Run: pip install MetaTrader5")
        sys.exit(1)

    print(f"[INFO] MetaTrader5 Python package version: {mt5.__version__}")

    # --- Terminal path ---
    # Try Exness branded first, then standard
    paths = [
        r"C:\Program Files\Exness MetaTrader 5\terminal64.exe",
        r"C:\Program Files\MetaTrader 5\terminal64.exe",
    ]
    
    terminal_path = None
    for p in paths:
        if os.path.exists(p):
            terminal_path = p
            break
    
    if terminal_path:
        print(f"[INFO] Terminal path: {terminal_path}")
    else:
        print("[WARN] No terminal64.exe found in standard paths")
        print("       Will try mt5.initialize() without path")

    # --- Initialize ---
    print("\n[TEST] Initializing MT5 connection...")
    
    if terminal_path:
        ok = mt5.initialize(path=terminal_path, timeout=30000)
    else:
        ok = mt5.initialize(timeout=30000)
    
    if not ok:
        error = mt5.last_error()
        print(f"[FAIL] MT5 initialize failed!")
        print(f"       Error code: {error[0]}")
        print(f"       Error message: {error[1]}")
        
        # Troubleshooting hints
        if error[0] == -10005:
            print("\n[HINT] IPC Timeout — possible causes:")
            print("       1. MT5 terminal not running")
            print("       2. MT5 terminal running but not logged in")
            print("       3. Python package version mismatch with terminal build")
            print("       4. Another MT5 instance blocking IPC")
        elif error[0] == -10003:
            print("\n[HINT] IPC Initialize Failed — possible causes:")
            print("       1. terminal64.exe path incorrect")
            print("       2. MT5 already running (close it first, then retry)")
            print("       3. Permission issue")
        
        mt5.shutdown()
        sys.exit(1)
    
    print("[OK] MT5 initialized successfully!")
    
    # --- Version ---
    version = mt5.version()
    print(f"\n[INFO] MT5 version: {version}")
    
    # --- Terminal Info ---
    terminal = mt5.terminal_info()
    if terminal:
        print(f"\n[TERMINAL]")
        print(f"  Name: {terminal.name}")
        print(f"  Build: {terminal.build}")
        print(f"  Connected: {terminal.connected}")
        print(f"  Trade allowed: {terminal.trade_allowed}")
        print(f"  Path: {terminal.path}")
    else:
        print(f"[WARN] Cannot get terminal info: {mt5.last_error()}")
    
    # --- Account Info (masked) ---
    account = mt5.account_info()
    if account:
        login_str = str(account.login)
        masked_login = "***" + login_str[-4:] if len(login_str) > 4 else "***"
        print(f"\n[ACCOUNT]")
        print(f"  Login: {masked_login}")
        print(f"  Server: {account.server}")
        print(f"  Company: {account.company}")
        print(f"  Currency: {account.currency}")
        print(f"  Balance: {account.balance}")
        print(f"  Leverage: 1:{account.leverage}")
        trade_mode = {0: "Demo", 1: "Contest", 2: "Real"}.get(account.trade_mode, "Unknown")
        print(f"  Trade mode: {trade_mode}")
    else:
        print(f"\n[WARN] No account logged in: {mt5.last_error()}")
    
    # --- Symbol Ticks ---
    print(f"\n[TICKS]")
    for symbol in ["EURUSD", "XAUUSD"]:
        info = mt5.symbol_info(symbol)
        if info is None:
            # Try with suffix
            for suffix in ["m", "c", ""]:
                test = symbol + suffix
                info = mt5.symbol_info(test)
                if info:
                    symbol = test
                    break
        
        if info:
            tick = mt5.symbol_info_tick(symbol)
            if tick:
                print(f"  {symbol}: Bid={tick.bid} Ask={tick.ask} Spread={info.spread}")
            else:
                print(f"  {symbol}: No tick data")
        else:
            print(f"  {symbol}: Symbol not found")
    
    # --- Available Symbols ---
    symbols = mt5.symbols_get()
    if symbols:
        print(f"\n[SYMBOLS] Total available: {len(symbols)}")
        # Show first 10
        for s in symbols[:10]:
            print(f"  - {s.name}")
        if len(symbols) > 10:
            print(f"  ... and {len(symbols) - 10} more")
    
    # --- Shutdown ---
    mt5.shutdown()
    print(f"\n[DONE] Connection test complete. MT5 shutdown OK.")


if __name__ == "__main__":
    main()

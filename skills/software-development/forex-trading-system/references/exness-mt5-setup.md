# Exness + MT5 Python Setup Guide

## Prerequisites

1. **MT5 Terminal** — Download from https://www.exness.com/metatrader-5/
2. **Install on VPS** — Windows Server with RDP access
3. **Login** to Exness trading account in MT5
4. **Python package:** `pip install MetaTrader5 pandas numpy`

## Finding Your Exness Server Name

In MT5 terminal: File → Login to Trade Account → Server field shows exact name.
Common patterns:
- `Exness-MT5Real` (real account)
- `Exness-MT5Trial` (demo account)
- `ExnessReal` (older naming)

## Python Connection

```python
import MetaTrader5 as mt5

# Initialize
if not mt5.initialize(
    path='C:\\Program Files\\MetaTrader 5\\terminal64.exe',
    login=YOUR_ACCOUNT_NUMBER,
    password='YOUR_PASSWORD',
    server='Exness-MT5Real'
):
    print(f"Init failed: {mt5.last_error()}")
    exit()

# Verify
info = mt5.account_info()
print(f"Connected: {info.login} @ {info.server}, Balance: {info.balance}")
```

## Exness-Specific Notes

- **Filling mode:** Exness uses `ORDER_FILLING_IOC` (not FOK)
- **Check filling:** `mt5.symbol_info(symbol).filling_mode`
- **Min lot:** Varies by account type (0.01 for Standard)
- **Stop level:** Check `mt5.symbol_info(symbol).trade_stops_level`
- **Spread:** Floating, check before entry: `mt5.symbol_info_tick(symbol).ask - mt5.symbol_info_tick(symbol).bid`

## VPS Considerations

- MT5 needs GUI session (RDP or virtual display)
- Keep MT5 running 24/5 for forex market hours
- Set MT5 to auto-login on startup
- Windows Firewall: allow MT5 outbound connections

## MT5 Installation on VPS

The MT5 installer is GUI-only. Silent install flags (`/S`, `/quiet`) do NOT work. Use `pyautogui` + `win32gui` to automate the installer. See `references/mt5-gui-automation.md` for full code patterns.

### Steps
1. Download from `https://download.metatrader.com/cdn/web/exness.technologies.ltd/mt5/exness5setup.exe`
2. Run with `pyautogui.hotkey('alt', 'n')` in a loop (15 iterations)
3. Close "Open an Account" wizard with `WM_CLOSE`
4. Open File → Login to Trade Account (menu id 32853)
5. Fill login/password/server via `WM_SETTEXT` on ComboBox Edit children

### Known Server Names
- Demo: `Exness-MT5Trial14`, `Exness-MT5Trial15` (number varies)
- Real: `Exness-MT5Real`, `ExnessReal`

## Python MT5 Package Compatibility

The MetaTrader5 Python package version MUST match or exceed the terminal build. As of June 2026:
- pip package: `5.0.5735`
- Latest terminal build: `5836`
- **Result: IPC HANG — package too old for latest terminal**

If `mt5.initialize()` hangs indefinitely (no timeout), this is the cause. Check `MetaTrader5.__version__` vs terminal build in logs (`MetaTrader 5 x64 build XXXX`).

Workarounds: downgrade terminal, use GUI automation, or wait for package update.

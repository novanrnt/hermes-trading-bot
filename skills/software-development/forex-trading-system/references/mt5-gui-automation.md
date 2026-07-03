# MT5 GUI Automation Patterns (Windows)

Use when the MT5 Python API is unavailable (version mismatch, IPC hang) or when you need to install/login MT5 programmatically on a VPS.

## Prerequisites

```bash
pip install pyautogui pygetwindow pywin32
```

## Key Libraries

- `win32gui` — find windows, get/set text, send messages
- `win32con` — window message constants (WM_CLOSE, BM_CLICK, WM_SETTEXT, etc.)
- `pyautogui` — keyboard/mouse automation (hotkey, typewrite, press)
- `ctypes` — low-level Windows API calls (GetMenuStringW, etc.)

## Pattern 1: MT5 Silent Install

The MT5 installer is NSIS-based but `/S` flag does NOT work. Automate the GUI:

```python
import subprocess, time, pyautogui

pyautogui.FAILSAFE = False
proc = subprocess.Popen([r'C:\Users\Administrator\mt5setup.exe'])

# Click through 10-15 "Next" steps
for step in range(15):
    pyautogui.hotkey('alt', 'n')  # Alt+N = Next in NSIS
    time.sleep(3)

pyautogui.press('enter')  # Finish
```

Install location: `C:\Program Files\MetaTrader 5\terminal64.exe`

## Pattern 2: Close "Open an Account" Wizard

After install/launch, MT5 shows an account wizard. Close it:

```python
import win32gui, win32con, time

def find_window(title_exact):
    results = []
    def enum_callback(hwnd, _):
        if win32gui.IsWindowVisible(hwnd):
            if win32gui.GetWindowText(hwnd) == title_exact:
                results.append(hwnd)
    win32gui.EnumWindows(enum_callback, None)
    return results

for hwnd in find_window("Open an Account"):
    win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
    time.sleep(1)
```

## Pattern 3: Open Login Dialog via Menu

MT5 menu: File → Login to Trade Account (command id 32853)

```python
import ctypes, win32gui, win32con, time

user32 = ctypes.windll.user32

mt5_hwnds = find_window("MetaTrader 5")
hwnd = mt5_hwnds[0]

menu = win32gui.GetMenu(hwnd)
file_menu = win32gui.GetSubMenu(menu, 0)  # File = index 0

# Find "Login to Trade Account" by iterating menu items
count = win32gui.GetMenuItemCount(file_menu)
for i in range(count):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetMenuStringW(file_menu, i, buf, 256, win32con.MF_BYPOSITION)
    if 'login to trade account' in buf.value.lower():
        item_id = win32gui.GetMenuItemID(file_menu, i)
        win32gui.PostMessage(hwnd, win32con.WM_COMMAND, item_id, 0)
        time.sleep(3)
        break
```

## Pattern 4: Fill Login Dialog

Login dialog structure:
- ComboBox (Login) → contains Edit child
- Edit (Password) — direct child of dialog
- Edit (Certificate password) — direct child
- ComboBox (Server) → contains Edit child
- OK / Cancel buttons

```python
login_hwnd = find_window("Login")[0]

children = []
def enum_child(chwnd, _):
    text = win32gui.GetWindowText(chwnd)
    cls = win32gui.GetClassName(chwnd)
    children.append((chwnd, text, cls))
win32gui.EnumChildWindows(login_hwnd, enum_child, None)

combo_boxes = [ch for ch, ct, cc in children if cc == 'ComboBox']
direct_edits = [ch for ch, ct, cc in children if cc == 'Edit' and win32gui.GetParent(ch) == login_hwnd]

# Get Edit inside each ComboBox
combo_edits = []
for combo in combo_boxes:
    combo_ch = []
    def enum_combo(chwnd, _):
        if win32gui.GetClassName(chwnd) == 'Edit':
            combo_ch.append(chwnd)
    win32gui.EnumChildWindows(combo, enum_combo, None)
    combo_edits.extend(combo_ch)

# Set login (first combo edit)
win32gui.SendMessage(combo_edits[0], win32con.WM_SETTEXT, 0, "LOGIN_NAME")

# Set password (first direct edit)
win32gui.SendMessage(direct_edits[0], win32con.WM_SETTEXT, 0, "PASSWORD")

# Set server (second combo edit)
win32gui.SendMessage(combo_edits[1], win32con.WM_SETTEXT, 0, "Exness-MT5Trial14")

# Click OK
buttons = [(ch, ct) for ch, ct, cc in children if cc == 'Button']
for ch, ct in buttons:
    if 'OK' in ct:
        win32gui.PostMessage(ch, win32con.BM_CLICK, 0, 0)
        time.sleep(8)
        break
```

## Pattern 5: List Server Dropdown Contents

To find available Exness servers:

```python
# After opening login dialog, get server combo
server_combo = combo_boxes[1]
count = win32gui.SendMessage(server_combo, win32con.CB_GETCOUNT, 0, 0)
for i in range(count):
    length = win32gui.SendMessage(server_combo, win32con.CB_GETLBTEXTLEN, i, 0)
    buf = ctypes.create_unicode_buffer(length + 1)
    win32gui.SendMessage(server_combo, win32con.CB_GETLBTEXT, i, buf)
    print(f"Server {i}: '{buf.value}'")
```

## Pattern 6: List All MT5 Menu Items

```python
menu = win32gui.GetMenu(hwnd)
count = win32gui.GetMenuItemCount(menu)
for i in range(count):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetMenuStringW(menu, i, buf, 256, win32con.MF_BYPOSITION)
    print(f"Menu {i}: '{buf.value}'")

# Get submenu items
file_menu = win32gui.GetSubMenu(menu, 0)
count = win32gui.GetMenuItemCount(file_menu)
for i in range(count):
    buf = ctypes.create_unicode_buffer(256)
    user32.GetMenuStringW(file_menu, i, buf, 256, win32con.MF_BYPOSITION)
    item_id = win32gui.GetMenuItemID(file_menu, i)
    print(f"  {i}: '{buf.value}' (id={item_id})")
```

## Pitfalls

1. **`win32gui.SetFocus()` returns "Access is denied"** when targeting windows owned by another process. Use `WM_SETTEXT` directly instead of trying to focus + type.

2. **`pyautogui.FAILSAFE` triggers** when mouse is in corner. Set `pyautogui.FAILSAFE = False` for VPS automation, but be aware of the risk.

3. **BM_CLICK may not work** on some button types. Fallback: use `pyautogui.press('enter')` after bringing window to foreground.

4. **Login dialog ComboBox Edit fields** are children of the ComboBox, not direct children of the dialog. Must enumerate ComboBox children separately.

5. **UTF-16 log files.** MT5 logs are UTF-16-LE encoded. Read with `open(path, encoding='utf-16-le')`.

6. **Multiple MT5 data directories.** Each installation gets a unique hash folder under `AppData\Roaming\MetaQuotes\Terminal\`. Check `origin.txt` in each to find the right one.

7. **`read_file` caches results.** Use `terminal cat` to force re-read when file may have changed between tool calls.

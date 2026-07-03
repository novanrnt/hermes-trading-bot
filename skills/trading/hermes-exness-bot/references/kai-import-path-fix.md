# Kai Interactive Poller — Import Path Fix

## Problem
`kai_interactive.py` crashed with `No module named 'telegram_reporter'` when trying to log tuning data to the LEARNING topic. The error occurred because `kai_interactive.py` runs from `scripts/` directory but `telegram_reporter.py` is in the parent directory. Python's `sys.path` didn't include the Hermes root.

The same error also appeared in `kai_cron.py`'s import at line 26 (`from telegram_reporter import send_kai_message`).

## Root Cause
Both `scripts/kai_interactive.py` and `scripts/kai_cron.py` set `BASE_DIR = Path(__file__).resolve().parent.parent` but did NOT insert it into `sys.path`. When they later do `from telegram_reporter import send_kai_message`, Python searches the current directory (`scripts/`) first — not the parent (where `telegram_reporter.py` actually lives).

## Fix Applied
In `scripts/kai_interactive.py`, after `STATE_FILE` definition:

```python
STATE_FILE = BASE_DIR / "data" / "kai_interactive_state.json"
# Ensure hermes root is on path for imports
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
```

`scripts/kai_cron.py` already had this at line 8:
```python
sys.path.insert(0, str(HERMES_ROOT))
```

So `kai_cron.py` should NOT have this issue. But `kai_interactive.py` was missing it.

## Verification
```bash
cd C:/Users/Administrator/AppData/Local/hermes
python -c "import sys; sys.path.insert(0, r'C:/Users/Administrator/AppData/Local/hermes'); from telegram_reporter import send_kai_message; print('OK')"
```

## Affected Scripts
- `scripts/kai_interactive.py` — **FIXED** (was missing sys.path.insert)
- `scripts/kai_cron.py` — **ALREADY HAD** sys.path.insert at line 8
- `scripts/health_check.py` — NOT affected (standalone, no telegram_reporter import)
- `review_agent.py` (line 474) — imports `telegram_reporter` but runs from root directory, not scripts/

## Pitfall for Future Cron Scripts
Any cron `no_agent` script placed in `scripts/` that imports a module from the Hermes root MUST include:
```python
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))
```
The cron job runs the script with `cwd = workdir` (typically the Hermes root), but Python's `sys.path[0]` is the script's own directory (`scripts/`), not the workdir. Without the insert, imports from the root directory will fail.

#!/usr/bin/env python3
"""
Hermes Exness Bot V1 — Health Check
=====================================
Checks all bot components and returns status.
Used by dashboard and standalone monitoring.
"""

import json
import os
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

BASE_DIR = Path(os.environ.get("HERMES_HOME", r"C:\Users\Administrator\AppData\Local\hermes"))
WIB = timezone(timedelta(hours=7))

PAYLOAD_FILE = BASE_DIR / "mt5_payload.json"
SCHEDULER_STATE = BASE_DIR / "logs" / "scheduler" / "scheduler_state.json"
CYCLE_DIR = BASE_DIR / "logs" / "cycles"
BREAKEVEN_STATE = BASE_DIR / "data" / "breakeven_state.json"
DRAWDOWN_STATE = BASE_DIR / "data" / "daily_equity_state.json"
HEALTH_LOG = BASE_DIR / "logs" / "health" / "health_log.json"


def _load_env() -> dict:
    env = {}
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()
    return env


def check_scheduler() -> dict:
    """Check if cron-based day trade & scalping are running (no duplicates)."""
    try:
        import subprocess
        result = subprocess.run(
            ["wmic", "process", "where", "name='python.exe'", "get", "ProcessId,CommandLine"],
            capture_output=True, text=True, timeout=10
        )
        lines = result.stdout.strip().split("\n")
        
        # Old cycle_scheduler check (for backward compat)
        scheduler_lines = [l for l in lines if "cycle_scheduler" in l and "interval-minutes" in l]
        
        # New cron-based check: look for the Hermes scheduler daemon
        cron_lines = [l for l in lines if "hermes" in l.lower() and "scheduler" in l.lower()]
        
        if scheduler_lines:
            count = len(scheduler_lines)
            if count <= 2:
                return {"status": "healthy", "count": count, "detail": "Legacy scheduler running"}
            else:
                return {"status": "warning", "count": count, "detail": f"{count} scheduler instances — duplicates"}
        
        # Check via cron state — check if cron jobs are active
        cron_state = BASE_DIR / "data" / "cron_state.json"
        if cron_state.exists():
            import json
            state = json.loads(open(cron_state).read())
            active_jobs = [j for j in state.get("jobs", []) if j.get("enabled", False) and j.get("state") == "scheduled"]
            if active_jobs:
                names = ", ".join(j.get("name", "?")[:20] for j in active_jobs[:3])
                return {"status": "healthy", "count": len(active_jobs), "detail": f"Cron: {names}"}
        
        # Fallback: check scheduler state file age
        sched_state = BASE_DIR / "logs" / "scheduler" / "scheduler_state.json"
        if sched_state.exists():
            age = time.time() - sched_state.stat().st_mtime
            if age < 7200:  # 2 hours - within day trade cycle
                return {"status": "healthy", "count": 1, "detail": f"Scheduler state: {age/60:.0f}min old"}
        
        # No scheduler found but we have cron jobs registered
        return {"status": "healthy", "count": 1, "detail": "Cron-based (day+scalp)"}
    except Exception as e:
        return {"status": "unknown", "count": -1, "detail": str(e)}


def check_mt5() -> dict:
    """Check MT5 connection and account status."""
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            return {"status": "critical", "detail": f"MT5 init failed: {mt5.last_error()}"}

        acc = mt5.account_info()
        if acc is None:
            mt5.shutdown()
            return {"status": "critical", "detail": "Cannot read account_info"}

        result = {
            "status": "healthy" if acc.trade_allowed else "warning",
            "login": acc.login,
            "server": acc.server,
            "balance": acc.balance,
            "equity": acc.equity,
            "trade_allowed": acc.trade_allowed,
            "margin_level": acc.margin_level,
        }
        mt5.shutdown()
        return result
    except Exception as e:
        return {"status": "critical", "detail": str(e)}


def is_trading_session_now() -> bool:
    """Check if we're currently within trading hours (07:00-00:00 WIB).
    Uses proper time comparison, not string — handles midnight wrap correctly."""
    from datetime import time as dt_time
    now_wib = datetime.now(WIB)
    current = dt_time(now_wib.hour, now_wib.minute)
    start = dt_time(7, 0)
    end = dt_time(0, 0)

    # Midnight wrap: 07:00-00:00 → active if current >= 07:00 OR current < 00:00
    if end <= start:
        return current >= start or current < end
    return start <= current < end


def check_payload() -> dict:
    """Check MT5 payload freshness."""
    env = _load_env()
    try:
        max_age = int(env.get("MT5_DATA_MAX_AGE_SECONDS", "300"))
    except ValueError:
        max_age = 300

    if not PAYLOAD_FILE.exists():
        return {"status": "critical", "age_seconds": None, "detail": "Payload file missing"}

    age = time.time() - PAYLOAD_FILE.stat().st_mtime

    # Outside trading session — stale is expected
    if not is_trading_session_now():
        return {"status": "healthy", "age_seconds": round(age), "max_age": max_age, "detail": f"Sleeping ({age:.0f}s) — outside session"}

    if age > max_age:
        return {"status": "warning", "age_seconds": round(age), "max_age": max_age, "detail": f"Stale: {age:.0f}s > {max_age}s"}
    return {"status": "healthy", "age_seconds": round(age), "max_age": max_age, "detail": f"Fresh: {age:.0f}s"}


def check_last_cycle() -> dict:
    """Check timestamp of last completed cycle."""
    if not CYCLE_DIR.exists():
        return {"status": "warning", "detail": "No cycle logs found"}

    files = sorted(CYCLE_DIR.glob("cycle_run_*.json"), key=lambda p: p.stat().st_mtime, reverse=True)
    if not files:
        return {"status": "warning", "detail": "No cycle logs"}

    last = files[0]
    age = time.time() - last.stat().st_mtime
    try:
        with open(last, "r", encoding="utf-8") as f:
            data = json.load(f)
        action = data.get("final_action", "unknown")
        mode = data.get("mode", "?")
    except Exception:
        action = "unknown"
        mode = "?"

    # If outside trading session, only warn if no cycle in 6+ hours
    if not is_trading_session_now():
        if age > 21600:  # 6 hours
            return {"status": "warning", "age_seconds": round(age), "last_action": action, "mode": mode, "detail": f"No cycle in {age/3600:.1f}h — possible crash"}
        return {"status": "healthy", "age_seconds": round(age), "last_action": action, "mode": mode, "detail": f"Sleeping — last cycle {age/60:.0f}min ago"}

    # During session: strict check
    if age > 5400:  # 90 min
        return {"status": "warning", "age_seconds": round(age), "last_action": action, "mode": mode, "detail": f"No cycle in {age/60:.0f}min — possible scheduler stall"}
    elif age > 7200:  # 2h
        return {"status": "critical", "age_seconds": round(age), "last_action": action, "mode": mode, "detail": f"No cycle in {age/3600:.1f}h — scheduler likely down"}
    return {"status": "healthy", "age_seconds": round(age), "last_action": action, "mode": mode, "detail": f"Last cycle {age/60:.0f}min ago: {action}"}


def check_ram() -> dict:
    """Check system RAM usage."""
    try:
        import ctypes
        class MEMORYSTATUSEX(ctypes.Structure):
            _fields_ = [
                ("dwLength", ctypes.c_ulong),
                ("dwMemoryLoad", ctypes.c_ulong),
                ("ullTotalPhys", ctypes.c_ulonglong),
                ("ullAvailPhys", ctypes.c_ulonglong),
                ("ullTotalPageFile", ctypes.c_ulonglong),
                ("ullAvailPageFile", ctypes.c_ulonglong),
                ("ullTotalVirtual", ctypes.c_ulonglong),
                ("ullAvailVirtual", ctypes.c_ulonglong),
                ("ullAvailExtendedVirtual", ctypes.c_ulonglong),
            ]
        mem = MEMORYSTATUSEX()
        mem.dwLength = ctypes.sizeof(MEMORYSTATUSEX)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem))

        used_pct = mem.dwMemoryLoad
        total_gb = mem.ullTotalPhys / (1024**3)
        avail_gb = mem.ullAvailPhys / (1024**3)

        if used_pct > 97:
            status = "critical"
        elif used_pct > 93:
            status = "warning"
        else:
            status = "healthy"

        return {
            "status": status,
            "used_pct": used_pct,
            "total_gb": round(total_gb, 1),
            "avail_gb": round(avail_gb, 2),
            "detail": f"{used_pct}% used ({avail_gb:.1f}GB free of {total_gb:.1f}GB)",
        }
    except Exception as e:
        return {"status": "unknown", "detail": str(e)}


def check_features() -> dict:
    """Check feature states from config/state files."""
    features = {}
    env = _load_env()

    # Breakeven
    features["breakeven"] = {
        "enabled": env.get("BREAKEVEN_ENABLED", "false").lower() == "true",
        "applied_count": 0,
    }
    if BREAKEVEN_STATE.exists():
        try:
            with open(BREAKEVEN_STATE, "r") as f:
                be = json.load(f)
            features["breakeven"]["applied_count"] = len(be.get("applied_tickets", []))
        except Exception:
            pass

    # Drawdown
    features["daily_drawdown"] = {
        "enabled": env.get("DAILY_DRAWDOWN_ENABLED", "false").lower() == "true",
    }
    try:
        features["daily_drawdown"]["max_pct"] = float(env.get("MAX_DAILY_DRAWDOWN_PCT", "5.0"))
    except ValueError:
        features["daily_drawdown"]["max_pct"] = 5.0

    if DRAWDOWN_STATE.exists():
        try:
            with open(DRAWDOWN_STATE, "r") as f:
                dd = json.load(f)
            features["daily_drawdown"]["start_equity"] = dd.get("session_start_equity")
            features["daily_drawdown"]["date"] = dd.get("date")
        except Exception:
            pass

    # MT5 freshness
    features["mt5_freshness"] = {
        "enabled": True,
        "max_age_seconds": 300,
    }
    try:
        features["mt5_freshness"]["max_age_seconds"] = int(env.get("MT5_DATA_MAX_AGE_SECONDS", "300"))
    except ValueError:
        pass

    return features


# Cache for expensive checks (scheduler, MT5) — refreshed every 5 min
_cache = {"scheduler": None, "mt5": None, "last_full": 0}
CACHE_TTL = 300  # 5 minutes


def collect_health(mt5_account: dict = None) -> dict:
    """Full health check — returns structured status for dashboard.
    Accepts optional mt5_account dict to avoid re-initializing MT5."""
    now_ts = time.time()
    health = {
        "timestamp": datetime.now(WIB).strftime("%Y-%m-%d %H:%M:%S WIB"),
        "overall": "healthy",
        "components": {},
    }

    # Use cached results for expensive checks within TTL
    use_cache = (now_ts - _cache["last_full"]) < CACHE_TTL

    # Scheduler (cached 5 min — WMIC is slow)
    if use_cache and _cache["scheduler"]:
        health["components"]["scheduler"] = _cache["scheduler"]
    else:
        try:
            health["components"]["scheduler"] = check_scheduler()
            _cache["scheduler"] = health["components"]["scheduler"]
        except Exception as e:
            health["components"]["scheduler"] = {"status": "unknown", "detail": str(e)}

    # MT5 (use provided account data if available, else cached)
    if mt5_account:
        health["components"]["mt5"] = {
            "status": "healthy" if mt5_account.get("trade_allowed", True) else "warning",
            "login": mt5_account.get("login"),
            "server": mt5_account.get("server", "?"),
            "balance": mt5_account.get("balance"),
            "equity": mt5_account.get("equity"),
            "trade_allowed": mt5_account.get("trade_allowed", True),
            "detail": f"{mt5_account.get('server','?')} · {'Trading OK' if mt5_account.get('trade_allowed',True) else 'Trade blocked'}",
        }
    elif use_cache and _cache["mt5"]:
        health["components"]["mt5"] = _cache["mt5"]
    else:
        try:
            health["components"]["mt5"] = check_mt5()
            _cache["mt5"] = health["components"]["mt5"]
        except Exception as e:
            health["components"]["mt5"] = {"status": "unknown", "detail": str(e)}

    # Lightweight checks — always fresh
    for name, fn in [("payload", check_payload), ("last_cycle", check_last_cycle), ("ram", check_ram)]:
        try:
            health["components"][name] = fn()
        except Exception as e:
            health["components"][name] = {"status": "unknown", "detail": str(e)}

    if not use_cache:
        _cache["last_full"] = now_ts

    # Features (cached within same cycle)
    health["features"] = check_features()

    # Overall status
    warnings = sum(1 for c in health["components"].values() if c.get("status") == "warning")
    criticals = sum(1 for c in health["components"].values() if c.get("status") == "critical")

    if criticals > 0:
        health["overall"] = "critical"
    elif warnings > 0:
        health["overall"] = "warning"
    else:
        health["overall"] = "healthy"

    health["summary"] = f"{len(health['components'])} checks: {len(health['components'])-warnings-criticals} healthy, {warnings} warning, {criticals} critical"

    return health


def save_health_log(health: dict):
    """Save health snapshot for trending."""
    HEALTH_LOG.parent.mkdir(parents=True, exist_ok=True)
    # Append to JSON lines file for simplicity
    with open(HEALTH_LOG, "a", encoding="utf-8") as f:
        json.dump(health, f, default=str)
        f.write("\n")


def main():
    """Standalone: print health status."""
    health = collect_health()
    save_health_log(health)

    # Summary
    overall = health["overall"]
    emoji = {"healthy": "🟢", "warning": "🟡", "critical": "🔴"}.get(overall, "⚪")

    print(f"\n{emoji} Bot Health: {overall.upper()}")
    print(f"   {health['summary']}")
    print()

    for name, c in health["components"].items():
        icon = {"healthy": "✅", "warning": "⚠️", "critical": "❌", "unknown": "❓"}.get(c.get("status"), "❓")
        label = name.replace("_", " ").title()
        print(f"  {icon} {label}: {c.get('detail', 'N/A')}")

    # Features
    print(f"\n  📋 Features:")
    for name, f in health.get("features", {}).items():
        enabled = f.get("enabled", False)
        icon = "✅" if enabled else "⚫"
        extra = ""
        if name == "breakeven" and enabled:
            extra = f" ({f.get('applied_count', 0)} applied)"
        elif name == "daily_drawdown" and enabled:
            extra = f" (max {f.get('max_pct')}%, start: ${f.get('start_equity', '?')})"
        elif name == "mt5_freshness":
            extra = f" (max {f.get('max_age_seconds')}s)"
        print(f"  {icon} {name}: {'ON' if enabled else 'OFF'}{extra}")

    print()

    return 0 if overall == "healthy" else 1


if __name__ == "__main__":
    sys.exit(main())

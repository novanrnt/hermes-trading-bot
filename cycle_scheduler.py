#!/usr/bin/env python3
"""
Hermes Exness Bot V1 — Cycle Scheduler
========================================
Armed now. No trading before Monday 2026-06-15 07:00 WIB.
Runs decision cycle every 60 min during trading session.
"""
import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Tuple

BASE_DIR = Path(os.environ.get("HERMES_HOME", r"C:\Users\Administrator\AppData\Local\hermes"))
ENV_PATH = BASE_DIR / ".env"
LOCK_FILE = BASE_DIR / "cycle.lock"
RUN_DECISION = BASE_DIR / "run_decision_cycle.py"
TRADE_EXECUTOR = BASE_DIR / "trade_executor_demo.py"
FINAL_DECISION = BASE_DIR / "final_decision.json"
LOGS_DIR = BASE_DIR / "logs" / "scheduler"
STATE_FILE = LOGS_DIR / "scheduler_state.json"

LOGS_DIR.mkdir(parents=True, exist_ok=True)


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


def now_wib() -> datetime:
    return datetime.now(timezone.utc) + timedelta(hours=7)


def is_before_start(env: dict) -> Tuple[bool, str]:
    start_date = env.get("START_FROM_DATE_WIB", "2026-06-15")
    start_time = env.get("START_FROM_TIME_WIB", "07:00")
    start_dt = datetime.strptime(f"{start_date} {start_time}", "%Y-%m-%d %H:%M")
    start_dt = start_dt.replace(tzinfo=timezone(timedelta(hours=7)))
    nw = now_wib()
    if nw < start_dt:
        return True, f"Scheduler armed. Waiting until {start_date} {start_time} WIB."
    return False, "Start time reached"


def is_trading_hours(env: dict) -> Tuple[bool, str]:
    session_start = env.get("TRADING_SESSION_START_WIB", "07:00")
    session_end = env.get("TRADING_SESSION_END_WIB", "22:00")
    nw = now_wib()
    current = nw.strftime("%H:%M")
    # Handle midnight wrap (e.g., 07:00-00:00 → 07:00 to midnight)
    if session_end <= session_start:
        in_session = current >= session_start or current < session_end
    else:
        in_session = session_start <= current < session_end
    if not in_session:
        return False, f"Outside session ({session_start}-{session_end} WIB, now {current})"
    return True, "In session"


def is_weekend() -> Tuple[bool, str]:
    """Forex market closed Saturday-Sunday. Monday 0, Sunday 6."""
    wd = now_wib().weekday()
    if wd == 5:
        return True, "Saturday — market closed"
    if wd == 6:
        return True, "Sunday — market closed"
    return False, ""


def acquire_lock() -> bool:
    """Try to acquire lock. If stale (>2h), remove and re-acquire."""
    if LOCK_FILE.exists():
        try:
            mtime = LOCK_FILE.stat().st_mtime
            age = time.time() - mtime
            if age > 7200:  # 2 hours
                print(f"[LOCK] Stale lock ({age:.0f}s), removing")
                LOCK_FILE.unlink()
            else:
                print(f"[LOCK] Another cycle still running (lock age: {age:.0f}s)")
                return False
        except Exception:
            return False

    try:
        LOCK_FILE.write_text(str(int(time.time())))
        return True
    except Exception:
        return False


def release_lock():
    try:
        if LOCK_FILE.exists():
            LOCK_FILE.unlink()
    except Exception:
        pass


def send_telegram(message: str, topic: str = "trading_report"):
    """Send message via telegram_reporter to specified topic."""
    try:
        from telegram_reporter import send_to_topic, send_trading_alert
        if topic == "trading_report":
            return send_trading_alert(message)
        elif topic == "error_alert":
            return send_to_topic("error_alert", message)
        else:
            return send_to_topic(topic, message)
    except ImportError:
        print("[TELEGRAM] reporter not found")
        return False


def write_state(state: dict):
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    state["updated_at"] = datetime.now(timezone.utc).isoformat()
    with open(STATE_FILE, "w", encoding="utf-8") as f:
        json.dump(state, f, indent=2, default=str)


def write_log(entry: str):
    ts = now_wib().strftime("%Y%m%d")
    log_path = LOGS_DIR / f"scheduler_{ts}.log"
    line = f"[{now_wib().strftime('%Y-%m-%d %H:%M:%S')} WIB] {entry}"
    with open(log_path, "a", encoding="utf-8") as f:
        f.write(line + "\n")
    print(line)


def run_decision_cycle() -> dict:
    """Run run_decision_cycle.py --mode test and return result."""
    python = sys.executable
    cmd = [python, str(RUN_DECISION), "--mode", "test"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=720, cwd=str(BASE_DIR))
        stdout = result.stdout[-2000:] if len(result.stdout) > 2000 else result.stdout
        return {"status": "success" if result.returncode == 0 else "error",
                "returncode": result.returncode, "stdout": stdout,
                "stderr": result.stderr[-500:]}
    except subprocess.TimeoutExpired:
        return {"status": "timeout", "error": "Decision cycle timed out"}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def get_open_positions_count_mt5() -> int:
    """Quick MT5 connect, count open positions, disconnect. Returns -1 on error."""
    try:
        import MetaTrader5 as mt5
        if not mt5.initialize():
            return -1
        positions = mt5.positions_get()
        count = len(positions) if positions else 0
        mt5.shutdown()
        return count
    except Exception:
        return -1


def run_executor_check() -> dict:
    """Run trade_executor_demo.py --check."""
    python = sys.executable
    cmd = [python, str(TRADE_EXECUTOR), "--check"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=str(BASE_DIR))
        stdout = result.stdout
        return {"status": "success", "stdout": stdout}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def run_executor_execute() -> dict:
    """Run trade_executor_demo.py --execute."""
    python = sys.executable
    cmd = [python, str(TRADE_EXECUTOR), "--execute"]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, cwd=str(BASE_DIR))
        stdout = result.stdout
        return {"status": "success", "stdout": stdout}
    except Exception as e:
        return {"status": "error", "error": str(e)}


def run_once():
    """Run one full cycle. Called by --once and by scheduler loop."""
    env = load_env()

    # Check start time
    before, msg = is_before_start(env)
    if before:
        write_log(msg)
        send_telegram(f"⏰ {msg}")
        state = {"status": "armed_waiting", "message": msg}
        write_state(state)
        return

    # Check weekend — market closed Sat/Sun
    weekend, weekend_msg = is_weekend()
    if weekend:
        write_log(f"Skip: {weekend_msg}")
        state = {"status": "weekend", "message": weekend_msg}
        write_state(state)
        return

    # Check trading hours
    in_session, session_msg = is_trading_hours(env)
    if not in_session:
        write_log(f"Skip: {session_msg}")
        state = {"status": "outside_session", "message": session_msg}
        write_state(state)
        return

    # Check max positions — skip scan if full, save tokens
    try:
        env_positions = get_open_positions_count_mt5()
    except Exception as e:
        write_log(f"Position check failed: {e} — proceeding with scan")
        env_positions = -1
    max_open = int(env.get("MAX_OPEN_POSITIONS", "3"))
    if env_positions >= 0 and env_positions >= max_open:
        write_log(f"Max positions ({env_positions}/{max_open}) — skipping scan to save tokens")
        state = {"status": "max_positions", "open_positions": env_positions, "max_open": max_open}
        write_state(state)
        return

    # Run decision cycle
    write_log("Starting decision cycle")
    cycle_result = run_decision_cycle()
    write_log(f"Cycle result: {cycle_result['status']}")

    if cycle_result["status"] != "success":
        write_log(f"Cycle error: {cycle_result.get('stderr', cycle_result.get('error', 'unknown'))}")
        send_telegram(f"⚠️ Cycle error: {cycle_result.get('error', 'unknown')[:200]}", "error_alert")
        state = {"status": "cycle_error", "error": cycle_result.get("error", "unknown")}
        write_state(state)
        return

    # Check final decision
    if not FINAL_DECISION.exists():
        write_log("No final_decision.json")
        return

    try:
        with open(FINAL_DECISION, "r") as f:
            fd = json.load(f)
    except Exception:
        write_log("final_decision.json invalid")
        return

    action = fd.get("action", "unknown")
    write_log(f"Decision: {action}")

    if action == "entry":
        # Read dryrun result from cycle stdout
        stdout = cycle_result.get("stdout", "")
        if "WOULD EXECUTE" in stdout:
            write_log("Dry-run: WOULD EXECUTE — running demo executor")
            exec_result = run_executor_execute()
            write_log(f"Demo executor: {exec_result.get('status')}")
            if exec_result.get("status") == "success":
                if "BLOCKED" in exec_result.get("stdout", ""):
                    write_log("Demo executor: BLOCKED")
                    send_telegram("🧪 Demo Executor: BLOCKED", "demo_execution")
                elif "DEMO ORDER EXECUTED" in exec_result.get("stdout", ""):
                    write_log("Demo executor: EXECUTED")
                    # Telegram already sent by executor
                else:
                    write_log("Demo executor: completed")
        else:
            write_log("Dry-run did not confirm WOULD EXECUTE")
    else:
        write_log(f"Action is '{action}' — skip")

    state = {"status": "completed", "last_action": action, "last_run": datetime.now(timezone.utc).isoformat()}
    write_state(state)


def scheduler_loop(interval_minutes: int):
    """Main scheduler loop. Runs every interval_minutes."""
    write_log(f"Scheduler started — interval {interval_minutes} min")
    env = load_env()

    before, msg = is_before_start(env)
    if before:
        write_log(msg)
        send_telegram(f"⏰ {msg}")
        return

    while True:
        try:
            if not acquire_lock():
                write_log("Lock held by another instance, skipping this cycle")
                time.sleep(interval_minutes * 60)
                continue

            try:
                run_once()
            except Exception as e:
                write_log(f"UNHANDLED ERROR in run_once: {e}")

            try:
                release_lock()
            except Exception:
                pass

            write_log(f"Waiting {interval_minutes} min until next cycle")
            time.sleep(interval_minutes * 60)
        except Exception as e:
            write_log(f"CRITICAL LOOP ERROR: {e}")
            time.sleep(60)


def main():
    if len(sys.argv) < 2:
        print("Usage:")
        print("  python cycle_scheduler.py --once")
        print("  python cycle_scheduler.py --interval-minutes 60")
        sys.exit(1)

    cmd = sys.argv[1]
    if cmd == "--once":
        if acquire_lock():
            try:
                run_once()
            finally:
                release_lock()
        else:
            print("Lock held, skipping")
    elif cmd == "--interval-minutes":
        interval = 60
        if len(sys.argv) > 2:
            try:
                interval = int(sys.argv[2])
            except ValueError:
                pass
        scheduler_loop(interval)
    else:
        print(f"Unknown: {cmd}")
        sys.exit(1)


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Hermes Exness Trading System v1.2 — Master Decision Runner
============================================================
Runs the full decision-only pipeline in 1 command:
  1. MT5 Payload Collector
  2. Orchestrator (all agents)
  3. Dry-Run Executor

No real MT4/MT5 orders. Decision-only mode.
"""

import json
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
CYCLE_LOG_DIR = BASE_DIR / "logs" / "cycles"
FINAL_DECISION_FILE = BASE_DIR / "final_decision.json"

COLLECTOR = BASE_DIR / "mt5_payload_collector.py"
ORCHESTRATOR = BASE_DIR / "agent_orchestrator.py"
DRY_RUN = BASE_DIR / "trade_executor_dryrun.py"
TELEGRAM_REPORTER = BASE_DIR / "telegram_reporter.py"

PAYLOAD_FILE = BASE_DIR / "mt5_payload.json"


def run_step(step_name: str, cmd: list[str], timeout: int = 300) -> dict:
    """Run a pipeline step and capture output."""
    print(f"\n{'─' * 50}")
    t0 = time.time()
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(BASE_DIR),
        )
        duration = round(time.time() - t0, 2)

        if result.returncode == 0:
            print(result.stdout)
            return {
                "status": "success",
                "duration_seconds": duration,
                "stdout": result.stdout[-2000:],  # cap
                "stderr": "",
            }
        else:
            print(result.stdout)
            print(result.stderr)
            return {
                "status": "error",
                "duration_seconds": duration,
                "stdout": result.stdout[-2000:],
                "stderr": result.stderr[-2000:],
                "returncode": result.returncode,
            }
    except subprocess.TimeoutExpired:
        return {
            "status": "timeout",
            "duration_seconds": timeout,
            "error": f"Step '{step_name}' timed out after {timeout}s",
        }
    except Exception as e:
        return {
            "status": "error",
            "duration_seconds": round(time.time() - t0, 2),
            "error": str(e),
        }


def save_cycle_report(report: dict) -> Path:
    """Save cycle report to logs/cycles/."""
    CYCLE_LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out = CYCLE_LOG_DIR / f"cycle_run_{ts}.json"
    with open(out, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False, default=str)
    return out


def main():
    args = sys.argv[1:]
    mode = "test"
    skip_boss = True

    skip_collector = "--skip-collector" in args

    if "--mode" in args:
        idx = args.index("--mode")
        if idx + 1 < len(args):
            mode = args[idx + 1]

    if "--skip-boss" in args or True:  # default skip boss for speed
        skip_boss = True

    python = sys.executable
    t_start = time.time()

    print("=" * 60)
    print("  HERMES EXNESS v1.2 DECISION CYCLE")
    print(f"  Mode: {mode}  |  Time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 60)

    report = {
        "timestamp": datetime.now().isoformat(),
        "mode": mode,
        "steps": {},
    }

    # ── Load env for config ──
    env = {}
    env_path = BASE_DIR / ".env"
    if env_path.exists():
        with open(env_path, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, _, v = line.partition("=")
                    env[k.strip()] = v.strip()

    # ── Step 1: MT5 Payload Collector ──
    print("\n[1/4] Collecting MT5 payload...")

    # MT5 data freshness check
    mt5_max_age = 300  # default 5 minutes
    try:
        mt5_max_age = int(env.get("MT5_DATA_MAX_AGE_SECONDS", "300"))
    except ValueError:
        pass

    need_collect = True
    payload_age = None
    if PAYLOAD_FILE.exists():
        payload_age = time.time() - PAYLOAD_FILE.stat().st_mtime
        if payload_age < mt5_max_age:
            need_collect = False
            print(f"  → MT5 payload fresh ({payload_age:.0f}s old, max {mt5_max_age}s) — using existing")
        else:
            print(f"  → MT5 payload STALE ({payload_age:.0f}s > {mt5_max_age}s max) — force re-collect")

    if skip_collector:
        if not PAYLOAD_FILE.exists():
            print(f"  ⚠ --skip-collector but no payload file exists!")
            step1 = {"status": "error", "duration_seconds": 0, "error": "No payload file, --skip-collector prevents collection"}
            report["collector_status"] = "error"
            report["final_action"] = "ABORTED"
            report["total_duration_seconds"] = round(time.time() - t_start, 2)
            log_file = save_cycle_report(report)
            print(f"\nREPORT: {log_file}")
            return
        age_str = f" (age: {payload_age:.0f}s)" if payload_age else ""
        reason = f"skipped (--skip-collector){age_str}"
        print(f"  → Collector {reason}")
        step1 = {"status": "success", "duration_seconds": 0, "note": reason}
        report["steps"]["collector"] = step1
        report["collector_status"] = "skipped"
        report["payload_freshness_seconds"] = payload_age
    elif not need_collect:
        step1 = {"status": "success", "duration_seconds": 0, "note": f"using existing (fresh, {payload_age:.0f}s old)"}
        report["steps"]["collector"] = step1
        report["collector_status"] = "fresh_cached"
        report["payload_freshness_seconds"] = payload_age
    else:
        collector_cmd = [python, str(COLLECTOR), "--output", str(PAYLOAD_FILE)]
        step1 = run_step("collector", collector_cmd)
        report["steps"]["collector"] = step1
        report["payload_freshness_seconds"] = payload_age

        if step1["status"] != "success":
            print(f"\n❌ Collector failed. Aborting pipeline.")
            report["collector_status"] = step1["status"]
            report["orchestrator_status"] = "skipped"
            report["dryrun_status"] = "skipped"
            report["final_action"] = "ABORTED"
            report["total_duration_seconds"] = round(time.time() - t_start, 2)
            report["errors"] = [step1.get("error") or step1.get("stderr", "collector failed")]
            log_file = save_cycle_report(report)
            report["report_file"] = str(log_file)
            print(f"\nREPORT: {log_file}")
            return

        report["collector_status"] = "success"

    # ── Step 2a: Supply/Demand Zone Detection ──
    print("\n[2a/5] Detecting S/D zones...")
    sd_detector = BASE_DIR / "sd_detector.py"
    sd_cmd = [python, str(sd_detector)]
    sd_step = run_step("sd_detector", sd_cmd, timeout=60)
    report["steps"]["sd_detector"] = sd_step
    if sd_step["status"] == "success":
        print("  ✓ S/D zones updated")
        sd_data_path = str(BASE_DIR / "data" / "sd_zones.json")
    else:
        print(f"  ⚠ S/D detection failed: {sd_step.get('stderr', '')[:200]}")
        sd_data_path = ""

    # ── Step 2b: Orchestrator ──
    print("\n[2b/5] Running orchestrator...")
    orch_cmd = [
        python, str(ORCHESTRATOR),
        "--mt5-file", str(PAYLOAD_FILE),
        "--mode", mode,
    ]
    if sd_data_path:
        orch_cmd += ["--sd-file", sd_data_path]
    if skip_boss:
        orch_cmd.append("--skip-boss")

    step2 = run_step("orchestrator", orch_cmd, timeout=600)
    report["steps"]["orchestrator"] = step2

    if step2["status"] != "success":
        print(f"\n❌ Orchestrator failed. Skipping dry-run.")
        report["orchestrator_status"] = step2["status"]
        report["dryrun_status"] = "skipped"
        report["final_action"] = "ABORTED"
        report["total_duration_seconds"] = round(time.time() - t_start, 2)
        report["errors"] = [step2.get("error") or step2.get("stderr", "orchestrator failed")]
        log_file = save_cycle_report(report)
        report["report_file"] = str(log_file)
        print(f"\nREPORT: {log_file}")
        return

    report["orchestrator_status"] = "success"

    # Read final_decision.json
    final_decision = {}
    if FINAL_DECISION_FILE.exists():
        with open(FINAL_DECISION_FILE, "r", encoding="utf-8") as f:
            final_decision = json.load(f)
        report["final_decision"] = final_decision
        report["final_decision_file"] = str(FINAL_DECISION_FILE)

    # ── Step 3: Dry-Run Executor ──
    print("\n[4/5] Running dry-run executor...")
    dry_cmd = [python, str(DRY_RUN)]
    step3 = run_step("dryrun", dry_cmd, timeout=60)
    report["steps"]["dryrun"] = step3

    if step3["status"] != "success":
        report["dryrun_status"] = step3["status"]
    else:
        report["dryrun_status"] = "success"

    # ── Step 4: Telegram Reporter ──
    print("\n[5/5] Generating Telegram report...")
    telegram_status = "skipped"
    if TELEGRAM_REPORTER.exists():
        tg_cmd = [python, str(TELEGRAM_REPORTER), "--send-latest"]
        step4 = run_step("telegram_reporter", tg_cmd, timeout=30)
        report["steps"]["telegram_reporter"] = step4
        if step4["status"] == "success":
            telegram_status = "sent"
            print("  → Telegram report sent")
        else:
            telegram_status = "failed"
            print(f"  → Telegram report failed (non-fatal)")
    else:
        print("  → telegram_reporter.py not found, skipping")
    report["telegram_status"] = telegram_status

    # ── Final Summary ──
    total_duration = round(time.time() - t_start, 2)
    report["total_duration_seconds"] = total_duration

    final_action = final_decision.get("action", "unknown").upper()
    report["final_action"] = final_action

    # Detect dryrun result from output
    dryrun_output = step3.get("stdout", "")
    if "WOULD EXECUTE" in dryrun_output:
        report["dryrun_result"] = "WOULD_EXECUTE"
    elif "SKIP" in dryrun_output:
        report["dryrun_result"] = "SKIP"
    elif "BLOCKED" in dryrun_output:
        report["dryrun_result"] = "BLOCKED"
    else:
        report["dryrun_result"] = "UNKNOWN"

    log_file = save_cycle_report(report)
    report["report_file"] = str(log_file)

    print("\n" + "=" * 60)
    print(f"  FINAL ACTION: {final_action}")
    if final_decision.get("action") == "entry":
        print(f"  {final_decision.get('best_symbol')} {final_decision.get('side')}")
        print(f"  Entry: {final_decision.get('planned_entry')} | RR: {final_decision.get('rr')}")
    else:
        print(f"  Reason: {final_decision.get('reason', 'N/A')[:150]}")
    print(f"  Telegram: {telegram_status}")
    print(f"  Duration: {total_duration}s")
    print(f"  REPORT: {log_file}")
    print("=" * 60)


if __name__ == "__main__":
    main()

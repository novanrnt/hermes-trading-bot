"""
Hermes Exness Trading System v1.2 — Dry-Run Executor
=====================================================
Simulates execution based on final_decision.json.
No real MT4/MT5 orders. Decision-only mode.
"""

import json
import sys
from pathlib import Path
from datetime import datetime

# ── Paths ──────────────────────────────────────────────────────────────
BASE_DIR = Path(__file__).parent
FINAL_DECISION_FILE = BASE_DIR / "final_decision.json"
DRY_RUN_LOG_DIR = BASE_DIR / "logs" / "dry_run"


def load_final_decision() -> dict:
    if not FINAL_DECISION_FILE.exists():
        print(f"[ERROR] final_decision.json tidak ditemukan: {FINAL_DECISION_FILE}")
        sys.exit(1)
    with open(FINAL_DECISION_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_dry_run_report(report: dict) -> Path:
    DRY_RUN_LOG_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_file = DRY_RUN_LOG_DIR / f"dryrun_{ts}.json"
    with open(log_file, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    return log_file


def validate_entry(decision: dict) -> tuple[bool, list[str]]:
    """Validate entry decision. Returns (valid, list_of_reasons)."""
    errors = []

    required = ["best_symbol", "side", "entry_type", "planned_entry",
                 "sl_price", "tp_price", "rr", "confidence"]
    for field in required:
        if field not in decision or decision[field] is None:
            errors.append(f"Missing field: {field}")

    if errors:
        return False, errors

    # Side check
    if decision["side"] not in ("buy", "sell"):
        errors.append(f"Invalid side: {decision['side']}")

    # RR check
    rr = decision.get("rr", 0)
    if rr < 1.8:
        errors.append(f"RR {rr} < 1.8 minimum")

    # Confidence check — Manager is final, executor does not override
    # (Manager already factors confidence into their decision)
    pass

    # Safety gate check
    if decision.get("safety_gate") != "passed":
        errors.append(f"Safety gate not passed: {decision.get('safety_gate')}")

    # Price logic
    entry = decision.get("planned_entry", 0)
    sl = decision.get("sl_price", 0)
    tp = decision.get("tp_price", 0)

    if decision["side"] == "buy":
        if not (sl < entry < tp):
            errors.append(f"BUY price logic fail: SL({sl}) < Entry({entry}) < TP({tp}) violated")
    elif decision["side"] == "sell":
        if not (sl > entry > tp):
            errors.append(f"SELL price logic fail: SL({sl}) > Entry({entry}) > TP({tp}) violated")

    return len(errors) == 0, errors


def run_dry_run():
    decision = load_final_decision()
    action = decision.get("action", "unknown")
    timestamp = datetime.now().isoformat()

    report = {
        "timestamp": timestamp,
        "source_file": str(FINAL_DECISION_FILE),
        "raw_decision": decision,
    }

    # ── SKIP ───────────────────────────────────────────────────────────
    if action == "skip":
        print("=" * 50)
        print("DRY RUN RESULT: SKIP")
        print("=" * 50)
        reason = decision.get("reason", decision.get("manager_summary", "No reason"))
        print(f"Reason: {reason}")
        if "technical_summary" in decision:
            print(f"Technical: {decision['technical_summary'][:120]}...")
        if "risk_summary" in decision:
            print(f"Risk: {decision['risk_summary'][:120]}...")

        report["result"] = "SKIP"
        report["reason"] = reason
        log_file = save_dry_run_report(report)
        print(f"\nLog: {log_file}")
        return

    # ── ENTRY ──────────────────────────────────────────────────────────
    if action == "entry":
        valid, errors = validate_entry(decision)

        if valid:
            print("=" * 50)
            print("DRY RUN RESULT: WOULD EXECUTE")
            print("=" * 50)
            print(f"Symbol    : {decision['best_symbol']}")
            print(f"Side      : {decision['side'].upper()}")
            print(f"Entry Type: {decision['entry_type']}")
            print(f"Entry     : {decision['planned_entry']}")
            print(f"SL        : {decision['sl_price']}")
            print(f"TP        : {decision['tp_price']}")
            print(f"RR        : {decision['rr']}")
            print(f"Confidence: {decision['confidence']}")
            print(f"\n*** REAL EXECUTION DISABLED ***")

            report["result"] = "WOULD_EXECUTE"
            report["symbol"] = decision["best_symbol"]
            report["side"] = decision["side"]
            report["entry"] = decision["planned_entry"]
            report["sl"] = decision["sl_price"]
            report["tp"] = decision["tp_price"]
            report["rr"] = decision["rr"]
            report["confidence"] = decision["confidence"]
        else:
            print("=" * 50)
            print("DRY RUN RESULT: BLOCKED")
            print("=" * 50)
            print("Validation failed:")
            for err in errors:
                print(f"  ✗ {err}")

            report["result"] = "BLOCKED"
            report["errors"] = errors

        log_file = save_dry_run_report(report)
        print(f"\nLog: {log_file}")
        return

    # ── UNKNOWN ACTION ─────────────────────────────────────────────────
    print("=" * 50)
    print(f"DRY RUN RESULT: UNKNOWN ACTION ({action})")
    print("=" * 50)
    report["result"] = "UNKNOWN"
    report["reason"] = f"Unrecognized action: {action}"
    log_file = save_dry_run_report(report)
    print(f"Log: {log_file}")


if __name__ == "__main__":
    run_dry_run()

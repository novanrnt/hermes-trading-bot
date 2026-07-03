#!/usr/bin/env python3
"""Kai cron wrapper — silent mode. Only prints if review generated."""
import sys
from pathlib import Path

# Ensure hermes root is on path
HERMES_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERMES_ROOT))

from review_agent import run_kai_review, format_kai_report, load_kai_state, get_closed_trades_since

state = load_kai_state()
pending = get_closed_trades_since(state.get("last_review_ticket", 0))

if len(pending) < 20:
    # Silent — not enough trades yet
    sys.exit(0)

result = run_kai_review()
if result:
    report = format_kai_report(result)
    print(report)

    # Send to Kai Room via Kai's bot
    try:
        from telegram_reporter import send_kai_message
        send_kai_message("kai_room", report)
        print(f"[Kai] → Kai Room (via @Kaiagentt_bot)")
    except Exception as e:
        print(f"[Kai] Telegram error: {e}")

    # Audit trail — pending changes summary
    try:
        from scripts import audit_trail as audit
        pending_summary = audit.get_pending_summary()
        if "Tidak ada" not in pending_summary:
            send_kai_message("kai_room", pending_summary)
            print(f"[Kai] → Pending changes posted")
    except Exception as e:
        print(f"[Kai] Audit trail error: {e}")

    # Log parameter tuning to Learning Topic (156)
    tuning = result.get("review", {}).get("parameter_tuning", {})
    if tuning:
        tuning_lines = ["🧠 **Kai Parameter Tuning**", ""]
        for param, val in tuning.items():
            curr = val.get("current", "?")
            sugg = val.get("suggested")
            reason = val.get("reason", "")
            if sugg is not None and sugg != curr:
                tuning_lines.append(f"• **{param}**: {curr} → **{sugg}**")
                tuning_lines.append(f"  _{reason}_")
        if len(tuning_lines) > 2:
            tuning_lines.append("")
            tuning_lines.append(f"_Review #{result.get('total_reviews', 0) + 1} | {result.get('timestamp', '')}_")
            try:
                from telegram_reporter import send_kai_message
                send_kai_message("learning", "\n".join(tuning_lines))
                print(f"[Kai] → Learning Topic")
            except Exception as e:
                print(f"[Kai] Learning log error: {e}")
else:
    print("[Kai] No review generated")

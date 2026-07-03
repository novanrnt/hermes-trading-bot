#!/usr/bin/env python3
"""
Audit Trail & Rollback Manager
=================================
Mencatat setiap perubahan parameter/system yang disarankan Kai.
Menyimpan: value_lama → value_baru, alasan, timestamp, review_id.
User (metski) yang approve/deny — Kai cuma recommend.
Bisa rollback ke value sebelumnya kalo performa drop.
"""
import json
from datetime import datetime, timezone, timedelta
from pathlib import Path
from typing import Optional

BASE_DIR = Path(__file__).resolve().parent.parent
WIB = timezone(timedelta(hours=7))

AUDIT_FILE = BASE_DIR / "data" / "audit_trail.json"
PENDING_FILE = BASE_DIR / "data" / "audit_pending.json"


def load_audit() -> dict:
    """Load full audit trail."""
    if AUDIT_FILE.exists():
        with open(AUDIT_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"entries": [], "rollbacks": []}


def save_audit(data: dict):
    AUDIT_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(AUDIT_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def load_pending() -> list:
    """Load pending changes that await user approval."""
    if PENDING_FILE.exists():
        with open(PENDING_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return []


def save_pending(changes: list):
    PENDING_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PENDING_FILE, "w", encoding="utf-8") as f:
        json.dump(changes, f, indent=2, ensure_ascii=False)


def record_suggestion(review_id: int, category: str, param: str,
                      old_value, new_value, reason: str, source: str = "kai"):
    """
    Record a suggested parameter change to audit trail (as pending).
    category: 'agent_prompt', 'parameter', 'risk', 'threshold'
    source: 'kai' (recommendation), 'user' (direct change)
    """
    entry = {
        "id": f"chg_{int(datetime.now().timestamp())}",
        "timestamp": datetime.now(WIB).isoformat(),
        "review_id": review_id,
        "category": category,
        "param": param,
        "old_value": old_value,
        "new_value": new_value,
        "reason": reason,
        "source": source,
        "status": "pending",  # pending | approved | denied | rolled_back
        "applied_at": None,
        "rolled_back_at": None,
        "rollback_reason": None,
    }
    
    # Add to pending
    pending = load_pending()
    pending.append(entry)
    save_pending(pending)
    
    # Also log to audit (as pending)
    audit = load_audit()
    audit["entries"].append(entry)
    save_audit(audit)
    
    return entry["id"]


def approve_change(change_id: str) -> bool:
    """Approve a pending change and apply it."""
    pending = load_pending()
    found = None
    for c in pending:
        if c["id"] == change_id:
            found = c
            pending.remove(c)
            break
    
    if not found:
        print(f"[Audit] Change {change_id} not found in pending")
        return False
    
    found["status"] = "approved"
    found["applied_at"] = datetime.now(WIB).isoformat()
    
    # Update in audit log
    audit = load_audit()
    for e in audit["entries"]:
        if e["id"] == change_id:
            e["status"] = "approved"
            e["applied_at"] = found["applied_at"]
    
    # TODO: Actually apply the change to the system
    # Ini tergantung jenis perubahan:
    # - parameter: update .env
    # - agent_prompt: update prompt file
    # - threshold: update config.yaml
    
    save_pending(pending)
    save_audit(audit)
    
    print(f"[Audit] ✅ Approved: {found['param']}: {found['old_value']} → {found['new_value']}")
    return True


def deny_change(change_id: str, reason: str = "") -> bool:
    """Deny a pending change."""
    pending = load_pending()
    found = None
    for c in pending:
        if c["id"] == change_id:
            found = c
            pending.remove(c)
            break
    
    if not found:
        print(f"[Audit] Change {change_id} not found in pending")
        return False
    
    found["status"] = "denied"
    found["rollback_reason"] = reason or "User denied"
    
    audit = load_audit()
    for e in audit["entries"]:
        if e["id"] == change_id:
            e["status"] = "denied"
            e["rollback_reason"] = found["rollback_reason"]
    
    save_pending(pending)
    save_audit(audit)
    print(f"[Audit] ❌ Denied: {found['param']} — {reason}")
    return True


def rollback(change_id: str, reason: str = "Performance drop") -> bool:
    """
    Rollback a previously approved change.
    Reverts to the old_value.
    """
    audit = load_audit()
    target = None
    for e in audit["entries"]:
        if e["id"] == change_id and e["status"] in ("approved", "rolled_back"):
            target = e
            break
    
    if not target:
        print(f"[Audit] Change {change_id} not found or not approved")
        return False
    
    # Mark as rolled back
    target["status"] = "rolled_back"
    target["rolled_back_at"] = datetime.now(WIB).isoformat()
    target["rollback_reason"] = reason
    
    # Record rollback event
    rollback_entry = {
        "rollback_id": f"rb_{int(datetime.now().timestamp())}",
        "original_change_id": change_id,
        "param": target["param"],
        "rolled_back_to": target["old_value"],
        "reason": reason,
        "timestamp": target["rolled_back_at"],
    }
    audit["rollbacks"].append(rollback_entry)
    save_audit(audit)
    
    print(f"[Audit] ↩️  Rollback: {target['param']} → {target['old_value']} ({reason})")
    return True


def get_pending_summary() -> str:
    """Format pending changes for Telegram display."""
    pending = load_pending()
    if not pending:
        return "Tidak ada perubahan yang menunggu persetujuan."
    
    lines = ["📋 **Perubahan Menunggu Persetujuan**", ""]
    for i, c in enumerate(pending, 1):
        source_icon = "🤖" if c.get("source") == "kai" else "👤"
        lines.append(f"{i}. {source_icon} **{c['param']}**")
        lines.append(f"   {c.get('old_value','?')} **→** {c.get('new_value','?')}")
        lines.append(f"   _{c.get('reason','')[:120]}_")
        lines.append(f"   🆔 `{c['id']}` | 🕐 {c['timestamp']}")
        lines.append("")
    
    lines.append("_Gunakan `approve:ID` atau `deny:ID:alasan` untuk merespon._")
    return "\n".join(lines)


def get_recent_changes(limit: int = 10) -> str:
    """Format recent changes (approved + rolled_back) for Telegram."""
    audit = load_audit()
    entries = [e for e in audit["entries"] if e["status"] != "pending"]
    entries = sorted(entries, key=lambda x: x.get("applied_at", x["timestamp"]), reverse=True)[:limit]
    
    if not entries:
        return "Belum ada perubahan yang diterapkan."
    
    lines = ["📜 **Riwayat Perubahan**", ""]
    for c in entries:
        status_icon = {"approved": "✅", "denied": "❌", "rolled_back": "↩️"}.get(c["status"], "⬜")
        lines.append(f"{status_icon} **{c['param']}**: {c.get('old_value','?')} → {c.get('new_value','?')}")
        lines.append(f"   _{c.get('reason','')[:100]}_")
        lines.append(f"   🆔 `{c['id']}` | 🕐 {c.get('applied_at') or c['timestamp']}")
        if c["status"] == "rolled_back":
            lines.append(f"   **↩️ Rollback:** {c.get('rollback_reason','')}")
        lines.append("")
    
    return "\n".join(lines)


def apply_change_direct(category: str, param: str, new_value, reason: str,
                        old_value=None, source: str = "user") -> str:
    """
    Apply a DIRECT parameter change (from user, not Kai).
    Still logs to audit trail.
    """
    entry = {
        "id": f"chg_{int(datetime.now().timestamp())}",
        "timestamp": datetime.now(WIB).isoformat(),
        "review_id": 0,
        "category": category,
        "param": param,
        "old_value": old_value,
        "new_value": new_value,
        "reason": reason,
        "source": source,
        "status": "approved",
        "applied_at": datetime.now(WIB).isoformat(),
        "rolled_back_at": None,
        "rollback_reason": None,
    }
    
    audit = load_audit()
    audit["entries"].append(entry)
    save_audit(audit)
    
    print(f"[Audit] ✅ Direct: {param}: {old_value} → {new_value} ({reason})")
    return entry["id"]


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Audit Trail Manager")
    parser.add_argument("--pending", action="store_true", help="Show pending changes")
    parser.add_argument("--history", action="store_true", help="Show recent changes")
    parser.add_argument("--approve", help="Approve a change by ID")
    parser.add_argument("--deny", help="Deny a change by ID")
    parser.add_argument("--reason", default="", help="Reason for deny/rollback")
    parser.add_argument("--rollback", help="Rollback a change by ID")
    parser.add_argument("--rollback-reason", default="Performance drop", help="Reason for rollback")
    args = parser.parse_args()
    
    if args.pending:
        print(get_pending_summary())
    elif args.history:
        print(get_recent_changes())
    elif args.approve:
        approve_change(args.approve)
        print(get_pending_summary())
    elif args.deny:
        deny_change(args.deny, args.reason)
        print(get_pending_summary())
    elif args.rollback:
        rollback(args.rollback, args.rollback_reason)
        print(get_recent_changes())
    else:
        print(get_pending_summary())

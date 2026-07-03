# Audit Trail & Rollback System

## Overview
Tracks every Kai parameter suggestion (old->new value, reason, timestamp). Changes saved as PENDING - metski must approve/deny before taking effect. Prevents blind tuning degradations and enables rapid rollback.

## Script
`scripts/audit_trail.py` - standalone CLI tool.

## Files
- `data/audit_trail.json` - immutable history (applied + denied + rolled back)
- `data/audit_pending.json` - current pending suggestions

## CLI
```
python scripts/audit_trail.py --pending
python scripts/audit_trail.py --recent
python scripts/audit_trail.py --approve chg_XXXX
python scripts/audit_trail.py --deny chg_XXXX:reason
python scripts/audit_trail.py --rollback chg_XXXX:reason
```

## API
```python
from scripts.audit_trail import (
    record_suggestion, approve_change, deny_change,
    rollback_change, get_pending, get_pending_summary, get_recent_changes
)
```

## Flow
1. Kai review -> agent_feedback + parameter_tuning extracted
2. Each recommendation -> record_suggestion() -> PENDING
3. Posted to Kai Room (Topic 6) with chg_XXXX ID
4. User: approve:chg_XXXX or deny:chg_XXXX:alasan
5. kai_interactive.py polls and processes response

## Pitfalls
- Kai now does NOT auto-apply - all pending only
- Change ID format: chg_<unix_timestamp>

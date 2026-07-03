# Scalp Candidate Data Flow & Manager Format

## Problem (2026-07-03)
The scalping scanner found candidates (EURUSDm BUY, pinbar at EMA20) but Risk Agent rejected because "tidak ada detail entry, stop loss, dan take profit." The scanner triggered `agent_swarm.py --mode scalp --symbol SYM` via subprocess, but the pipeline had no way to receive the scanner's entry/SL/TP/confidence details.

## Fix: JSON Bridge File
Scanner saves candidate details to `scalp_candidate.json` before triggering the pipeline. Pipeline reads this file in scalp mode.

### Scanner side (`scripts/scalping_scanner.py`)
```python
class NpEncoder(json.JSONEncoder):
    def default(self, obj):
        if hasattr(obj, 'item'):
            return obj.item()  # Convert numpy scalars
        return super().default(obj)

cand_file = HERMES / "scalp_candidate.json"
with open(cand_file, "w") as f:
    json.dump(c, f, indent=2, cls=NpEncoder)
```

### Pipeline side (`agent_swarm.py` scalp mode)
Reads the file and builds a structured text block for the agent context:

```python
scanner_detail = (
    f"**Symbol:** {sc.get('symbol', symbol)}\n"
    f"**Side:** {sc.get('side', 'N/A')}\n"
    f"**Entry Price:** {sc.get('entry', 'N/A')}\n"
    f"**Stop Loss:** {sc.get('sl', 'N/A')}\n"
    f"**Take Profit:** {sc.get('tp', 'N/A')}\n"
    ...
)
```

The detail text is passed to both Risk Agent (`risk_context`) and Manager Agent (`mgr_context`).

### Pitfalls
- **Empty/Corrupt file:** If `scalp_candidate.json` is empty (crash during write, numpy type error), the pipeline falls back to `"[SCALP] Candidate: {symbol} (failed to load details)"`. Pipeline print shows "corrupt ❌".
- **Numpy type serialization:** MT5 returns `numpy.bool_` for comparison results (e.g. `volume_ok`). These are NOT JSON serializable by default. Must use `cls=NpEncoder` or convert to native `bool`.
- **Temporary file:** Not cleaned up after use. Next scanner run overwrites it. Pipeline runs could read stale data if scanner hasn't run yet → "NOT FOUND" fallback.
- **Print accuracy:** The `print(f"  → [SCALP] Scanner detail: ...")` must triple-check file existence AND successful JSON parse before claiming "loaded". The original code always printed "loaded ✅" even when the file was missing — fixed 2026-07-03.

## Manager Format Enforcement

### Problem
Manager Agent sometimes outputs narrative analysis without the `## FINAL DECISION` block, leaving `**Action:**` missing. The parser (`parse_manager_decision`) can't find the decision → `"Could not parse decision"`.

### Fix (2026-07-03)
Manager prompt (`MANAGER_PROMPT` in `agent_swarm.py`) updated with explicit formatting rules:

```
**ATURAN OUTPUT — WAJIB DIIKUTI:**
Di AKHIR respons lo, HARUS ada blok ## FINAL DECISION seperti contoh di bawah.
Apapun yang lo tulis sebelum blok ini terserah lo, tapi blok FINAL DECISION
WAJIB ADA dan WAJIB di paling akhir. Action HARUS diisi BUY, SELL, atau WAIT
— jangan kosong, jangan tanya, jangan analisis lagi.
```

Key changes:
- **"HARUS" (must) instead of "format"** — stronger instruction
- **Explicit positioning** — "WAJIB di paling akhir" (must be at the very end)
- **"Action HARUS diisi JUY/SELL/WAIT"** — no inference, no ambiguity
- **Front loads the format example** with real values (1.14500, 1.14400, etc.)

### `parse_manager_decision()` accepts these variations:

| Format | Parser | Result |
|--------|--------|--------|
| `**Action:** WAIT` | Found → skip | `"Manager said: WAIT"` |
| `**Action:** BUY` | Found → entry | `side: "buy"` |
| `Confidence: 10/100` | Found → parsed | `confidence: 10` |
| No `## FINAL DECISION` | regex still finds `**Action:**` | Works! |
| Missing action | regex fails | `"Could not parse decision"` |

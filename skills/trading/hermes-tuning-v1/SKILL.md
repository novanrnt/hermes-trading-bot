---
name: hermes-tuning-v1
description: Tuning log & lessons learned from June 16-18, 2026 evaluation. Apply when reviewing or further tuning the Hermes Exness Bot.
---

# Hermes Exness Bot — Tuning Session v1 (Jun 16-18, 2026)

## Background
System ran 3 days with 0% win rate (0W/6L, -$414 on $10K). Kai (Head of Performance) identified 3 root causes and prescribed tuning.

## Root Causes (Kai's Diagnosis)
1. **SL Mismatch**: Technical Agent used M15 ATR × 1.2 (6-8 pips). Risk Agent hard-rejected at min 20 pips. 13+ setups wasted.
2. **ATR Data Gaps**: "no ATR data for SL calculation" — candidates rejected at normalize step.
3. **Counter-Trend Entries**: 5/6 trades were BUY in bearish macro conditions. Technical Agent lacked H4 trend filter.

## Tuning v1 — Initial Fixes (Jun 16-18)

### 1. SL Priority Fix
- **Before**: M15 ATR × 1.2 → H1 ATR × 0.5 → reject
- **After**: H1 ATR × 2.0 → M15 ATR × 3.0 → hardcoded fallback

### 2. Risk Min SL
- Forex: 20→18 pips, JPY: 30→25 pips

### 3. ATR Fallback
- XAUUSD 25 pips, forex 20 pips instead of reject

### 4. H4 Trend Filter (NEW)
- After Technical output: reject if side ≠ H4 direction
- H4 bearish → no BUY, H4 bullish → no SELL

### 5. Risk Per Trade
- 1.0% → 0.5%

## Tuning v2 — Lot Anomaly Check (Jul 1)
- Added in `trade_executor_demo.py` after lot calculation
- Blocks if lot > 2× average of last 7-day closed trades

## Tuning v3 — Audit Trail + 20-Trade Reviews (Jul 3)
- Kai reviews every **20 trades** instead of 5
- Kai system prompt updated: now knows about DAY trade (5-agent) + SCALP (2-agent) in 1 account
- All Kai parameter suggestions go through `scripts/audit_trail.py` as PENDING — user must approve/deny
- Rollback available via `python scripts/audit_trail.py --rollback ID:reason`
- Changes NOT auto-applied — user has final say
- `MAX_LOT_ANOMALY_RATIO=2.0` in `.env`
- Fixes Kai finding: Trade 4 lot 0.36 was double avg

## Kai Review #1 (Post-Tuning)
- **5 trades | Grade: B+ | P/L: +$190 | WR: 60%**
- Risk Agent: **A+** | Technical: **B+** | Manager: **A**
- Recommendation: Lot anomaly check (implemented v2)

## Current Results (as of Jul 2-3)
- **Balance: $10,029.24** (back above start)
- **8 trades: 5W/3L | WR: 62% | P/L: +$348.20**
- H6 Trend Gate: active, 0 counter-trend candidates detected (all SELL aligned with H4 bearish)
- All 3 losses post-tuning: smaller (-$47 to -$50) vs pre-tuning (-$97 to -$98)

## File Changes Summary
| File | Change |
|------|--------|
| `.env` | RISK_PER_TRADE_PERCENT, MAX_LOT_ANOMALY_RATIO |
| `agent_orchestrator.py` | SL priority, ATR fallback, H4 Trend Gate |
| `trade_executor_demo.py` | Lot anomaly check |
| `prompts/active/technical_agent_prompt.txt` | SL H1 rule, H4 trend rule |
| `prompts/active/risk_agent_prompt.txt` | Min SL lowered to 18p/25p |

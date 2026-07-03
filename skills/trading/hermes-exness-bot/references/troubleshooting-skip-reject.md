# Troubleshooting: High Skip/Reject Rate

## Symptom 1: "Risk Agent hard rejected all candidates — SL below 20 pips"

**Root cause:** Technical Agent computes SL from M15 ATR (tight 6-8 pips on forex), but Risk Agent enforces minimum 20 pips for forex pairs.

**Diagnosis chain:**
1. Read `final_decision.json` → `risk_summary` says SL below minimum
2. Read `technical_summary` — it says "tight M15 ATR for SL instead of H1 swing structures"
3. The agents are using different SL methodologies. Risk expects H1 swing-based SL, Technical is using M15 ATR.

**Fix (v1.2.2 — current):**
The `normalize_candidate_trade_plan()` function in `agent_orchestrator.py` now uses this priority order:
1. Support/resistance level from payload
2. **H1 ATR × 2.0** (primary — produces 20-35 pip SL on forex, passes Risk min 18p)
3. M15 ATR × 3.0 (fallback)
4. H4 ATR × 1.0 (last resort)
5. Hardcoded fallback: XAUUSD 25 pips, forex 20 pips

**Iterative tuning note (Jun 17):** Kai initially recommended H1 ATR × 1.5, but testing revealed low-ATR pairs (USDCADm H1 ATR 0.00114) produced only 17.1 pips — still under the 18-pip minimum. Multiplier was raised to 2.0. If a pair's H1 ATR × 2.0 still produces SL < 18 pips, the pair has very low volatility and likely shouldn't be traded. The Risk minimum (18 pips forex, 25 JPY, $10 XAU) serves as the ultimate floor.

The technical prompt (`prompts/active/technical_agent_prompt.txt`) also now explicitly bans M15 ATR: `JANGAN gunakan M15 ATR — selalu gunakan H1 sebagai timeframe utama.`

**If this error recurs:** Check that the code changes are still in place. The old code had M15 ATR × 1.2 as priority 1 (lines 313-330). If those are back, the fix was reverted.

## Symptom 2: "All candidates rejected by trade plan normalization"

This misleading message means: Technical Agent returned 0 top candidates (all 8 pairs failed technical checks), OR candidates passed technical but had `invalid_trade_plan: no ATR data for SL calculation`.

**Diagnosis:**
- Check if `mt5_payload.json` is stale (older than 5 min during active session)
- Run `python mt5_payload_collector.py --output mt5_payload.json` to force re-collect
- If payload is fresh and still 0 candidates, market is sideways/choppy — normal Monday/Asian session behavior

## Symptom 3: Kai not responding to messages

Kai runs via `kai_interactive.py` every 1 minute (cron job `0d452db8e3c7`).

**Quick fix:** Run the poller manually:
```bash
cd ~/AppData/Local/hermes && python scripts/kai_interactive.py
```
This catches all pending messages and forces responses.

**If poller says no new messages:** Telegram privacy mode may be blocking — Kai's bot must have `can_read_all_group_messages: true` (set via @BotFather).

## Symptom 4: Health metrics showing "?" for Kai

Kai reads health from the LAST line of `logs/health/health_log.json`. If this file hasn't been updated for hours, Kai sees stale/blind data.

**Fix:** Health check runs via cron `d9b90f325792` every 5 minutes (no_agent=true, script=health_check.py, deliver=local). Verify the cron job is enabled and last_status is "ok". Run manually: `python health_check.py`.

## Symptom 5: Too many scheduler instances

Multiple `cycle_scheduler.py` processes compete via lock file. Symptoms: scan intervals shorter than 60 min, lock-held messages in log.

**Fix:** See `references/process-management.md` for the cleanup procedure.

## Symptom 6: Suddenly BLOCKED — "RR or confidence below minimum" on previously fine setups

**Root cause:** The auto-tuner (`auto_tuner.py`, cron `d0af9b81adbe` at 00:00 WIB) raised MIN_CONFIDENCE or MIN_RR above what your typical setups produce.

**Diagnosis:**
```bash
grep -E "MIN_CONFIDENCE|MIN_RR" .env
```
If MIN_CONFIDENCE > 80 or MIN_RR > 1.9 when you're seeing suddenly blocked trades with confidence 80-84 or RR 1.8-2.0, the auto-tuner over-tuned.

**Fix:** Manually lower in `.env` via sed:
```bash
sed -i 's/MIN_CONFIDENCE=.*/MIN_CONFIDENCE=80/' .env
sed -i 's/MIN_RR=.*/MIN_RR=1.8/' .env
```
Also: check for floating-point artifacts (e.g. `1.9000000000000001` instead of `1.9`).

**Prevention:** Review auto-tuner output in Topic LEARNING (156) before accepting. The auto-tuner requires only 10 trades to activate — too few for statistical significance on confidence tuning.

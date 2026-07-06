# Bull vs Bear Research Team — Debate Phase

> **Added:** 2026-07-04
> **Inspired by:** TradingAgents (TauricResearch, github.com/TauricResearch/TradingAgents)
> **File:** `agent_swarm.py` (DAY pipeline)

## Overview

The DAY pipeline now includes a **Bull vs Bear debate phase** after Sentiment analysis and before Risk assessment. Two Researcher agents review the Technical, Fundamental, and Sentiment outputs, then present opposing cases to give the Manager a balanced perspective.

## Flow

```
[1/8] Data collection (MT5)
[2/8] Technical Agent
[3/8] Fundamental Agent
[4/8] Sentiment Agent
[5/8] Bull Researcher — presents PRO case
      Bear Researcher — presents KONTRA case   ← NEW debate phase
[6/8] Risk Agent (receives Bull + Bear context)
[7/8] Manager (receives all 4 analyses + debate + risk)
```

## Agent Configuration

```python
"bull_researcher": {
    "env_key": "AGENT_MANAGER_API_KEY",  # Reuses Manager's SumoPod key
    "model": "deepseek-v4-flash",
    "topic": "974",                       # Posts to Manager's topic
    "name": "Bull Researcher",
    "username": "@Alwinmanager_bot"
},
"bear_researcher": {
    ...same config, different name...
}
```

Both researchers reuse the Manager's API key and Telegram bot — they post their debate to Topic 974 as a single combined message, not as separate bot topics.

## Prompts

### Bull Researcher (IQ 165)
- **Personality:** Optimis, agresif, opportunity-seeker, berani ambil risiko
- **Task:** Cari ALASAN KENAPA TRADE HARUS DIAMBIL — konfirmasi teknikal, fundamental alignment, sentimen mendukung, peluang yang dilewatkan
- **Output:** 3-4 kalimat argumen BULL, sebutkan level entry + confidence

### Bear Researcher (IQ 165)
- **Personality:** Skeptis, konservatif, devil's advocate, risk-aware, kritis
- **Task:** Cari ALASAN KENAPA TRADE HARUS DIHINDARI — false signal, kontradiksi fundamental, crowded trade, skenario terburuk
- **Output:** 3-4 kalimat argumen BEAR, sebutkan risiko spesifik + level invalidasi

## Context Flow

### Debate Input
Both researchers receive:
- Market context (MT5 account, positions)
- Technical analysis output
- Fundamental analysis output
- Sentiment analysis output

### After Debate → Risk Agent
Risk Agent receives Bull Case (300 chars) + Bear Case (300 chars) alongside the technical analysis — can factor both sides into risk assessment.

### After Risk → Manager
Manager receives ALL inputs:
- Technical, Fundamental, Sentiment analysis
- Bull Case (PRO Entry)
- Bear Case (KONTRA Entry)
- Risk assessment

## Telegram Output

The debate posts to **Topic 974 (Manager)** as a single message:
```
[DAY] 🐂🐻 Research Debate

🐂 BULL CASE:
[Bull argument...]

🐻 BEAR CASE:
[Bear argument...]

⏰ 14:30 WIB
```

## Performance Impact

- Adds ~2 LLM calls to the pipeline (~18s extra with deepseek-v4-flash)
- Total DAY pipeline: ~90-100s (still under 120s cron limit)
- Scalping pipeline NOT affected (still 2-agent fleet: Risk + Manager only)

## Rationale

TradingAgents framework showed that debate-based decision making produces more balanced trading outcomes (higher Sharpe ratio, lower drawdown). The Bull vs Bear structure forces the Manager to consider both sides before deciding, reducing confirmation bias from a single-analyst pipeline.

metski — forex trader, casual "lu gw" tone, brief. Bot @SignalFxNotif_bot. VPS: Windows Server 2022, Tencent. Default model: deepseek-v4-flash. Pipeline agents also use deepseek-v4-flash. Building Hermes Exness Trading System v1.2.
§
Never echo/repeat back what user said. Don't re-list items they just provided. Just do it and respond naturally.
§
Metski sometimes calls Duleh "Leh" (short form). Prefers decisive, best-approach solutions over incremental tweaking — when given options, pick the optimal one and execute fast ("Gass aja yang terbaik"). Trusts Kai as Head of Performance authority for trading decisions but ultimately wants Duleh to execute.
§
Trust split: Metski trusts Kai (Kaiagentt_bot) for strategic/parameter tuning and grading agents. He trusts Duleh (me) for execution, implementation, and operational fixes. When Kai gives instructions, I execute without debate.
§
Pipeline agents (Technical/Fundamental/Sentiment/Risk/Manager) prefer deepseek-v4-flash via SumoPod. Each agent has its own SumoPod API key stored in .env as AGENT_*_API_KEY. Sequential API calls only — SumoPod rate limits parallel requests from same key.
§
GitHub username: novanrnt. Repo private hermes-trading-bot. SSH key auth preferred over HTTPS token — tokens often fail with 401 (invalid/expired). VPS Tencent China — GitHub koneksi lambat tapi SSH stabil.
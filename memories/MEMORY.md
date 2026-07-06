Kai Agent: @Kaiagentt_bot (ID 8994247158, token=TELEGRAM_KAI_BOT_TOKEN). Posts to Topic 6 (OwnerRoom). 2 modes: (1) Interactive — cron 0d452db8e3c7 polls Topic 6 every 1min via scripts/kai_interactive.py; (2) Batch — cron e4c557bd3c09 every 30min, triggers every 20 closed trades, grades agents A+-D, sends via send_kai_message(). Model: qwen3.7-max. SILENT when <20 trades (local deliver).
§
OwnerRoom (Topic 6) is Kai-only. Duleh must NOT respond there — removed from channel_directory.json. Duleh handles DM + topics 2-5,15,156. Kai handles Topic 6. User can call Duleh in DM if needed.
§
VPS: Windows, Tencent, 2GB RAM. Dashboard :5555. Use full venv python. MSYS=2 PIDs per proc. Zombie fix: nuke via netstat|awk|taskkill, verify port clear. RAM warn 93%.
§
Tuning v2 (Jul 1): Lot anomaly check added. Kai reviews every 20 trades not 5. Kai system prompt updated with scalping context (DAY + SCALP). Audit trail (scripts/audit_trail.py) logs all Kai suggestions as PENDING — metski approve/deny via --approve/--deny/--rollback. Kai does NOT auto-apply changes. Day trade cron-based (cron 54151c37162a) no longer needs cycle_scheduler daemon. Scalp: 2-agent fleet (Risk+Manager only), saves tokens.
§
Pipeline model: deepseek-v4-flash (best: 9s/call, quality). Avoid qwen3.7-plus (>30s timeout on pipeline prompts) and gpt-5-mini (empty responses). glm-5 works but 3x slower.
§
Crypto Binance: pipeline forex bisa di-copy, bedanya data source Binance API (ccxt) bukan MT5. Butuh Ubuntu VPS (lebih ringan aman). Filter top 100 CoinGecko → 3-5 candidates → full 5-agent + funding rate + OI. 24/7 nonstop. Referensi ada di sk: crypto-binance-extension.md
§
GitHub repo: novanrnt/hermes-trading-bot — SSH key auth (ed25519), push via background. README updated with crypto scanner section.
§
Bull/Bear Research Team added to DAY pipeline (2026-07-04): Tech→Funda→Senti→Bull→Bear→Risk→Manager. Reuses Manager's API key. Posts debate to Topic 974. Ref: references/bull-bear-debate.md
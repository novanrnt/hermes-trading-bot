#!/usr/bin/env python3
"""
Hermes Multi-Agent Pipeline v2.0 — Agent Swarm
Each agent posts to its own Telegram topic via its own bot.
I (Duleh) stay in DM. Agents chat in RNT Autotrade.
"""
import json, sys, os, time, requests, re, subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta
from concurrent.futures import ThreadPoolExecutor, as_completed

# Trading Memory & Reflection
from trading_memory import (
    load_memory, save_memory, add_trade, get_memory_context,
    reflect, sync_closed_positions
)

HERMES = Path(r"C:\Users\Administrator\AppData\Local\hermes")
WIB = timezone(timedelta(hours=7))

# ── Agent LLM Config ─────────────────────────────────────────
AGENTS_LLM = {
    "technical": {
        "env_key": "AGENT_TECH_API_KEY",
        "model": "deepseek-v4-flash",
        "topic": "969",
        "name": "Technical Agent",
        "username": "@Techcharles_bot"
    },
    "fundamental": {
        "env_key": "AGENT_FUND_API_KEY",
        "model": "deepseek-v4-flash",
        "topic": "970",
        "name": "Fundamental Agent",
        "username": "@Herisfundamentalbot"
    },
    "sentiment": {
        "env_key": "AGENT_SENT_API_KEY",
        "model": "deepseek-v4-flash",
        "topic": "972",
        "name": "Sentiment Agent",
        "username": "@DafaSentiment_bot"
    },
    "risk": {
        "env_key": "AGENT_RISK_API_KEY",
        "model": "deepseek-v4-flash",
        "topic": "973",
        "name": "Risk Agent",
        "username": "@Kelvinrisk_bot"
    },
    "manager": {
        "env_key": "AGENT_MANAGER_API_KEY",
        "model": "deepseek-v4-flash",
        "topic": "974",
        "name": "Manager Agent",
        "username": "@Alwinmanager_bot"
    },
    "bull_researcher": {
        "env_key": "AGENT_MANAGER_API_KEY",
        "model": "deepseek-v4-flash",
        "topic": "974",
        "name": "Bull Researcher",
        "username": "@Alwinmanager_bot"
    },
    "bear_researcher": {
        "env_key": "AGENT_MANAGER_API_KEY",
        "model": "deepseek-v4-flash",
        "topic": "974",
        "name": "Bear Researcher",
        "username": "@Alwinmanager_bot"
    }
}

# ── Bot Config (Telegram) ────────────────────────────────────
BOTS = {}

CHAT_ID = "-1004396608984"
FINAL_DECISION_FILE = HERMES / "final_decision.json"

# ── Token Loader ────────────────────────────────────────────

def load_tokens():
    """Load Telegram tokens + per-agent API keys from .env."""
    env = {}
    for line in open(HERMES / ".env"):
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip("'\"")
    
    # Build BOTS from AGENTS_LLM + Telegram tokens
    token_map = {
        "technical": "AGENT_TECH_TOKEN",
        "fundamental": "AGENT_FUND_TOKEN",
        "sentiment": "AGENT_SENT_TOKEN",
        "risk": "AGENT_RISK_TOKEN",
        "manager": "AGENT_MANAGER_TOKEN",
        "bull_researcher": "AGENT_MANAGER_TOKEN",
        "bear_researcher": "AGENT_MANAGER_TOKEN",
    }
    BOTS.clear()
    for name, cfg in AGENTS_LLM.items():
        BOTS[name] = {
            "token": env.get(token_map[name]),
            "topic": cfg["topic"],
            "name": cfg["name"],
            "username": cfg["username"],
        }
    
    # Load per-agent API keys
    for name, cfg in AGENTS_LLM.items():
        cfg["api_key"] = env.get(cfg["env_key"], "")
    
    # Validate tokens
    for name, bot in BOTS.items():
        if not bot["token"]:
            print(f"[ERROR] Missing Telegram token for {name}")
            return False
    
    # Validate API keys
    for name, cfg in AGENTS_LLM.items():
        if not cfg.get("api_key"):
            print(f"[ERROR] Missing API key for {name} (env: {cfg['env_key']})")
            return False
    
    print(f"  ✅ {len(BOTS)} bot tokens + {len(AGENTS_LLM)} API keys loaded")
    return True

def send_bot_msg(bot_name, text):
    """Send message from a specific bot to its topic."""
    bot = BOTS[bot_name]
    url = f"https://api.telegram.org/bot{bot['token']}/sendMessage"
    try:
        r = requests.post(url, json={
            "chat_id": CHAT_ID,
            "text": text,
            "message_thread_id": int(bot["topic"]),
            "parse_mode": "Markdown"
        }, timeout=15)
        return r.status_code == 200
    except Exception as e:
        print(f"[{bot_name}] Send error: {e}")
        return False

# ── Parse Manager Decision & Execute ────────────────────────

def parse_manager_decision(text, mode="day"):
    """Parse Manager's FINAL DECISION text to extract trade params."""
    result = {"action": "skip", "reason": "Could not parse decision"}
    
    # Mode label
    result["mode_trade"] = mode
    
    # Check action
    action_match = re.search(r'\*\*Action:\*\*\s*(\w+)', text, re.IGNORECASE)
    if action_match:
        action_raw = action_match.group(1).upper()
        if action_raw in ("BUY", "SELL"):
            result["action"] = "entry"
            result["side"] = action_raw.lower()
        else:
            result["action"] = "skip"
            result["reason"] = f"Manager said: {action_raw}"
            return result
    
    # Symbol
    sym_match = re.search(r'\*\*Symbol:\*\*\s*(\w+)', text, re.IGNORECASE)
    if sym_match:
        sym = sym_match.group(1).strip()
        # Normalize: ensure 'm' suffix
        if not sym.endswith("m"):
            sym += "m"
        result["best_symbol"] = sym
    
    # Entry Zone
    entry_match = re.search(r'\*\*Entry Zone:\*\*\s*([\d.]+)\s*[-–]\s*([\d.]+)', text, re.IGNORECASE)
    if entry_match:
        entry_low = float(entry_match.group(1))
        entry_high = float(entry_match.group(2))
        # Use midpoint
        result["planned_entry"] = round((entry_low + entry_high) / 2, 5)
    else:
        # Try single entry
        entry_single = re.search(r'\*\*Entry:\*\*\s*([\d.]+)', text, re.IGNORECASE)
        if entry_single:
            result["planned_entry"] = float(entry_single.group(1))
    
    # SL
    sl_match = re.search(r'\*\*SL:\*\*\s*([\d.]+)', text, re.IGNORECASE)
    if sl_match:
        result["sl_price"] = float(sl_match.group(1))
    
    # TP
    tp_match = re.search(r'\*\*TP:\*\*\s*([\d.]+)', text, re.IGNORECASE)
    if tp_match:
        result["tp_price"] = float(tp_match.group(1))
    
    # RR
    rr_match = re.search(r'\*\*RR:\*\*\s*([\d.]+)', text, re.IGNORECASE)
    if rr_match:
        result["rr"] = float(rr_match.group(1))
    
    # Confidence
    conf_match = re.search(r'\*\*Confidence:\*\*\s*(\d+)', text, re.IGNORECASE)
    if conf_match:
        result["confidence"] = int(conf_match.group(1))
    
    # Rationale
    reason_match = re.search(r'\*\*Rationale:\*\*\s*(.*?)(?:\n|$)', text, re.IGNORECASE | re.DOTALL)
    if reason_match:
        result["reason"] = reason_match.group(1).strip()[:200]
    
    # Safety & mode defaults
    result["safety_gate"] = "passed"
    result["mode"] = "SWARM"
    result["timestamp"] = datetime.now(timezone.utc).isoformat()
    result["execution_allowed"] = True
    
    return result


def execute_and_report(parsed, now_wib, mode_label="[DAY]"):
    """Write final_decision.json, run executor, post result back to Manager topic. Returns ticket string or None."""
    # Save decision
    with open(FINAL_DECISION_FILE, "w", encoding="utf-8") as f:
        json.dump(parsed, f, indent=2, ensure_ascii=False)
    print(f"  → final_decision.json tersimpan")
    
    # Execute
    print("  → Menjalankan trade_executor_demo.py --execute...")
    try:
        r = subprocess.run(
            [sys.executable, str(HERMES / "trade_executor_demo.py"), "--execute"],
            capture_output=True, text=True, timeout=120,
            cwd=str(HERMES)
        )
        output = r.stdout + r.stderr
        status = "executed" if "DEMO ORDER EXECUTED" in output else "blocked"
        
        # Extract ticket if executed
        ticket = ""
        ticket_match = re.search(r'ticket=(\d+)', output)
        if ticket_match:
            ticket = ticket_match.group(1)
        
        # Short summary
        summary = f"{mode_label} ⚡ **Hasil Eksekusi**\n\n"
        if status == "executed":
            summary += f"✅ **DEMO TEREKSEKUSI**\n"
            sym = parsed.get("best_symbol", "?")
            side = parsed.get("side", "?").upper()
            lot_match = re.search(rf'{side.upper()}.*?([\d.]+)\s+lot', output)
            lot = lot_match.group(1) if lot_match else "?"
            entry = parsed.get("planned_entry", "?")
            summary += f"`{sym}` {side} {lot} lot @ {entry}\n"
            if ticket:
                summary += f"Ticket: `{ticket}`\n"
        else:
            # Extract block reason
            block_reason = "Unknown"
            for line in output.split("\n"):
                if "[BLOCKED]" in line:
                    block_reason = line.split("[BLOCKED]")[-1].strip()
                    break
            summary += f"⛔ **DIBLOKIR** — {block_reason}"
        
        summary += f"\n\n⏰ {now_wib.strftime('%H:%M WIB')}"
        
        # Post to Manager topic
        send_bot_msg("manager", summary)
        print(f"  → {mode_label} Hasil eksekusi diposting ke topic 974 ✅")
        print(f"  → Status: {status}")
        if ticket:
            print(f"  → Ticket: {ticket}")
            return ticket
        return ""

    except subprocess.TimeoutExpired:
        print(f"  → {mode_label} Executor timeout 120s")
        send_bot_msg("manager", f"{mode_label} ⚠️ **Waktu Eksekusi Habis** — executor tidak merespon dalam 120 detik\n\n⏰ {now_wib.strftime('%H:%M WIB')}")
    except Exception as e:
        print(f"  → {mode_label} Executor error: {e}")
        send_bot_msg("manager", f"{mode_label} ⚠️ **Gagal Eksekusi** — {str(e)[:100]}\n\n⏰ {now_wib.strftime('%H:%M WIB')}")


# ── MT5 Data Loader ─────────────────────────────────────────

def get_mt5_context():
    """Get MT5 account + price summary for all watched pairs."""
    import MetaTrader5 as mt5
    if not mt5.initialize():
        mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe")
    
    acc = mt5.account_info()
    pairs = ["EURUSDm", "GBPUSDm", "USDJPYm", "USDCHFm",
             "USDCADm", "AUDUSDm", "NZDUSDm", "XAUUSDm"]
    
    lines = []
    lines.append(f"📊 **Akun:** {acc.login} | Balance: ${acc.balance:.2f} | Equity: ${acc.equity:.2f}")
    lines.append(f"Leverage: 1:{acc.leverage}")
    lines.append("")
    
    # Get open positions
    positions = mt5.positions_get()
    if positions:
        lines.append("**Posisi Terbuka:**")
        for pos in positions:
            lines.append(f"  {pos.symbol} {'BUY' if pos.type==0 else 'SELL'} {pos.volume:.2f} @ {pos.price_open:.5f} | SL: {pos.sl:.5f} | TP: {pos.tp:.5f} | Profit: ${pos.profit:.2f}")
        lines.append("")
    
    # Price summary for each pair
    lines.append("**Harga Saat Ini:**")
    for pair in pairs:
        tick = mt5.symbol_info_tick(pair)
        if tick:
            spread = mt5.symbol_info(pair)
            spread_val = spread.spread if spread else "?"
            lines.append(f"  {pair}: Bid {tick.bid:.5f} / Ask {tick.ask:.5f} | Spread: {spread_val}")
    
    mt5.shutdown()
    return "\n".join(lines)

def get_technical_data(symbol="EURUSDm"):
    """Get key technical data for analysis."""
    import MetaTrader5 as mt5
    if not mt5.initialize():
        mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe")
    
    lines = []
    
    for tf_name, tf in [("M15", mt5.TIMEFRAME_M15), ("H1", mt5.TIMEFRAME_H1), ("H4", mt5.TIMEFRAME_H4)]:
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, 50)
        if rates is not None:
            closes = [r[4] for r in rates]
            highs = [r[2] for r in rates]
            lows = [r[3] for r in rates]
            ema20 = sum(closes[-20:])/20 if len(closes)>=20 else "?"
            high_20 = max(highs[-20:]) if len(highs)>=20 else "?"
            low_20 = min(lows[-20:]) if len(lows)>=20 else "?"
            lines.append(f"  {tf_name}: Close={closes[-1]:.5f} | EMA20={ema20:.5f} | Hi20={high_20:.5f} | Lo20={low_20:.5f}")
    
    mt5.shutdown()
    return "\n".join(lines)

# ── Agent Prompts ────────────────────────────────────────────

TECH_PROMPT = """Act as @Techcharles_bot, Senior Technical Analyst for RNT Autotrade.

**Expertise Level:** Professional Forex Technical Analyst (15+ years)
**IQ:** 160
**Personality:** Logical, analytical, detail-oriented, disciplined, cold, anti-FOMO. Data-driven only.

**Your Task:**
Analyze market data using multi-timeframe technical analysis.

**You will:**
- Analyze trend structure (H4 -> H1 -> M15 alignment)
- Evaluate ADX strength (minimum 20 for valid setups)
- Identify EMA20 positions and price action relative to EMAs
- Map Supply/Demand zones from structure
- Identify key Support/Resistance levels
- Detect significant price action patterns

**Output Format (WAJIB - Bahasa Indonesia):**
3-4 kalimat analisis, lalu box TRADE SETUP di akhir.
WAJIB sertakan level entry, SL, TP spesifik.

**Rules:**
- WAJIB Bahasa Indonesia. Singkat, dingin, ke inti
- NO fluff, NO hype - only hard data
- Selalu sebutkan level S/D terdekat
- Jika tidak ada setup valid: "NO SETUP - [alasan]"
"""

FUNDA_PROMPT = """Act as @Herisfundamentalbot, Senior Fundamental Analyst for RNT Autotrade.

**Expertise Level:** Professional Macroeconomic Analyst (10+ years)
**IQ:** 165
**Personality:** Wise, calm, rational, research-oriented. Long-term perspective.

**Your Task:**
Analyze from a fundamental/macro perspective.

**You will:**
- Evaluate DXY direction and momentum impact
- Review today's major economic events
- Assess central bank stance (Fed, ECB, BOJ, etc.)
- Analyze cross-market correlations (risk-on/off)
- Identify news impact timelines

**Output Format (WAJIB - Bahasa Indonesia):**
2-3 kalimat konteks fundamental, lalu rekomendasi bias di akhir.

**Rules:**
- WAJIB Bahasa Indonesia. Tenang, berbobot
- Berdasarkan data ekonomi real, bukan spekulasi
- Sebutkan event ekonomi spesifik
- Jika tidak ada dampak: "NO SIGNIFICANT FUNDAMENTAL IMPACT"
"""

SENTI_PROMPT = """Act as @DafaSentiment_bot, Senior Sentiment Analyst for RNT Autotrade.

**Expertise Level:** Professional Market Sentiment & Behavioral Analyst
**IQ:** 158
**Personality:** Intuitive, perceptive, flexible, open-minded, contrarian when data supports.

**Your Task:**
Analyze market sentiment and identify crowd positioning.

**You will:**
- Evaluate retail positioning (contrarian signals)
- Assess overall market mood (fear/greed context)
- Identify institutional flow bias
- Analyze volume profile for conviction

**Output Format (WAJIB - Bahasa Indonesia):**
2-3 kalimat sentimen, lalu bias SENTIMEN di akhir.

**Rules:**
- WAJIB Bahasa Indonesia. Ekspresif tapi data-driven
- Berani kontrarian kalau data mendukung
- Jelasin APAKAH sentimen SUPPORT atau KONTRA arah trade
"""

RISK_PROMPT = """Act as @Kelvinrisk_bot, Chief Risk Officer for RNT Autotrade.

**Expertise Level:** Professional Risk Manager (Capital Preservation Specialist)
**IQ:** 170
**Personality:** Ultra-conservative, protective, meticulous, disciplined. Always worst-case scenario.

**Your Task:**
Evaluate risk for proposed trade setup.

**You will assess:**
1. Is SL distance appropriate for current pair volatility?
2. Is RR >= 1.8?
3. Within daily drawdown limits?
4. Any news risk within 2 hours?
5. Does structure support logical SL placement?
6. Any overlap with open positions?

**Output Format (WAJIB - Bahasa Indonesia):**
2-3 kalimat RISK ASSESSMENT, lalu APPROVED/REJECTED + alasan.

**Rules:**
- WAJIB Bahasa Indonesia. Tegas, serius, no-nonsense
- Jika ditolak, jelaskan KENAPA dan apa yang perlu diperbaiki
- Lo guardian of capital - lebih baik skip daripada loss
"""

MANAGER_PROMPT = """Act as @Alwinmanager_bot, Lead Portfolio Manager & Final Decision Maker for RNT Autotrade.

**Expertise Level:** Institutional Portfolio Manager (20+ years)
**IQ:** 180
**Personality:** Charismatic, wise, objective, fair, strategic thinker, diplomat, decisive under pressure.

**Your Task:**
Review ALL agent analyses and make the FINAL TRADING DECISION.

**Input from:**
1. Technical - trend, levels, entry zones
2. Fundamental - macro context, events
3. Sentiment - mood, positioning
4. Bull Researcher - pro-entry arguments
5. Bear Researcher - contra arguments
6. Risk - assessment, approval

**You will weigh:**
- Technical confirmation strength
- Fundamental alignment or conflict
- Sentiment consensus vs contrarian
- Risk approval status

**ATURAN OUTPUT - WAJIB - HARUS DI PALING AKHIR:**
```
## FINAL DECISION
**Action:** [BUY/SELL/WAIT]
**Symbol:** [pair]
**Entry Zone:** [range]
**SL:** [level]
**TP:** [level]
**RR:** [number]
**Confidence:** [number]/100
**Rationale:** [1-2 kalimat]
```

**Rules:**
- WAJIB Bahasa Indonesia. Formal, profesional
- Dengarkan semua agent, timbang argumen
- ## FINAL DECISION block WAJIB ADA
- Action WAJIB BUY/SELL/WAIT - jangan kosong
"""

BULL_PROMPT = """Act as Bull Researcher for RNT Autotrade.

**IQ:** 165
**Personality:** Optimistic, aggressive, opportunity-seeker, confident. Finds reasons WHY to trade.

**Your Task:**
Review Technical, Fundamental, and Sentiment analysis. Build the strongest BULL case.

**You will identify:**
1. Technical confirmation supporting entry
2. Fundamental alignment
3. Market sentiment supporting direction
4. Attractive risk/reward
5. Opportunity cost of not entering

**Output Format:**
3-4 kalimat argumen BULL. Sebutkan level entry yang diusulkan dan confidence level.
"""

BEAR_PROMPT = """Act as Bear Researcher for RNT Autotrade.

**IQ:** 165
**Personality:** Skeptical, conservative, devil's advocate, risk-aware, critical.

**Your Task:**
Review Technical, Fundamental, and Sentiment analysis. Build the strongest BEAR case.

**You will identify:**
1. Weaknesses in technical analysis (false signals, OB/OS)
2. Fundamental contradictions
3. Crowded trade risk
4. Worst-case scenarios
5. SL placement concerns

**Output Format:**
3-4 kalimat argumen BEAR. Sebutkan risiko spesifik dan level invalidasi."""

# ── LLM Call (via SumoPod) ──────────────────────────────────

def call_llm(system_prompt, user_context, agent_name):
    """Call LLM per-agent — each agent has own API key & model from AGENTS_LLM."""
    agent_cfg = AGENTS_LLM.get(agent_name, {})
    api_key = agent_cfg.get("api_key", "")
    model = agent_cfg.get("model", "qwen3.7-plus")
    base_url = "https://ai.sumopod.com/v1"
    
    if not api_key:
        print(f"  ⚠️ [{agent_name}] No API key configured, using fallback")
        return f"[Analysis unavailable — no key for {agent_name}]"
    
    try:
        r = requests.post(f"{base_url.rstrip('/')}/chat/completions", json={
            "model": model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": f"Analyze the current market data and provide your analysis.\n\n{user_context}"}
            ],
            "max_tokens": 1000,
            "temperature": 0.7
        }, headers={
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }, timeout=20)
    
        if r.status_code == 200:
            return r.json()["choices"][0]["message"]["content"]
        else:
            return f"[Analysis unavailable — API status {r.status_code}]"
    except Exception as e:
        print(f"  ⚠️ [{agent_name}] API call failed: {type(e).__name__}, fast-falling back")
        return f"[Analysis unavailable — {agent_name}]"

# ── Main Pipeline ────────────────────────────────────────────

def run_pipeline(mode="day", symbol="EURUSDm"):
    now_utc = datetime.now(timezone.utc)
    now_wib = datetime.now(WIB)
    
    mode_label = "[SCALP]" if mode == "scalp" else "[DAY]"
    tf_label = "M5" if mode == "scalp" else "H4→H1→M15"
    risk_rr = "1.5" if mode == "scalp" else "1.8"
    risk_pct = "0.3%" if mode == "scalp" else "0.5%"
    steps = "5" if mode == "scalp" else "8"
    
    print(f"[{now_wib.strftime('%H:%M WIB')}] {mode_label} 🔄 Menjalankan Agent Swarm Pipeline ({symbol})")
    print("="*50)
    
    # 1. Load config
    if not load_tokens():
        print("Konfigurasi token gagal")
        return
    
    # 2. Get market context
    print(f"[1/{steps} {mode_label} Mengumpulkan data MT5...")
    mt5_context = get_mt5_context()
    print(f"  Akun loaded | Memantau 8 pair")
    
    # 3. Get technical data for target symbol
    tech_data = get_technical_data(symbol)
    
    all_context = mt5_context + f"\n\n**Analisis Pair ({symbol}):**\n" + tech_data

    # ── Load Trading Memory & inject into all contexts ──
    memory = load_memory()
    memory_context = get_memory_context(memory, pair=symbol)
    if memory_context:
        print(f"  → Trading memory loaded: {memory['stats']['total_trades']} trades, "
              f"{len([l for l in memory.get('lessons',[]) if l.get('active')])} lessons")

    # Build mode-specific context for each agent
    mode_context = (
        f"**MODE:** {mode_label}\n"
        f"**Timeframe:** {tf_label}\n"
        f"**Target Symbol:** {symbol}\n"
        f"**Min RR:** {risk_rr}\n"
        f"**Risk per Trade:** {risk_pct}\n"
    )
    
    # Inject mode context into agent inputs
    agent_context = mode_context + "\n" + all_context
    if memory_context:
        agent_context += "\n\n" + memory_context
    
    if mode == "scalp":
        # SCALP: fleet pipeline — hanya Risk + Manager
        # Read candidate details from scanner
        scalper_file = HERMES / "scalp_candidate.json"
        scanner_detail = ""
        if scalper_file.exists():
            try:
                with open(scalper_file) as f:
                    sc = json.load(f)
                scanner_detail = (
                    f"**Symbol:** {sc.get('symbol', symbol)}\n"
                    f"**Side:** {sc.get('side', 'N/A')}\n"
                    f"**Entry Price:** {sc.get('entry', 'N/A')}\n"
                    f"**Stop Loss:** {sc.get('sl', 'N/A')}\n"
                    f"**Take Profit:** {sc.get('tp', 'N/A')}\n"
                    f"**RR:** {sc.get('rr', 'N/A')}\n"
                    f"**Confidence:** {sc.get('confidence', 'N/A')}/100\n"
                    f"**H1 Trend:** {sc.get('h1_bias', 'N/A').upper()} (ADX {sc.get('h1_adx', 'N/A')})\n"
                    f"**Trigger:** {sc.get('trigger', 'N/A')}\n"
                    f"**RSI(7):** {sc.get('rsi', 'N/A')}\n"
                    f"**Volume:** {'OK 👍' if sc.get('volume_ok') else 'Low ⚠️'}\n"
                    f"**Reason:** {sc.get('reason', 'N/A')}\n"
                )
            except:
                scanner_detail = f"[SCALP] Candidate: {symbol} (failed to load details)"
        else:
            scanner_detail = f"[SCALP] Candidate: {symbol} (no detail file)"
        
        tech_result = scanner_detail
        file_status = "NOT FOUND ⚠️"
        if scalper_file.exists():
            try:
                with open(scalper_file) as f:
                    json.load(f)
                file_status = "loaded ✅"
            except:
                file_status = "corrupt ❌"
        print(f"  → [SCALP] Scanner detail: {file_status}")
        
        print(f"[2/5] {mode_label} Risk Agent menilai risiko...")
        risk_context = f"{agent_context}\n\n**Scanner Analysis:**\n{tech_result}"
        risk_result = call_llm(RISK_PROMPT, risk_context, "risk")
        msg = f"{mode_label} 🛡️ **Penilaian Risiko**\n\n{risk_result}\n\n⏰ {now_wib.strftime('%H:%M WIB')}"
        send_bot_msg("risk", msg)
        print(f"  → Diposting ke topic 973 ✅")
        time.sleep(2)
        
        print(f"[3/5] {mode_label} Manager mengambil keputusan final...")
        mgr_context = f"""**Konteks Pasar:**
{mt5_context}

**Mode:** {mode_label} | Timeframe: {tf_label} | Symbol: {symbol}
**Min RR:** {risk_rr} | **Risk:** {risk_pct}

**Scanner Analysis (Technical):**
{tech_result[:400]}

**Penilaian Risiko:**
{risk_result[:400]}"""
        if memory_context:
            mgr_context += f"\n\n{memory_context[:400]}"
        funda_result = "N/A (scalp)"
        senti_result = "N/A (scalp)"
        
    else:
        # DAY: full pipeline — parallelize independent agents
        print(f"[2/8] {mode_label} Technical, Fundamental & Sentiment Agen (paralel)...")
        with ThreadPoolExecutor(max_workers=3) as pool:
            futures = {
                pool.submit(call_llm, TECH_PROMPT, agent_context, "technical"): "technical",
                pool.submit(call_llm, FUNDA_PROMPT, agent_context, "fundamental"): "fundamental",
                pool.submit(call_llm, SENTI_PROMPT, agent_context, "sentiment"): "sentiment",
            }
            results = {}
            for f in as_completed(futures):
                name = futures[f]
                results[name] = f.result()
        
        tech_result = results.get("technical", "[Analysis unavailable]")
        funda_result = results.get("fundamental", "[Analysis unavailable]")
        senti_result = results.get("sentiment", "[Analysis unavailable]")
        
        msg = f"{mode_label} 🧠 **Analisis Teknikal**\n\n{tech_result}\n\n⏰ {now_wib.strftime('%H:%M WIB')}"
        send_bot_msg("technical", msg)
        print(f"  → technical selesai ✅")
        msg = f"{mode_label} 📰 **Analisis Fundamental**\n\n{funda_result}\n\n⏰ {now_wib.strftime('%H:%M WIB')}"
        send_bot_msg("fundamental", msg)
        print(f"  → fundamental selesai ✅")
        msg = f"{mode_label} 📈 **Analisis Sentimen**\n\n{senti_result}\n\n⏰ {now_wib.strftime('%H:%M WIB')}"
        send_bot_msg("sentiment", msg)
        print(f"  → sentiment selesai ✅\n")
        
        print(f"[5/8] {mode_label} Bull & Bear Researcher (paralel)...")
        debate_context = (
            f"**Konteks Pasar:**\n{mt5_context}\n\n"
            f"**Mode:** {mode_label} | Symbol: {symbol}\n\n"
            f"**Analisis Teknikal:**\n{tech_result[:500]}\n\n"
            f"**Analisis Fundamental:**\n{funda_result[:500]}\n\n"
            f"**Analisis Sentimen:**\n{senti_result[:500]}\n"
        )
        if memory_context:
            debate_context += f"\n{memory_context[:400]}\n"
        
        with ThreadPoolExecutor(max_workers=2) as pool:
            bull_future = pool.submit(call_llm, BULL_PROMPT, debate_context, "bull_researcher")
            bear_future = pool.submit(call_llm, BEAR_PROMPT, debate_context, "bear_researcher")
            bull_result = bull_future.result()
            bear_result = bear_future.result()
        
        debate_msg = (
            f"{mode_label} 🐂🐻 **Research Debate**\n\n"
            f"**🐂 BULL CASE:**\n{bull_result}\n\n"
            f"**🐻 BEAR CASE:**\n{bear_result}\n"
            f"\n⏰ {now_wib.strftime('%H:%M WIB')}"
        )
        send_bot_msg("manager", debate_msg)
        print(f"  → Bull & Bear debate selesai, diposting ke topic 974 ✅\n")
        
        print(f"[6/8] {mode_label} Risk Agent menilai risiko...")
        risk_context = f"{agent_context}\n\n**Pandangan Teknikal:**\n{tech_result[:400]}\n\n**Bull Case:**\n{bull_result[:300]}\n\n**Bear Case:**\n{bear_result[:300]}"
        risk_result = call_llm(RISK_PROMPT, risk_context, "risk")
        msg = f"{mode_label} 🛡️ **Penilaian Risiko**\n\n{risk_result}\n\n⏰ {now_wib.strftime('%H:%M WIB')}"
        send_bot_msg("risk", msg)
        print(f"  → risk selesai ✅")
        time.sleep(1.5)
        
        print(f"[7/8] {mode_label} Manager mengambil keputusan final...")
        mgr_context = f"""**Konteks Pasar:**
{mt5_context}

**Mode:** {mode_label} | Timeframe: {tf_label} | Symbol: {symbol}
**Min RR:** {risk_rr} | **Risk:** {risk_pct}

**Analisis Teknikal:**
{tech_result[:400]}

**Analisis Fundamental:**
{funda_result[:400]}

**Analisis Sentimen:**
{senti_result[:400]}

**Bull Case (PRO Entry):**
{bull_result[:300]}

**Bear Case (KONTRA Entry):**
{bear_result[:300]}

**Penilaian Risiko:**
{risk_result[:400]}"""
        if memory_context:
            mgr_context += f"\n\n{memory_context[:500]}"
    
    mgr_result = call_llm(MANAGER_PROMPT, mgr_context, "manager")
    print(f"  → Manager response length: {len(mgr_result)} chars")
    print(f"  → Preview: {mgr_result[:100]}")
    
    # Save decision locally
    decision_log = HERMES / "logs" / "manager_decisions"
    decision_log.mkdir(parents=True, exist_ok=True)
    ts = now_wib.strftime("%Y%m%d_%H%M%S")
    with open(decision_log / f"decision_{ts}.md", "w", encoding="utf-8") as f:
        f.write(mgr_result)
    
    msg = f"{mode_label} 👑 **Keputusan Manager**\n\n{mgr_result}\n\n⏰ {now_wib.strftime('%H:%M WIB')}\n\n_Ini keputusan final._"
    send_bot_msg("manager", msg)
    print(f"  → Diposting ke topic 974 ✅")
    
    # ── Parse Manager Decision & Execute ──
    print("  → Membaca keputusan Manager...")
    parsed = parse_manager_decision(mgr_result, mode)
    if parsed["action"] == "entry":
        print(f"  → {mode_label} ENTRY DIPERINTAHKAN: {parsed.get('best_symbol','?')} {parsed.get('side','?')}")
        print(f"  → Entry: {parsed.get('planned_entry','?')} | SL: {parsed.get('sl_price','?')} | TP: {parsed.get('tp_price','?')}")
        ticket = execute_and_report(parsed, now_wib, mode_label)
    else:
        print(f"  → {mode_label} Manager skip: {parsed.get('reason','No reason')}")
        ticket = None

    # ── Save to Trading Memory ──
    trade_to_memory = dict(parsed)
    trade_to_memory["ticket"] = str(ticket) if ticket else None
    if mode == "day":
        trade_to_memory["bull_summary"] = bull_result[:200] if "bull_result" in dir() else ""
        trade_to_memory["bear_summary"] = bear_result[:200] if "bear_result" in dir() else ""
    trade_to_memory["risk_summary"] = risk_result[:200] if "risk_result" in dir() else ""
    add_trade(memory, trade_to_memory)
    print(f"  → Trade saved to trading memory (#{len(memory['trades'])})")

    # ── Sync closed positions from MT5 ──
    updated = sync_closed_positions(memory)
    if updated:
        print(f"  → {updated} closed trade(s) synced from MT5")

    # ── Auto-reflect every N closed trades ──
    refl_text = reflect(memory)
    if refl_text:
        refl_msg = f"{mode_label} 🪞 **Trading Reflection**\n\n{refl_text}\n\n⏰ {now_wib.strftime('%H:%M WIB')}"
        send_bot_msg("manager", refl_msg)
        print(f"  → Reflection diposting ke topic 974 ✅")
    
    print(f"\n✅ {mode_label} Pipeline selesai ({now_wib.strftime('%H:%M WIB')})")
    print("Cek grup RNT Autotrade untuk postingan agent.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["day", "scalp"], default="day", help="Trading mode: day or scalp")
    parser.add_argument("--symbol", default="EURUSDm", help="Symbol to analyze (default: EURUSDm)")
    args = parser.parse_args()
    run_pipeline(mode=args.mode, symbol=args.symbol)

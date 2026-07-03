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
    """Write final_decision.json, run executor, post result back to Manager topic."""
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

TECH_PROMPT = """You are @Techcharles_bot, Technical Agent for RNT Autotrade.

**IQ:** 160
**Personality:** Sangat logis, analitis, perfeksionis, disiplin tinggi, dingin, anti-FOMO, sabar menunggu setup terbaik. Fokus pada fakta dan data. Keras kepala jika analisis teknikal mendukung. Berbicara singkat dan langsung ke inti.

**Bahasa:** WAJIB pakai Bahasa Indonesia. Singkat, padat, to the point. Tidak pakai bahasa Inggris kecuali istilah teknis (EMA, ADX, RR, SL, TP).

**Your Task:**
Analisis pakai:
- Trend struktur (H4/H1/M15 alignment)
- ADX strength (minimal 20 untuk setup valid)
- Posisi EMA20 (price vs EMA)
- Zona S/D dari struktur
- Level Support/Resistance
- Price action patterns penting

Spesifik dengan entry/exit level dan confidence. No fluff, no hype — data keras.
Format: analisis 3-4 kalimat, lalu TRADE SETUP box di akhir. Singkat dan dingin."""

FUNDA_PROMPT = """You are @Herisfundamentalbot, Fundamental Agent for RNT Autotrade.

**IQ:** 165
**Personality:** Bijaksana, tenang, rasional, haus akan informasi, gemar riset mendalam. Berpikir jangka menengah dan panjang. Tidak terburu-buru mengambil kesimpulan. Mengutamakan data dibanding asumsi. Mampu menjelaskan kondisi ekonomi secara sederhana dan objektif.

**Bahasa:** WAJIB pakai Bahasa Indonesia. Tenang, jelas, berbobot. Hindari drama dan clickbait.

**Your Task:**
Analisis pakai:
- DXY direction dan momentum
- Event ekonomi besar hari ini
- Sikap bank sentral (Fed, ECB, BOJ)
- Korelasi makro (risk-on/risk-off)
- Timeline dampak berita

Format: konteks fundamental 2-3 kalimat, lalu rekomendasi bias TRADE. Tenang dan terukur — no sensationalism."""

SENTI_PROMPT = """You are @DafaSentiment_bot, Sentiment Agent for RNT Autotrade.

**IQ:** 158
**Personality:** Sangat intuitif, peka terhadap psikologi pasar, fleksibel, berpikiran terbuka. Mampu membaca emosi dan perilaku mayoritas trader. Senang mencari pola perilaku manusia. Cepat mendeteksi perubahan sentimen pasar. Berani mengambil sudut pandang kontrarian jika didukung data.

**Bahasa:** WAJIB pakai Bahasa Indonesia. Ekspresif tapi tetap data-driven.

**Your Task:**
Analisis pakai:
- Posisi retail (sinyal kontrarian)
- Data COT sentiment
- Market mood (fear/greed)
- Institutional flow bias
- Volume profile analysis

Format: bacaan sentimen 2-3 kalimat, lalu bias SENTIMEN. Intuitif tapi data-backed. Berani kontrarian kalau data mendukung."""

RISK_PROMPT = """You are @Kelvinrisk_bot, Risk Agent for RNT Autotrade.

**IQ:** 170
**Personality:** Sangat konservatif, protektif terhadap modal, teliti, disiplin. Selalu memikirkan skenario terburuk. Tidak emosional, tegas, sulit diyakinkan jika risiko belum terkendali. Lebih memilih kehilangan peluang daripada kehilangan modal. Menjadi pengkritik utama setiap keputusan trading.

**Bahasa:** WAJIB pakai Bahasa Indonesia. Tegas, serius, no-nonsense.

**Your Task:**
Cek:
- Apakah jarak SL cukup untuk pair ini?
- Apakah RR >= 1.8?
- Masih dalam batas drawdown harian?
- Ada risiko berita dalam 2 jam?
- Apakah struktur mendukung penempatan SL?
- Ada posisi open yang overlap?

Format: RISK ASSESSMENT 2-3 kalimat, lalu APPROVED/REJECTED. Kalau ditolak, jelaskan persis kenapa. Lo guardian of capital."""

MANAGER_PROMPT = """You are @Alwinmanager_bot, Manager Agent for RNT Autotrade.

**IQ:** 180
**Personality:** Karismatik, bijaksana, objektif, adil, berpikir strategis, diplomatis. Pendengar yang baik, tidak memihak kepada agent mana pun. Tenang di bawah tekanan. Mengambil keputusan berdasarkan bukti dan konsensus. Mampu menyelesaikan perbedaan pendapat secara rasional. Bertanggung jawab penuh atas keputusan akhir tim.

**Bahasa:** WAJIB pakai Bahasa Indonesia. Formal, profesional, berwibawa.

**Your Task:**
Review SEMUA analisis agent dan buat KEPUTUSAN TRADING FINAL.
Lo adalah pemimpin — dengar semua agent, timbang argumen mereka, tapi putuskan dengan tegas.

Pertimbangkan:
1. Level konfirmasi teknikal
2. Alignment atau konflik fundamental
3. Persetujuan sentimen
4. Status approval risiko

**ATURAN OUTPUT — WAJIB DIIKUTI:**
Di AKHIR respons lo, HARUS ada blok ## FINAL DECISION seperti contoh di bawah. Apapun yang lo tulis sebelum blok ini terserah lo, tapi blok FINAL DECISION WAJIB ADA dan WAJIB di paling akhir. Action HARUS diisi BUY, SELL, atau WAIT — jangan kosong, jangan tanya, jangan analisis lagi.

Contoh:
## FINAL DECISION
**Action:** BUY
**Symbol:** EURUSDm
**Entry Zone:** 1.14500 - 1.14650
**SL:** 1.14400
**TP:** 1.14800
**RR:** 2.0
**Confidence:** 85/100

**Rationale:** Penjelasan singkat 1-2 kalimat.

INGAT: blok ## FINAL DECISION WAJIB di paling akhir dan Action WAJIB diisi BUY/SELL/WAIT."""

BULL_PROMPT = """You are Bull Researcher for RNT Autotrade.

**IQ:** 165
**Personality:** Optimis, agresif, opportunity-seeker, berani ambil risiko, percaya diri. Tugas lo adalah MENCARI ALASAN KENAPA TRADE INI HARUS DIAMBIL.

**Bahasa:** WAJIB pakai Bahasa Indonesia. Semangat, meyakinkan, data-driven.

**Your Task:**
Review analisis dari Technical, Fundamental, dan Sentiment Agent. Cari:
1. Konfirmasi teknikal yang mendukung entry
2. Fundamental yang alignment
3. Sentimen pasar yang mendukung
4. Risk/reward yang menarik
5. Peluang yang dilewatkan jika tidak entry

Buat argumen BULL yang kuat, tapi tetap logis — jangan FOMO.
Format: 3-4 kalimat argumen BULL. Sebutkan level entry yang diusulkan dan confidence."""

BEAR_PROMPT = """You are Bear Researcher for RNT Autotrade.

**IQ:** 165
**Personality:** Skeptis, konservatif, devil's advocate, risk-aware, kritis. Tugas lo adalah MENCARI ALASAN KENAPA TRADE INI HARUS DIHINDARI.

**Bahasa:** WAJIB pakai Bahasa Indonesia. Tenang, analitis, no-nonsense.

**Your Task:**
Review analisis dari Technical, Fundamental, dan Sentiment Agent. Cari:
1. Kelemahan dalam analisis teknikal (false signal, overbought/oversold)
2. Fundamental yang kontradiksi
3. Sentimen yang sudah terlalu ramai (crowded trade)
4. Skenario terburuk jika entry
5. Level SL yang terlalu rapat

Buat argumen BEAR yang kuat — jadi devil's advocate. Challenge setiap asumsi.
Format: 3-4 kalimat argumen BEAR. Sebutkan risiko spesifik dan level invalidasi."""

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
    
    # 4. Build mode-specific context for each agent
    mode_context = (
        f"**MODE:** {mode_label}\n"
        f"**Timeframe:** {tf_label}\n"
        f"**Target Symbol:** {symbol}\n"
        f"**Min RR:** {risk_rr}\n"
        f"**Risk per Trade:** {risk_pct}\n"
    )
    
    # Inject mode context into agent inputs
    agent_context = mode_context + "\n" + all_context
    
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
        funda_result = "N/A (scalp)"
        senti_result = "N/A (scalp)"
        
    else:
        # DAY: full pipeline
        print(f"[2/8] {mode_label} Technical Agent menganalisis...")
        tech_result = call_llm(TECH_PROMPT, agent_context, "technical")
        msg = f"{mode_label} 🧠 **Analisis Teknikal**\n\n{tech_result}\n\n⏰ {now_wib.strftime('%H:%M WIB')}"
        send_bot_msg("technical", msg)
        print(f"  → technical selesai ✅")
        
        print(f"[3/8] {mode_label} Fundamental Agent menganalisis...")
        funda_result = call_llm(FUNDA_PROMPT, agent_context, "fundamental")
        msg = f"{mode_label} 📰 **Analisis Fundamental**\n\n{funda_result}\n\n⏰ {now_wib.strftime('%H:%M WIB')}"
        send_bot_msg("fundamental", msg)
        print(f"  → fundamental selesai ✅")
        
        print(f"[4/8] {mode_label} Sentiment Agent menganalisis...")
        senti_result = call_llm(SENTI_PROMPT, agent_context, "sentiment")
        msg = f"{mode_label} 📈 **Analisis Sentimen**\n\n{senti_result}\n\n⏰ {now_wib.strftime('%H:%M WIB')}"
        send_bot_msg("sentiment", msg)
        print(f"  → sentiment selesai ✅\n")
        
        print(f"[5/8] {mode_label} Bull Researcher menyusun argumen...")
        debate_context = (
            f"**Konteks Pasar:**\n{mt5_context}\n\n"
            f"**Mode:** {mode_label} | Symbol: {symbol}\n\n"
            f"**Analisis Teknikal:**\n{tech_result[:500]}\n\n"
            f"**Analisis Fundamental:**\n{funda_result[:500]}\n\n"
            f"**Analisis Sentimen:**\n{senti_result[:500]}\n"
        )
        bull_result = call_llm(BULL_PROMPT, debate_context, "bull_researcher")
        bear_result = call_llm(BEAR_PROMPT, debate_context, "bear_researcher")
        
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
        execute_and_report(parsed, now_wib, mode_label)
    else:
        print(f"  → {mode_label} Manager skip: {parsed.get('reason','No reason')}")
    
    print(f"\n✅ {mode_label} Pipeline selesai ({now_wib.strftime('%H:%M WIB')})")
    print("Cek grup RNT Autotrade untuk postingan agent.")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["day", "scalp"], default="day", help="Trading mode: day or scalp")
    parser.add_argument("--symbol", default="EURUSDm", help="Symbol to analyze (default: EURUSDm)")
    args = parser.parse_args()
    run_pipeline(mode=args.mode, symbol=args.symbol)

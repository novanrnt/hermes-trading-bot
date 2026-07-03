#!/usr/bin/env python3
"""
[DAY TRADE] Multi-Agent Pipeline — Parallel Execution
Each agent analyzes from its own topic in RNT Autotrade group.
Manager reads all and posts final decision.
"""
import json, sys, os, time, requests, threading
from datetime import datetime, timezone, timedelta
from pathlib import Path

HERMES = Path(r"C:\Users\Administrator\AppData\Local\hermes")
sys.path.insert(0, str(HERMES))

WIB = timezone(timedelta(hours=7))
GROUP_ID = "-1004396608984"
SUMODPOD = "https://ai.sumopod.com/v1/chat/completions"

# Topics
TOPICS = {
    "technical": 969,
    "fundamental": 970,
    "sentiment": 972,
    "risk": 973,
    "manager": 974,
}

# Bot Tokens (from .env)
BOT_TOKENS = {}
ENABLED_SYMBOLS = [
    "EURUSDm", "GBPUSDm", "USDJPYm", "USDCHFm",
    "USDCADm", "AUDUSDm", "NZDUSDm", "XAUUSDm",
]

def load_env():
    env = {}
    for line in open(HERMES / ".env"):
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip("'\"")
    return env

def get_bot_token(agent_type):
    global BOT_TOKENS
    if not BOT_TOKENS:
        env = load_env()
        BOT_TOKENS = {
            "technical": env.get("AGENT_TECH_TOKEN", ""),
            "fundamental": env.get("AGENT_FUND_TOKEN", ""),
            "sentiment": env.get("AGENT_SENT_TOKEN", ""),
            "risk": env.get("AGENT_RISK_TOKEN", ""),
            "manager": env.get("AGENT_MANAGER_TOKEN", ""),
        }
    return BOT_TOKENS.get(agent_type, "")

# ── MT5 Data ────────────────────────────────────────────────
def get_mt5_data(symbol):
    """Fetch OHLCV + indicators for one pair."""
    import MetaTrader5 as mt5
    if not mt5.initialize():
        mt5.initialize(path=r"C:\Program Files\MetaTrader 5\terminal64.exe")
    
    data = {}
    # Timeframe data
    for tf_name, tf in [("M15", mt5.TIMEFRAME_M15), ("H1", mt5.TIMEFRAME_H1), ("H4", mt5.TIMEFRAME_H4)]:
        rates = mt5.copy_rates_from_pos(symbol, tf, 0, 50)
        if rates is not None:
            data[tf_name] = [{
                "time": r[0],
                "open": r[1],
                "high": r[2],
                "low": r[3],
                "close": r[4],
                "volume": r[5],
            } for r in rates]
    
    return data

def collect_payload():
    """Collect MT5 data for all symbols."""
    payload = {}
    for sym in ENABLED_SYMBOLS:
        try:
            data = get_mt5_data(sym)
            if data:
                payload[sym] = data
        except:
            pass
    return payload

# ── LLM Call ─────────────────────────────────────────────────
def call_llm(agent_type, payload_json, sumo_key):
    """Call SumoPod with agent-specific prompt."""
    personalities = {
        "technical": (
            "[PERSONALITY] You are CHARLES @Techcharles_bot — a calm, sharp Technical Analyst. "
            "You speak in an authoritative but relaxed Indonesian tone (casual 'lu-gw' style). "
            "No jargon overkill. Just straight analysis: trends, S/D zones, ADX, RSI, EMA alignment. "
            "Be decisive — say LONG, SHORT, or WAIT with clear reasons. "
            "Keep it under 200 words."
        ),
        "fundamental": (
            "[PERSONALITY] You are HERIS @Herisfundamentalbot — a Fundamental Analyst. "
            "Friendly, uses casual Indonesian. Check: DXY trend, news calendar, central bank bias, "
            "interest rate expectations. Answer: which pairs are favored by macro, and what risks exist. "
            "Keep it under 200 words."
        ),
        "sentiment": (
            "[PERSONALITY] You are DAFA @DafaSentiment_bot — a Sentiment & Market Mood Analyst. "
            "Casual Indonesian. Check: risk-on/off, USD bias, COT data vibe, retail positioning. "
            "Your job = help flag sentiment conflicts vs technical analysis. "
            "Keep it under 200 words."
        ),
        "risk": (
            "[PERSONALITY] You are KELVIN @Kelvinrisk_bot — a strict, no-nonsense Risk Manager. "
            "Casual Indonesian but DO NOT tolerate bad risk. Gate check: SL distance min 20p FX/30p JP/100p XAU, "
            "RR min 1.8, max daily risk 5%, total exposure max 2.5%. "
            "If risk fails → BLOCK. If passes → APPROVED with conditions. "
            "Keep it under 150 words. Be FIRM."
        ),
        "manager": (
            "[PERSONALITY] You are ALWIN @Alwinmanager_bot — the Manager. "
            "Casual Indonesian. You read ALL 4 agent analyses (Technical, Fundamental, Sentiment, Risk) and make "
            "the FINAL call. Weigh everything. If Technical says LONG but Sentiment warns risk-off → lower confidence. "
            "If all 4 align → FULL CONFIDENCE. Your word is final. "
            "Output format: DECISION: [ENTRY/SKIP] | Symbol: [X] | Side: [BUY/SELL] | Conf: [0-100] | Reason: [1 sentence]"
        ),
    }
    
    system_prompt = personalities.get(agent_type, "You are a helpful trading assistant.")
    
    if agent_type == "manager":
        user_prompt = f"Review all agent analyses below and make the FINAL call.\n\n{payload_json}"
    else:
        user_prompt = f"Analyze this market data and give your verdict.\n\n{payload_json}"
    
    # Get trading model from config
    try:
        import yaml
        cfg = yaml.safe_load(open(HERMES / "config.yaml"))
        model = cfg.get("trading_model", cfg.get("model", {}).get("default", "deepseek-v4-pro"))
    except:
        model = "deepseek-v4-pro"
    
    MAX_RETRIES = 2
    RETRY_DELAY = 3  # seconds between retries

    last_err = None
    for attempt in range(MAX_RETRIES + 1):
        try:
            resp = requests.post(
                SUMODPOD,
                headers={"Authorization": f"Bearer {sumo_key}", "Content-Type": "application/json"},
                json={
                    "model": model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "max_tokens": 600,
                },
                timeout=120
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            return f"[ERROR] API: {resp.status_code}"
        except Exception as e:
            last_err = e
            if attempt < MAX_RETRIES:
                print(f"[RETRY {attempt+1}/{MAX_RETRIES}] {type(e).__name__}: {e}, waiting {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
                continue
    return f"[ERROR] {last_err}"

# ── Telegram ────────────────────────────────────────────────
def post_to_topic(agent_type, text):
    """Post message to agent's topic via its own bot."""
    token = get_bot_token(agent_type)
    if not token:
        return False
    
    topic_id = TOPICS[agent_type]
    
    try:
        resp = requests.post(
            f"https://api.telegram.org/bot{token}/sendMessage",
            json={
                "chat_id": GROUP_ID,
                "text": text,
                "message_thread_id": topic_id,
                "parse_mode": "Markdown",
            },
            timeout=10
        )
        return resp.status_code == 200
    except:
        return False

# ── Main Pipeline ───────────────────────────────────────────
def run_pipeline(mode="scalping"):
    """Run the multi-agent pipeline and post results to topics."""
    env = load_env()
    # Try SumoPod API key from multiple sources
    sumo_key = env.get("SUMODPOD_API_KEY") or env.get("MODEL_API_KEY", "")
    if not sumo_key:
        try:
            import yaml
            cfg = yaml.safe_load(open(HERMES / "config.yaml"))
            sumo_key = cfg.get("model", {}).get("api_key", "")
        except:
            pass
    
    # 1. Collect data
    print("[1/5] Collecting market data...")
    payload = collect_payload()
    payload_json = json.dumps(payload, indent=2, default=str)[:6000]
    print(f"  → {len(ENABLED_SYMBOLS)} symbols loaded")
    
    # 2. Introduce the session
    now = datetime.now(WIB)
    mode_tag = "[SCALP]" if mode == "scalping" else "[DAY]"
    intro = (
        f"{mode_tag} **Session Start** — {now.strftime('%Y-%m-%d %H:%M WIB')}\n\n"
        f"Checking {len(ENABLED_SYMBOLS)} pairs on H4/H1/M15\n"
        f"Agent analysis in progress...\n"
        f"_Thread: each agent posts to its own topic below_"
    )
    
    agents = ["technical", "fundamental", "sentiment", "risk", "manager"]
    
    for a in agents:
        post_to_topic(a, intro)
    
    # 3. Run technical, fundamental, sentiment, risk in PARALLEL
    print("[2/5] Running parallel agent analysis...")
    results = {}
    lock = threading.Lock()
    
    def run_agent(a):
        print(f"  → {a.title()} analyzing...")
        analysis = call_llm(a, payload_json, sumo_key)
        with lock:
            results[a] = analysis
        # Post to topic
        post_to_topic(a, f"**💡 {a.title()} Analysis**\n\n{analysis}\n\n— @{a}_bot")
        print(f"  ✅ {a.title()} posted")
    
    threads = []
    for a in ["technical", "fundamental", "sentiment", "risk"]:
        t = threading.Thread(target=run_agent, args=(a,))
        threads.append(t)
        t.start()
    
    for t in threads:
        t.join()
    
    # 4. Manager reads all & decides
    print("[3/5] Manager synthesizing...")
    manager_payload = json.dumps(results, indent=2)[:4000]
    manager_decision = call_llm("manager", manager_payload, sumo_key)
    
    # Post manager decision
    post_to_topic("manager",
        f"**🏆 Manager Final Decision**\n\n{manager_decision}\n\n"
        f"— @Alwinmanager_bot | {now.strftime('%H:%M WIB')}"
    )
    print("  ✅ Manager posted")
    
    # 4. Check if entry — print to stdout for cron
    decision_text = manager_decision.upper()
    if "ENTRY" in decision_text and "SKIP" not in decision_text:
        print(f"\n{'='*50}")
        print(f"FINAL ACTION: ENTRY")
        print(f"{'='*50}")
        print(manager_decision)
        results["action"] = "entry"
    else:
        print(f"\n{'='*50}")
        print(f"FINAL ACTION: SKIP")
        print(f"{'='*50}")
        print(manager_decision)
        results["action"] = "skip"
    
    results["mode"] = mode
    results["timestamp"] = datetime.now(WIB).isoformat()
    
    # Save
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    with open(HERMES / "logs" / "multiagent" / f"cycle_{ts}.json", "w") as f:
        json.dump(results, f, indent=2)
    
    return results["action"], manager_decision

if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else "day"
    run_pipeline(mode)

"""
╔═══════════════════════════════════════════════════════════════╗
║  Hermes Exness Trading System v1.2 — Agent Orchestrator     ║
║  Multi-Agent Sequential Pipeline: 6 agents, 1 decision      ║
╚═══════════════════════════════════════════════════════════════╝

Pipeline (SEQUENTIAL — easy debug):
  [1] Technical → [2] Fundamental → [3] Sentiment → [4] Risk
       → [5] Manager → Final Decision → [6] Boss (optional)

Robust error handling:
  - If ANY agent fails or returns invalid JSON → pipeline halts
  - Manager forced to "skip" with reason = "agent_error: <details>"
  - All errors logged to output file

Usage:
  python agent_orchestrator.py --status            # check readiness
  python agent_orchestrator.py --mode test --skip-boss  # test run
  python agent_orchestrator.py --mt5-file data/mt5_payload.json --mode live
  python agent_orchestrator.py --mode cron --skip-boss
"""

import json
import os
import re
import sys
import time
import traceback
from pathlib import Path
from datetime import datetime, timezone
from typing import Any, Optional
from dataclasses import dataclass, field, asdict

import yaml

# ─── Paths ────────────────────────────────────────────────────────────────
HERMES_DIR = Path(__file__).parent.resolve()
PROMPTS_DIR = HERMES_DIR / "prompts" / "active"
CONFIG_PATH = HERMES_DIR / "config" / "agents.json"
MAIN_CONFIG_PATH = HERMES_DIR / "config.yaml"
LOG_DIR = HERMES_DIR / "logs"
DEBATE_DIR = LOG_DIR / "agent_debates"
FINAL_DECISION_FILE = HERMES_DIR / "final_decision.json"
MT5_DATA_PATH = HERMES_DIR / "data" / "mt5_payload.json"
NEWS_CALENDAR_PATH = HERMES_DIR / "economic_calendar_payload.json"
SENTIMENT_PAYLOAD_PATH = HERMES_DIR / "sentiment_payload.json"
REQUEST_TIMEOUT = 120  # seconds per agent call


def _load_env_orch() -> dict:
    """Load .env as dict for orchestrator config."""
    env = {}
    env_path = HERMES_DIR / ".env"
    if not env_path.exists():
        return env
    with open(env_path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                k, _, v = line.partition("=")
                env[k.strip()] = v.strip()
    return env


def get_enabled_symbols_orch() -> list:
    """Read ENABLED_SYMBOLS from .env, fallback to default 8."""
    env = _load_env_orch()
    raw = env.get("ENABLED_SYMBOLS", "")
    if raw:
        syms = [s.strip() for s in raw.split(",") if s.strip()]
        if syms:
            return syms
    return ["EURUSDm", "GBPUSDm", "USDJPYm", "USDCHFm", "USDCADm", "AUDUSDm", "NZDUSDm", "XAUUSDm"]

LOG_DIR.mkdir(parents=True, exist_ok=True)
DEBATE_DIR.mkdir(parents=True, exist_ok=True)


# ─── Data Classes ─────────────────────────────────────────────────────────
@dataclass
class AgentResult:
    agent_name: str
    status: str  # "completed" | "failed"
    output_json: Optional[dict] = None
    error: Optional[str] = None
    duration_ms: float = 0.0


@dataclass
class CycleLog:
    timestamp: str
    mode: str
    model: str
    mt5_payload: dict = field(default_factory=dict)
    agent_results: dict = field(default_factory=dict)
    manager_output_raw: Optional[dict] = None
    safety_gate_result: dict = field(default_factory=dict)
    final_decision: Optional[dict] = None
    technical_candidates_normalized: list = field(default_factory=list)
    news_payload: dict = field(default_factory=dict)
    sentiment_payload: dict = field(default_factory=dict)
    duration_per_agent: dict = field(default_factory=dict)
    total_duration_ms: float = 0.0
    pipeline_error: Optional[str] = None


# ─── Config Loader ────────────────────────────────────────────────────────
def load_api_config() -> dict:
    """Load API credentials from main config.yaml"""
    if not MAIN_CONFIG_PATH.exists():
        raise FileNotFoundError(f"config.yaml not found at {MAIN_CONFIG_PATH}")
    with open(MAIN_CONFIG_PATH, "r") as f:
        cfg = yaml.safe_load(f)

    model = cfg.get("model", {})
    return {
        "base_url": model.get("base_url", "https://api.openai.com/v1"),
        "default_model": cfg.get("trading_model", model.get("default", "unknown")),
    }


def load_agent_registry() -> dict:
    """Load agent configs from agents.json"""
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "r") as f:
        return json.load(f)


def load_prompt(agent_name: str) -> str:
    """Load the FULL system prompt for an agent"""
    prompt_path = PROMPTS_DIR / f"{agent_name}_prompt.txt"
    if not prompt_path.exists():
        raise FileNotFoundError(f"Prompt not found: {prompt_path}")
    return prompt_path.read_text(encoding="utf-8")


# ─── MT5 Data ─────────────────────────────────────────────────────────────
def load_mt5_payload(source: Optional[str] = None) -> dict:
    """Load MT5 market data. Falls back to dummy data."""
    paths = []
    if source:
        paths.append(Path(source))
    paths.append(MT5_DATA_PATH)

    for p in paths:
        if p.exists():
            with open(p, "r") as f:
                data = json.load(f)
            print(f"[OK] Loaded MT5 payload: {len(data.get('symbols', {}))} symbols from {p.name}")
            return data

    print("[WARN] No MT5 payload found. Using dummy test data.")
    return _dummy_mt5_payload()


def load_economic_calendar() -> dict:
    """Load economic calendar payload. Returns status dict for downstream agents."""
    if not NEWS_CALENDAR_PATH.exists():
        return {"status": "missing", "source": "not_found", "events": [], "rules": {}}
    try:
        with open(NEWS_CALENDAR_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        events = data.get("events", [])
        high_impact = [
            e for e in events if e.get("impact", "").lower() == "high"
        ]
        # Only block currencies from BIG news events within ±2 hours of now
        from datetime import datetime as _dt, timezone as _tz, timedelta as _td
        _now = _dt.now(_tz.utc)
        _blocked = []
        for e in events:
            if e.get("impact", "").lower() != "high" or not e.get("big_news", False):
                continue
            # Parse event time
            _edate = e.get("date", "")
            _etime = e.get("time_utc", "00:00")
            try:
                _evt_dt = _dt.strptime(f"{_edate} {_etime}", "%Y-%m-%d %H:%M:%S").replace(tzinfo=_tz.utc)
            except Exception:
                continue
            if abs((_evt_dt - _now).total_seconds()) <= 7200:  # 2 hours
                _blocked.append(e.get("currency", ""))
        big_news = [e for e in events if e.get("impact", "").lower() == "high" and e.get("big_news", False)]
        data["_high_impact_nearby"] = len(_blocked) > 0
        data["_blocked_currencies"] = list(set(_blocked))
        print(f"[OK] News calendar loaded: {len(events)} event(s), {len(high_impact)} high-impact")
        return data
    except Exception as e:
        print(f"[WARN] Failed to load news calendar: {e}")
        return {"status": "error", "source": "load_failed", "events": [], "rules": {}}


def load_sentiment_payload() -> dict:
    """Load sentiment payload. Returns status dict for downstream agents."""
    if not SENTIMENT_PAYLOAD_PATH.exists():
        return {"status": "missing", "source": "not_found"}
    try:
        with open(SENTIMENT_PAYLOAD_PATH, "r", encoding="utf-8") as f:
            data = json.load(f)
        blocked = data.get("blocked_symbols", [])
        data["_has_blocked_symbols"] = len(blocked) > 0
        mood = data.get("market_mood", "unknown")
        data["_is_extreme_risk_off"] = mood.lower() in ("extreme_fear", "risk_off", "panic")
        print(f"[OK] Sentiment payload loaded: mood={mood}, blocked={blocked}")
        return data
    except Exception as e:
        print(f"[WARN] Failed to load sentiment payload: {e}")
        return {"status": "error", "source": "load_failed"}


def _dummy_mt5_payload() -> dict:
    """Generate dummy MT5 payload for testing"""
    return {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "source": "dummy_test_data",
        "symbols": {
            "EURUSD": {
                "bid": 1.0852, "ask": 1.0854, "spread": 2,
                "h4": {"ema20": 1.0850, "ema50": 1.0830, "rsi": 58, "atr": 0.0065, "adx": 22, "trend": "bullish"},
                "h1": {"ema20": 1.0855, "ema50": 1.0840, "rsi": 55, "trend": "bullish"},
                "m15": {"rsi": 52, "trend": "neutral", "atr": 0.0025},
                "m5": {"rsi": 50, "trend": "neutral"},
            },
            "GBPUSD": {
                "bid": 1.2695, "ask": 1.2698, "spread": 3,
                "h4": {"ema20": 1.2700, "ema50": 1.2720, "rsi": 42, "atr": 0.0080, "adx": 18, "trend": "bearish"},
                "h1": {"ema20": 1.2690, "ema50": 1.2710, "rsi": 44, "trend": "ranging"},
                "m15": {"rsi": 46, "trend": "neutral", "atr": 0.0030},
                "m5": {"rsi": 48, "trend": "neutral"},
            },
            "USDJPY": {
                "bid": 157.50, "ask": 157.53, "spread": 3,
                "h4": {"ema20": 157.20, "ema50": 156.80, "rsi": 65, "atr": 0.85, "adx": 28, "trend": "bullish"},
                "h1": {"ema20": 157.35, "ema50": 157.00, "rsi": 62, "trend": "bullish"},
                "m15": {"rsi": 58, "trend": "bullish", "atr": 0.35},
                "m5": {"rsi": 55, "trend": "neutral"},
            },
            "XAUUSD": {
                "bid": 2325.50, "ask": 2326.00, "spread": 50,
                "h4": {"ema20": 2320.00, "ema50": 2310.00, "rsi": 62, "atr": 15.0, "adx": 20, "trend": "bullish"},
                "h1": {"ema20": 2322.00, "ema50": 2318.00, "rsi": 57, "trend": "bullish"},
                "m15": {"rsi": 55, "trend": "bullish", "atr": 8.0},
                "m5": {"rsi": 54, "trend": "bullish"},
            },
        },
    }


# ─── Normalize Candidate Trade Plan ──────────────────────────────────────
def normalize_candidate_trade_plan(candidate: dict, symbol_payload: dict) -> dict:
    """
    Ensure every Technical candidate has a complete trade plan:
    planned_entry, sl_price, tp_price, rr, confidence, sl_reason, tp_reason.

    If the agent already provided them, keep them.
    If missing, calculate conservative fallbacks from MT5 payload data.

    Returns candidate with trade_plan_source: "agent" or "python_fallback".
    If validation fails, returns candidate with rejected=True and reason.
    """
    c = dict(candidate)  # shallow copy
    sym = c.get("symbol", "UNKNOWN")
    side = c.get("side", "").lower()

    # Helper: resolve timeframe keys (payload may use H4/h4/M15/m15)
    def _tf(key):
        return (symbol_payload.get(key)
                or symbol_payload.get(key.upper())
                or symbol_payload.get(key.lower())
                or {})

    h4 = _tf("h4")
    h1 = _tf("h1")
    m15 = _tf("m15")
    bid = symbol_payload.get("bid", 0)
    ask = symbol_payload.get("ask", 0)

    # Check if already complete from agent
    has_plan = all(c.get(k) is not None and c.get(k) != 0 for k in [
        "planned_entry", "sl_price", "tp_price", "rr"
    ])

    if has_plan:
        # Agent provided full plan — validate logic only
        c["trade_plan_source"] = "agent"
        return _validate_trade_plan_logic(c, side)

    # ── Fallback: build trade plan from payload data ──
    c["trade_plan_source"] = "python_fallback"

    # 1. planned_entry
    if not c.get("planned_entry"):
        if side == "buy":
            c["planned_entry"] = ask if ask else bid
        elif side == "sell":
            c["planned_entry"] = bid if bid else ask
        else:
            c["rejected"] = True
            c["reject_reason"] = f"invalid_trade_plan: unknown side '{side}'"
            return c

    entry = c["planned_entry"]

    # 2. SL price
    if not c.get("sl_price"):
        atr_m15 = m15.get("atr", 0)
        atr_h1 = h1.get("atr", 0)
        atr_h4 = h4.get("atr", 0)

        if side == "buy":
            # Priority: support level > ATR_H1 * 2.0 > ATR_M15 * 3.0 > H4 > fallback
            support = c.get("support_level") or symbol_payload.get("support")
            if support and support < entry:
                c["sl_price"] = support
                c["sl_reason"] = f"support level at {support}"
            elif atr_h1:
                c["sl_price"] = round(entry - atr_h1 * 2.0, 5)
                c["sl_reason"] = f"H1 ATR({atr_h1}) x 2.0"
            elif atr_m15:
                c["sl_price"] = round(entry - atr_m15 * 3.0, 5)
                c["sl_reason"] = f"M15 ATR({atr_m15}) x 3.0"
            elif atr_h4:
                c["sl_price"] = round(entry - atr_h4 * 1.0, 5)
                c["sl_reason"] = f"H4 ATR({atr_h4}) x 1.0"
            else:
                # Hardcoded fallback: XAUUSD = 25 pips, forex = 20 pips
                is_gold = "XAU" in sym.upper()
                fallback_sl = 25 if is_gold else 20
                pip_size = 1.0 if is_gold else 0.0001
                c["sl_price"] = round(entry - fallback_sl * pip_size, 5)
                c["sl_reason"] = f"fallback SL {fallback_sl} pips (no ATR data)"
        elif side == "sell":
            resistance = c.get("resistance_level") or symbol_payload.get("resistance")
            if resistance and resistance > entry:
                c["sl_price"] = resistance
                c["sl_reason"] = f"resistance level at {resistance}"
            elif atr_h1:
                c["sl_price"] = round(entry + atr_h1 * 2.0, 5)
                c["sl_reason"] = f"H1 ATR({atr_h1}) x 2.0"
            elif atr_m15:
                c["sl_price"] = round(entry + atr_m15 * 3.0, 5)
                c["sl_reason"] = f"M15 ATR({atr_m15}) x 3.0"
            elif atr_h4:
                c["sl_price"] = round(entry + atr_h4 * 1.0, 5)
                c["sl_reason"] = f"H4 ATR({atr_h4}) x 1.0"
            else:
                # Hardcoded fallback: XAUUSD = 25 pips, forex = 20 pips
                is_gold = "XAU" in sym.upper()
                fallback_sl = 25 if is_gold else 20
                pip_size = 1.0 if is_gold else 0.0001
                c["sl_price"] = round(entry + fallback_sl * pip_size, 5)
                c["sl_reason"] = f"fallback SL {fallback_sl} pips (no ATR data)"
    else:
        c.setdefault("sl_reason", "provided by agent")

    sl = c["sl_price"]

    # 3. TP price (target RR = 2.0)
    if not c.get("tp_price"):
        sl_distance = abs(entry - sl)
        target_rr = 2.0
        if side == "buy":
            c["tp_price"] = round(entry + sl_distance * target_rr, 5)
            c["tp_reason"] = f"fallback RR {target_rr} from SL distance {sl_distance}"
        elif side == "sell":
            c["tp_price"] = round(entry - sl_distance * target_rr, 5)
            c["tp_reason"] = f"fallback RR {target_rr} from SL distance {sl_distance}"
    else:
        c.setdefault("tp_reason", "provided by agent")

    tp = c["tp_price"]

    # 4. Calculate RR
    sl_dist = abs(entry - sl)
    tp_dist = abs(tp - entry)
    if sl_dist > 0:
        c["rr"] = round(tp_dist / sl_dist, 2)
    else:
        c["rejected"] = True
        c["reject_reason"] = "invalid_trade_plan: SL distance is zero"
        return c

    # 5. Default confidence if missing
    if not c.get("confidence"):
        score = c.get("technical_score", 0.5)
        setup = c.get("setup_quality", "weak")
        base = {"strong": 80, "medium": 70, "weak": 60}.get(setup, 60)
        c["confidence"] = min(base + int(score * 15), 95)

    # 6. Validate logic
    return _validate_trade_plan_logic(c, side)


def _validate_trade_plan_logic(c: dict, side: str) -> dict:
    """Validate SL/TP/entry logic and minimum RR."""
    entry = c.get("planned_entry", 0)
    sl = c.get("sl_price", 0)
    tp = c.get("tp_price", 0)
    rr = c.get("rr", 0)

    if side == "buy":
        if not (sl < entry < tp):
            c["rejected"] = True
            c["reject_reason"] = f"invalid_trade_plan: buy requires SL({sl}) < entry({entry}) < TP({tp})"
            return c
    elif side == "sell":
        if not (sl > entry > tp):
            c["rejected"] = True
            c["reject_reason"] = f"invalid_trade_plan: sell requires SL({sl}) > entry({entry}) > TP({tp})"
            return c

    if rr < 1.8:
        c["rejected"] = True
        c["reject_reason"] = f"invalid_trade_plan: RR {rr} < minimum 1.8"
        return c

    return c


# ─── Prompt Builders ──────────────────────────────────────────────────────
def _compact_technical(mt5: dict) -> dict:
    symbols = mt5.get("symbols", {})
    result = {}
    for sym, data in symbols.items():
        def _get(k, _data=data):
            return _data.get(k) or _data.get(k.upper()) or _data.get(k.lower()) or {}
        result[sym] = {
            "h4": _get("h4"),
            "h1": _get("h1"),
            "m15": _get("m15"),
            "m5": _get("m5"),
            "spread": data.get("spread") or data.get("spread_points", 0),
            "bid": data.get("bid", 0),
            "ask": data.get("ask", 0),
            "m5_candle_size": data.get("m5_candle_size", 0),
        }
    return result


def build_technical_prompt(mt5: dict, sd_zones: dict = None) -> str:
    prompt = load_prompt("technical_agent")
    compact = _compact_technical(mt5)

    # Build S/D zone summary if available
    sd_text = ""
    if sd_zones:
        zones_data = sd_zones.get("zones", {})
        lines = []
        for sym, zones in sorted(zones_data.items()):
            active = [z for z in zones if not z.get("expired")]
            if not active:
                continue
            for z in active:
                conf_penalty = z["touch_count"] * 10  # -0 fresh, -10 1x, -20 2x
                lines.append(
                    f"  {sym}: {z['type']} zone {z['zone_low']:.5f}-{z['zone_high']:.5f} "
                    f"({z['status']}, {z['touch_count']} touch, conf -{conf_penalty})"
                )
        if lines:
            sd_text = "\n\nSUPPLY/DEMAND ZONES (H1, wick+body touch counted):\n" + "\n".join(lines)
            sd_text += "\n\nRules:\n"
            sd_text += "- Entry near (<1 ATR) a fresh zone → higher confidence\n"
            sd_text += "- 0 touch = fresh (full power), 1 touch = conf -10, 2 touch = conf -20\n"
            sd_text += "- 3+ touches or price closed through zone → zone expired, DO NOT use\n"
            sd_text += "- Prioritize entries at fresh zones over tested zones"

    return f"{prompt}\n\nMT5 COMPACT PAYLOAD:\n{json.dumps(compact, indent=2)}{sd_text}\n\nRespond ONLY with the required JSON. No markdown, no explanation."


def build_fundamental_prompt(technical_output: dict, mt5: dict, news_payload: Optional[dict] = None) -> str:
    prompt = load_prompt("fundamental_agent")
    candidates = technical_output.get("top_candidates", [])

    # Use dedicated news_payload if available, fallback to mt5.news
    if news_payload and news_payload.get("status") != "missing":
        news_str = json.dumps(news_payload, indent=2)
    else:
        news = mt5.get("news", [])
        news_str = json.dumps(news, indent=2) if news else "No news payload provided."

    return (
        f"{prompt}\n\n"
        f"NEWS PAYLOAD:\n{news_str}\n\n"
        f"TECHNICAL CANDIDATES:\n{json.dumps(candidates, indent=2)}\n\n"
        f"Respond ONLY with the required JSON. No markdown, no explanation."
    )


def build_sentiment_prompt(technical_output: dict, sentiment_payload: Optional[dict] = None) -> str:
    prompt = load_prompt("sentiment_agent")
    candidates = technical_output.get("top_candidates", [])

    if sentiment_payload and sentiment_payload.get("status") != "missing":
        sent_str = json.dumps(sentiment_payload, indent=2)
    else:
        sent_str = "No sentiment payload provided."

    return (
        f"{prompt}\n\n"
        f"SENTIMENT PAYLOAD:\n{sent_str}\n\n"
        f"TECHNICAL CANDIDATES:\n{json.dumps(candidates, indent=2)}\n\n"
        f"Respond ONLY with the required JSON. No markdown, no explanation."
    )


def build_risk_prompt(technical_output: dict, mt5: dict) -> str:
    prompt = load_prompt("risk_agent")
    candidates = technical_output.get("top_candidates", [])
    account = mt5.get("account", {})
    daily_loss = mt5.get("daily_loss", 0)
    xau_loss = mt5.get("xauusd_daily_loss", 0)
    open_pos = mt5.get("open_positions", 0)
    risk_ctx = {
        "account": account,
        "daily_loss": daily_loss,
        "xauusd_daily_loss": xau_loss,
        "open_positions": open_pos,
    }
    return (
        f"{prompt}\n\n"
        f"RISK CONTEXT:\n{json.dumps(risk_ctx, indent=2)}\n\n"
        f"CANDIDATES TO VALIDATE:\n{json.dumps(candidates, indent=2)}\n\n"
        f"Respond ONLY with the required JSON. No markdown, no explanation."
    )


def build_manager_prompt(
    mt5: dict,
    technical: dict,
    fundamental: dict,
    sentiment: dict,
    risk: dict,
) -> str:
    prompt = load_prompt("manager_agent")
    return (
        f"{prompt}\n\n"
        f"INPUT DATA:\n"
        f"--- MT5 Market Payload ---\n{json.dumps(_compact_technical(mt5), indent=2)}\n\n"
        f"--- Technical Agent Output ---\n{json.dumps(technical, indent=2)}\n\n"
        f"--- Fundamental Agent Output ---\n{json.dumps(fundamental, indent=2)}\n\n"
        f"--- Sentiment Agent Output ---\n{json.dumps(sentiment, indent=2)}\n\n"
        f"--- Risk Agent Output ---\n{json.dumps(risk, indent=2)}\n\n"
        f"Respond ONLY with the required JSON. No markdown, no explanation."
    )


def build_boss_prompt(all_outputs: dict) -> str:
    prompt = load_prompt("boss_agent")
    return (
        f"{prompt}\n\n"
        f"REVIEW DATA:\n"
        f"--- Closed Trades ---\nNo closed trades yet.\n\n"
        f"--- Full Agent Outputs ---\n{json.dumps(all_outputs, indent=2)}\n\n"
        f"Respond ONLY with the required JSON. No markdown, no explanation."
    )


# ─── LLM Call (uses Hermes internal delegation pattern) ───────────────────
def _call_llm(system_prompt: str, api_config: dict) -> dict:
    """Call LLM API and return parsed JSON. Retries on empty/error responses."""
    import urllib.request
    import urllib.error
    import socket

    MAX_RETRIES = 2
    RETRY_DELAY = 2  # seconds

    url = f"{api_config['base_url'].rstrip('/')}/chat/completions"
    model = api_config["default_model"]

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": "Run analysis now."},
        ],
        "temperature": 0.3,
        "max_tokens": 4096,
    }

    data = json.dumps(payload).encode("utf-8")
    last_error = None

    for attempt in range(MAX_RETRIES + 1):
        try:
            req = urllib.request.Request(
                url,
                data=data,
                headers={
                    "Content-Type": "application/json",
                    "Authorization": f"Bearer {_get_api_key()}",
                },
            )
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT) as resp:
                raw = resp.read().decode("utf-8")

        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8", errors="replace")
            last_error = RuntimeError(f"HTTP {e.code}: {error_body[:300]}")
            if attempt < MAX_RETRIES:
                print(f"[RETRY {attempt+1}/{MAX_RETRIES}] HTTP {e.code}, waiting {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
                continue
            raise last_error

        except (urllib.error.URLError, socket.timeout, TimeoutError, ConnectionError) as e:
            last_error = RuntimeError(f"Connection/timeout error: {e}")
            if attempt < MAX_RETRIES:
                print(f"[RETRY {attempt+1}/{MAX_RETRIES}] {type(e).__name__}: {e}, waiting {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
                continue
            raise last_error

        except Exception as e:
            last_error = RuntimeError(f"API call failed: {e}")
            if attempt < MAX_RETRIES:
                print(f"[RETRY {attempt+1}/{MAX_RETRIES}] {e}, waiting {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
                continue
            raise last_error

        # ── Validate response ──
        if not raw or not raw.strip():
            last_error = ValueError("Empty response body from LLM API")
            if attempt < MAX_RETRIES:
                print(f"[RETRY {attempt+1}/{MAX_RETRIES}] Empty response, waiting {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
                continue
            raise last_error

        try:
            result = json.loads(raw)
            content = result["choices"][0]["message"]["content"]
        except (KeyError, IndexError, json.JSONDecodeError) as e:
            last_error = RuntimeError(f"Malformed API response: {e}")
            if attempt < MAX_RETRIES:
                print(f"[RETRY {attempt+1}/{MAX_RETRIES}] Malformed response: {e}, waiting {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
                continue
            raise last_error

        # ── Validate content ──
        if not content or not content.strip():
            last_error = ValueError("Empty content in LLM response")
            if attempt < MAX_RETRIES:
                print(f"[RETRY {attempt+1}/{MAX_RETRIES}] Empty content, waiting {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
                continue
            raise last_error

        try:
            return _extract_json(content)
        except (ValueError, json.JSONDecodeError) as e:
            last_error = e
            if attempt < MAX_RETRIES:
                print(f"[RETRY {attempt+1}/{MAX_RETRIES}] JSON extraction failed: {e}, waiting {RETRY_DELAY}s...")
                time.sleep(RETRY_DELAY)
                continue
            raise

    # Should never reach here
    if last_error:
        raise last_error
    raise RuntimeError("Unknown error in _call_llm (all retries exhausted)")


def _get_api_key() -> str:
    """Get API key from config.yaml. Never logged or printed."""
    with open(MAIN_CONFIG_PATH, "r") as f:
        cfg = yaml.safe_load(f)
    return cfg.get("model", {}).get("api_key", "")


def _extract_json(text: str) -> dict:
    """Extract JSON from LLM response (handles ```json fences)."""
    text = re.sub(r"```(?:json)?\s*", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"No JSON object found in response. First 200 chars: {text[:200]}")
    return json.loads(text[start:end + 1])


# ─── Safety Gate ──────────────────────────────────────────────────────────
class SafetyGate:
    MIN_RR = 1.8
    MIN_CONFIDENCE = 75
    REQUIRED_ENTRY_FIELDS = [
        "best_symbol", "side", "entry_type",
        "planned_entry", "sl_price", "tp_price",
        "rr", "confidence",
    ]

    @staticmethod
    def validate(manager_output: dict) -> tuple[bool, str, dict]:
        """Validate manager output. Returns (passed, reason, corrected_output)."""
        action = manager_output.get("action", "")

        if action == "skip":
            return True, "skip is always safe", manager_output

        if action != "entry":
            corrected = dict(manager_output, action="skip",
                           reason=f"Unknown action '{action}' overridden to skip by safety gate")
            return False, f"unknown action: {action}", corrected

        # Check required fields
        missing = [k for k in SafetyGate.REQUIRED_ENTRY_FIELDS if k not in manager_output]
        if missing:
            corrected = {
                "action": "skip",
                "reason": f"safety_gate: missing fields {missing}",
                "original_action": manager_output,
            }
            return False, f"missing required fields: {missing}", corrected

        # RR check
        rr = manager_output.get("rr", 0)
        if rr < SafetyGate.MIN_RR:
            corrected = {
                "action": "skip",
                "reason": f"safety_gate: RR {rr} < minimum {SafetyGate.MIN_RR}",
                "original_action": manager_output,
            }
            return False, f"RR {rr} < {SafetyGate.MIN_RR}", corrected

        # Confidence check
        confidence = manager_output.get("confidence", 0)
        if confidence < SafetyGate.MIN_CONFIDENCE:
            corrected = {
                "action": "skip",
                "reason": f"safety_gate: confidence {confidence} < {SafetyGate.MIN_CONFIDENCE}",
                "original_action": manager_output,
            }
            return False, f"confidence {confidence} < {SafetyGate.MIN_CONFIDENCE}", corrected

        # Price logic
        sl = manager_output.get("sl_price", 0)
        tp = manager_output.get("tp_price", 0)
        entry = manager_output.get("planned_entry", 0)
        side = manager_output.get("side", "")

        if side == "buy":
            if sl >= entry:
                corrected = dict(manager_output, action="skip",
                               reason=f"safety_gate: buy SL {sl} >= entry {entry}")
                return False, f"buy SL {sl} >= entry {entry}", corrected
            if tp <= entry:
                corrected = dict(manager_output, action="skip",
                               reason=f"safety_gate: buy TP {tp} <= entry {entry}")
                return False, f"buy TP {tp} <= entry {entry}", corrected
        elif side == "sell":
            if sl <= entry:
                corrected = dict(manager_output, action="skip",
                               reason=f"safety_gate: sell SL {sl} <= entry {entry}")
                return False, f"sell SL {sl} <= entry {entry}", corrected
            if tp >= entry:
                corrected = dict(manager_output, action="skip",
                               reason=f"safety_gate: sell TP {tp} >= entry {entry}")
                return False, f"sell TP {tp} >= entry {entry}", corrected
        else:
            corrected = dict(manager_output, action="skip",
                           reason=f"safety_gate: invalid side '{side}'")
            return False, f"invalid side: {side}", corrected

        return True, "all checks passed", manager_output


def save_final_decision(final_decision: dict) -> None:
    """Save final decision after Safety Gate to final_decision.json"""
    FINAL_DECISION_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(FINAL_DECISION_FILE, "w", encoding="utf-8") as f:
        json.dump(final_decision, f, indent=2, ensure_ascii=False)
    print(f"[FINAL] Decision disimpan: {FINAL_DECISION_FILE}")


# ─── Pipeline ─────────────────────────────────────────────────────────────
class AgentPipeline:
    """Sequential multi-agent pipeline with robust error handling."""

    AGENT_ORDER = [
        "technical_agent",
        "fundamental_agent",
        "sentiment_agent",
        "risk_agent",
        "manager_agent",
    ]

    def __init__(self, mt5_payload: dict, api_config: dict, mode: str = "test", skip_boss: bool = False, sd_zones: dict = None):
        self.mt5 = mt5_payload
        self.api_config = api_config
        self.mode = mode
        self.skip_boss = skip_boss
        self.sd_zones = sd_zones or {}
        self.results: dict[str, AgentResult] = {}
        self.cycle_log = CycleLog(
            timestamp=datetime.now(timezone.utc).isoformat(),
            mode=mode,
            model=api_config["default_model"],
            mt5_payload=mt5_payload,
        )
        self.pipeline_error: Optional[str] = None
        self.t0 = time.time()

    def run(self) -> CycleLog:
        try:
            self._run_stages()
        except Exception as e:
            self.pipeline_error = f"Pipeline exception: {e}\n{traceback.format_exc()}"
            print(f"\n[FATAL] {self.pipeline_error}")
            self.cycle_log.pipeline_error = self.pipeline_error
            self.cycle_log.final_decision = {
                "action": "skip",
                "reason": f"pipeline_error: {str(e)[:200]}",
            }

        self.cycle_log.total_duration_ms = (time.time() - self.t0) * 1000
        self._save_log()
        return self.cycle_log

    def _run_stages(self):
        print("\n" + "=" * 70)
        print(f"  Hermes Exness Trading System v1.2 — Pipeline")
        print(f"  Mode: {self.mode}  |  Model: {self.api_config['default_model']}")
        print(f"  Symbols: {list(self.mt5.get('symbols', {}).keys())}")
        print("=" * 70)

        # ── MT5 Data Freshness Check (defense-in-depth) ──
        if MT5_DATA_PATH.exists():
            env = _load_env_orch()
            mt5_max_age = 300
            try:
                mt5_max_age = int(env.get("MT5_DATA_MAX_AGE_SECONDS", "300"))
            except ValueError:
                pass
            age = time.time() - MT5_DATA_PATH.stat().st_mtime
            if age > mt5_max_age:
                print(f"[WARNING] MT5 payload is {age:.0f}s old (max: {mt5_max_age}s). Data may be stale!")
            else:
                print(f"[OK] MT5 payload fresh: {age:.0f}s old")
        else:
            print("[WARNING] MT5 data file not found at", MT5_DATA_PATH)

        # ── Load News & Sentiment early (for logging even if tech skips) ──
        news_payload = load_economic_calendar()
        self.cycle_log.news_payload = news_payload
        sentiment_payload = load_sentiment_payload()
        self.cycle_log.sentiment_payload = sentiment_payload

        # ── ADX Gate: filter ranging/choppy symbols before Technical ──
        adx_min = 20
        symbols_data = self.mt5.get("symbols", {})
        adx_blocked = []
        for sym, sdata in list(symbols_data.items()):
            h1 = sdata.get("H1", {})
            h1_adx = h1.get("adx", None)
            if h1_adx is not None and h1_adx < adx_min:
                adx_blocked.append({"symbol": sym, "adx": h1_adx, "reason": f"H1 ADX {h1_adx:.1f} < {adx_min} — ranging/choppy"})
                del symbols_data[sym]
        if adx_blocked:
            print(f"[ADX Gate] Blocked {len(adx_blocked)} symbol(s):")
            for b in adx_blocked:
                print(f"  ✗ {b['symbol']}: {b['reason']}")
            self.mt5["symbols"] = symbols_data
            self.mt5["_adx_blocked"] = adx_blocked

        # If all symbols filtered by ADX, skip pipeline
        if not symbols_data:
            print("[ADX Gate] All symbols blocked — pipeline skip")
            ts_now = datetime.now(timezone.utc).isoformat()
            skip_fd = {
                "action": "skip",
                "reason": f"All symbols filtered by ADX gate (H1 ADX < {adx_min})",
                "adx_blocked": adx_blocked,
                "safety_gate": "passed",
                "mode": self.mode,
                "timestamp": ts_now,
            }
            self.cycle_log.final_decision = skip_fd
            self.cycle_log.manager_output_raw = skip_fd
            self.cycle_log.safety_gate_result = {"passed": True, "reason": "skip is always safe"}
            self.cycle_log.agent_results["adx_gate"] = {"status": "all_blocked", "blocked": adx_blocked}
            self._save_log()
            return

        # ── Stage 1: Technical ──
        tech = self._run_agent("technical_agent", build_technical_prompt(self.mt5, self.sd_zones))
        if tech.status == "failed":
            return self._abort(f"Technical Agent failed: {tech.error}")

        tech_out = tech.output_json
        candidates = tech_out.get("top_candidates", [])
        print(f"\n[1/6] Technical: {len(candidates)} candidate(s)")
        for c in candidates:
            print(f"      {c.get('symbol')} {c.get('side')} | score={c.get('technical_score')} | {c.get('setup_quality')}")

        if not candidates:
            print("      No candidates → pipeline ends (skip)")
            ts_now = datetime.now(timezone.utc).isoformat()
            skip_fd = {
                "action": "skip",
                "reason": "No technical candidates",
                "safety_gate": "passed",
                "mode": self.mode,
                "timestamp": ts_now,
            }
            self.cycle_log.final_decision = skip_fd
            self.cycle_log.manager_output_raw = skip_fd
            self.cycle_log.safety_gate_result = {"passed": True, "reason": "skip is always safe"}
            save_final_decision(skip_fd)
            return

        # ── H4 Trend Filter: reject candidates against macro trend ──
        # Rule from Kai: only trade in the direction of H4 macro trend
        symbols_data = self.mt5.get("symbols", {})
        h4_trend_blocked = []
        passed_candidates = []
        for c in candidates:
            sym = c.get("symbol", "")
            sym_payload = symbols_data.get(sym, {})
            h4 = sym_payload.get("H4") or sym_payload.get("h4") or {}
            h4_ema50 = h4.get("ema50", 0)
            current_price = sym_payload.get("bid") or sym_payload.get("ask", 0)
            side = c.get("side", "").lower()

            if h4_ema50 and current_price:
                h4_trend = "bullish" if current_price > h4_ema50 else "bearish"
                if (side == "buy" and h4_trend == "bearish") or (side == "sell" and h4_trend == "bullish"):
                    h4_trend_blocked.append({
                        "symbol": sym,
                        "side": side,
                        "reason": f"H4 Trend Filter: {side.upper()} rejected — H4 is {h4_trend} (price {current_price} vs EMA50 {h4_ema50})"
                    })
                    print(f"      ✗ {sym} {side} blocked by H4 Trend: H4 is {h4_trend}")
                    continue
            passed_candidates.append(c)

        if h4_trend_blocked:
            self.mt5["_h4_trend_blocked"] = h4_trend_blocked
            print(f"[H4 Trend Gate] Blocked {len(h4_trend_blocked)} counter-trend candidate(s)")

        candidates = passed_candidates

        if not candidates:
            print("[H4 Trend Gate] All candidates blocked — pipeline skip")
            ts_now = datetime.now(timezone.utc).isoformat()
            skip_fd = {
                "action": "skip",
                "reason": "All candidates rejected by H4 Trend Filter: trade direction must match H4 macro trend",
                "h4_trend_blocked": h4_trend_blocked,
                "safety_gate": "passed",
                "mode": self.mode,
                "timestamp": ts_now,
            }
            self.cycle_log.final_decision = skip_fd
            self.cycle_log.manager_output_raw = skip_fd
            self.cycle_log.safety_gate_result = {"passed": True, "reason": "skip is always safe"}
            self.cycle_log.agent_results["h4_trend_gate"] = {"status": "all_blocked", "blocked": h4_trend_blocked}
            save_final_decision(skip_fd)
            return

        # ── Normalize candidates trade plan ──
        symbols_data = self.mt5.get("symbols", {})
        normalized = []
        rejected_by_normalize = []
        for c in candidates:
            sym = c.get("symbol", "")
            sym_payload = symbols_data.get(sym, {})
            nc = normalize_candidate_trade_plan(c, sym_payload)
            if nc.get("rejected"):
                rejected_by_normalize.append({"symbol": sym, "reason": nc.get("reject_reason", "")})
                print(f"      ✗ {sym} rejected by normalize: {nc.get('reject_reason', '')[:80]}")
            else:
                normalized.append(nc)
                src = nc.get("trade_plan_source", "unknown")
                print(f"      → {sym} normalized (source={src}) | SL={nc.get('sl_price')} TP={nc.get('tp_price')} RR={nc.get('rr')}")

        self.cycle_log.technical_candidates_normalized = normalized

        # Update tech_out with normalized candidates for downstream agents
        tech_out["top_candidates"] = normalized
        if rejected_by_normalize:
            existing_rejected = tech_out.get("rejected_pairs", [])
            tech_out["rejected_pairs"] = existing_rejected + rejected_by_normalize

        if not normalized:
            print("      All candidates rejected by normalize → pipeline ends (skip)")
            ts_now = datetime.now(timezone.utc).isoformat()
            skip_fd = {
                "action": "skip",
                "reason": "All candidates rejected by trade plan normalization",
                "rejected_pairs": rejected_by_normalize,
                "safety_gate": "passed",
                "mode": self.mode,
                "timestamp": ts_now,
            }
            self.cycle_log.final_decision = skip_fd
            self.cycle_log.manager_output_raw = skip_fd
            self.cycle_log.safety_gate_result = {"passed": True, "reason": "skip is always safe"}
            save_final_decision(skip_fd)
            return

        # ── Stage 2: Fundamental ──
        fund = self._run_agent("fundamental_agent", build_fundamental_prompt(tech_out, self.mt5, news_payload))
        if fund.status == "failed":
            return self._abort(f"Fundamental Agent failed: {fund.error}")
        print(f"[2/6] Fundamental: {fund.output_json.get('approval')} | {fund.output_json.get('research_status')}")

        # ── Stage 3: Sentiment ──
        sent = self._run_agent("sentiment_agent", build_sentiment_prompt(tech_out, sentiment_payload))
        if sent.status == "failed":
            return self._abort(f"Sentiment Agent failed: {sent.error}")
        print(f"[3/6] Sentiment: {sent.output_json.get('approval')} | {sent.output_json.get('sentiment_status')}")

        # ── Stage 4: Risk ──
        risk = self._run_agent("risk_agent", build_risk_prompt(tech_out, self.mt5))
        if risk.status == "failed":
            return self._abort(f"Risk Agent failed: {risk.error}")
        print(f"[4/6] Risk: {risk.output_json.get('risk_status')}")

        # ── Stage 5: Manager ──
        mgr = self._run_agent(
            "manager_agent",
            build_manager_prompt(
                self.mt5,
                tech_out,
                fund.output_json,
                sent.output_json,
                risk.output_json,
            ),
        )
        if mgr.status == "failed":
            return self._abort(f"Manager Agent failed: {mgr.error}")

        mgr_raw = mgr.output_json
        self.cycle_log.manager_output_raw = mgr_raw
        print(f"[5/6] Manager: action={mgr_raw.get('action')}")

        # ── Safety Gate ──
        ts_now = datetime.now(timezone.utc).isoformat()
        passed, reason, corrected = SafetyGate.validate(mgr_raw)
        self.cycle_log.safety_gate_result = {
            "passed": passed,
            "reason": reason,
        }
        if not passed:
            print(f"      ⚠ SAFETY GATE: {reason} → action overridden to SKIP")
            final_fd = {
                "action": "skip",
                "reason": f"Safety Gate rejected: {reason}",
                "safety_gate": "rejected",
                "mode": self.mode,
                "timestamp": ts_now,
                "raw_manager_output": mgr_raw,
            }
            self.cycle_log.final_decision = final_fd
            save_final_decision(final_fd)
        else:
            print(f"      ✓ Safety Gate: {reason}")
            if mgr_raw.get("action") == "skip":
                final_fd = {
                    **mgr_raw,
                    "safety_gate": "passed",
                    "mode": self.mode,
                    "timestamp": ts_now,
                }
            else:
                # entry case — add execution metadata
                final_fd = {
                    **mgr_raw,
                    "safety_gate": "passed",
                    "mode": self.mode,
                    "timestamp": ts_now,
                    "execution_allowed": os.environ.get("REAL_EXECUTION_ENABLED", "false").lower() == "true" if self.mode == "live" else True,
                    "execution_note": "",
                }
            self.cycle_log.final_decision = final_fd
            save_final_decision(final_fd)

        # ── Stage 6: Boss (optional) ──
        if not self.skip_boss:
            all_out = {
                "technical": tech_out,
                "fundamental": fund.output_json,
                "sentiment": sent.output_json,
                "risk": risk.output_json,
                "manager": mgr_raw,
            }
            boss = self._run_agent("boss_agent", build_boss_prompt(all_out))
            if boss.status == "completed":
                findings = boss.output_json.get("main_findings", [])
                print(f"[6/6] Boss: {len(findings)} finding(s)")
            else:
                print(f"[6/6] Boss: failed — {boss.error}")
        else:
            print(f"[6/6] Boss: SKIPPED (--skip-boss)")

        # Final summary
        fd = self.cycle_log.final_decision or {}
        print("\n" + "=" * 70)
        print(f"  FINAL: {fd.get('action', 'unknown')}")
        if fd.get("action") == "entry":
            print(f"  {fd.get('best_symbol')} {fd.get('side')} | Entry: {fd.get('planned_entry')}")
            print(f"  SL: {fd.get('sl_price')} | TP: {fd.get('tp_price')} | RR: {fd.get('rr')}")
            print(f"  Confidence: {fd.get('confidence')}")
        else:
            print(f"  Reason: {fd.get('reason', 'N/A')[:200]}")
        print("=" * 70)

    def _run_agent(self, name: str, system_prompt: str) -> AgentResult:
        t0 = time.time()
        try:
            output = _call_llm(system_prompt, self.api_config)
            duration = (time.time() - t0) * 1000
            result = AgentResult(agent_name=name, status="completed", output_json=output, duration_ms=duration)
        except Exception as e:
            duration = (time.time() - t0) * 1000
            result = AgentResult(agent_name=name, status="failed", error=str(e), duration_ms=duration)

        self.results[name] = result
        self.cycle_log.agent_results[name] = {
            "status": result.status,
            "output_json": result.output_json if result.status == "completed" else None,
            "error": result.error,
        }
        self.cycle_log.duration_per_agent[name] = result.duration_ms
        return result

    def _abort(self, reason: str) -> None:
        """Abort pipeline — force skip with agent_error reason."""
        self.pipeline_error = reason
        self.cycle_log.pipeline_error = reason
        ts_now = datetime.now(timezone.utc).isoformat()
        abort_fd = {
            "action": "skip",
            "reason": f"agent_error: {reason[:300]}",
            "safety_gate": "passed",
            "mode": self.mode,
            "timestamp": ts_now,
        }
        self.cycle_log.final_decision = abort_fd
        self.cycle_log.manager_output_raw = abort_fd
        self.cycle_log.safety_gate_result = {
            "passed": True,
            "reason": "skip due to agent_error (pipeline aborted)",
        }
        save_final_decision(abort_fd)
        print(f"\n[ABORT] {reason}")
        print("      → Final: skip (agent_error)")

    def _save_log(self) -> None:
        """Save full cycle log to agent_debates folder."""
        ts = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        out_path = DEBATE_DIR / f"cycle_{ts}.json"

        log_data = {
            "timestamp": self.cycle_log.timestamp,
            "mode": self.cycle_log.mode,
            "model": self.cycle_log.model,
            "mt5_payload": self.cycle_log.mt5_payload,
            "news_payload": self.cycle_log.news_payload,
            "sentiment_payload": self.cycle_log.sentiment_payload,
            "agent_results": self.cycle_log.agent_results,
            "technical_candidates_normalized": self.cycle_log.technical_candidates_normalized,
            "manager_output_raw": self.cycle_log.manager_output_raw,
            "safety_gate_result": self.cycle_log.safety_gate_result,
            "final_decision": self.cycle_log.final_decision,
            "final_decision_file": str(FINAL_DECISION_FILE),
            "duration_per_agent": self.cycle_log.duration_per_agent,
            "total_duration_ms": self.cycle_log.total_duration_ms,
        }
        if self.cycle_log.pipeline_error:
            log_data["pipeline_error"] = self.cycle_log.pipeline_error

        with open(out_path, "w") as f:
            json.dump(log_data, f, indent=2, default=str)

        print(f"\n📁 Debate log saved: {out_path}")


# ─── Status Check ─────────────────────────────────────────────────────────
def check_status() -> dict:
    """Check all agent files and config readiness."""
    status = {
        "agents_json_exists": CONFIG_PATH.exists(),
        "config_yaml_exists": MAIN_CONFIG_PATH.exists(),
        "prompt_dir_exists": PROMPTS_DIR.exists(),
        "agents": {},
        "issues": [],
    }

    if not CONFIG_PATH.exists():
        status["issues"].append("agents.json not found")
        return status

    registry = load_agent_registry()
    agents = registry.get("agents", {})

    for name in AgentPipeline.AGENT_ORDER + ["boss_agent"]:
        cfg = agents.get(name, {})
        prompt_file = cfg.get("prompt_file", "")
        prompt_path = Path(prompt_file) if prompt_file else None
        prompt_exists = prompt_path.exists() if prompt_path else False

        status["agents"][name] = {
            "enabled": cfg.get("enabled", False),
            "prompt_ready": prompt_exists,
            "role": cfg.get("role", "unknown"),
        }

        if not cfg.get("enabled"):
            status["issues"].append(f"{name}: disabled in agents.json")
        if not prompt_exists:
            status["issues"].append(f"{name}: prompt file not found ({prompt_file})")

    if not status["issues"]:
        status["ready"] = True
    else:
        status["ready"] = False

    return status


# ─── CLI ──────────────────────────────────────────────────────────────────
def main():
    import argparse

    parser = argparse.ArgumentParser(
        description="Hermes Exness Trading System v1.2 — Agent Orchestrator"
    )
    parser.add_argument("--status", action="store_true", help="Check agent readiness")
    parser.add_argument("--mt5-file", type=str, help="Path to MT5 payload JSON file")
    parser.add_argument(
        "--mode", choices=["test", "live", "cron"], default="test",
        help="Run mode: test (dummy data), live (real MT5), cron (scheduled)"
    )
    parser.add_argument("--skip-boss", action="store_true", help="Skip Boss Agent review")
    parser.add_argument("--sd-file", type=str, default="", help="Path to S/D zones JSON file")

    args = parser.parse_args()

    # --status: check readiness
    if args.status:
        print("\n╔══════════════════════════════════════╗")
        print("║  Agent Readiness Check              ║")
        print("╚══════════════════════════════════════╝\n")
        status = check_status()
        for agent, info in status.get("agents", {}).items():
            icon = "✓" if info["prompt_ready"] and info["enabled"] else "✗"
            print(f"  {icon} {agent}: prompt={info['prompt_ready']}, enabled={info['enabled']}")
        if status.get("issues"):
            print(f"\n⚠ Issues ({len(status['issues'])}):")
            for issue in status["issues"]:
                print(f"  - {issue}")
        else:
            print(f"\n✓ All agents ready.")
        print(f"\nJSON:\n{json.dumps(status, indent=2)}")
        return

    # Load config
    try:
        api_config = load_api_config()
    except Exception as e:
        print(f"[ERROR] Cannot load config.yaml: {e}")
        sys.exit(1)

    print(f"\nModel: {api_config['default_model']}")

    # Load MT5 data
    try:
        mt5_payload = load_mt5_payload(args.mt5_file)
    except Exception as e:
        print(f"[ERROR] Cannot load MT5 payload: {e}")
        if args.mode != "test":
            sys.exit(1)
        mt5_payload = _dummy_mt5_payload()

    # Load S/D zone data
    sd_zones = {}
    if args.sd_file:
        try:
            with open(args.sd_file, "r") as f:
                sd_zones = json.load(f)
            active_count = sum(
                len([z for z in zones if not z.get("expired")])
                for zones in sd_zones.get("zones", {}).values()
            )
            print(f"[SD] Loaded {active_count} active zones from {args.sd_file}")
        except Exception as e:
            print(f"[SD] Could not load zones: {e}")

    # Run pipeline
    pipeline = AgentPipeline(
        mt5_payload=mt5_payload,
        api_config=api_config,
        mode=args.mode,
        skip_boss=args.skip_boss,
        sd_zones=sd_zones,
    )
    cycle = pipeline.run()

    # Final output
    fd = cycle.final_decision or {}
    print(f"\n{'✅ ENTRY' if fd.get('action') == 'entry' else '⊘ SKIP'}")
    print(json.dumps(fd, indent=2, default=str))


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""
Multi-Agent Bot System — tiap agent punya bot sendiri di topic sendiri
Setiap agent posting analysis ke topic-nya via Telegram API.
Manager baca semua topic, merge, post keputusan final.

Tokens loaded from agent_tokens.json (bypass redactor).
"""
import json, subprocess, time, os, sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

HERMES = Path(r"C:\Users\Administrator\AppData\Local\hermes")
sys.path.insert(0, str(HERMES))
WIB = timezone(timedelta(hours=7))

# ── Load Tokens from .env ──────────────────────────────────
def load_env():
    env = {}
    for line in open(HERMES / ".env"):
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip("'\"")
    return env

_env = load_env()
AGENT_TOKENS = {
    "technical": _env.get("AGENT_TECH_TOKEN", ""),
    "fundamental": _env.get("AGENT_FUND_TOKEN", ""),
    "sentiment": _env.get("AGENT_SENT_TOKEN", ""),
    "risk": _env.get("AGENT_RISK_TOKEN", ""),
    "manager": _env.get("AGENT_MGR_TOKEN", ""),
}

TOPIC_IDS = {
    AGENT_TOKENS = {}

TOPIC_IDS = {
    "technical": 969,
    "fundamental": 970,
    "sentiment": 972,
    "risk": 973,
    "manager": 974,
}

GROUP_ID = "-1004396608984"
LABELS = {
    "technical": "📊 TEKNIKAL",
    "fundamental": "📰 FUNDAMENTAL",
    "sentiment": "📈 SENTIMEN",
    "risk": "🛡️ RISK",
    "manager": "👑 MANAGER",
}

# ── Telegram API ───────────────────────────────────────────

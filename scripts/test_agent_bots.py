#!/usr/bin/env python3
"""Test all 5 agent bots - sends test message to each topic."""
import subprocess, json, os, sys, time
from datetime import datetime

HOME = "C:\\Users\\Administrator\\AppData\\Local\\hermes"
os.chdir(HOME)

def load_env():
    env = {}
    for line in open(".env"):
        line = line.strip()
        if "=" in line and not line.startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip().strip("'\"")
    return env

env = load_env()

group_id = "-1004396608984"
bots = [
    ("technical", 969, env.get("AGENT_TECH_TOKEN", "")),
    ("fundamental", 970, env.get("AGENT_FUND_TOKEN", "")),
    ("sentiment", 972, env.get("AGENT_SENT_TOKEN", "")),
    ("risk", 973, env.get("AGENT_RISK_TOKEN", "")),
    ("manager", 974, env.get("AGENT_MGR_TOKEN", "")),
]

print("=" * 40)
print("TESTING ALL 5 AGENT BOTS")
print("=" * 40)
print()

for name, topic, token in bots:
    if not token:
        print(f"  {name}: NO TOKEN")
        continue
    
    msg = f"[TEST] {name} agent bot connected! [{datetime.now().strftime('%H:%M:%S')}]"
    
    cmd = [
        "curl", "-s", "-X", "POST",
        f"https://api.telegram.org/bot{token}/sendMessage",
        "-d", f"chat_id={group_id}",
        "-d", f"text={msg[:4000]}",
        "-d", f"message_thread_id={topic}",
        "-d", "parse_mode=Markdown"
    ]
    
    time.sleep(0.5)
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
    
    try:
        resp = json.loads(result.stdout)
        if resp.get("ok"):
            print(f"  ✅ @{name}: OK -> topic {topic}")
        else:
            print(f"  ❌ @{name}: {resp.get('description', 'FAILED')}")
    except:
        print(f"  ❌ @{name}: JSON error")

print()
print("DONE")

#!/usr/bin/env python3
"""Send test messages from each agent bot to its topic."""
import subprocess, json

CHAT_ID = "-1004396608984"
ENV_PATH = r"C:\Users\Administrator\AppData\Local\hermes\.env"

lines = open(ENV_PATH).readlines()

agents = [
    {
        "var": "AGENT_TECH_TOKEN",
        "topic": 969,
        "msg": "🤖 *Technical Agent* reporting for duty!\n\nH1 trend: Bearish, ADX 28\nKey level: EMA20 zone\n\nSignal: SELL pending on M5 confirmation."
    },
    {
        "var": "AGENT_FUND_TOKEN",
        "topic": 970,
        "msg": "📰 *Fundamental Agent* reporting!\n\nDXY: Bullish\nNo high-impact news.\n\nMacro: USD strength supports short EURUSD."
    },
    {
        "var": "AGENT_SENT_TOKEN",
        "topic": 972,
        "msg": "📊 *Sentiment Agent* ready!\n\nRetail: 68% long EURUSD (contrarian bearish)\nRisk mood: Neutral\n\nSentiment aligns with sell bias."
    },
    {
        "var": "AGENT_RISK_TOKEN",
        "topic": 973,
        "msg": "🛡️ *Risk Agent* active!\n\nPositions: 2/5 filled\nDaily loss: 0%\nNews: Clear\n\nStatus: Ready to approve new signals."
    },
    {
        "var": "AGENT_MANAGER_TOKEN",
        "topic": 974,
        "msg": "👑 *Manager Agent* online!\n\nAll 4 agents connected.\nWaiting for scanner data.\n\nNext cycle: t+10m for scalping, t+2h for day trade."
    },
]

for agent in agents:
    # Find token
    token = None
    for l in lines:
        if l.startswith(agent["var"] + "="):
            token = l.split("=", 1)[1].strip()
            break
    
    if not token:
        print(f"FAIL: {agent['var']} not found")
        continue
    
    # Send message
    result = subprocess.run(
        ["curl", "-s", "-X", "POST",
         f"https://api.telegram.org/bot{token}/sendMessage",
         "-d", f"chat_id={CHAT_ID}",
         "-d", f"message_thread_id={agent['topic']}",
         "-d", f"text={agent['msg']}",
         "-d", "parse_mode=Markdown"],
        capture_output=True, text=True, timeout=10
    )
    resp = json.loads(result.stdout)
    name = agent['var'].replace('AGENT_', '').replace('_TOKEN', '').lower()
    if resp.get("ok"):
        print(f"  ✅ @{name} -> topic {agent['topic']}")
    else:
        print(f"  ❌ @{name}: {resp.get('description','error')}")

print("\nALL AGENTS REPORTED!")

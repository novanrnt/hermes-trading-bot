#!/usr/bin/env python3
"""
News Feed Collector — Hermes Exness Bot V1
============================================
Collects forex economic calendar from free JSON API.
Updates economic_calendar_payload.json for Fundamental Agent.
No API key needed.
"""
import json
import re
import sys
import urllib.request
from datetime import datetime, timezone, date, timedelta
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
OUTPUT_FILE = BASE_DIR / "economic_calendar_payload.json"
LOGS_DIR = BASE_DIR / "logs" / "news_collector"
LOGS_DIR.mkdir(parents=True, exist_ok=True)

FREE_CALENDAR_URL = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"
RELEVANT_CURRENCIES = {"USD", "EUR", "GBP", "JPY", "CHF", "CAD", "AUD", "NZD"}

# Only these event types block currency pairs — truly market-moving events
BIG_NEWS_KEYWORDS = [
    "federal funds rate", "fomc", "interest rate decision",
    "cash rate", "policy rate", "official bank rate",
    "cpi", "consumer price index",
    "gdp", "gross domestic product",
    "non-farm payroll", "nonfarm payroll", "nfp",
    "employment change", "unemployment rate",
    "boj policy rate", "ecb interest rate", "snb policy rate",
    "monetary policy assessment",
]


def scrape_free_calendar() -> list | None:
    """Scrape free economic calendar JSON — no API key needed."""
    try:
        req = urllib.request.Request(FREE_CALENDAR_URL, headers={
            "User-Agent": "HermesBot/1.0", "Accept": "application/json",
        })
        with urllib.request.urlopen(req, timeout=20) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except Exception as e:
        print(f"  Free calendar: {e}")
        return None

    if not isinstance(data, list) or not data:
        return None

    events = []
    for evt in data:
        currency = evt.get("country", "").upper()
        if currency not in RELEVANT_CURRENCIES:
            continue
        impact_raw = str(evt.get("impact", "")).lower()
        if "high" in impact_raw or "red" in impact_raw:
            impact = "high"
        elif "medium" in impact_raw or "orange" in impact_raw:
            impact = "medium"
        else:
            impact = "low"
        # Check if this is a truly big news event
        title_lower = evt.get("title", "").lower()
        is_big = any(kw in title_lower for kw in BIG_NEWS_KEYWORDS)
        
        raw_date = evt.get("date", "")
        events.append({
            "date": raw_date[:10] if raw_date else "",
            "time_utc": raw_date[11:19] if len(raw_date) > 11 else "",
            "currency": currency,
            "impact": impact,
            "big_news": is_big,
            "event": evt.get("title", ""),
            "actual": evt.get("actual") or None,
            "forecast": evt.get("forecast") or None,
            "previous": evt.get("previous") or None,
            "risk_window_before_minutes": 60 if impact == "high" else 30,
            "risk_window_after_minutes": 60 if impact == "high" else 30,
        })

    print(f"  Scraped {len(events)} relevant events from free calendar API")

    # Truncate to this week + high/medium only to keep prompt manageable
    events = [e for e in events if e["impact"] in ("high", "medium")]
    events.sort(key=lambda e: e.get("date", "") or "")
    # Keep this week only (Mon-Fri)
    today = date.today()
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)
    events = [e for e in events if monday.strftime("%Y-%m-%d") <= e.get("date", "") <= friday.strftime("%Y-%m-%d")]
    print(f"  Filtered to {len(events)} high/medium this-week events")
    return events if events else None


def collect() -> dict:
    print("[NEWS COLLECTOR] Starting...")
    events = scrape_free_calendar()

    if not events:
        print("  No live source, keeping existing payload")
        if OUTPUT_FILE.exists():
            try:
                with open(OUTPUT_FILE) as f:
                    return json.load(f)
            except Exception:
                pass
        events = [{
            "date": datetime.now().strftime("%Y-%m-%d"), "time_utc": "00:00",
            "currency": "USD", "impact": "low",
            "event": "Check nfs.faireconomy.media for scheduled events",
            "actual": None, "forecast": None, "previous": None,
            "risk_window_before_minutes": 60, "risk_window_after_minutes": 60,
        }]

    payload = {
        "status": "available",
        "source": "faireconomy_live",
        "timezone": "UTC",
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "events": events,
        "rules": {
            "block_big_news_before_minutes": 60,
            "block_big_news_after_minutes": 60,
            "big_news_only_blocks": True,
            "allow_if_no_big_news": True,
            "unknown_news_policy": "conditional_not_reject",
        },
    }

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(payload, f, indent=2, ensure_ascii=False)
    print(f"[OK] Saved {len(events)} events to {OUTPUT_FILE}")

    high = [e for e in events if e.get("impact") == "high"]
    print(f"[OK] High-impact events this week: {len(high)}")
    for e in high:
        print(f"     {e['currency']} {e['event']} ({e['date']} {e['time_utc']})")
    return payload


def main():
    if "--check" in sys.argv:
        if OUTPUT_FILE.exists():
            with open(OUTPUT_FILE) as f:
                p = json.load(f)
            print(f"Source: {p.get('source')}")
            print(f"Events: {len(p.get('events', []))}")
            for e in p.get("events", [])[:5]:
                print(f"  {e.get('currency','')} {e.get('event','')} [{e.get('impact','')}]")
        else:
            print("No payload yet")
    else:
        collect()


if __name__ == "__main__":
    main()

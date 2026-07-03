"""
Crypto Scanner for Binance Futures
====================================
STATUS: DRAFT — NOT ACTIVATED
Target: Scan Top 100 CoinGecko → filter → 3-5 candidates → masuk pipeline Hermes

Pipeline flow:
  Crypto Scanner → Technical Agent → Fundamental Agent → Sentiment Agent → Risk Agent → Manager → Executor

Sama persis kaya pipeline forex, bedanya:
  - Data source: CoinGecko API + Binance API (bukan MT5)
  - Filter tambahan: funding rate, open interest, volume 24h
  - 24/7 (gak ada libur weekend)

Run: python crypto_scanner.py
"""
import requests
import json
import time
from typing import Dict, List, Optional

# ═══════════════════════════════════════════
# CONFIG
# ═══════════════════════════════════════════

COINGECKO_API = "https://api.coingecko.com/api/v3"
BINANCE_API = "https://fapi.binance.com"  # Binance Futures API

# Filter thresholds (bisa di-tuning nanti)
MIN_VOLUME_USD = 50_000_000       # Minimal volume 24h $50M
MIN_VOLATILITY_24H = 2.0          # Minimal pergerakan 2%
MAX_FUNDING_RATE = 0.05           # Max funding rate 0.05% (hindari over-leverage)
MIN_OPEN_INTEREST_USD = 10_000_000 # Min open interest $10M
MAX_CANDIDATES = 5

# ═══════════════════════════════════════════
# FETCHERS
# ═══════════════════════════════════════════

def fetch_top_100() -> List[Dict]:
    """Ambil top 100 coin dari CoinGecko by market cap"""
    url = f"{COINGECKO_API}/coins/markets"
    params = {
        "vs_currency": "usd",
        "order": "market_cap_desc",
        "per_page": 100,
        "page": 1,
        "sparkline": "false",
        "price_change_percentage": "24h"
    }
    try:
        resp = requests.get(url, params=params, timeout=15)
        resp.raise_for_status()
        data = resp.json()
        # Tambah symbol format Binance (BTC → BTCUSDT)
        for coin in data:
            sym = coin["symbol"].upper()
            coin["binance_symbol"] = f"{sym}USDT" if sym != "USDT" else None
        return data
    except Exception as e:
        print(f"[ERROR] CoinGecko fetch failed: {e}")
        return []

def fetch_binance_funding(symbols: List[str]) -> Dict[str, float]:
    """Ambil funding rate dari Binance Futures untuk symbol tertentu"""
    rates = {}
    for sym in symbols:
        try:
            url = f"{BINANCE_API}/fapi/v1/premiumIndex"
            resp = requests.get(url, params={"symbol": sym}, timeout=10)
            if resp.status_code == 200:
                d = resp.json()
                rates[sym] = float(d.get("lastFundingRate", 0)) * 100  # ke persen
            else:
                rates[sym] = None
        except Exception:
            rates[sym] = None
    return rates

def fetch_binance_oi(symbols: List[str]) -> Dict[str, float]:
    """Ambil open interest dari Binance Futures"""
    oi = {}
    for sym in symbols:
        try:
            url = f"{BINANCE_API}/fapi/v1/openInterest"
            resp = requests.get(url, params={"symbol": sym}, timeout=10)
            if resp.status_code == 200:
                d = resp.json()
                oi[sym] = float(d.get("openInterest", 0))
            else:
                oi[sym] = None
        except Exception:
            oi[sym] = None
    return oi

# ═══════════════════════════════════════════
# FILTERS
# ═══════════════════════════════════════════

def filter_candidates(coins: List[Dict]) -> List[Dict]:
    """
    Multi-pass filter:
      Pass 1: Volume + Volatility
      Pass 2: Funding Rate + Open Interest
      Pass 3: Rank by combo score → top 3-5
    """
    # Pass 1: Filter dasar
    passed = []
    for coin in coins:
        vol = coin.get("total_volume", 0) or 0
        change = coin.get("price_change_percentage_24h", 0) or 0
        sym = coin.get("binance_symbol")
        
        if not sym:
            continue
        if vol < MIN_VOLUME_USD:
            continue
        if abs(change) < MIN_VOLATILITY_24H:
            continue
        
        passed.append(coin)
    
    print(f"  Pass 1 (volume+volatility): {len(coins)} → {len(passed)}")
    
    # Pass 2: Funding Rate + OI (dari Binance)
    if passed:
        symbols = [c["binance_symbol"] for c in passed]
        funding_rates = fetch_binance_funding(symbols)
        oi_data = fetch_binance_oi(symbols)
        
        for coin in passed:
            sym = coin["binance_symbol"]
            fr = funding_rates.get(sym)
            oi = oi_data.get(sym)
            coin["funding_rate"] = fr
            coin["open_interest"] = oi
    
    # Pass 3: Scoring
    scored = []
    for coin in passed:
        score = 0
        vol = coin.get("total_volume", 0) or 0
        change = abs(coin.get("price_change_percentage_24h", 0) or 0)
        fr = coin.get("funding_rate")
        oi = coin.get("open_interest")
        
        # Volume score (semakin besar semakin baik)
        if vol > 500_000_000:
            score += 3
        elif vol > 200_000_000:
            score += 2
        elif vol > 100_000_000:
            score += 1
        
        # Volatility score
        if change > 5:
            score += 2
        elif change > 3:
            score += 1
        
        # Funding rate score (netral/negatif lebih aman buat long)
        if fr is not None:
            if abs(fr) < 0.01:
                score += 2  # netral
            elif abs(fr) < 0.03:
                score += 1
            # Fr > 0.05 gak dikasih score (warning)
        
        # Open Interest (bisa dipakai nanti buat konfirmasi)
        if oi and oi > 50_000_000:
            score += 1
        
        coin["pipeline_score"] = score
        scored.append(coin)
    
    # Sort by score, ambil top candidates
    scored.sort(key=lambda x: x["pipeline_score"], reverse=True)
    final = scored[:MAX_CANDIDATES]
    
    print(f"  Pass 2+3 (scoring): {len(passed)} → {len(final)} candidates")
    
    return final

# ═══════════════════════════════════════════
# REPORT
# ═══════════════════════════════════════════

def format_report(candidates: List[Dict]) -> str:
    """Format candidate list untuk dikirim ke pipeline / Telegram"""
    lines = ["**🔶 Crypto Scanner — Kandidat Pipeline**\n"]
    for i, c in enumerate(candidates, 1):
        sym = c.get("binance_symbol", "?")
        name = c.get("name", "?")
        price = c.get("current_price", 0)
        vol_b = c.get("total_volume", 0) / 1e9
        change = c.get("price_change_percentage_24h", 0)
        fr = c.get("funding_rate")
        oi_m = (c.get("open_interest", 0) or 0) / 1e6
        score = c.get("pipeline_score", 0)
        
        fr_str = f"{fr:.4f}%" if fr is not None else "N/A"
        oi_str = f"${oi_m:.0f}M" if oi_m else "N/A"
        
        lines.append(
            f"{i}. **{sym}** ({name})\n"
            f"   Harga: ${price:,.2f} | Vol: ${vol_b:.1f}B\n"
            f"   24h: {change:+.2f}% | FR: {fr_str} | OI: {oi_str}\n"
            f"   Score: {score}/10\n"
        )
    
    lines.append("_\n_")
    lines.append("Pipeline siap menerima kandidat. Kirim ke Technical Agent → ...")
    return "\n".join(lines)

# ═══════════════════════════════════════════
# MAIN
# ═══════════════════════════════════════════

def run_scan(save_json: bool = True) -> List[Dict]:
    """
    Main scan loop:
      1. Fetch Top 100 CoinGecko
      2. Filter by volume + volatility + funding rate + OI
      3. Return top 3-5 candidates
    
    Args:
        save_json: If True, save candidates to crypto_candidates.json untuk pipeline
    
    Returns:
        List of candidate dicts
    """
    print("🔶 Crypto Scanner — Starting...\n")
    
    # Step 1: Fetch
    coins = fetch_top_100()
    if not coins:
        print("[ERROR] No data from CoinGecko")
        return []
    print(f"  Step 1: {len(coins)} coins fetched from CoinGecko")
    
    # Step 2: Filter
    candidates = filter_candidates(coins)
    
    # Step 3: Report
    report = format_report(candidates)
    print(f"\n{report}\n")
    
    # Save for pipeline
    if save_json and candidates:
        output = []
        for c in candidates:
            output.append({
                "symbol": c.get("binance_symbol"),
                "name": c.get("name"),
                "price": c.get("current_price"),
                "volume_24h": c.get("total_volume"),
                "change_24h_pct": c.get("price_change_percentage_24h"),
                "funding_rate": c.get("funding_rate"),
                "open_interest": c.get("open_interest"),
                "market_cap": c.get("market_cap"),
                "pipeline_score": c.get("pipeline_score"),
                "timestamp": time.time()
            })
        
        with open("crypto_candidates.json", "w") as f:
            json.dump(output, f, indent=2)
        print(f"  ✅ Saved {len(output)} candidates to crypto_candidates.json")
    
    print("🔶 Crypto Scanner — Done")
    return candidates


if __name__ == "__main__":
    run_scan()

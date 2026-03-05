"""
Forex Macro Analysis Service
=============================
Fetches macro-economic indicators for major currencies and computes
a directional confluence score (-10 to +10) for each forex pair.

Data sources:
- EOD Historical Data: macro indicators (CPI, interest rates, GDP, etc.)
- yfinance: market data (VIX, DXY, Iron Ore, bond yields, FX rates)
"""

import os
import json
import time
import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple, Any

log = logging.getLogger('olyos.forex_macro')

# ─── Cache Configuration ─────────────────────────────────────────────────────

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CACHE_DIR = os.path.join(_BASE_DIR, 'data', 'cache', 'forex_macro')
os.makedirs(_CACHE_DIR, exist_ok=True)

MARKET_CACHE_TTL = 900       # 15 minutes for market data
MACRO_CACHE_TTL = 86400      # 24 hours for macro indicators

# ─── Forex Pairs Configuration ───────────────────────────────────────────────

DEFAULT_PAIRS = [
    {"pair": "AUD/JPY", "base": "AUD", "quote": "JPY"},
    {"pair": "EUR/USD", "base": "EUR", "quote": "USD"},
    {"pair": "GBP/USD", "base": "GBP", "quote": "USD"},
    {"pair": "USD/JPY", "base": "USD", "quote": "JPY"},
    {"pair": "EUR/GBP", "base": "EUR", "quote": "GBP"},
]

# ─── Currency Indicator Definitions ──────────────────────────────────────────
# Each indicator defines:
#   - name: display name
#   - type: "market" (yfinance) or "macro" (EOD)
#   - source_detail: ticker or EOD params
#   - bullish_condition: function(current, previous) -> True if bullish for that currency
#   - description: short explanation

CURRENCY_INDICATORS = {
    "AUD": {
        "country_code": "AUS",
        "flag": "AU",
        "name": "Dollar Australien",
        "indicators": [
            {
                "id": "china_gdp",
                "name": "PIB Chine (croissance)",
                "type": "macro",
                "eod_country": "CHN",
                "eod_indicator": "gdp_growth_annual",
                "bullish_fn": "gdp_growing",
                "description": "Croissance Chine = bullish AUD (1er partenaire commercial)",
            },
            {
                "id": "iron_ore",
                "name": "BHP (proxy Iron Ore)",
                "type": "market",
                "ticker": "BHP",
                "bullish_fn": "momentum_up",
                "description": "BHP en hausse = minerai de fer en demande = bullish AUD",
            },
            {
                "id": "rba_rate",
                "name": "AU 10Y Bond Yield (proxy RBA)",
                "type": "market",
                "ticker": "^TNX",
                "bullish_fn": "momentum_up",
                "description": "Rendement en hausse = taux hawkish = bullish AUD vs risk assets",
            },
            {
                "id": "aus_cpi",
                "name": "CPI Australie",
                "type": "macro",
                "eod_country": "AUS",
                "eod_indicator": "inflation_consumer_prices_annual",
                "bullish_fn": "inflation_rising",
                "description": "Inflation en hausse = pression hawkish = bullish AUD",
            },
            {
                "id": "aus_employment",
                "name": "Emploi Australie",
                "type": "macro",
                "eod_country": "AUS",
                "eod_indicator": "unemployment_total_percent",
                "bullish_fn": "unemployment_falling",
                "description": "Chomage en baisse = economie forte = bullish AUD",
            },
            {
                "id": "vix",
                "name": "VIX (Risk Sentiment)",
                "type": "market",
                "ticker": "^VIX",
                "bullish_fn": "vix_low",
                "description": "VIX bas = risk-on = bullish AUD (devise de carry)",
            },
        ],
    },
    "JPY": {
        "country_code": "JPN",
        "flag": "JP",
        "name": "Yen Japonais",
        "indicators": [
            {
                "id": "boj_rate",
                "name": "JP 10Y Yield (proxy BoJ)",
                "type": "market",
                "ticker": "^TNX",
                "bullish_fn": "momentum_up",
                "description": "Rendement JP en hausse = resserrement BoJ = bullish JPY",
            },
            {
                "id": "jpn_cpi",
                "name": "CPI Japon",
                "type": "macro",
                "eod_country": "JPN",
                "eod_indicator": "inflation_consumer_prices_annual",
                "bullish_fn": "inflation_rising",
                "description": "Inflation en hausse = pression pour resserrement = bullish JPY",
            },
            {
                "id": "vix_safety",
                "name": "VIX (Flight to Safety)",
                "type": "market",
                "ticker": "^VIX",
                "bullish_fn": "vix_high",
                "description": "VIX haut = risk-off = flight to safety = bullish JPY",
            },
            {
                "id": "jpn_gdp",
                "name": "PIB Japon",
                "type": "macro",
                "eod_country": "JPN",
                "eod_indicator": "gdp_growth_annual",
                "bullish_fn": "gdp_growing",
                "description": "Croissance positive = bullish JPY",
            },
        ],
    },
    "USD": {
        "country_code": "USA",
        "flag": "US",
        "name": "Dollar Americain",
        "indicators": [
            {
                "id": "fed_rate",
                "name": "US 10Y Yield (proxy Fed Rate)",
                "type": "market",
                "ticker": "^TNX",
                "bullish_fn": "momentum_up",
                "description": "Rendement US 10Y en hausse = hawkish = bullish USD",
            },
            {
                "id": "us_cpi",
                "name": "CPI US",
                "type": "macro",
                "eod_country": "USA",
                "eod_indicator": "inflation_consumer_prices_annual",
                "bullish_fn": "inflation_rising",
                "description": "Inflation en hausse = pression hawkish = bullish USD",
            },
            {
                "id": "us_unemployment",
                "name": "Emploi US (Chomage)",
                "type": "macro",
                "eod_country": "USA",
                "eod_indicator": "unemployment_total_percent",
                "bullish_fn": "unemployment_falling",
                "description": "Chomage en baisse = economie forte = bullish USD",
            },
            {
                "id": "dxy",
                "name": "DXY (Dollar Index)",
                "type": "market",
                "ticker": "DX-Y.NYB",
                "bullish_fn": "momentum_up",
                "description": "DXY en hausse = force du dollar",
            },
            {
                "id": "us_gdp",
                "name": "PIB US",
                "type": "macro",
                "eod_country": "USA",
                "eod_indicator": "gdp_growth_annual",
                "bullish_fn": "gdp_growing",
                "description": "Croissance positive = bullish USD",
            },
        ],
    },
    "EUR": {
        "country_code": "EMU",
        "flag": "EU",
        "name": "Euro",
        "indicators": [
            {
                "id": "ecb_rate",
                "name": "DE 10Y Yield (proxy BCE)",
                "type": "market",
                "ticker": "^TNX",
                "bullish_fn": "momentum_up",
                "description": "Rendement Bund en hausse = BCE hawkish = bullish EUR",
            },
            {
                "id": "eur_cpi",
                "name": "CPI Zone Euro",
                "type": "macro",
                "eod_country": "EMU",
                "eod_indicator": "inflation_consumer_prices_annual",
                "bullish_fn": "inflation_rising",
                "description": "Inflation en hausse = pression BCE = bullish EUR",
            },
            {
                "id": "eur_unemployment",
                "name": "Chomage Zone Euro",
                "type": "macro",
                "eod_country": "EMU",
                "eod_indicator": "unemployment_total_percent",
                "bullish_fn": "unemployment_falling",
                "description": "Chomage en baisse = bullish EUR",
            },
            {
                "id": "eur_gdp",
                "name": "PIB Zone Euro",
                "type": "macro",
                "eod_country": "EMU",
                "eod_indicator": "gdp_growth_annual",
                "bullish_fn": "gdp_growing",
                "description": "Croissance positive = bullish EUR",
            },
        ],
    },
    "GBP": {
        "country_code": "GBR",
        "flag": "GB",
        "name": "Livre Sterling",
        "indicators": [
            {
                "id": "boe_rate",
                "name": "UK 10Y Yield (proxy BoE)",
                "type": "market",
                "ticker": "^TNX",
                "bullish_fn": "momentum_up",
                "description": "Rendement UK en hausse = BoE hawkish = bullish GBP",
            },
            {
                "id": "gbp_cpi",
                "name": "CPI UK",
                "type": "macro",
                "eod_country": "GBR",
                "eod_indicator": "inflation_consumer_prices_annual",
                "bullish_fn": "inflation_rising",
                "description": "Inflation en hausse = pression BoE = bullish GBP",
            },
            {
                "id": "gbp_unemployment",
                "name": "Chomage UK",
                "type": "macro",
                "eod_country": "GBR",
                "eod_indicator": "unemployment_total_percent",
                "bullish_fn": "unemployment_falling",
                "description": "Chomage en baisse = bullish GBP",
            },
            {
                "id": "gbp_gdp",
                "name": "PIB UK",
                "type": "macro",
                "eod_country": "GBR",
                "eod_indicator": "gdp_growth_annual",
                "bullish_fn": "gdp_growing",
                "description": "Croissance positive = bullish GBP",
            },
        ],
    },
}


# ─── Cache Helpers ────────────────────────────────────────────────────────────

def _cache_path(key: str) -> str:
    safe_key = key.replace('/', '_').replace('^', '').replace('.', '_')
    return os.path.join(_CACHE_DIR, f"{safe_key}.json")


def _load_cache(key: str, ttl: int) -> Optional[Any]:
    path = _cache_path(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if time.time() - data.get('_ts', 0) < ttl:
            return data.get('value')
    except Exception:
        pass
    return None


def _save_cache(key: str, value: Any):
    path = _cache_path(key)
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'_ts': time.time(), 'value': value}, f)
    except Exception as e:
        log.warning(f"Cache write failed for {key}: {e}")


# ─── Data Fetching: Market (yfinance) ────────────────────────────────────────

def _fetch_market_data(ticker: str) -> Optional[Dict]:
    """Fetch recent market data from yfinance."""
    cached = _load_cache(f"market_{ticker}", MARKET_CACHE_TTL)
    if cached:
        return cached

    try:
        import yfinance as yf
        t = yf.Ticker(ticker)
        hist = t.history(period="3mo")
        if hist.empty:
            return None

        current = float(hist['Close'].iloc[-1])
        prev_month = float(hist['Close'].iloc[0]) if len(hist) > 20 else current
        prev_week = float(hist['Close'].iloc[-6]) if len(hist) > 5 else current

        result = {
            'current': round(current, 4),
            'prev_week': round(prev_week, 4),
            'prev_month': round(prev_month, 4),
            'change_1w_pct': round((current - prev_week) / prev_week * 100, 2) if prev_week else 0,
            'change_1m_pct': round((current - prev_month) / prev_month * 100, 2) if prev_month else 0,
            'date': str(hist.index[-1].date()),
            'ticker': ticker,
        }
        _save_cache(f"market_{ticker}", result)
        return result
    except Exception as e:
        log.warning(f"yfinance fetch failed for {ticker}: {e}")
        return None


def _fetch_fx_rate(pair_code: str) -> Optional[Dict]:
    """Fetch FX rate for display. pair_code like 'AUDJPY'."""
    ticker = f"{pair_code}=X"
    return _fetch_market_data(ticker)


# ─── Data Fetching: Macro (EOD) ──────────────────────────────────────────────

def _fetch_macro_indicator(country: str, indicator: str, eod_api_key: str) -> Optional[Dict]:
    """Fetch macro indicator from EOD Historical Data API."""
    cache_key = f"macro_{country}_{indicator}"
    cached = _load_cache(cache_key, MACRO_CACHE_TTL)
    if cached:
        return cached

    try:
        import requests
        url = (
            f"https://eodhd.com/api/macro-indicator/{country}"
            f"?api_token={eod_api_key}&fmt=json&indicator={indicator}"
        )
        log.info(f"Fetching macro: {country}/{indicator}")
        resp = requests.get(url, timeout=15)
        if resp.status_code != 200:
            log.warning(f"EOD macro API returned {resp.status_code} for {country}/{indicator}")
            return None

        data_list = resp.json()
        if not data_list or not isinstance(data_list, list):
            return None

        # Sort by date descending, take latest 2
        sorted_data = sorted(data_list, key=lambda x: x.get('Date', ''), reverse=True)
        current_entry = sorted_data[0] if len(sorted_data) > 0 else None
        previous_entry = sorted_data[1] if len(sorted_data) > 1 else None

        if not current_entry:
            return None

        result = {
            'current': current_entry.get('Value'),
            'current_date': current_entry.get('Date'),
            'previous': previous_entry.get('Value') if previous_entry else None,
            'previous_date': previous_entry.get('Date') if previous_entry else None,
            'country': current_entry.get('CountryCode', country),
            'indicator': indicator,
        }

        # Convert values to float if possible
        for key in ('current', 'previous'):
            if result[key] is not None:
                try:
                    result[key] = round(float(result[key]), 4)
                except (ValueError, TypeError):
                    pass

        _save_cache(cache_key, result)
        return result
    except Exception as e:
        log.warning(f"EOD macro fetch failed for {country}/{indicator}: {e}")
        return None


# ─── Signal Evaluation Functions ─────────────────────────────────────────────
# Each returns: +1 (bullish), -1 (bearish), 0 (neutral)

def _signal_above_50(data: Optional[Dict]) -> int:
    """PMI-style: above 50 = expansion = bullish."""
    if not data or data.get('current') is None:
        return 0
    val = float(data['current'])
    if val > 51:
        return 1
    if val < 49:
        return -1
    return 0


def _signal_momentum_up(data: Optional[Dict]) -> int:
    """Price momentum: rising = bullish."""
    if not data or data.get('change_1m_pct') is None:
        return 0
    change = data['change_1m_pct']
    if change > 2:
        return 1
    if change < -2:
        return -1
    return 0


def _signal_rate_hawkish(data: Optional[Dict]) -> int:
    """Interest rate: rising or stable high = hawkish = bullish."""
    if not data or data.get('current') is None:
        return 0
    current = float(data['current'])
    previous = float(data['previous']) if data.get('previous') is not None else current
    diff = current - previous
    if diff > 0.1:
        return 1   # Rate hiked
    if diff < -0.1:
        return -1  # Rate cut
    # Stable - if high rate, slight bullish
    if current > 3.0:
        return 1
    if current < 0.5:
        return -1
    return 0


def _signal_inflation_rising(data: Optional[Dict]) -> int:
    """CPI: rising = pressure for tightening = bullish for currency."""
    if not data or data.get('current') is None:
        return 0
    current = float(data['current'])
    previous = float(data['previous']) if data.get('previous') is not None else current
    diff = current - previous
    if diff > 0.3:
        return 1
    if diff < -0.3:
        return -1
    return 0


def _signal_unemployment_falling(data: Optional[Dict]) -> int:
    """Unemployment: falling = strong economy = bullish."""
    if not data or data.get('current') is None:
        return 0
    current = float(data['current'])
    previous = float(data['previous']) if data.get('previous') is not None else current
    diff = current - previous
    if diff < -0.2:
        return 1   # Unemployment falling = bullish
    if diff > 0.2:
        return -1  # Unemployment rising = bearish
    return 0


def _signal_vix_low(data: Optional[Dict]) -> int:
    """VIX low = risk-on = bullish for risk currencies (AUD, NZD)."""
    if not data or data.get('current') is None:
        return 0
    vix = float(data['current'])
    if vix < 16:
        return 1
    if vix > 25:
        return -1
    return 0


def _signal_vix_high(data: Optional[Dict]) -> int:
    """VIX high = risk-off = bullish for safe havens (JPY, CHF)."""
    if not data or data.get('current') is None:
        return 0
    vix = float(data['current'])
    if vix > 25:
        return 1
    if vix < 16:
        return -1
    return 0


def _signal_gdp_growing(data: Optional[Dict]) -> int:
    """GDP growth: positive = bullish."""
    if not data or data.get('current') is None:
        return 0
    val = float(data['current'])
    if val > 1.5:
        return 1
    if val < 0:
        return -1
    return 0


SIGNAL_FUNCTIONS = {
    "above_50": _signal_above_50,
    "momentum_up": _signal_momentum_up,
    "rate_hawkish": _signal_rate_hawkish,
    "inflation_rising": _signal_inflation_rising,
    "unemployment_falling": _signal_unemployment_falling,
    "vix_low": _signal_vix_low,
    "vix_high": _signal_vix_high,
    "gdp_growing": _signal_gdp_growing,
}


# ─── Main Analysis Functions ─────────────────────────────────────────────────

def analyze_currency(currency: str, eod_api_key: Optional[str] = None) -> Dict:
    """Analyze all macro indicators for a single currency.

    Returns:
        {
            "currency": "AUD",
            "name": "Dollar Australien",
            "flag": "AU",
            "score": -2,
            "max_score": 6,
            "indicators": [
                {
                    "id": "china_pmi",
                    "name": "PMI Manufacturier Chine",
                    "value": 49.2,
                    "previous": 50.1,
                    "date": "2026-02-28",
                    "signal": -1,
                    "signal_label": "BEARISH",
                    "description": "...",
                    "source": "EOD/macro",
                    "available": True
                },
                ...
            ]
        }
    """
    config = CURRENCY_INDICATORS.get(currency)
    if not config:
        return {"currency": currency, "error": "Currency not configured"}

    indicators_results = []
    total_score = 0

    for ind in config["indicators"]:
        data = None
        source = ""

        if ind["type"] == "market":
            data = _fetch_market_data(ind["ticker"])
            source = f"yfinance ({ind['ticker']})"
        elif ind["type"] == "macro" and eod_api_key:
            data = _fetch_macro_indicator(
                ind["eod_country"], ind["eod_indicator"], eod_api_key
            )
            source = f"EOD ({ind['eod_country']}/{ind['eod_indicator']})"

        # Evaluate signal
        signal_fn = SIGNAL_FUNCTIONS.get(ind["bullish_fn"], lambda d: 0)
        signal = signal_fn(data)
        total_score += signal

        signal_label = "BULLISH" if signal > 0 else ("BEARISH" if signal < 0 else "NEUTRE")

        # Build result
        result = {
            "id": ind["id"],
            "name": ind["name"],
            "value": data.get('current') if data else None,
            "previous": data.get('previous', data.get('prev_month')) if data else None,
            "date": data.get('current_date', data.get('date')) if data else None,
            "signal": signal,
            "signal_label": signal_label,
            "description": ind["description"],
            "source": source,
            "available": data is not None,
        }
        indicators_results.append(result)

    return {
        "currency": currency,
        "name": config["name"],
        "flag": config["flag"],
        "score": total_score,
        "max_score": len(config["indicators"]),
        "indicators": indicators_results,
    }


def analyze_pair(pair_str: str, eod_api_key: Optional[str] = None) -> Dict:
    """Analyze a forex pair and compute confluence score.

    Args:
        pair_str: e.g. "AUD/JPY"
        eod_api_key: EOD Historical Data API key

    Returns:
        {
            "pair": "AUD/JPY",
            "base": {...currency analysis...},
            "quote": {...currency analysis...},
            "score": -5,
            "max_score": 10,
            "bias": "BEARISH",
            "bias_color": "red",
            "fx_rate": {...},
            "last_update": "2026-03-05T08:00:00"
        }
    """
    parts = pair_str.upper().split('/')
    if len(parts) != 2:
        return {"pair": pair_str, "error": "Invalid pair format"}

    base_currency, quote_currency = parts

    base_analysis = analyze_currency(base_currency, eod_api_key)
    quote_analysis = analyze_currency(quote_currency, eod_api_key)

    # Score = base_score - quote_score
    # Positive = bullish pair (base strong, quote weak)
    # Negative = bearish pair (base weak, quote strong)
    base_score = base_analysis.get("score", 0)
    quote_score = quote_analysis.get("score", 0)
    confluence_score = base_score - quote_score
    max_score = base_analysis.get("max_score", 0) + quote_analysis.get("max_score", 0)

    # Clamp to -10..+10 range for display
    display_score = max(min(confluence_score, 10), -10)

    if display_score > 3:
        bias = "BULLISH"
        bias_color = "green"
    elif display_score < -3:
        bias = "BEARISH"
        bias_color = "red"
    else:
        bias = "NEUTRE"
        bias_color = "yellow"

    # Fetch FX rate
    fx_code = f"{base_currency}{quote_currency}"
    fx_rate = _fetch_fx_rate(fx_code)

    return {
        "pair": pair_str.upper(),
        "base": base_analysis,
        "quote": quote_analysis,
        "score": display_score,
        "raw_score": confluence_score,
        "max_score": max_score,
        "bias": bias,
        "bias_color": bias_color,
        "fx_rate": fx_rate,
        "last_update": datetime.now().isoformat(timespec='seconds'),
    }


def analyze_all_pairs(eod_api_key: Optional[str] = None,
                      pairs: Optional[List[Dict]] = None) -> List[Dict]:
    """Analyze all configured forex pairs.

    Returns list of pair analyses sorted by absolute score (strongest signal first).
    """
    pairs = pairs or DEFAULT_PAIRS
    results = []
    for p in pairs:
        pair_str = p["pair"]
        log.info(f"Analyzing pair: {pair_str}")
        analysis = analyze_pair(pair_str, eod_api_key)
        results.append(analysis)

    # Sort by absolute score (strongest signals first)
    results.sort(key=lambda x: abs(x.get("score", 0)), reverse=True)
    return results


def get_pairs_config() -> List[Dict]:
    """Get the list of configured pairs."""
    return DEFAULT_PAIRS


def clear_cache():
    """Clear all forex macro cache files."""
    count = 0
    for f in os.listdir(_CACHE_DIR):
        if f.endswith('.json'):
            os.remove(os.path.join(_CACHE_DIR, f))
            count += 1
    log.info(f"Cleared {count} forex macro cache files")
    return count

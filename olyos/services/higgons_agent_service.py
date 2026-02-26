"""
Higgons Agent Service

Multi-source agent that computes and updates Higgons scores
(PER, ROE, Dette, Small Cap, Momentum) for portfolio stocks.

Sources:
1. Yahoo Finance (yfinance) — live market data
2. PDF upload (pdfplumber + Claude API) — analyst report parsing
3. EOD Historical Data — fundamentals API
"""

import os
import json
import time
import math
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List, Tuple

from olyos.logger import get_logger

log = get_logger('higgons_agent')

# Cache directory (same location as other caches)
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'data')
CACHE_DIR = os.path.join(_DATA_DIR, 'cache')
SCORES_HISTORY_FILE = os.path.join(CACHE_DIR, 'higgons_scores_history.json')


# ============================================================================
# Cache management
# ============================================================================

def load_scores_history() -> Dict[str, Any]:
    """Load cached Higgons scores history."""
    try:
        if os.path.exists(SCORES_HISTORY_FILE):
            with open(SCORES_HISTORY_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
    except Exception as e:
        log.error(f"Error loading scores history: {e}")
    return {}


def save_scores_history(data: Dict[str, Any]):
    """Save Higgons scores to cache file."""
    try:
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(SCORES_HISTORY_FILE, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False, default=str)
    except Exception as e:
        log.error(f"Error saving scores history: {e}")


# ============================================================================
# Yahoo Finance ticker resolution
# ============================================================================

# European exchange suffixes to try when resolving a bare ticker
EXCHANGE_SUFFIXES = [
    ".PA",   # Euronext Paris
    ".CO",   # Copenhagen (Denmark)
    ".ST",   # Stockholm (Sweden)
    ".OL",   # Oslo (Norway)
    ".HE",   # Helsinki (Finland)
    ".AS",   # Amsterdam
    ".BR",   # Brussels
    ".DE",   # Frankfurt / Xetra
    ".MI",   # Milan
    ".MC",   # Madrid
    ".LS",   # Lisbon
    ".SW",   # Zurich
    ".L",    # London LSE
    "",      # US (no suffix)
]


def resolve_yahoo_ticker(base_ticker: str) -> Tuple[str, dict]:
    """
    Try multiple exchange suffixes to find a valid Yahoo Finance ticker.
    Returns (resolved_ticker, info_dict).

    A ticker is considered valid if Yahoo returns a name AND a price.
    If base_ticker already contains a '.', it is tested first as-is.
    """
    try:
        import yfinance as yf
    except ImportError:
        log.warning("yfinance not installed")
        return base_ticker, {}

    candidates = []

    # If the ticker already has a suffix, test it first
    if "." in base_ticker:
        candidates.append(base_ticker)

    # Then try all suffix combinations with the bare name
    clean = base_ticker.split(".")[0].upper()
    for suffix in EXCHANGE_SUFFIXES:
        candidate = clean + suffix
        if candidate not in candidates:
            candidates.append(candidate)

    for candidate in candidates:
        try:
            stock = yf.Ticker(candidate)
            info = stock.info or {}
            has_name = bool(info.get("longName") or info.get("shortName"))
            has_price = bool(
                info.get("currentPrice")
                or info.get("regularMarketPrice")
                or info.get("previousClose")
            )
            if has_name and has_price:
                log.info(f"Ticker resolved: {base_ticker} -> {candidate}")
                return candidate, info
        except Exception:
            continue

    log.warning(f"Could not resolve ticker: {base_ticker}")
    return base_ticker, {}


# ============================================================================
# Yahoo Finance data fetching
# ============================================================================

def fetch_yahoo_data(ticker: str) -> Dict[str, Any]:
    """
    Fetch live financial data from Yahoo Finance.
    Uses resolve_yahoo_ticker() to automatically find the right exchange suffix.
    Returns dict with PER, ROE, debt ratios, market cap, momentum data.
    """
    try:
        import yfinance as yf
    except ImportError:
        log.warning("yfinance not installed")
        return {'error': 'yfinance not installed', 'source': 'yahoo'}

    try:
        # Smart ticker resolution
        resolved_ticker, info = resolve_yahoo_ticker(ticker)
        if not info:
            stock = yf.Ticker(resolved_ticker)
            info = stock.info or {}

        # Price / momentum data
        current_price = info.get('currentPrice') or info.get('regularMarketPrice', 0)
        high_52w = info.get('fiftyTwoWeekHigh', 0)
        low_52w = info.get('fiftyTwoWeekLow', 0)
        sma_50 = info.get('fiftyDayAverage', 0)
        sma_200 = info.get('twoHundredDayAverage', 0)

        # Valuation
        pe_trailing = info.get('trailingPE')
        pe_forward = info.get('forwardPE')

        # Profitability
        roe_raw = info.get('returnOnEquity')
        roe = (roe_raw * 100) if roe_raw and abs(roe_raw) < 5 else roe_raw

        # Debt
        debt_to_equity = info.get('debtToEquity')  # in % (e.g. 45.0 = 45%)
        total_debt = info.get('totalDebt', 0)
        total_cash = info.get('totalCash', 0)
        ebitda = info.get('ebitda', 0)

        net_debt = (total_debt or 0) - (total_cash or 0)
        net_debt_ebitda = None
        if ebitda and ebitda > 0:
            net_debt_ebitda = round(net_debt / ebitda, 2)

        # Size
        market_cap = info.get('marketCap', 0)

        # Momentum: distance from 52w high
        momentum_pct = None
        if current_price and high_52w and high_52w > 0:
            momentum_pct = round(((current_price - high_52w) / high_52w) * 100, 2)

        return {
            'source': 'yahoo',
            'ticker': resolved_ticker,
            'resolved_ticker': resolved_ticker,
            'name': info.get('shortName') or info.get('longName', ticker),
            'currency': info.get('currency', 'EUR'),
            'current_price': current_price,
            'market_cap': market_cap,
            'pe_trailing': pe_trailing,
            'pe_forward': pe_forward,
            'roe': roe,
            'debt_to_equity': debt_to_equity,
            'net_debt_ebitda': net_debt_ebitda,
            'total_debt': total_debt,
            'total_cash': total_cash,
            'ebitda': ebitda,
            'high_52w': high_52w,
            'low_52w': low_52w,
            'sma_50': sma_50,
            'sma_200': sma_200,
            'momentum_pct': momentum_pct,
            'sector': info.get('sector', ''),
            'industry': info.get('industry', ''),
            'fetched_at': datetime.now().isoformat(),
        }
    except Exception as e:
        log.error(f"Yahoo Finance error for {ticker}: {e}")
        return {'error': str(e), 'source': 'yahoo', 'ticker': ticker, 'resolved_ticker': ticker}


# ============================================================================
# EOD Historical Data fetching
# ============================================================================

def fetch_eod_data(ticker: str, api_key: str) -> Dict[str, Any]:
    """
    Fetch fundamentals from EOD Historical Data API.
    Complements Yahoo data with additional ratios.
    """
    if not api_key:
        return {'error': 'EOD API key not configured', 'source': 'eod'}

    try:
        import requests
    except ImportError:
        return {'error': 'requests not installed', 'source': 'eod'}

    try:
        # Convert ticker format: RWM.PA → RWM.PA (EOD uses same format for Euronext)
        eod_ticker = ticker
        if '.' not in ticker:
            eod_ticker = ticker + '.PA'

        url = f"https://eodhd.com/api/fundamentals/{eod_ticker}"
        params = {'api_token': api_key, 'fmt': 'json'}

        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code != 200:
            return {'error': f'EOD API returned {resp.status_code}', 'source': 'eod'}

        data = resp.json()
        highlights = data.get('Highlights', {})
        valuation = data.get('Valuation', {})
        balance = data.get('Balance_Sheet', {})

        return {
            'source': 'eod',
            'ticker': ticker,
            'name': data.get('General', {}).get('Name', ''),
            'pe_trailing': highlights.get('PERatio'),
            'pe_forward': highlights.get('ForwardPE'),
            'roe': _safe_pct(highlights.get('ReturnOnEquityTTM')),
            'profit_margin': _safe_pct(highlights.get('ProfitMargin')),
            'market_cap': highlights.get('MarketCapitalization'),
            'debt_to_equity': valuation.get('DebtToEquity'),
            'ev_ebitda': highlights.get('EVToEBITDA') or valuation.get('EnterpriseValueEbitda'),
            'dividend_yield': _safe_pct(highlights.get('DividendYield')),
            'revenue_growth': _safe_pct(highlights.get('RevenueGrowthYearlyTTM')),
            'earnings_growth': _safe_pct(highlights.get('EarningsGrowthYearlyTTM')),
            'fetched_at': datetime.now().isoformat(),
        }
    except Exception as e:
        log.error(f"EOD API error for {ticker}: {e}")
        return {'error': str(e), 'source': 'eod', 'ticker': ticker}


def _safe_pct(val) -> Optional[float]:
    """Convert a ratio (0.15) or percentage (15.0) to percentage."""
    if val is None:
        return None
    try:
        v = float(val)
        if abs(v) < 5:  # likely a ratio like 0.15
            return round(v * 100, 2)
        return round(v, 2)
    except (ValueError, TypeError):
        return None


# ============================================================================
# PDF parsing with pdfplumber + Claude
# ============================================================================

def parse_pdf_report(pdf_bytes: bytes, ticker: str, anthropic_api_key: str) -> Dict[str, Any]:
    """
    Parse an analyst PDF report using pdfplumber for text extraction
    and Claude API for structured data extraction.

    Returns extracted financial metrics (PER, ROE, debt, etc.)
    """
    if not anthropic_api_key:
        return {'error': 'Anthropic API key not configured', 'source': 'pdf'}

    try:
        import pdfplumber
    except ImportError:
        return {'error': 'pdfplumber not installed. Run: pip install pdfplumber', 'source': 'pdf'}

    try:
        import anthropic
    except ImportError:
        return {'error': 'anthropic not installed', 'source': 'pdf'}

    # Step 1: Extract text from PDF
    try:
        import io
        pdf_text = ""
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            for page in pdf.pages[:20]:  # limit to 20 pages
                text = page.extract_text()
                if text:
                    pdf_text += text + "\n\n"

            # Also extract tables
            tables_text = ""
            for page in pdf.pages[:20]:
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        cells = [str(c or '') for c in row]
                        tables_text += " | ".join(cells) + "\n"
                    tables_text += "\n"

        if not pdf_text and not tables_text:
            return {'error': 'No text extracted from PDF', 'source': 'pdf'}

        full_text = pdf_text
        if tables_text:
            full_text += "\n\n=== TABLES ===\n" + tables_text

        # Limit text length for API call
        if len(full_text) > 30000:
            full_text = full_text[:30000] + "\n...[truncated]"

    except Exception as e:
        log.error(f"PDF text extraction error: {e}")
        return {'error': f'PDF extraction failed: {str(e)}', 'source': 'pdf'}

    # Step 2: Use Claude to extract structured metrics
    try:
        client = anthropic.Anthropic(api_key=anthropic_api_key)

        prompt = f"""Analyse ce rapport d'analyste financier pour le ticker {ticker}.

Extrais les métriques financières suivantes en format JSON strict :
{{
    "per_current": <PER actuel ou estimé, nombre ou null>,
    "per_forward": <PER forward/estimé année prochaine, nombre ou null>,
    "roe": <ROE en pourcentage (ex: 15.5), nombre ou null>,
    "net_debt_ebitda": <Dette nette / EBITDA, nombre ou null>,
    "debt_to_equity": <Gearing ou D/E en pourcentage, nombre ou null>,
    "market_cap_meur": <Capitalisation en millions EUR, nombre ou null>,
    "revenue_growth": <Croissance CA en %, nombre ou null>,
    "earnings_growth": <Croissance bénéfice en %, nombre ou null>,
    "target_price": <Objectif de cours de l'analyste, nombre ou null>,
    "recommendation": <"Acheter"/"Conserver"/"Vendre"/null>,
    "analyst_firm": <Nom du bureau d'analyse, string ou null>,
    "report_date": <Date du rapport YYYY-MM-DD, string ou null>,
    "notes": <Résumé en 2 phrases des points clés>
}}

IMPORTANT: Réponds UNIQUEMENT avec le JSON, sans texte autour.

=== CONTENU DU RAPPORT ===
{full_text}"""

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1500,
            messages=[{"role": "user", "content": prompt}]
        )

        response_text = response.content[0].text.strip()

        # Parse JSON from response (handle potential markdown wrapping)
        if response_text.startswith('```'):
            lines = response_text.split('\n')
            json_lines = [l for l in lines if not l.startswith('```')]
            response_text = '\n'.join(json_lines)

        extracted = json.loads(response_text)
        extracted['source'] = 'pdf'
        extracted['ticker'] = ticker
        extracted['extracted_at'] = datetime.now().isoformat()
        return extracted

    except json.JSONDecodeError as e:
        log.error(f"Claude returned invalid JSON for {ticker}: {e}")
        return {'error': 'Failed to parse Claude response as JSON', 'source': 'pdf', 'raw_response': response_text[:500]}
    except Exception as e:
        log.error(f"Claude API error for PDF parsing: {e}")
        return {'error': str(e), 'source': 'pdf'}


# ============================================================================
# Higgons Score Computation
# ============================================================================

def compute_higgons_score(data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Compute Higgons-style score from financial data.

    Criteria (William Higgons methodology):
    1. PER: Low PER preferred (value investing)
    2. ROE: High ROE preferred (quality)
    3. Debt: Low debt preferred (safety)
    4. Small Cap: Smaller companies get bonus (inefficiency premium)
    5. Momentum: Price momentum relative to 52w range

    Each criterion scored 0-5, total out of 25.
    """
    scores = {}
    details = {}

    # --- 1. PER Score (0-5) ---
    per = data.get('pe_trailing') or data.get('pe_forward') or data.get('per_current')
    if per and isinstance(per, (int, float)) and per > 0:
        if per < 8:
            scores['per'] = 5
        elif per < 12:
            scores['per'] = 4
        elif per < 16:
            scores['per'] = 3
        elif per < 22:
            scores['per'] = 2
        elif per < 30:
            scores['per'] = 1
        else:
            scores['per'] = 0
        details['per'] = f"PER = {per:.1f}"
    else:
        scores['per'] = 0
        details['per'] = "PER non disponible"

    # --- 2. ROE Score (0-5) ---
    roe = data.get('roe')
    if roe and isinstance(roe, (int, float)):
        if roe > 25:
            scores['roe'] = 5
        elif roe > 18:
            scores['roe'] = 4
        elif roe > 12:
            scores['roe'] = 3
        elif roe > 7:
            scores['roe'] = 2
        elif roe > 0:
            scores['roe'] = 1
        else:
            scores['roe'] = 0
        details['roe'] = f"ROE = {roe:.1f}%"
    else:
        scores['roe'] = 0
        details['roe'] = "ROE non disponible"

    # --- 3. Debt Score (0-5) ---
    # Prefer net_debt/ebitda, fallback to debt_to_equity
    net_debt_ebitda = data.get('net_debt_ebitda')
    debt_to_equity = data.get('debt_to_equity')

    if net_debt_ebitda is not None and isinstance(net_debt_ebitda, (int, float)):
        if net_debt_ebitda < 0:  # net cash
            scores['dette'] = 5
        elif net_debt_ebitda < 1:
            scores['dette'] = 4
        elif net_debt_ebitda < 2:
            scores['dette'] = 3
        elif net_debt_ebitda < 3:
            scores['dette'] = 2
        elif net_debt_ebitda < 4:
            scores['dette'] = 1
        else:
            scores['dette'] = 0
        details['dette'] = f"DN/EBITDA = {net_debt_ebitda:.1f}x"
    elif debt_to_equity is not None and isinstance(debt_to_equity, (int, float)):
        dte = debt_to_equity
        if dte < 20:
            scores['dette'] = 5
        elif dte < 50:
            scores['dette'] = 4
        elif dte < 80:
            scores['dette'] = 3
        elif dte < 120:
            scores['dette'] = 2
        elif dte < 200:
            scores['dette'] = 1
        else:
            scores['dette'] = 0
        details['dette'] = f"D/E = {dte:.0f}%"
    else:
        scores['dette'] = 0
        details['dette'] = "Dette non disponible"

    # --- 4. Small Cap Score (0-5) ---
    market_cap = data.get('market_cap') or 0
    market_cap_meur = data.get('market_cap_meur')
    if market_cap_meur:
        mc = market_cap_meur * 1e6  # convert to EUR
    else:
        mc = market_cap

    if mc and mc > 0:
        mc_b = mc / 1e9  # in billions
        if mc_b < 0.15:      # micro cap < 150M
            scores['small_cap'] = 5
        elif mc_b < 0.5:     # small cap < 500M
            scores['small_cap'] = 4
        elif mc_b < 1.5:     # mid-small < 1.5B
            scores['small_cap'] = 3
        elif mc_b < 5:       # mid cap < 5B
            scores['small_cap'] = 2
        elif mc_b < 15:      # large cap < 15B
            scores['small_cap'] = 1
        else:                 # mega cap
            scores['small_cap'] = 0
        details['small_cap'] = f"Cap = {_format_cap(mc)}"
    else:
        scores['small_cap'] = 0
        details['small_cap'] = "Cap non disponible"

    # --- 5. Momentum Score (0-5) ---
    momentum_pct = data.get('momentum_pct')
    sma_50 = data.get('sma_50')
    sma_200 = data.get('sma_200')
    current_price = data.get('current_price', 0)

    if momentum_pct is not None:
        # Distance from 52w high (0% = at high, -50% = half the high)
        if momentum_pct > -5:
            scores['momentum'] = 5
        elif momentum_pct > -15:
            scores['momentum'] = 4
        elif momentum_pct > -25:
            scores['momentum'] = 3
        elif momentum_pct > -35:
            scores['momentum'] = 2
        elif momentum_pct > -50:
            scores['momentum'] = 1
        else:
            scores['momentum'] = 0
        details['momentum'] = f"vs 52w high: {momentum_pct:+.1f}%"
    elif current_price and sma_200 and sma_200 > 0:
        # Fallback: price vs SMA200
        ratio = (current_price / sma_200 - 1) * 100
        if ratio > 15:
            scores['momentum'] = 5
        elif ratio > 5:
            scores['momentum'] = 4
        elif ratio > -5:
            scores['momentum'] = 3
        elif ratio > -15:
            scores['momentum'] = 2
        elif ratio > -30:
            scores['momentum'] = 1
        else:
            scores['momentum'] = 0
        details['momentum'] = f"vs SMA200: {ratio:+.1f}%"
    else:
        scores['momentum'] = 0
        details['momentum'] = "Momentum non disponible"

    total = sum(scores.values())
    max_score = 25

    # Grade
    if total >= 20:
        grade = 'A'
    elif total >= 16:
        grade = 'B'
    elif total >= 12:
        grade = 'C'
    elif total >= 8:
        grade = 'D'
    else:
        grade = 'E'

    return {
        'scores': scores,
        'details': details,
        'total': total,
        'max': max_score,
        'grade': grade,
        'pct': round(total / max_score * 100, 1),
    }


# ============================================================================
# AI Brief generation
# ============================================================================

def generate_brief(
    result_data: Dict[str, Any],
    higgons_data: Dict[str, Any],
    anthropic_api_key: Optional[str] = None,
    pdf_data: Optional[Dict[str, Any]] = None,
) -> str:
    """
    Generate a short investment brief (~120 words) via Claude API.
    Summarises the Higgons score, strengths, weaknesses, and PDF reco if any.
    """
    if not anthropic_api_key:
        return ""

    try:
        import anthropic
    except ImportError:
        return ""

    company = result_data.get('name', result_data.get('ticker', ''))
    ticker = result_data.get('ticker', '')
    scores = higgons_data.get('scores', {})
    details = higgons_data.get('details', {})
    total = higgons_data.get('total', 0)
    grade = higgons_data.get('grade', '?')

    criteria_lines = []
    label_map = {'per': 'PER', 'roe': 'ROE', 'dette': 'Dette', 'small_cap': 'Small Cap', 'momentum': 'Momentum'}
    for key in ['per', 'roe', 'dette', 'small_cap', 'momentum']:
        val = scores.get(key, 0)
        detail = details.get(key, '')
        status = 'OK' if val >= 3 else ('MOYEN' if val >= 2 else 'FAIBLE')
        criteria_lines.append(f"- {label_map[key]}: {val}/5 ({detail}) -> {status}")

    criteria_summary = "\n".join(criteria_lines)

    pdf_context = ""
    if pdf_data:
        parts = []
        if pdf_data.get('analyst_firm'):
            parts.append(f"Bureau: {pdf_data['analyst_firm']}")
        if pdf_data.get('recommendation'):
            parts.append(f"Reco: {pdf_data['recommendation']}")
        if pdf_data.get('target_price'):
            parts.append(f"Objectif: {pdf_data['target_price']} EUR")
        if pdf_data.get('notes'):
            parts.append(f"Notes: {pdf_data['notes']}")
        if parts:
            pdf_context = f"\nRapport analyste:\n" + "\n".join(f"- {p}" for p in parts) + "\n"

    prompt = f"""Tu es un analyste financier expert en value investing (methode Higgons).
Redige un brief d'investissement TRES CONCIS (~120 mots max) sur {company} ({ticker}).

Score Higgons : {total}/25 — Grade : {grade}

Criteres :
{criteria_summary}
{pdf_context}
Format attendu :
- 1 phrase de synthese sur le profil global
- Points forts Higgons (criteres valides)
- Points de vigilance (criteres echoues ou limites)
- 1 phrase de conclusion sur le timing/opportunite

Ton: professionnel, factuel, Bloomberg-style. Pas de mise en forme markdown. Texte brut uniquement."""

    try:
        client = anthropic.Anthropic(api_key=anthropic_api_key)
        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=300,
            messages=[{"role": "user", "content": prompt}]
        )
        return response.content[0].text.strip()
    except Exception as e:
        log.error(f"Brief generation error for {ticker}: {e}")
        return ""


def _format_cap(mc: float) -> str:
    """Format market cap in human-readable form."""
    if mc >= 1e9:
        return f"{mc/1e9:.1f}B"
    elif mc >= 1e6:
        return f"{mc/1e6:.0f}M"
    else:
        return f"{mc:,.0f}"


# ============================================================================
# Main analysis functions
# ============================================================================

def analyze_ticker(
    ticker: str,
    eod_api_key: Optional[str] = None,
    anthropic_api_key: Optional[str] = None,
    force_refresh: bool = False,
) -> Dict[str, Any]:
    """
    Analyze a single ticker using all available data sources.
    Merges data from Yahoo + EOD, computes Higgons score.

    Returns complete analysis result.
    """
    log.info(f"Analyzing {ticker}...")

    # Check cache first (unless force refresh)
    if not force_refresh:
        history = load_scores_history()
        cached = history.get(ticker)
        if cached:
            cached_at = cached.get('analyzed_at', '')
            try:
                cached_dt = datetime.fromisoformat(cached_at)
                if datetime.now() - cached_dt < timedelta(hours=12):
                    # Backfill brief if missing (cache predates brief feature)
                    if not cached.get('brief') and anthropic_api_key:
                        log.info(f"Backfilling brief for cached {ticker}")
                        cached['brief'] = generate_brief(
                            result_data=cached,
                            higgons_data=cached.get('higgons', {}),
                            anthropic_api_key=anthropic_api_key,
                            pdf_data=cached.get('pdf_data'),
                        )
                        history[ticker] = cached
                        save_scores_history(history)
                    log.info(f"Using cached analysis for {ticker} (from {cached_at})")
                    cached['from_cache'] = True
                    return cached
            except (ValueError, TypeError):
                pass

    # Fetch from all sources
    merged = {'ticker': ticker}

    # Source 1: Yahoo Finance (with auto-resolution)
    yahoo = fetch_yahoo_data(ticker)
    resolved_ticker = yahoo.get('resolved_ticker', ticker)
    if 'error' not in yahoo:
        merged.update({k: v for k, v in yahoo.items() if v is not None})
        log.info(f"  Yahoo OK for {resolved_ticker}")
    else:
        log.warning(f"  Yahoo failed for {ticker}: {yahoo.get('error')}")

    # Source 2: EOD Historical Data
    if eod_api_key:
        eod = fetch_eod_data(ticker, eod_api_key)
        if 'error' not in eod:
            # Merge EOD data (only fill gaps, don't override Yahoo)
            for key in ['pe_trailing', 'pe_forward', 'roe', 'debt_to_equity',
                        'market_cap', 'profit_margin', 'ev_ebitda',
                        'dividend_yield', 'revenue_growth', 'earnings_growth']:
                if eod.get(key) is not None and merged.get(key) is None:
                    merged[key] = eod[key]
            log.info(f"  EOD OK for {ticker}")
        else:
            log.warning(f"  EOD failed for {ticker}: {eod.get('error')}")

    # Compute Higgons score
    higgons = compute_higgons_score(merged)

    result = {
        'ticker': resolved_ticker,
        'original_ticker': ticker,
        'resolved_ticker': resolved_ticker,
        'name': merged.get('name', ticker),
        'current_price': merged.get('current_price'),
        'currency': merged.get('currency', 'EUR'),
        'market_cap': merged.get('market_cap'),
        'sector': merged.get('sector', ''),
        'industry': merged.get('industry', ''),
        'pe_trailing': merged.get('pe_trailing'),
        'pe_forward': merged.get('pe_forward'),
        'roe': merged.get('roe'),
        'debt_to_equity': merged.get('debt_to_equity'),
        'net_debt_ebitda': merged.get('net_debt_ebitda'),
        'momentum_pct': merged.get('momentum_pct'),
        'high_52w': merged.get('high_52w'),
        'low_52w': merged.get('low_52w'),
        'higgons': higgons,
        'sources': {
            'yahoo': 'error' not in yahoo,
            'eod': eod_api_key is not None and 'error' not in (eod if eod_api_key else {'error': True}),
        },
        'analyzed_at': datetime.now().isoformat(),
        'from_cache': False,
        'brief': '',
    }

    # Generate AI brief (reuse existing if score unchanged)
    if anthropic_api_key:
        history_for_brief = load_scores_history()
        previous = history_for_brief.get(resolved_ticker)
        existing_brief = ""
        if previous and previous.get('brief'):
            prev_score = previous.get('higgons', {}).get('total')
            curr_score = higgons.get('total')
            if prev_score == curr_score:
                existing_brief = previous['brief']
                log.info(f"  Reusing cached brief for {resolved_ticker} (score unchanged)")

        if existing_brief:
            result['brief'] = existing_brief
        else:
            result['brief'] = generate_brief(
                result_data=result,
                higgons_data=higgons,
                anthropic_api_key=anthropic_api_key,
            )

    # Save to cache (keyed by resolved ticker)
    history = load_scores_history()
    history[resolved_ticker] = result
    save_scores_history(history)

    return result


def analyze_with_pdf(
    pdf_bytes: bytes,
    ticker: str,
    anthropic_api_key: str,
    eod_api_key: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Analyze ticker using PDF report + other sources.
    PDF data takes priority for metrics it provides.
    """
    # First get base analysis (pass anthropic key for brief generation)
    base = analyze_ticker(ticker, eod_api_key=eod_api_key, anthropic_api_key=anthropic_api_key, force_refresh=True)

    # Parse PDF
    pdf_data = parse_pdf_report(pdf_bytes, ticker, anthropic_api_key)

    if 'error' in pdf_data:
        base['pdf_error'] = pdf_data['error']
        return base

    # Merge PDF data (PDF takes priority for provided fields)
    if pdf_data.get('per_current') is not None:
        base['pe_trailing'] = pdf_data['per_current']
    if pdf_data.get('per_forward') is not None:
        base['pe_forward'] = pdf_data['per_forward']
    if pdf_data.get('roe') is not None:
        base['roe'] = pdf_data['roe']
    if pdf_data.get('net_debt_ebitda') is not None:
        base['net_debt_ebitda'] = pdf_data['net_debt_ebitda']
    if pdf_data.get('debt_to_equity') is not None:
        base['debt_to_equity'] = pdf_data['debt_to_equity']
    if pdf_data.get('market_cap_meur') is not None:
        base['market_cap'] = pdf_data['market_cap_meur'] * 1e6

    # Recompute Higgons with enriched data
    base['higgons'] = compute_higgons_score(base)

    # Add PDF metadata
    base['pdf_data'] = {
        'target_price': pdf_data.get('target_price'),
        'recommendation': pdf_data.get('recommendation'),
        'analyst_firm': pdf_data.get('analyst_firm'),
        'report_date': pdf_data.get('report_date'),
        'notes': pdf_data.get('notes'),
    }
    base['sources']['pdf'] = True
    base['analyzed_at'] = datetime.now().isoformat()

    # Regenerate brief with PDF context (always fresh since PDF provides new data)
    base['brief'] = generate_brief(
        result_data=base,
        higgons_data=base['higgons'],
        anthropic_api_key=anthropic_api_key,
        pdf_data=base.get('pdf_data'),
    )

    # Update cache (keyed by resolved ticker)
    resolved = base.get('resolved_ticker', ticker)
    history = load_scores_history()
    history[resolved] = base
    save_scores_history(history)

    return base


def scan_portfolio(
    tickers: List[Dict[str, str]],
    eod_api_key: Optional[str] = None,
    anthropic_api_key: Optional[str] = None,
    force_refresh: bool = False,
) -> List[Dict[str, Any]]:
    """
    Scan all portfolio tickers and compute Higgons scores.

    Args:
        tickers: List of {'yahoo': 'RWM.PA', 'name': 'Reworld Media'}
        eod_api_key: Optional EOD API key
        anthropic_api_key: Optional Anthropic API key (for brief generation)
        force_refresh: Force re-fetch all data

    Returns:
        List of analysis results sorted by Higgons score (desc)
    """
    results = []
    for t in tickers:
        yahoo_ticker = t.get('yahoo', '')
        if not yahoo_ticker:
            continue

        try:
            result = analyze_ticker(
                yahoo_ticker,
                eod_api_key=eod_api_key,
                anthropic_api_key=anthropic_api_key,
                force_refresh=force_refresh,
            )
            # Override name with portfolio name if available
            if t.get('name'):
                result['name'] = t['name']
            results.append(result)
        except Exception as e:
            log.error(f"Error analyzing {yahoo_ticker}: {e}")
            results.append({
                'ticker': yahoo_ticker,
                'name': t.get('name', yahoo_ticker),
                'error': str(e),
                'higgons': {'total': 0, 'max': 25, 'grade': '?', 'pct': 0,
                            'scores': {}, 'details': {}},
            })

        # Small delay to avoid rate limiting
        time.sleep(0.5)

    # Sort by Higgons score descending
    results.sort(key=lambda x: x.get('higgons', {}).get('total', 0), reverse=True)
    return results

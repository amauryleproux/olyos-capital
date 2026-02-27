"""
Publications Service — Corporate earnings, press releases & AI summaries

Fetches earnings calendar, historical EPS data, and press releases
from yfinance + EODHD, then generates AI summaries via Claude.
"""

import os
import json
import time
from datetime import datetime, timedelta
from typing import Dict, List, Any, Optional

from olyos.logger import get_logger

try:
    import yfinance as yf
    YFINANCE_OK = True
except ImportError:
    YFINANCE_OK = False

try:
    import requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

log = get_logger('publications')

# ═══════════════════════════════════════════════════════════
# CACHE
# ═══════════════════════════════════════════════════════════

_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'data')
PUBLICATIONS_CACHE_DIR = os.path.join(_DATA_DIR, 'cache', 'publications')
CACHE_TTL_HOURS = 6


def get_cached_publications(ticker: str) -> Optional[Dict[str, Any]]:
    """Returns cached publications data if less than CACHE_TTL_HOURS old."""
    cache_file = os.path.join(PUBLICATIONS_CACHE_DIR, f'{ticker}_publications.json')
    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cached = json.load(f)
            cached_time = datetime.fromisoformat(cached.get('cached_at', '2000-01-01'))
            if datetime.now() - cached_time < timedelta(hours=CACHE_TTL_HOURS):
                log.info(f"Cache hit for publications of {ticker}")
                return cached
            else:
                log.info(f"Cache expired for publications of {ticker}")
        except Exception as e:
            log.warning(f"Error reading publications cache for {ticker}: {e}")
    return None


def cache_publications(ticker: str, data: Dict[str, Any]) -> None:
    """Saves publications data to cache."""
    try:
        os.makedirs(PUBLICATIONS_CACHE_DIR, exist_ok=True)
        cache_file = os.path.join(PUBLICATIONS_CACHE_DIR, f'{ticker}_publications.json')
        data['cached_at'] = datetime.now().isoformat()
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, default=str)
        log.info(f"Cached publications for {ticker}")
    except Exception as e:
        log.warning(f"Error caching publications for {ticker}: {e}")


# ═══════════════════════════════════════════════════════════
# DATA FETCHING — yfinance
# ═══════════════════════════════════════════════════════════

def fetch_earnings_calendar(ticker: str) -> Dict[str, Any]:
    """Fetch next earnings date and estimates from yfinance .calendar."""
    result = {'date': None, 'eps_estimate_avg': None, 'eps_estimate_low': None,
              'eps_estimate_high': None, 'revenue_estimate_avg': None,
              'revenue_estimate_low': None, 'revenue_estimate_high': None}
    if not YFINANCE_OK:
        return result
    try:
        t = yf.Ticker(ticker)
        cal = t.calendar
        if cal is not None and isinstance(cal, dict):
            # Earnings Date can be a list of dates
            earnings_dates = cal.get('Earnings Date', [])
            if earnings_dates:
                if isinstance(earnings_dates, list) and len(earnings_dates) > 0:
                    result['date'] = str(earnings_dates[0])
                else:
                    result['date'] = str(earnings_dates)
            result['eps_estimate_avg'] = cal.get('Earnings Average')
            result['eps_estimate_low'] = cal.get('Earnings Low')
            result['eps_estimate_high'] = cal.get('Earnings High')
            result['revenue_estimate_avg'] = cal.get('Revenue Average')
            result['revenue_estimate_low'] = cal.get('Revenue Low')
            result['revenue_estimate_high'] = cal.get('Revenue High')
        elif cal is not None:
            # Sometimes calendar returns a DataFrame
            try:
                cal_dict = cal.to_dict()
                for key, val in cal_dict.items():
                    if 'earning' in str(key).lower() and 'date' in str(key).lower():
                        dates = list(val.values()) if isinstance(val, dict) else [val]
                        if dates:
                            result['date'] = str(dates[0])
                    if 'earning' in str(key).lower() and 'average' in str(key).lower():
                        vals = list(val.values()) if isinstance(val, dict) else [val]
                        if vals:
                            result['eps_estimate_avg'] = vals[0]
            except Exception:
                pass
        log.info(f"Fetched earnings calendar for {ticker}: next={result['date']}")
    except Exception as e:
        log.warning(f"Could not fetch earnings calendar for {ticker}: {e}")
    return result


def fetch_earnings_history(ticker: str, limit: int = 12) -> List[Dict[str, Any]]:
    """Fetch historical earnings dates with EPS surprise from yfinance."""
    results = []
    if not YFINANCE_OK:
        return results
    try:
        t = yf.Ticker(ticker)
        df = t.get_earnings_dates(limit=limit)
        if df is not None and not df.empty:
            for idx, row in df.iterrows():
                eps_actual = row.get('Reported EPS')
                eps_estimate = row.get('EPS Estimate')
                surprise = row.get('Surprise(%)')

                # Skip future dates (no actual EPS)
                if eps_actual is None or (hasattr(eps_actual, '__float__') and str(eps_actual) == 'nan'):
                    continue

                try:
                    eps_actual = float(eps_actual)
                except (ValueError, TypeError):
                    continue

                try:
                    eps_estimate = float(eps_estimate) if eps_estimate is not None else None
                except (ValueError, TypeError):
                    eps_estimate = None

                try:
                    surprise = float(surprise) if surprise is not None else None
                except (ValueError, TypeError):
                    surprise = None

                date_str = str(idx.date()) if hasattr(idx, 'date') else str(idx)[:10]
                results.append({
                    'date': date_str,
                    'eps_estimate': round(eps_estimate, 3) if eps_estimate is not None else None,
                    'eps_actual': round(eps_actual, 3),
                    'surprise_pct': round(surprise, 2) if surprise is not None else None,
                })
        log.info(f"Fetched {len(results)} earnings history entries for {ticker}")
    except Exception as e:
        log.warning(f"Could not fetch earnings history for {ticker}: {e}")
    return results


def fetch_press_releases(ticker: str, count: int = 15) -> List[Dict[str, Any]]:
    """Fetch press releases from yfinance .get_news(tab='press releases')."""
    results = []
    if not YFINANCE_OK:
        return results
    try:
        t = yf.Ticker(ticker)
        # Try press releases first, fallback to all news
        for tab in ['press releases', 'all']:
            try:
                news = t.get_news(count=count, tab=tab)
                if news:
                    break
            except Exception:
                news = []
                continue

        if not news:
            # Fallback: try .news property
            try:
                news = t.news or []
            except Exception:
                news = []

        for item in news[:count]:
            title = item.get('title', '')
            link = item.get('link', '')
            publisher = item.get('publisher', '')
            pub_time = item.get('providerPublishTime')

            # Handle content structure (newer yfinance versions)
            if not title and 'content' in item:
                content = item['content']
                title = content.get('title', '')
                link = content.get('canonicalUrl', {}).get('url', '') or content.get('clickThroughUrl', {}).get('url', '')
                publisher = content.get('provider', {}).get('displayName', '')
                pub_time = content.get('pubDate')

            if not title:
                continue

            date_str = ''
            if pub_time:
                try:
                    if isinstance(pub_time, (int, float)):
                        date_str = datetime.fromtimestamp(pub_time).strftime('%Y-%m-%d %H:%M')
                    else:
                        date_str = str(pub_time)[:16]
                except Exception:
                    date_str = str(pub_time)[:16]

            results.append({
                'title': title,
                'link': link,
                'date': date_str,
                'publisher': publisher,
            })
        log.info(f"Fetched {len(results)} press releases for {ticker}")
    except Exception as e:
        log.warning(f"Could not fetch press releases for {ticker}: {e}")
    return results


# ═══════════════════════════════════════════════════════════
# DATA FETCHING — EODHD (complementary)
# ═══════════════════════════════════════════════════════════

def fetch_eod_earnings(ticker: str, api_key: str) -> List[Dict[str, Any]]:
    """Fetch earnings calendar data from EODHD API."""
    results = []
    if not REQUESTS_OK or not api_key:
        return results
    try:
        # EODHD expects ticker format like BEN.PA
        url = f"https://eodhd.com/api/calendar/earnings"
        params = {
            'api_token': api_key,
            'symbols': ticker,
            'fmt': 'json',
        }
        resp = requests.get(url, params=params, timeout=15)
        if resp.status_code == 200:
            data = resp.json()
            earnings = data.get('earnings', []) if isinstance(data, dict) else data
            for entry in earnings:
                if entry.get('code', '').upper() == ticker.upper() or entry.get('code', '') == ticker.split('.')[0]:
                    results.append({
                        'report_date': entry.get('report_date', ''),
                        'period_end': entry.get('date', ''),
                        'before_after': entry.get('before_after_market', ''),
                        'currency': entry.get('currency', ''),
                        'eps_actual': entry.get('actual'),
                        'eps_estimate': entry.get('estimate'),
                        'difference': entry.get('difference'),
                        'surprise_pct': entry.get('percent'),
                    })
            log.info(f"Fetched {len(results)} EODHD earnings entries for {ticker}")
    except Exception as e:
        log.warning(f"Could not fetch EODHD earnings for {ticker}: {e}")
    return results


# ═══════════════════════════════════════════════════════════
# MAIN ENTRY POINT
# ═══════════════════════════════════════════════════════════

def get_publications(ticker: str, eod_api_key: str = None,
                     force_refresh: bool = False) -> Dict[str, Any]:
    """
    Main entry point. Fetches all publications data for a ticker.
    Returns a dict with earnings calendar, history, press releases.
    """
    # Check cache first
    if not force_refresh:
        cached = get_cached_publications(ticker)
        if cached:
            cached['from_cache'] = True
            return cached

    log.info(f"Fetching publications for {ticker}...")

    data = {
        'ticker': ticker,
        'next_earnings': fetch_earnings_calendar(ticker),
        'earnings_history': fetch_earnings_history(ticker),
        'press_releases': fetch_press_releases(ticker),
        'eod_earnings': [],
        'ai_summary': None,
        'from_cache': False,
    }

    # Complement with EODHD data if API key available
    if eod_api_key:
        data['eod_earnings'] = fetch_eod_earnings(ticker, eod_api_key)

    # Cache the results
    cache_publications(ticker, data)

    return data


# ═══════════════════════════════════════════════════════════
# AI SUMMARY
# ═══════════════════════════════════════════════════════════

def generate_publications_summary(ticker: str, publications_data: Dict[str, Any],
                                   api_key: str) -> Dict[str, Any]:
    """
    Generate an AI summary of the publications using Claude.
    Returns dict with success, summary, ticker.
    """
    try:
        import anthropic
    except ImportError:
        return {'success': False, 'error': 'Module anthropic non installé'}

    if not api_key:
        return {'success': False, 'error': 'API Anthropic non configurée. Définir ANTHROPIC_API_KEY.'}

    # Build context from publications data
    next_e = publications_data.get('next_earnings', {})
    history = publications_data.get('earnings_history', [])
    press = publications_data.get('press_releases', [])
    eod = publications_data.get('eod_earnings', [])

    # Format earnings history
    history_text = "Aucune donnée disponible."
    if history:
        lines = []
        for h in history[:10]:
            surprise_str = f" (surprise: {h['surprise_pct']:+.1f}%)" if h.get('surprise_pct') is not None else ""
            estimate_str = f"estimé {h['eps_estimate']}" if h.get('eps_estimate') is not None else "estimé N/D"
            lines.append(f"  - {h['date']}: EPS réel {h['eps_actual']}, {estimate_str}{surprise_str}")
        history_text = '\n'.join(lines)

    # Format press releases
    press_text = "Aucun communiqué disponible."
    if press:
        lines = []
        for p in press[:10]:
            lines.append(f"  - [{p['date']}] {p['title']} ({p['publisher']})")
        press_text = '\n'.join(lines)

    # Format next earnings
    next_text = "Aucune date connue."
    if next_e.get('date'):
        next_text = f"Date: {next_e['date']}"
        if next_e.get('eps_estimate_avg'):
            next_text += f", EPS estimé: {next_e['eps_estimate_avg']}"
        if next_e.get('revenue_estimate_avg'):
            rev = next_e['revenue_estimate_avg']
            if isinstance(rev, (int, float)) and rev > 1e6:
                next_text += f", CA estimé: {rev/1e6:.0f}M"
            else:
                next_text += f", CA estimé: {rev}"

    # Format EODHD data if available
    eod_text = ""
    if eod:
        eod_lines = []
        for e in eod[:5]:
            eod_lines.append(f"  - Publication {e['report_date']}: EPS réel {e.get('eps_actual', 'N/D')}, "
                           f"estimé {e.get('eps_estimate', 'N/D')}, surprise {e.get('surprise_pct', 'N/D')}%")
        eod_text = f"\n\n## DONNÉES EODHD COMPLÉMENTAIRES\n" + '\n'.join(eod_lines)

    system_prompt = """Tu es un analyste equity research senior chez Olyos Capital, un fonds value investing
inspiré de la méthode William Higgons. Tu analyses les publications financières des entreprises
(résultats trimestriels/annuels, communiqués de presse) pour en extraire les informations clés.

RÈGLES :
- Sois factuel et concis
- Focus sur : croissance du BPA, surprises positives/négatives, tendance des résultats, prochaine échéance
- Perspective value investing : marges, rentabilité, valorisation, dette
- Français, format texte structuré (pas de HTML)
- Maximum 15 lignes
- Si les données sont limitées, indique-le et concentre-toi sur ce qui est disponible"""

    user_prompt = f"""Analyse les publications récentes de {ticker} :

## PROCHAINS RÉSULTATS
{next_text}

## HISTORIQUE DES RÉSULTATS (EPS)
{history_text}

## COMMUNIQUÉS DE PRESSE RÉCENTS
{press_text}{eod_text}

Génère un résumé structuré avec les sections :
1. **Derniers résultats** — Performance EPS vs consensus
2. **Tendance** — Évolution du BPA sur les derniers trimestres
3. **Prochaine échéance** — Date et attentes du marché
4. **Points d'attention** — Éléments clés pour un investisseur value"""

    try:
        client = anthropic.Anthropic(api_key=api_key)
        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1500,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )
        summary = message.content[0].text.strip()

        # Update the cached data with the summary
        publications_data['ai_summary'] = summary
        cache_publications(ticker, publications_data)

        log.info(f"Generated publications summary for {ticker}")
        return {'success': True, 'summary': summary, 'ticker': ticker}

    except Exception as e:
        log.error(f"Error generating publications summary for {ticker}: {e}", exc_info=True)
        return {'success': False, 'error': str(e), 'ticker': ticker}

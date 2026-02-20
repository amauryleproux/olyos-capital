"""
News Feed Service — RSS aggregation + AI Daily Digest

Fetches French/European financial news from multiple RSS feeds,
categorizes articles, detects mentioned tickers, and generates
AI daily digests via Claude.
"""

import os
import json
import hashlib
import re
import time
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Any, Optional, Tuple
from concurrent.futures import ThreadPoolExecutor, as_completed

from olyos.logger import get_logger

try:
    import feedparser
    FEEDPARSER_OK = True
except ImportError:
    FEEDPARSER_OK = False

try:
    import requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

log = get_logger('news')

# ═══════════════════════════════════════════════════════════
# CONFIGURATION
# ═══════════════════════════════════════════════════════════

FEEDS = {
    'ABCBourse': 'https://www.abcbourse.com/rss/displaynewsrss',
    'ABCBourse Analyses': 'https://www.abcbourse.com/rss/lastanalysisrss',
    'Investing.com': 'https://fr.investing.com/rss/news_25.rss',
    'BFM Business': 'https://www.bfmtv.com/rss/economie/',
    'Le Figaro Bourse': 'https://www.lefigaro.fr/rss/figaro_bourse.xml',
    'Capital': 'https://feed.prismamediadigital.com/v1/cap/rss?categories=entreprises-marches',
    'EasyBourse': 'https://www.easybourse.com/feeds/news/fr/',
}

# Cache paths
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'data')
NEWS_CACHE_DIR = os.path.join(_DATA_DIR, 'cache')
NEWS_CACHE_FILE = os.path.join(NEWS_CACHE_DIR, 'news.json')
DIGEST_CACHE_FILE = os.path.join(NEWS_CACHE_DIR, 'news_digest.json')

NEWS_CACHE_TTL = 3600       # 1 hour
DIGEST_CACHE_TTL = 43200    # 12 hours
FETCH_TIMEOUT = 15          # seconds per feed

# Category keywords (French)
CATEGORY_KEYWORDS = {
    'Résultats': [
        'résultat', 'bénéfice', 'chiffre d\'affaires', 'ca ', 'earnings',
        'bilan', 'ebitda', 'ebit', 'profit', 'perte', 'marge', 'guidance',
        'prévision', 'publication', 'semestriel', 'trimestriel', 'annuel',
        'croissance', 'recul', 'hausse du ca', 'baisse du ca', 'dividende',
        'bpa', 'bénéfice net', 'résultat net', 'résultat opérationnel',
        'warning', 'avertissement', 'révision',
    ],
    'M&A': [
        'acquisition', 'fusion', 'opa', 'opas', 'rachat', 'cession',
        'prise de participation', 'offre publique', 'spin-off', 'scission',
        'rapprochement', 'partenariat stratégique', 'joint venture',
        'introduction en bourse', 'ipo', 'retrait de cote', 'delisting',
    ],
    'Macro': [
        'bce', 'fed', 'taux', 'inflation', 'pib', 'emploi', 'chômage',
        'banque centrale', 'politique monétaire', 'récession', 'croissance',
        'zone euro', 'europe', 'etats-unis', 'chine', 'pétrole', 'or',
        'obligation', 'dette souveraine', 'spread', 'devises', 'euro',
        'dollar', 'rendement', 'qe', 'quantitative',
    ],
    'Secteur': [
        'automobile', 'pharma', 'luxe', 'bancaire', 'banque', 'assurance',
        'immobilier', 'technologie', 'tech', 'énergie', 'renouvelable',
        'télécoms', 'aéronautique', 'défense', 'agroalimentaire',
        'distribution', 'retail', 'construction', 'btp', 'santé',
    ],
    'Analyse': [
        'analyse', 'recommandation', 'objectif de cours', 'target',
        'upgrade', 'downgrade', 'relèvement', 'abaissement', 'consensus',
        'broker', 'courtier', 'notation', 'surperformance', 'sous-performance',
        'achat', 'vente', 'neutre', 'surpondérer', 'sous-pondérer',
    ],
}

# Common French/European company name patterns for ticker detection
COMPANY_TICKER_MAP = {
    'lvmh': 'MC.PA', 'total': 'TTE.PA', 'totalenergies': 'TTE.PA',
    'sanofi': 'SAN.PA', 'bnp': 'BNP.PA', 'bnp paribas': 'BNP.PA',
    'axa': 'CS.PA', 'société générale': 'GLE.PA', 'socgen': 'GLE.PA',
    'air liquide': 'AI.PA', 'danone': 'BN.PA', 'l\'oréal': 'OR.PA',
    'loreal': 'OR.PA', 'schneider': 'SU.PA', 'vinci': 'DG.PA',
    'saint-gobain': 'SGO.PA', 'michelin': 'ML.PA', 'renault': 'RNO.PA',
    'stellantis': 'STLAP.PA', 'carrefour': 'CA.PA', 'bouygues': 'EN.PA',
    'hermès': 'RMS.PA', 'hermes': 'RMS.PA', 'kering': 'KER.PA',
    'capgemini': 'CAP.PA', 'safran': 'SAF.PA', 'thales': 'HO.PA',
    'engie': 'ENGI.PA', 'veolia': 'VIE.PA', 'orange': 'ORA.PA',
    'crédit agricole': 'ACA.PA', 'credit agricole': 'ACA.PA',
    'pernod': 'RI.PA', 'pernod ricard': 'RI.PA', 'essilor': 'EL.PA',
    'dassault': 'AM.PA', 'legrand': 'LR.PA', 'publicis': 'PUB.PA',
    'worldline': 'WLN.PA', 'alstom': 'ALO.PA', 'accor': 'AC.PA',
    'eurofins': 'ERF.PA', 'téléperformance': 'TEP.PA',
}


# ═══════════════════════════════════════════════════════════
# RSS FETCHING
# ═══════════════════════════════════════════════════════════

def fetch_single_feed(name: str, url: str) -> List[Dict[str, Any]]:
    """Fetch and parse a single RSS feed. Returns list of normalized articles."""
    if not FEEDPARSER_OK:
        log.error("feedparser not installed")
        return []

    try:
        feed = feedparser.parse(url)
        if feed.bozo and not feed.entries:
            log.warning(f"Feed error for {name}: {feed.bozo_exception}")
            return []

        articles = []
        for entry in feed.entries[:30]:  # Max 30 articles per feed
            article = normalize_article(entry, name)
            if article:
                articles.append(article)

        log.info(f"Fetched {len(articles)} articles from {name}")
        return articles

    except Exception as e:
        log.error(f"Error fetching feed {name}: {e}")
        return []


def fetch_all_feeds() -> List[Dict[str, Any]]:
    """Fetch all RSS feeds in parallel. Returns combined list of articles."""
    all_articles = []

    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = {
            executor.submit(fetch_single_feed, name, url): name
            for name, url in FEEDS.items()
        }

        for future in as_completed(futures, timeout=30):
            name = futures[future]
            try:
                articles = future.result(timeout=FETCH_TIMEOUT)
                all_articles.extend(articles)
            except Exception as e:
                log.error(f"Feed {name} failed: {e}")

    # Sort by published date (newest first)
    all_articles.sort(key=lambda a: a.get('published', ''), reverse=True)

    # Deduplicate by title similarity
    seen_titles = set()
    unique_articles = []
    for article in all_articles:
        title_key = re.sub(r'\s+', ' ', article['title'].lower().strip())[:80]
        if title_key not in seen_titles:
            seen_titles.add(title_key)
            unique_articles.append(article)

    log.info(f"Total unique articles: {len(unique_articles)}")
    return unique_articles


def normalize_article(entry: Any, source_name: str) -> Optional[Dict[str, Any]]:
    """Normalize a feedparser entry into a standard article dict."""
    title = entry.get('title', '').strip()
    link = entry.get('link', '').strip()

    if not title or not link:
        return None

    # Parse published date
    published = None
    published_str = ''
    for date_field in ('published_parsed', 'updated_parsed'):
        parsed = entry.get(date_field)
        if parsed:
            try:
                published = datetime(*parsed[:6], tzinfo=timezone.utc)
                published_str = published.isoformat()
            except Exception:
                pass
            break

    if not published:
        published = datetime.now(timezone.utc)
        published_str = published.isoformat()

    # Summary (clean HTML tags, limit length)
    summary = entry.get('summary', '') or entry.get('description', '') or ''
    summary = re.sub(r'<[^>]+>', '', summary).strip()
    summary = re.sub(r'\s+', ' ', summary)
    if len(summary) > 200:
        summary = summary[:197] + '...'

    # Generate ID from link
    article_id = hashlib.md5(link.encode()).hexdigest()[:12]

    return {
        'id': article_id,
        'title': title,
        'link': link,
        'published': published_str,
        'published_ago': _time_ago(published),
        'summary': summary,
        'source': source_name,
        'category': 'Marché',  # Default, will be updated by categorize
        'tickers': [],
        'is_portfolio': False,
        'is_watchlist': False,
    }


def _time_ago(dt: datetime) -> str:
    """Convert datetime to human-readable relative time in French."""
    now = datetime.now(timezone.utc)
    diff = now - dt

    minutes = int(diff.total_seconds() / 60)
    hours = int(diff.total_seconds() / 3600)
    days = diff.days

    if minutes < 1:
        return "A l'instant"
    if minutes < 60:
        return f"Il y a {minutes}min"
    if hours < 24:
        return f"Il y a {hours}h"
    if days == 1:
        return "Hier"
    if days < 7:
        return f"Il y a {days}j"
    return dt.strftime('%d/%m/%Y')


# ═══════════════════════════════════════════════════════════
# CATEGORIZATION & TICKER DETECTION
# ═══════════════════════════════════════════════════════════

def categorize_article(article: Dict[str, Any]) -> str:
    """Classify article into a category based on keyword matching."""
    text = (article['title'] + ' ' + article.get('summary', '')).lower()

    scores = {}
    for category, keywords in CATEGORY_KEYWORDS.items():
        score = sum(1 for kw in keywords if kw in text)
        if score > 0:
            scores[category] = score

    if scores:
        return max(scores, key=scores.get)
    return 'Marché'


def detect_tickers(article: Dict[str, Any], known_tickers: List[str]) -> List[str]:
    """Detect ticker symbols mentioned in the article."""
    text = (article['title'] + ' ' + article.get('summary', '')).lower()
    found = set()

    # Check known company names
    for company_name, ticker in COMPANY_TICKER_MAP.items():
        if company_name in text:
            found.add(ticker)

    # Check known tickers (from portfolio/watchlist)
    for ticker in known_tickers:
        # Try ticker without suffix (e.g., "BEN" from "BEN.PA")
        base = ticker.split('.')[0].lower()
        if len(base) >= 2 and re.search(r'\b' + re.escape(base) + r'\b', text):
            found.add(ticker)

    return list(found)


# ═══════════════════════════════════════════════════════════
# CACHING
# ═══════════════════════════════════════════════════════════

def get_cached_news() -> Optional[List[Dict[str, Any]]]:
    """Return cached news if less than 1 hour old."""
    if not os.path.exists(NEWS_CACHE_FILE):
        return None
    try:
        with open(NEWS_CACHE_FILE, 'r', encoding='utf-8') as f:
            cached = json.load(f)
        cached_time = datetime.fromisoformat(cached['timestamp'])
        if datetime.now() - cached_time < timedelta(seconds=NEWS_CACHE_TTL):
            log.info(f"News cache hit ({len(cached['articles'])} articles)")
            return cached['articles']
    except Exception as e:
        log.warning(f"Error reading news cache: {e}")
    return None


def cache_news(articles: List[Dict[str, Any]]) -> None:
    """Save articles to cache."""
    try:
        os.makedirs(NEWS_CACHE_DIR, exist_ok=True)
        with open(NEWS_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump({
                'articles': articles,
                'timestamp': datetime.now().isoformat(),
                'count': len(articles),
            }, f, ensure_ascii=False)
        log.info(f"Cached {len(articles)} news articles")
    except Exception as e:
        log.warning(f"Error caching news: {e}")


def get_cached_digest() -> Optional[Dict[str, Any]]:
    """Return cached digest if less than 12 hours old."""
    if not os.path.exists(DIGEST_CACHE_FILE):
        return None
    try:
        with open(DIGEST_CACHE_FILE, 'r', encoding='utf-8') as f:
            cached = json.load(f)
        cached_time = datetime.fromisoformat(cached['timestamp'])
        age_hours = (datetime.now() - cached_time).total_seconds() / 3600
        if age_hours < (DIGEST_CACHE_TTL / 3600):
            cached['age_hours'] = round(age_hours, 1)
            log.info(f"Digest cache hit (age: {cached['age_hours']}h)")
            return cached
    except Exception as e:
        log.warning(f"Error reading digest cache: {e}")
    return None


def cache_digest(digest: Dict[str, Any]) -> None:
    """Save digest to cache."""
    try:
        os.makedirs(NEWS_CACHE_DIR, exist_ok=True)
        with open(DIGEST_CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(digest, f, ensure_ascii=False)
        log.info("Cached news digest")
    except Exception as e:
        log.warning(f"Error caching digest: {e}")


# ═══════════════════════════════════════════════════════════
# MAIN ENTRY POINTS
# ═══════════════════════════════════════════════════════════

def get_news(known_tickers: Optional[List[str]] = None,
             portfolio_tickers: Optional[List[str]] = None,
             watchlist_tickers: Optional[List[str]] = None) -> List[Dict[str, Any]]:
    """
    Main entry point: fetch, categorize, and enrich news articles.
    Returns list of articles sorted by date (newest first).
    """
    if not FEEDPARSER_OK:
        return []

    # Try cache first
    articles = get_cached_news()

    if articles is None:
        # Fetch fresh data
        log.info("Fetching fresh news from RSS feeds...")
        articles = fetch_all_feeds()

        # Categorize
        for article in articles:
            article['category'] = categorize_article(article)

        # Detect tickers
        all_tickers = list(set(
            (known_tickers or []) +
            (portfolio_tickers or []) +
            (watchlist_tickers or [])
        ))
        if all_tickers:
            for article in articles:
                article['tickers'] = detect_tickers(article, all_tickers)

        # Cache
        cache_news(articles)
    else:
        # Re-detect tickers for cached articles (portfolio may have changed)
        all_tickers = list(set(
            (known_tickers or []) +
            (portfolio_tickers or []) +
            (watchlist_tickers or [])
        ))
        if all_tickers:
            for article in articles:
                article['tickers'] = detect_tickers(article, all_tickers)

    # Mark portfolio/watchlist articles
    portfolio_set = set(portfolio_tickers or [])
    watchlist_set = set(watchlist_tickers or [])
    for article in articles:
        article['is_portfolio'] = bool(set(article.get('tickers', [])) & portfolio_set)
        article['is_watchlist'] = bool(set(article.get('tickers', [])) & watchlist_set)

    # Update published_ago (may be stale from cache)
    for article in articles:
        try:
            dt = datetime.fromisoformat(article['published'])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            article['published_ago'] = _time_ago(dt)
        except Exception:
            pass

    return articles


def generate_daily_digest(articles: List[Dict[str, Any]], api_key: str) -> Dict[str, Any]:
    """
    Generate a daily digest using Claude API.
    Returns dict with success, content, timestamp.
    """
    if not articles:
        return {
            'success': False,
            'error': 'Aucun article disponible pour le digest',
            'timestamp': datetime.now().isoformat(),
        }

    try:
        import anthropic

        # Build article summary for the prompt (top 40 articles)
        top_articles = articles[:40]
        articles_text = '\n'.join([
            f"- [{a['source']}] {a['title']} ({a['published_ago']})"
            for a in top_articles
        ])

        client = anthropic.Anthropic(api_key=api_key)

        message = client.messages.create(
            model="claude-sonnet-4-5-20250929",
            max_tokens=1500,
            system="""Tu es l'analyste morning brief d'Olyos Capital, un fonds value européen.
Tu rédiges un brief matinal concis et actionable pour le gérant de portefeuille.
Focus : small/mid caps européennes, méthode Higgons (PER bas, ROE élevé, faible dette).
Style : factuel, direct, sans fioritures. En français.""",
            messages=[{
                "role": "user",
                "content": f"""Voici les {len(top_articles)} dernières actualités financières :

{articles_text}

Rédige le DAILY BRIEF du {datetime.now().strftime('%d/%m/%Y')} en 8-12 lignes maximum.
Structure :
1. **Macro** (1-2 lignes) : contexte macro/marché du jour
2. **Mouvements** (2-3 lignes) : les mouvements corporate importants (résultats, M&A)
3. **Secteurs** (1-2 lignes) : tendances sectorielles notables
4. **Opportunités Higgons** (2-3 lignes) : signaux intéressants pour notre méthode value
5. **A surveiller** (1-2 lignes) : événements à venir

Utilise des bullet points (•). Sois concis et actionable."""
            }]
        )

        content = message.content[0].text.strip()

        digest = {
            'success': True,
            'content': content,
            'timestamp': datetime.now().isoformat(),
            'article_count': len(top_articles),
            'age_hours': 0,
        }

        # Cache the digest
        cache_digest(digest)

        log.info("Daily digest generated successfully")
        return digest

    except Exception as e:
        log.error(f"Error generating digest: {e}", exc_info=True)
        return {
            'success': False,
            'error': str(e),
            'timestamp': datetime.now().isoformat(),
        }

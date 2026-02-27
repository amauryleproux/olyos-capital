"""News & Publications API Router — RSS feeds, daily digest, corporate publications."""

import json
import os

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from olyos.logger import get_logger
from olyos.dependencies import ANTHROPIC_API_KEY, ANTHROPIC_OK, EOD_API_KEY, EOD_OK

log = get_logger('router.news')
router = APIRouter(tags=["news"])


# ─── Helper: get portfolio/watchlist tickers ──────────────────────────────────

def _get_tickers():
    """Get portfolio and watchlist tickers for news enrichment."""
    portfolio_tickers = []
    watchlist_tickers = []
    try:
        from olyos.dependencies import _get_app_module
        app = _get_app_module()
        df, _ = app.load_portfolio()
        if df is not None and not df.empty:
            portfolio_tickers = df['Ticker'].tolist() if 'Ticker' in df.columns else []
    except Exception:
        pass
    try:
        from olyos.dependencies import _get_app_module
        app = _get_app_module()
        wl = app.load_watchlist()
        watchlist_tickers = [w.get('ticker', '') for w in wl if w.get('ticker')]
    except Exception:
        pass
    return portfolio_tickers, watchlist_tickers


# ─── News Page ────────────────────────────────────────────────────────────────

@router.get("/news", response_class=HTMLResponse)
def news_page(request: Request):
    """Serve the News page (standalone HTML)."""
    try:
        news_template = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'templates', 'news.html'
        )
        with open(news_template, 'r', encoding='utf-8') as f:
            html = f.read()
        return HTMLResponse(content=html)
    except Exception as e:
        log.error(f"Error serving news page: {e}")
        return HTMLResponse(f"<h1>Error: {e}</h1>", status_code=500)


# ─── News Articles API ────────────────────────────────────────────────────────

@router.get("/api/news/articles")
def news_articles():
    """Fetch RSS news articles, categorized and enriched with ticker detection."""
    try:
        from olyos.services.news import get_news

        portfolio_tickers, watchlist_tickers = _get_tickers()
        all_tickers = list(set(portfolio_tickers + watchlist_tickers))

        articles = get_news(
            known_tickers=all_tickers,
            portfolio_tickers=portfolio_tickers,
            watchlist_tickers=watchlist_tickers,
        )

        return {'articles': articles, 'count': len(articles)}

    except Exception as e:
        log.error(f"Error fetching news: {e}", exc_info=True)
        return {'articles': [], 'error': str(e)}


# ─── News Digest (cached) ────────────────────────────────────────────────────

@router.get("/api/news/digest")
def news_digest():
    """Get cached AI daily digest."""
    try:
        from olyos.services.news import get_cached_digest
        digest = get_cached_digest()
        if digest:
            return digest
        return {'success': False, 'error': 'Aucun digest en cache'}
    except Exception as e:
        log.error(f"Error getting digest: {e}")
        return {'success': False, 'error': str(e)}


# ─── Generate Daily Digest ────────────────────────────────────────────────────

@router.get("/api/news/generate_digest")
def generate_digest():
    """Generate a new AI daily digest from latest articles."""
    if not ANTHROPIC_OK:
        return {'success': False, 'error': 'API Anthropic non configurée. Définir ANTHROPIC_API_KEY.'}

    try:
        from olyos.services.news import get_news, generate_daily_digest

        portfolio_tickers, watchlist_tickers = _get_tickers()
        all_tickers = list(set(portfolio_tickers + watchlist_tickers))

        articles = get_news(
            known_tickers=all_tickers,
            portfolio_tickers=portfolio_tickers,
            watchlist_tickers=watchlist_tickers,
        )

        result = generate_daily_digest(articles, ANTHROPIC_API_KEY)
        return result

    except Exception as e:
        log.error(f"Error generating digest: {e}", exc_info=True)
        return {'success': False, 'error': str(e)}


# ─── Publications API ────────────────────────────────────────────────────────

@router.get("/api/news/publications")
def get_publications_data(
    ticker: str = Query(..., description="Ticker symbol (e.g., BEN.PA)"),
    force: bool = Query(False, description="Force refresh from API"),
):
    """Get publications data for a specific ticker (earnings, press releases)."""
    if not ticker:
        return {'success': False, 'error': 'Ticker manquant'}

    try:
        from olyos.services.publications import get_publications

        result = get_publications(
            ticker=ticker,
            eod_api_key=EOD_API_KEY if EOD_OK else None,
            force_refresh=force,
        )

        return {'success': True, **result}

    except Exception as e:
        log.error(f"Error fetching publications for {ticker}: {e}", exc_info=True)
        return {'success': False, 'error': str(e)}


# ─── Publications AI Summary ─────────────────────────────────────────────────

@router.get("/api/news/publications/summary")
def publications_summary(
    ticker: str = Query(..., description="Ticker symbol"),
):
    """Generate AI summary for a ticker's publications."""
    if not ANTHROPIC_OK:
        return {'success': False, 'error': 'API Anthropic non configurée.'}

    if not ticker:
        return {'success': False, 'error': 'Ticker manquant'}

    try:
        from olyos.services.publications import get_publications, generate_publications_summary

        pub_data = get_publications(
            ticker=ticker,
            eod_api_key=EOD_API_KEY if EOD_OK else None,
        )

        result = generate_publications_summary(ticker, pub_data, ANTHROPIC_API_KEY)
        return result

    except Exception as e:
        log.error(f"Error generating publications summary for {ticker}: {e}", exc_info=True)
        return {'success': False, 'error': str(e)}

"""Sentiment & Macro Intelligence Router — AI-powered geopolitical and market analysis."""

import os

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from olyos.logger import get_logger
from olyos.dependencies import ANTHROPIC_API_KEY, ANTHROPIC_OK

log = get_logger('router.sentiment')
router = APIRouter(tags=["sentiment"])


# ── Sentiment Page ───────────────────────────────────────────────────────────

@router.get("/sentiment", response_class=HTMLResponse)
def sentiment_page(request: Request):
    """Serve the Sentiment & Macro Intelligence page."""
    try:
        template_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'templates', 'sentiment.html'
        )
        with open(template_path, 'r', encoding='utf-8') as f:
            html = f.read()
        return HTMLResponse(content=html)
    except Exception as e:
        log.error(f"Error serving sentiment page: {e}")
        return HTMLResponse(f"<h1>Error: {e}</h1>", status_code=500)


# ── API: Geopolitical Theme ──────────────────────────────────────────────────

@router.post("/api/sentiment/geopolitical")
def analyze_geopolitical(
    theme_id: str = Query(..., description="Theme ID (e.g. oil_conflict)"),
):
    """Analyze a geopolitical theme with AI + web search."""
    if not ANTHROPIC_OK:
        return JSONResponse(
            status_code=503,
            content={'error': 'API Anthropic non configuree. Definir ANTHROPIC_API_KEY.'}
        )
    try:
        from olyos.services.sentiment_service import analyze_geopolitical_theme
        result = analyze_geopolitical_theme(theme_id, ANTHROPIC_API_KEY)
        if 'error' in result and result['error'] != 'Analyse indisponible':
            return result
        return {'success': True, **result}
    except Exception as e:
        log.error(f"Error analyzing geopolitical theme {theme_id}: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={'error': str(e)})


# ── API: Global Sentiment ────────────────────────────────────────────────────

@router.post("/api/sentiment/global")
def analyze_global():
    """Get AI sentiment scores for all major currencies and assets."""
    if not ANTHROPIC_OK:
        return JSONResponse(
            status_code=503,
            content={'error': 'API Anthropic non configuree.'}
        )
    try:
        from olyos.services.sentiment_service import analyze_global_sentiment
        result = analyze_global_sentiment(ANTHROPIC_API_KEY)
        return {'success': True, **result}
    except Exception as e:
        log.error(f"Error analyzing global sentiment: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={'error': str(e)})


# ── API: Higgons Regime ──────────────────────────────────────────────────────

@router.post("/api/sentiment/higgons")
def analyze_higgons(
    context: str = Query("", description="Optional additional context"),
):
    """Analyze market regime for Higgons value investing strategy."""
    if not ANTHROPIC_OK:
        return JSONResponse(
            status_code=503,
            content={'error': 'API Anthropic non configuree.'}
        )
    try:
        from olyos.services.sentiment_service import analyze_higgons_regime
        result = analyze_higgons_regime(ANTHROPIC_API_KEY, custom_context=context)
        return {'success': True, **result}
    except Exception as e:
        log.error(f"Error analyzing Higgons regime: {e}", exc_info=True)
        return JSONResponse(status_code=500, content={'error': str(e)})


# ── API: Themes Config ───────────────────────────────────────────────────────

@router.get("/api/sentiment/themes")
def get_themes():
    """Get the list of configured geopolitical themes."""
    from olyos.services.sentiment_service import get_themes
    return {'themes': get_themes()}


# ── API: Cache Status ────────────────────────────────────────────────────────

@router.get("/api/sentiment/cache/status")
def cache_status():
    """Get cache status for all sentiment analyses."""
    from olyos.services.sentiment_service import get_cache_status
    return get_cache_status()


# ── API: Clear Cache ─────────────────────────────────────────────────────────

@router.post("/api/sentiment/cache/clear")
def clear_cache():
    """Clear all sentiment cached data."""
    try:
        from olyos.services.sentiment_service import clear_cache
        count = clear_cache()
        return {'success': True, 'cleared': count}
    except Exception as e:
        log.error(f"Error clearing sentiment cache: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})

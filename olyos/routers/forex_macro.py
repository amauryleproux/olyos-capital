"""Forex Macro Analysis Router — Macro confluence scoring for FX pairs."""

import os

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse

from olyos.logger import get_logger
from olyos.dependencies import EOD_API_KEY, EOD_OK

log = get_logger('router.forex_macro')
router = APIRouter(tags=["forex_macro"])


# ─── Forex Macro Page ────────────────────────────────────────────────────────

@router.get("/forex", response_class=HTMLResponse)
def forex_page(request: Request):
    """Serve the Forex Macro dashboard page."""
    try:
        template_path = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
            'templates', 'forex_macro.html'
        )
        with open(template_path, 'r', encoding='utf-8') as f:
            html = f.read()
        return HTMLResponse(content=html)
    except Exception as e:
        log.error(f"Error serving forex macro page: {e}")
        return HTMLResponse(f"<h1>Error: {e}</h1>", status_code=500)


# ─── API: All Pairs Dashboard ────────────────────────────────────────────────

@router.get("/api/forex/pairs")
def get_all_pairs():
    """Get confluence analysis for all configured forex pairs."""
    try:
        from olyos.services.forex_macro import analyze_all_pairs
        results = analyze_all_pairs(eod_api_key=EOD_API_KEY if EOD_OK else None)
        return {'success': True, 'pairs': results, 'count': len(results)}
    except Exception as e:
        log.error(f"Error analyzing pairs: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={'success': False, 'error': str(e)}
        )


# ─── API: Single Pair Detail ─────────────────────────────────────────────────

@router.get("/api/forex/pair")
def get_pair_detail(
    pair: str = Query(..., description="Forex pair (e.g. AUD/JPY)"),
):
    """Get detailed macro analysis for a specific forex pair."""
    try:
        from olyos.services.forex_macro import analyze_pair
        result = analyze_pair(pair, eod_api_key=EOD_API_KEY if EOD_OK else None)
        return {'success': True, **result}
    except Exception as e:
        log.error(f"Error analyzing pair {pair}: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={'success': False, 'error': str(e)}
        )


# ─── API: Single Currency ────────────────────────────────────────────────────

@router.get("/api/forex/currency")
def get_currency_analysis(
    currency: str = Query(..., description="Currency code (e.g. AUD, USD)"),
):
    """Get macro indicator analysis for a single currency."""
    try:
        from olyos.services.forex_macro import analyze_currency
        result = analyze_currency(
            currency.upper(),
            eod_api_key=EOD_API_KEY if EOD_OK else None,
        )
        return {'success': True, **result}
    except Exception as e:
        log.error(f"Error analyzing currency {currency}: {e}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={'success': False, 'error': str(e)}
        )


# ─── API: Configuration ──────────────────────────────────────────────────────

@router.get("/api/forex/config")
def get_forex_config():
    """Get the list of configured forex pairs and currencies."""
    from olyos.services.forex_macro import get_pairs_config, CURRENCY_INDICATORS
    return {
        'pairs': get_pairs_config(),
        'currencies': list(CURRENCY_INDICATORS.keys()),
    }


# ─── API: Clear Cache ────────────────────────────────────────────────────────

@router.get("/api/forex/clear_cache")
def clear_forex_cache():
    """Clear all forex macro cached data."""
    try:
        from olyos.services.forex_macro import clear_cache
        count = clear_cache()
        return {'success': True, 'cleared': count}
    except Exception as e:
        log.error(f"Error clearing forex cache: {e}")
        return JSONResponse(
            status_code=500,
            content={'success': False, 'error': str(e)}
        )

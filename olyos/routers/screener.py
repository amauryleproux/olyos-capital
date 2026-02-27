"""Screener API Router - Stock screener, data refresh, heatmap."""

import threading

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from olyos.dependencies import get_portfolio_service
from olyos.services.portfolio_service import PortfolioService
from olyos.logger import get_logger

log = get_logger('router.screener')
router = APIRouter(prefix="/api/screener", tags=["screener"])


@router.get("/data")
def screener_json(
    scope: str = Query("france"),
    mode: str = Query("standard"),
):
    """Get screener data as JSON."""
    try:
        from olyos.dependencies import _get_app_module
        app = _get_app_module()
        screener_data = app.run_screener(force=False, scope=scope, mode=mode)
        watchlist = app.load_watchlist()
        wl_tickers = {w.get('ticker', '').upper() for w in watchlist}

        for item in screener_data:
            item['in_watchlist'] = item.get('ticker', '').upper() in wl_tickers

        return {'success': True, 'data': screener_data, 'count': len(screener_data)}
    except Exception as e:
        log.error(f"Error getting screener data: {e}")
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})


@router.get("/refresh")
def refresh_screener_data(
    scope: str = Query("france"),
    mode: str = Query("standard"),
):
    """Start background data refresh."""
    try:
        from olyos.dependencies import _get_app_module
        app = _get_app_module()

        def _refresh():
            try:
                app.run_screener(force=True, scope=scope, mode=mode)
            except Exception as e:
                log.error(f"Background refresh error: {e}")

        t = threading.Thread(target=_refresh, daemon=True)
        t.start()
        return {'success': True, 'message': 'Refresh started'}
    except Exception as e:
        log.error(f"Error starting refresh: {e}")
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})


@router.get("/refresh_status")
def refresh_status():
    """Get refresh operation status."""
    try:
        from olyos.dependencies import _get_app_module
        app = _get_app_module()
        return app.REFRESH_STATUS
    except Exception as e:
        log.error(f"Error getting refresh status: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get("/heatmap")
def heatmap_data(
    metric: str = Query("perf_day"),
    grouping: str = Query("sector"),
    portfolio_svc: PortfolioService = Depends(get_portfolio_service),
):
    """Get portfolio data for treemap/heatmap visualization."""
    try:
        positions, total_value = portfolio_svc.get_heatmap_positions()

        # Group positions by the requested grouping field
        from collections import defaultdict
        grouped = defaultdict(lambda: {'positions': [], 'value': 0})
        for p in positions:
            key = p.get(grouping, 'Other') or 'Other'
            grouped[key]['positions'].append(p)
            grouped[key]['value'] += p.get('value', 0)

        groups = [
            {'name': name, 'value': round(g['value'], 2), 'positions': g['positions']}
            for name, g in sorted(grouped.items(), key=lambda x: -x[1]['value'])
        ]

        return {
            'success': True,
            'data': {
                'metric': metric,
                'grouping': grouping,
                'total_value': round(total_value, 0),
                'positions': positions,
                'groups': groups,
            },
        }
    except Exception as e:
        log.error(f"Error getting heatmap data: {e}")
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})

"""Backtest API Router - Strategy backtesting and history."""

import json
from datetime import datetime

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from olyos.dependencies import CONFIG
from olyos.logger import get_logger

log = get_logger('router.backtest')
router = APIRouter(prefix="/api/backtest", tags=["backtest"])


@router.get("/history")
def get_backtest_history():
    """Load backtest history."""
    try:
        from olyos.dependencies import _get_app_module
        app = _get_app_module()
        history = app.load_backtest_history()
        log.info(f"Loading backtest history: {len(history)} items")
        return history
    except Exception as e:
        log.error(f"Error loading backtest history: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.post("/run")
async def run_backtest(request: Request):
    """Execute backtesting with given parameters."""
    try:
        from olyos.dependencies import _get_app_module
        app = _get_app_module()

        params = await request.json()

        universe_str = params.get('universe', '')
        universe = [t.strip() for t in universe_str.split(',') if t.strip()]

        backtest_params = {
            'start_date': params.get('start_date', '2015-01-01'),
            'end_date': params.get('end_date', datetime.now().strftime('%Y-%m-%d')),
            'universe_scope': params.get('universe_scope', 'france'),
            'universe': universe if universe else [],
            'pe_max': params.get('pe_max', 12),
            'roe_min': params.get('roe_min', 10),
            'pe_sell': params.get('pe_sell', 17),
            'roe_min_hold': params.get('roe_min_hold', 8),
            'debt_equity_max': params.get('debt_equity_max', 100),
            'rebalance_freq': params.get('rebalance_freq', 'quarterly'),
            'initial_capital': params.get('initial_capital', 100000),
            'max_positions': params.get('max_positions', 20),
            'benchmark': params.get('benchmark', '^FCHI'),
        }

        log.info(f"Starting backtest: scope={backtest_params['universe_scope']}, "
                 f"period={backtest_params['start_date']} to {backtest_params['end_date']}")

        results = app.run_backtest(backtest_params)

        # Auto-save to history
        if results.get('metrics'):
            bt_id = app.save_backtest_result(results)
            results['saved_id'] = bt_id
            log.info(f"Saved to history with ID: {bt_id}")

        return results

    except Exception as e:
        log.error(f"Backtest error: {e}")
        return JSONResponse(status_code=200, content={'error': 'Backtest error occurred'})


@router.post("/rename")
async def rename_backtest(
    id: str = Query(""),
    name: str = Query(""),
):
    """Rename a backtest result."""
    try:
        from olyos.dependencies import _get_app_module
        app = _get_app_module()
        app.rename_backtest(id, name)
        return {'success': True}
    except Exception as e:
        log.error(f"Error renaming backtest: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.post("/delete")
async def delete_backtest(id: str = Query("")):
    """Delete a backtest result."""
    try:
        from olyos.dependencies import _get_app_module
        app = _get_app_module()
        app.delete_backtest(id)
        return {'success': True}
    except Exception as e:
        log.error(f"Error deleting backtest: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})

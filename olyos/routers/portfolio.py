"""Portfolio API Router - Portfolio CRUD, positions, transactions, P&L."""

import urllib.parse
from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from olyos.dependencies import get_portfolio_service, get_position_manager
from olyos.services.portfolio_service import PortfolioService
from olyos.services.position_manager import PositionManager
from olyos.logger import get_logger

log = get_logger('router.portfolio')
router = APIRouter(prefix="/api/portfolio", tags=["portfolio"])


# ─── Watchlist ─────────────────────────────────────────────────────────────────

@router.get("/watchlist/add")
def add_watchlist(
    ticker: str = Query(""),
    name: str = Query(""),
    country: str = Query(""),
    sector: str = Query(""),
):
    """Add ticker to watchlist."""
    try:
        from olyos.dependencies import _get_app_module
        app = _get_app_module()
        app.add_to_watchlist(ticker, name, country, sector)
        return {'success': True}
    except Exception as e:
        log.error(f"Error adding to watchlist: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get("/watchlist/remove")
def remove_watchlist(ticker: str = Query("")):
    """Remove ticker from watchlist."""
    try:
        from olyos.dependencies import _get_app_module
        app = _get_app_module()
        app.remove_from_watchlist(ticker)
        return {'success': True}
    except Exception as e:
        log.error(f"Error removing from watchlist: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})


# ─── Portfolio CRUD ────────────────────────────────────────────────────────────

@router.get("/add")
def add_portfolio(
    ticker: str = Query(""),
    name: str = Query(""),
    qty: str = Query("0"),
    avg_cost: str = Query("0"),
):
    """Add a new position to portfolio."""
    try:
        from olyos.dependencies import _get_app_module
        app = _get_app_module()
        success, err = app.add_portfolio_position(ticker, name, qty, avg_cost)
        if success:
            return {'success': True}
        return JSONResponse(status_code=400, content={'success': False, 'error': err})
    except Exception as e:
        log.error(f"Error adding portfolio position: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get("/edit")
def edit_portfolio(
    ticker: str = Query(""),
    qty: str = Query("0"),
    avg_cost: str = Query("0"),
):
    """Edit an existing position."""
    try:
        from olyos.dependencies import _get_app_module
        app = _get_app_module()
        success, err = app.edit_portfolio_position(ticker, qty, avg_cost)
        if success:
            return {'success': True}
        return JSONResponse(status_code=400, content={'success': False, 'error': err})
    except Exception as e:
        log.error(f"Error editing portfolio position: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get("/remove")
def remove_portfolio(ticker: str = Query("")):
    """Remove a position from portfolio."""
    try:
        from olyos.dependencies import _get_app_module
        app = _get_app_module()
        success, err = app.remove_portfolio_position(ticker)
        if success:
            return {'success': True}
        return JSONResponse(status_code=400, content={'success': False, 'error': err})
    except Exception as e:
        log.error(f"Error removing portfolio position: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})


# ─── Positions ─────────────────────────────────────────────────────────────────

@router.get("/positions")
def get_positions(
    portfolio_svc: PortfolioService = Depends(get_portfolio_service),
    manager: PositionManager = Depends(get_position_manager),
):
    """Get all open positions."""
    try:
        price_data, name_data = portfolio_svc.get_price_name_data()
        summary = manager.get_all_positions(price_data, name_data)
        return {'success': True, 'data': [p.to_dict() for p in summary.open_positions]}
    except Exception as e:
        log.error(f"Error getting positions: {e}")
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})


@router.get("/positions/closed")
def get_closed_positions(
    portfolio_svc: PortfolioService = Depends(get_portfolio_service),
    manager: PositionManager = Depends(get_position_manager),
):
    """Get all closed positions."""
    try:
        price_data, name_data = portfolio_svc.get_price_name_data()
        summary = manager.get_all_positions(price_data, name_data)
        return {'success': True, 'data': [p.to_dict() for p in summary.closed_positions]}
    except Exception as e:
        log.error(f"Error getting closed positions: {e}")
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})


@router.get("/positions/detail")
def get_position_detail(
    ticker: str = Query(...),
    portfolio_svc: PortfolioService = Depends(get_portfolio_service),
    manager: PositionManager = Depends(get_position_manager),
):
    """Get position detail with transactions."""
    try:
        df = portfolio_svc.load_dataframe_or_raise()
        price = 0.0
        name = ticker
        ticker_upper = ticker.upper()
        match = df[df['ticker'].str.upper() == ticker_upper]
        if not match.empty:
            price = float(match.iloc[0].get('price_eur', 0))
            name = match.iloc[0].get('name', ticker)

        position = manager.get_position(ticker, price, name)
        result = position.to_dict()
        result['transactions'] = [t.to_dict() for t in position.transactions]
        return {'success': True, 'data': result}
    except Exception as e:
        log.error(f"Error getting position detail: {e}")
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})


# ─── P&L ───────────────────────────────────────────────────────────────────────

@router.get("/pnl/summary")
def get_pnl_summary(
    portfolio_svc: PortfolioService = Depends(get_portfolio_service),
    manager: PositionManager = Depends(get_position_manager),
):
    """Get P&L summary."""
    try:
        price_data, name_data = portfolio_svc.get_price_name_data()
        summary = manager.get_all_positions(price_data, name_data)
        return {'success': True, 'data': summary.to_dict()}
    except Exception as e:
        log.error(f"Error getting P&L summary: {e}")
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})


@router.get("/pnl/history")
def get_pnl_history(
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    manager: PositionManager = Depends(get_position_manager),
):
    """Get P&L history for chart."""
    try:
        history = manager.get_pnl_history(start_date, end_date)
        return {'success': True, 'data': history}
    except Exception as e:
        log.error(f"Error getting P&L history: {e}")
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})


# ─── Transactions ──────────────────────────────────────────────────────────────

@router.get("/transactions")
def get_transactions(
    ticker: Optional[str] = Query(None),
    type: Optional[str] = Query(None),
    start_date: Optional[str] = Query(None),
    end_date: Optional[str] = Query(None),
    manager: PositionManager = Depends(get_position_manager),
):
    """List all transactions with optional filters."""
    try:
        transactions = manager.get_transactions(ticker, type, start_date, end_date)
        return {'success': True, 'data': [t.to_dict() for t in transactions]}
    except Exception as e:
        log.error(f"Error getting transactions: {e}")
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})


@router.get("/transactions/add")
def add_transaction(
    ticker: str = Query(...),
    type: str = Query("BUY"),
    date: str = Query(None),
    quantity: float = Query(0),
    price: float = Query(0),
    fees: float = Query(0),
    notes: str = Query(""),
    manager: PositionManager = Depends(get_position_manager),
    portfolio_svc: PortfolioService = Depends(get_portfolio_service),
):
    """Add a transaction."""
    try:
        date_str = date or datetime.now().strftime('%Y-%m-%d')
        txn, err = manager.add_transaction(
            ticker=ticker, txn_type=type, date_str=date_str,
            quantity=quantity, price=price, fees=fees, notes=notes,
        )
        if err:
            return JSONResponse(status_code=400, content={'success': False, 'error': err})

        # Sync to portfolio.xlsx
        portfolio_svc.sync_transaction_to_portfolio(ticker, type, quantity, price)

        return {'success': True, 'data': txn.to_dict()}
    except Exception as e:
        log.error(f"Error adding transaction: {e}")
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})


@router.get("/transactions/delete")
def delete_transaction(
    id: str = Query(...),
    manager: PositionManager = Depends(get_position_manager),
):
    """Delete a transaction."""
    try:
        success, err = manager.delete_transaction(id)
        if err:
            return JSONResponse(status_code=400, content={'success': False, 'error': err})
        return {'success': True}
    except Exception as e:
        log.error(f"Error deleting transaction: {e}")
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})


@router.get("/transactions/qty")
def get_ticker_qty(
    ticker: str = Query(...),
    manager: PositionManager = Depends(get_position_manager),
):
    """Get current quantity for a ticker (for sell validation)."""
    try:
        qty = manager._get_current_qty(ticker)
        return {'success': True, 'data': {'ticker': ticker.upper(), 'quantity': qty}}
    except Exception as e:
        log.error(f"Error getting ticker quantity: {e}")
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})

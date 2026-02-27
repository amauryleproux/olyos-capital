"""Dividends API Router - Dividend calendar, income projections, history."""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from olyos.dependencies import get_dividends_service, get_portfolio_service
from olyos.services.dividends import DividendsService
from olyos.services.portfolio_service import PortfolioService
from olyos.logger import get_logger

log = get_logger('router.dividends')
router = APIRouter(prefix="/api/dividends", tags=["dividends"])


@router.get("/calendar")
def dividends_calendar(
    months: int = Query(3),
    portfolio_svc: PortfolioService = Depends(get_portfolio_service),
    dividends_svc: DividendsService = Depends(get_dividends_service),
):
    """Get dividend calendar for portfolio."""
    try:
        positions = portfolio_svc.get_dividend_positions(include_price=True)
        calendar = dividends_svc.get_dividend_calendar(positions, months)
        return calendar
    except Exception as e:
        log.error(f"Error getting dividend calendar: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get("/income")
def dividends_income(
    portfolio_svc: PortfolioService = Depends(get_portfolio_service),
    dividends_svc: DividendsService = Depends(get_dividends_service),
):
    """Get projected annual income."""
    try:
        positions = portfolio_svc.get_dividend_positions(include_price=True)
        income = dividends_svc.project_annual_income(positions)
        return income
    except Exception as e:
        log.error(f"Error getting dividend income: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get("/ticker")
def dividends_ticker(
    ticker: str = Query(...),
    years: int = Query(5),
    dividends_svc: DividendsService = Depends(get_dividends_service),
):
    """Get dividend history for a ticker."""
    try:
        info = dividends_svc.get_dividend_history(ticker, years)
        return info.to_dict()
    except Exception as e:
        log.error(f"Error getting dividend history: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get("/upcoming")
def dividends_upcoming(
    portfolio_svc: PortfolioService = Depends(get_portfolio_service),
    dividends_svc: DividendsService = Depends(get_dividends_service),
):
    """Get upcoming dividends for portfolio."""
    try:
        positions = portfolio_svc.get_dividend_positions(include_price=False)
        upcoming = dividends_svc.get_upcoming_dividends(positions)
        return {'upcoming': upcoming}
    except Exception as e:
        log.error(f"Error getting upcoming dividends: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})

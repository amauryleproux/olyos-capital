"""Insider Trading API Router - Insider transactions, sentiment, alerts."""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from olyos.dependencies import get_insider_service, get_portfolio_service
from olyos.services.insider import InsiderService
from olyos.services.portfolio_service import PortfolioService
from olyos.logger import get_logger

log = get_logger('router.insider')
router = APIRouter(prefix="/api/insider", tags=["insider"])


@router.get("/transactions")
def insider_transactions(
    ticker: str = Query(...),
    months: int = Query(12),
    service: InsiderService = Depends(get_insider_service),
):
    """Get insider transactions for a ticker."""
    try:
        transactions = service.get_insider_transactions(ticker, months)
        return {
            'success': True,
            'data': {'ticker': ticker, 'transactions': [t.to_dict() for t in transactions]},
        }
    except Exception as e:
        log.error(f"Error fetching insider transactions: {e}")
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})


@router.get("/sentiment")
def insider_sentiment(
    ticker: str = Query(...),
    months: int = Query(12),
    service: InsiderService = Depends(get_insider_service),
):
    """Get insider sentiment for a ticker."""
    try:
        sentiment = service.calculate_insider_sentiment(ticker, months)
        return {'success': True, 'data': sentiment.to_dict()}
    except Exception as e:
        log.error(f"Error calculating insider sentiment: {e}")
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})


@router.get("/feed")
def insider_feed(
    scope: str = Query("portfolio"),
    limit: int = Query(50),
    service: InsiderService = Depends(get_insider_service),
    portfolio_svc: PortfolioService = Depends(get_portfolio_service),
):
    """Get insider feed. Scope: portfolio, watchlist, or all."""
    try:
        if scope == 'portfolio':
            tickers, _ = portfolio_svc.get_all_tickers(include_watchlist=False)
        elif scope == 'watchlist':
            watchlist = portfolio_svc.load_watchlist()
            tickers = [w.get('ticker', '').upper() for w in watchlist if w.get('ticker')]
        elif scope == 'all':
            tickers, _ = portfolio_svc.get_all_tickers(include_watchlist=True)
        else:
            tickers = []

        transactions = service.get_insider_feed(tickers, limit=limit)
        return {
            'success': True,
            'data': {
                'scope': scope,
                'count': len(transactions),
                'transactions': [t.to_dict() for t in transactions],
            },
        }
    except Exception as e:
        log.error(f"Error fetching insider feed: {e}")
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})


@router.get("/alerts")
def insider_alerts(
    service: InsiderService = Depends(get_insider_service),
    portfolio_svc: PortfolioService = Depends(get_portfolio_service),
):
    """Get recent insider alerts."""
    try:
        tickers, ticker_names = portfolio_svc.get_all_tickers(include_watchlist=True)
        alerts = service.detect_alerts(tickers, ticker_names)
        return {
            'success': True,
            'data': {'count': len(alerts), 'alerts': [a.to_dict() for a in alerts]},
        }
    except Exception as e:
        log.error(f"Error detecting insider alerts: {e}")
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})


@router.get("/score")
def insider_score(
    ticker: str = Query(...),
    service: InsiderService = Depends(get_insider_service),
):
    """Get insider score adjustment for a ticker."""
    try:
        adjustment = service.get_insider_score_adjustment(ticker)
        sentiment = service.calculate_insider_sentiment(ticker, months=6)
        return {
            'success': True,
            'data': {
                'ticker': ticker,
                'score_adjustment': adjustment,
                'recent_buy_days': sentiment.recent_buy_days,
                'is_cluster_buying': sentiment.is_cluster_buying,
                'sentiment_ratio': sentiment.sentiment_ratio,
            },
        }
    except Exception as e:
        log.error(f"Error calculating insider score: {e}")
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})

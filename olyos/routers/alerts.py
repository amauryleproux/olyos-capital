"""Alerts API Router - Price and fundamental alerts for watched securities."""

from datetime import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from olyos.dependencies import get_alerts_service
from olyos.services.alerts import AlertsService, AlertConfig
from olyos.logger import get_logger

log = get_logger('router.alerts')
router = APIRouter(prefix="/api/alerts", tags=["alerts"])


@router.get("")
def get_alerts(service: AlertsService = Depends(get_alerts_service)):
    """Get active alerts."""
    try:
        alerts = service.check_alerts()
        return {'alerts': [a.to_dict() for a in alerts], 'count': len(alerts)}
    except Exception as e:
        log.error(f"Error getting alerts: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get("/check")
def check_alerts(service: AlertsService = Depends(get_alerts_service)):
    """Force check alerts."""
    try:
        alerts = service.check_alerts()
        return {
            'alerts': [a.to_dict() for a in alerts],
            'count': len(alerts),
            'checked_at': datetime.now().isoformat(),
        }
    except Exception as e:
        log.error(f"Error checking alerts: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get("/watchlist_status")
def watchlist_status(service: AlertsService = Depends(get_alerts_service)):
    """Get watchlist with alert status."""
    try:
        items = service.get_watchlist_with_status()
        return {'watchlist': items, 'count': len(items)}
    except Exception as e:
        log.error(f"Error getting watchlist status: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get("/dismiss")
def dismiss_alert(
    ticker: str = Query(...),
    alert_type: str = Query(...),
    service: AlertsService = Depends(get_alerts_service),
):
    """Dismiss an alert."""
    try:
        success = service.dismiss_alert(ticker, alert_type)
        status = 200 if success else 404
        return JSONResponse(status_code=status, content={'success': success})
    except Exception as e:
        log.error(f"Error dismissing alert: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get("/config")
def set_alert_config(
    ticker: str = Query(...),
    pe_threshold: Optional[float] = Query(None),
    roe_threshold: Optional[float] = Query(None),
    price_below: Optional[float] = Query(None),
    price_above: Optional[float] = Query(None),
    service: AlertsService = Depends(get_alerts_service),
):
    """Set alert config for a ticker."""
    try:
        config = AlertConfig(
            pe_threshold=pe_threshold,
            roe_threshold=roe_threshold,
            price_below=price_below,
            price_above=price_above,
        )
        success = service.update_alert_config(ticker, config)
        status = 200 if success else 404
        return JSONResponse(
            status_code=status,
            content={'success': success, 'ticker': ticker, 'config': config.to_dict()},
        )
    except Exception as e:
        log.error(f"Error setting alert config: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})

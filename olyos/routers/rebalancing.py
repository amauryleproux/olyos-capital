"""Rebalancing API Router - Portfolio balance checking and trade proposals."""

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from olyos.dependencies import get_rebalancing_service, get_portfolio_service
from olyos.services.rebalancing import RebalancingService
from olyos.services.portfolio_service import PortfolioService
from olyos.logger import get_logger

log = get_logger('router.rebalancing')
router = APIRouter(prefix="/api/rebalancing", tags=["rebalancing"])


@router.get("/check")
def rebalance_check(
    service: RebalancingService = Depends(get_rebalancing_service),
    portfolio_svc: PortfolioService = Depends(get_portfolio_service),
):
    """Check portfolio for imbalances."""
    try:
        positions, total_value = portfolio_svc.get_positions_list(include_metrics=True)
        imbalances = service.check_portfolio_balance(positions, total_value)
        return {
            'success': True,
            'data': {
                'total_value': round(total_value, 0),
                'num_positions': len(positions),
                'imbalances': [i.to_dict() for i in imbalances],
                'is_balanced': len(imbalances) == 0,
            },
        }
    except Exception as e:
        log.error(f"Error checking rebalance: {e}")
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})


@router.get("/propose")
def rebalance_propose(
    method: str = Query("equal"),
    service: RebalancingService = Depends(get_rebalancing_service),
    portfolio_svc: PortfolioService = Depends(get_portfolio_service),
):
    """Get trade proposals for rebalancing."""
    try:
        positions, total_value = portfolio_svc.get_positions_list(include_metrics=False)
        target_weights = service.calculate_target_weights(positions, method)
        proposals = service.propose_rebalancing(positions, target_weights, total_value)

        total_buy = sum(t.trade_value for t in proposals if t.trade_value > 0)
        total_sell = sum(abs(t.trade_value) for t in proposals if t.trade_value < 0)

        return {
            'success': True,
            'data': {
                'method': method,
                'total_value': round(total_value, 0),
                'proposals': [p.to_dict() for p in proposals],
                'total_buy': round(total_buy, 0),
                'total_sell': round(total_sell, 0),
                'net_flow': round(total_buy - total_sell, 0),
            },
        }
    except Exception as e:
        log.error(f"Error proposing rebalance: {e}")
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})


@router.get("/analyze")
def rebalance_analyze(
    service: RebalancingService = Depends(get_rebalancing_service),
    portfolio_svc: PortfolioService = Depends(get_portfolio_service),
):
    """Full portfolio analysis with rebalancing recommendations."""
    try:
        positions, total_value = portfolio_svc.get_positions_list(include_metrics=True)
        result = service.analyze_portfolio(positions, total_value)
        return {'success': True, 'data': result.to_dict()}
    except Exception as e:
        log.error(f"Error analyzing portfolio: {e}")
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})


@router.get("/simulate")
def rebalance_simulate(
    method: str = Query("equal"),
    service: RebalancingService = Depends(get_rebalancing_service),
    portfolio_svc: PortfolioService = Depends(get_portfolio_service),
):
    """Simulate trade impact."""
    try:
        positions, total_value = portfolio_svc.get_positions_list(include_metrics=False)
        target_weights = service.calculate_target_weights(positions, method)
        proposals = service.propose_rebalancing(positions, target_weights, total_value)
        simulation = service.simulate_trades(positions, proposals)
        return {'success': True, 'data': simulation}
    except Exception as e:
        log.error(f"Error simulating rebalance: {e}")
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})

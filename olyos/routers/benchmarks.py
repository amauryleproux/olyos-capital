"""Benchmarks API Router - Portfolio vs market benchmark comparison."""

from datetime import datetime, timedelta

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from olyos.dependencies import get_benchmark_service
from olyos.services.benchmark import BenchmarkService, BENCHMARKS
from olyos.logger import get_logger

log = get_logger('router.benchmarks')
router = APIRouter(prefix="/api/benchmarks", tags=["benchmarks"])


@router.get("")
def get_benchmarks():
    """Get list of available benchmarks."""
    try:
        benchmarks = [{'key': k, **v} for k, v in BENCHMARKS.items()]
        return {'benchmarks': benchmarks}
    except Exception as e:
        log.error(f"Error getting benchmarks: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get("/compare")
def benchmark_compare(
    benchmark: str = Query("CACMS"),
    period: str = Query("1Y"),
    service: BenchmarkService = Depends(get_benchmark_service),
):
    """Get comparison data (portfolio vs benchmark)."""
    try:
        data = service.get_comparison_data(benchmark, period)
        return data
    except Exception as e:
        log.error(f"Error getting benchmark comparison: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get("/metrics")
def benchmark_metrics(
    benchmark: str = Query("CACMS"),
    period: str = Query("1Y"),
    service: BenchmarkService = Depends(get_benchmark_service),
):
    """Get performance metrics only."""
    try:
        metrics = service.calculate_metrics(benchmark, period)
        return metrics.to_dict()
    except Exception as e:
        log.error(f"Error getting benchmark metrics: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.get("/history")
def benchmark_history(
    benchmark: str = Query("CACMS"),
    period: str = Query("1Y"),
    service: BenchmarkService = Depends(get_benchmark_service),
):
    """Get benchmark price history."""
    try:
        end_date = datetime.now()
        period_map = {
            'YTD': datetime(end_date.year, 1, 1),
            '1Y': end_date - timedelta(days=365),
            '3Y': end_date - timedelta(days=365 * 3),
            '5Y': end_date - timedelta(days=365 * 5),
        }
        start_date = period_map.get(period, datetime(2010, 1, 1))

        prices, err = service.get_benchmark_history(
            benchmark,
            start_date.strftime('%Y-%m-%d'),
            end_date.strftime('%Y-%m-%d'),
        )

        if err:
            return JSONResponse(status_code=400, content={'error': err})
        return {'benchmark': benchmark, 'prices': prices, 'period': period}
    except Exception as e:
        log.error(f"Error getting benchmark history: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})

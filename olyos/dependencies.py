"""
FastAPI Dependency Injection - Replaces global singletons from app.py.
Each service is created once and injected via FastAPI's Depends().
"""

import os
from functools import lru_cache

from olyos.logger import get_logger

log = get_logger('dependencies')

# ─── Path Configuration ────────────────────────────────────────────────────────

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_DATA_DIR = os.path.join(_BASE_DIR, 'data')

CONFIG = {
    'portfolio_file': os.path.join(_DATA_DIR, 'portfolio.xlsx'),
    'transactions_file': os.path.join(_DATA_DIR, 'transactions.json'),
    'watchlist_file': os.path.join(_DATA_DIR, 'watchlist.json'),
    'screener_cache_file': os.path.join(_DATA_DIR, 'screener_cache.json'),
    'nav_history_file': os.path.join(_DATA_DIR, 'nav_history.json'),
    'backtest_cache_dir': os.path.join(_DATA_DIR, 'backtest_cache'),
    'backtest_history_file': os.path.join(_DATA_DIR, 'backtest_history.json'),
    'memo_dir': _DATA_DIR,
    'reports_dir': os.path.join(_BASE_DIR, 'docs', 'reports'),
    'port': 8080,
    'cache_days': 30,
}

# ─── API Keys ──────────────────────────────────────────────────────────────────

EOD_API_KEY = os.environ.get('EOD_API_KEY')
ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')

try:
    import requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

EOD_OK = EOD_API_KEY is not None and REQUESTS_OK

try:
    import anthropic
    ANTHROPIC_OK = ANTHROPIC_API_KEY is not None
except ImportError:
    ANTHROPIC_OK = False

try:
    import yfinance
    YFINANCE_OK = True
except ImportError:
    YFINANCE_OK = False


# ─── Lazy imports from app.py (business functions) ─────────────────────────────
# These will be imported from the old app.py during transition,
# then progressively moved into proper service modules.

def _get_app_module():
    """Lazy import of the old app module to access business functions."""
    import olyos.app as app_module
    return app_module


# ─── Service Singletons ───────────────────────────────────────────────────────

@lru_cache()
def get_portfolio_service():
    """Portfolio data access service."""
    from olyos.services.portfolio_service import PortfolioService
    app = _get_app_module()
    return PortfolioService(
        load_portfolio_func=app.load_portfolio,
        save_portfolio_func=app.save_portfolio,
        load_watchlist_func=app.load_watchlist,
    )


@lru_cache()
def get_alerts_service():
    """Alerts service."""
    from olyos.services.alerts import AlertsService
    app = _get_app_module()
    return AlertsService(
        watchlist_file=CONFIG['watchlist_file'],
        get_fundamentals_func=app.eod_get_fundamentals,
        get_prices_func=app.eod_get_historical_prices,
    )


@lru_cache()
def get_benchmark_service():
    """Benchmark comparison service."""
    from olyos.services.benchmark import BenchmarkService
    app = _get_app_module()
    benchmark_cache_dir = os.path.join(_DATA_DIR, 'benchmark_cache')
    return BenchmarkService(
        cache_dir=benchmark_cache_dir,
        nav_history_file=CONFIG['nav_history_file'],
        get_prices_func=app.eod_get_historical_prices,
    )


@lru_cache()
def get_dividends_service():
    """Dividends tracking service."""
    from olyos.services.dividends import DividendsService
    app = _get_app_module()
    dividends_cache_file = os.path.join(_DATA_DIR, 'dividends_cache.json')
    return DividendsService(
        cache_file=dividends_cache_file,
        get_dividends_func=app.eod_get_dividends,
        get_fundamentals_func=app.eod_get_fundamentals,
    )


@lru_cache()
def get_position_manager():
    """Position & transaction manager."""
    from olyos.services.position_manager import PositionManager
    app = _get_app_module()

    def get_current_price(ticker: str) -> float:
        try:
            fund, err = app.eod_get_fundamentals(ticker, use_cache=True)
            if fund and not err:
                price = fund.get('General', {}).get('LastClose')
                if price:
                    return float(price)
        except Exception:
            pass
        return 0.0

    return PositionManager(
        transactions_file=CONFIG['transactions_file'],
        get_price_func=get_current_price,
    )


@lru_cache()
def get_pdf_report_service():
    """PDF report generation service."""
    from olyos.services.pdf_report import PDFReportService
    os.makedirs(CONFIG['reports_dir'], exist_ok=True)
    app = _get_app_module()
    return PDFReportService(
        reports_dir=CONFIG['reports_dir'],
        nav_history_file=CONFIG['nav_history_file'],
        portfolio_func=app.load_portfolio,
        benchmark_service=get_benchmark_service(),
        position_manager=get_position_manager(),
    )


@lru_cache()
def get_insider_service():
    """Insider trading service."""
    from olyos.services.insider import InsiderService
    cache_file = os.path.join(_DATA_DIR, 'insider_cache.json')
    return InsiderService(
        eod_api_key=EOD_API_KEY or '',
        cache_file=cache_file,
        cache_days=3,
    )


@lru_cache()
def get_rebalancing_service():
    """Portfolio rebalancing service."""
    from olyos.services.rebalancing import RebalancingService, RebalanceConfig
    return RebalancingService(
        config=RebalanceConfig(
            max_position_weight=10.0,
            min_position_weight=2.0,
            max_sector_weight=30.0,
            min_higgons_score=4,
            max_pe=17.0,
        )
    )

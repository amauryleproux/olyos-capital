#!/usr/bin/env python3
"""
OLYOS CAPITAL - Portfolio Terminal v5.0 (FastAPI)
=================================================
Bloomberg-style portfolio management terminal.

Migration from http.server to FastAPI.
Run with: python -m olyos.main
"""

import os
import sys
import webbrowser
import threading

# Add parent directory to path for module imports
_current_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_current_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

# Load .env file (must happen before any import that reads env vars)
from dotenv import load_dotenv
_env_path = os.path.join(_parent_dir, '.env')
if os.path.exists(_env_path):
    load_dotenv(_env_path, override=True)
else:
    # Also try current working directory
    load_dotenv(override=True)

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.middleware.cors import CORSMiddleware

from olyos.logger import get_logger, configure as configure_logging
from olyos.dependencies import CONFIG

log = get_logger('main')

# ─── Application Setup ────────────────────────────────────────────────────────

app = FastAPI(
    title="Olyos Capital - Portfolio Terminal",
    version="5.0",
    description="Bloomberg-style portfolio management with Quality Value methodology (Higgons)",
)

# Jinja2 Templates
_templates_dir = os.path.join(_current_dir, 'templates')
templates = Jinja2Templates(directory=_templates_dir)

# CORS (for local development)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Static files (CSS, JS, images)
_static_dir = os.path.join(_parent_dir, 'static')
if os.path.exists(_static_dir):
    app.mount("/static", StaticFiles(directory=_static_dir), name="static")

# ─── Backward Compatibility Layer ──────────────────────────────────────────────
# During migration, we maintain backward compatibility with the old ?action= URLs.
# The frontend JS still uses fetch('/?action=xxx'). This middleware redirects those
# to the new /api/ endpoints.

from fastapi import Request
from fastapi.responses import RedirectResponse

# Map old action names to new API paths
ACTION_MAP = {
    # Alerts
    'get_alerts': '/api/alerts',
    'check_alerts': '/api/alerts/check',
    'watchlist_status': '/api/alerts/watchlist_status',
    'dismiss_alert': '/api/alerts/dismiss',
    'set_alert_config': '/api/alerts/config',
    # Benchmarks
    'get_benchmarks': '/api/benchmarks',
    'benchmark_compare': '/api/benchmarks/compare',
    'benchmark_metrics': '/api/benchmarks/metrics',
    'benchmark_history': '/api/benchmarks/history',
    # Dividends
    'dividends_calendar': '/api/dividends/calendar',
    'dividends_income': '/api/dividends/income',
    'dividends_ticker': '/api/dividends/ticker',
    'dividends_upcoming': '/api/dividends/upcoming',
    # Transactions / Positions
    'get_transactions': '/api/portfolio/transactions',
    'get_positions': '/api/portfolio/positions',
    'get_closed_positions': '/api/portfolio/positions/closed',
    'get_position_detail': '/api/portfolio/positions/detail',
    'add_transaction': '/api/portfolio/transactions/add',
    'delete_transaction': '/api/portfolio/transactions/delete',
    'get_ticker_qty': '/api/portfolio/transactions/qty',
    # P&L
    'get_pnl_summary': '/api/portfolio/pnl/summary',
    'get_pnl_history': '/api/portfolio/pnl/history',
    # Portfolio CRUD
    'addportfolio': '/api/portfolio/add',
    'editportfolio': '/api/portfolio/edit',
    'rmportfolio': '/api/portfolio/remove',
    'addwatch': '/api/portfolio/watchlist/add',
    'rmwatch': '/api/portfolio/watchlist/remove',
    # Screener
    'screener_json': '/api/screener/data',
    'refresh_screener_data': '/api/screener/refresh',
    'refresh_status': '/api/screener/refresh_status',
    'heatmap_data': '/api/screener/heatmap',
    # Reports
    'generate_report': '/api/reports/generate',
    'get_latest_report': '/api/reports/latest',
    'list_reports': '/api/reports/list',
    # Insider
    'insider_transactions': '/api/insider/transactions',
    'insider_sentiment': '/api/insider/sentiment',
    'insider_feed': '/api/insider/feed',
    'insider_alerts': '/api/insider/alerts',
    'insider_score': '/api/insider/score',
    # Rebalancing
    'rebalance_check': '/api/rebalancing/check',
    'rebalance_propose': '/api/rebalancing/propose',
    'rebalance_analyze': '/api/rebalancing/analyze',
    'rebalance_simulate': '/api/rebalancing/simulate',
    # Backtest
    'get_backtest_history': '/api/backtest/history',
    'run_backtest': '/api/backtest/run',
    'rename_backtest': '/api/backtest/rename',
    'delete_backtest': '/api/backtest/delete',
    # Cache
    'cache_stats': '/api/cache/stats',
    'clear_cache': '/api/cache/clear',
    # Analysis
    'create_memo': '/api/analysis/memo/create',
    'generate_ai_memo': '/api/analysis/memo/generate',
    'analyze_stock': '/api/analysis/stock',
    'portfolio_advisor': '/api/analysis/portfolio_advisor',
    'ai_optimize': '/api/analysis/optimize',
    'download_data': '/api/analysis/download_data',
    # News & Publications
    'news_articles': '/api/news/articles',
    'news_digest': '/api/news/digest',
    'generate_news_digest': '/api/news/generate_digest',
    'get_publications': '/api/news/publications',
    'generate_publications_summary': '/api/news/publications/summary',
}


@app.middleware("http")
async def legacy_action_redirect(request: Request, call_next):
    """Redirect legacy ?action=xxx URLs to new /api/xxx paths."""
    action = request.query_params.get('action')

    if action and action in ACTION_MAP and request.url.path in ('/', ''):
        new_path = ACTION_MAP[action]
        # Rebuild query string without the 'action' parameter
        params = dict(request.query_params)
        params.pop('action', None)
        query_string = '&'.join(f'{k}={v}' for k, v in params.items())
        new_url = f"{new_path}?{query_string}" if query_string else new_path

        return RedirectResponse(url=new_url, status_code=307)

    return await call_next(request)


# ─── Register Routers ─────────────────────────────────────────────────────────

from olyos.routers import alerts, benchmarks, dividends, portfolio, insider
from olyos.routers import rebalancing, reports, backtest, screener, analysis, cache
from olyos.routers import pages, news

app.include_router(alerts.router)
app.include_router(benchmarks.router)
app.include_router(dividends.router)
app.include_router(portfolio.router)
app.include_router(insider.router)
app.include_router(rebalancing.router)
app.include_router(reports.router)
app.include_router(backtest.router)
app.include_router(screener.router)
app.include_router(news.router)
app.include_router(analysis.router)
app.include_router(cache.router)
app.include_router(pages.router)


# ─── Entry Point ───────────────────────────────────────────────────────────────

def main():
    import uvicorn

    port = CONFIG.get('port', 8080)

    log.info("=" * 50)
    log.info("   OLYOS CAPITAL - PORTFOLIO TERMINAL v5.0")
    log.info("   Powered by FastAPI")
    log.info("=" * 50)

    if not os.path.exists(CONFIG['portfolio_file']):
        log.error(f"Erreur: {CONFIG['portfolio_file']} non trouvé")
        sys.exit(1)

    # Diagnostic: API keys
    from olyos.dependencies import EOD_API_KEY, EOD_OK, ANTHROPIC_OK
    log.info(f"EOD API: {'OK' if EOD_OK else 'NOT CONFIGURED'}" +
             (f" (key: {EOD_API_KEY[:8]}...)" if EOD_API_KEY else ""))
    log.info(f"Anthropic API: {'OK' if ANTHROPIC_OK else 'NOT CONFIGURED'}")
    log.info(f"http://localhost:{port}")
    log.info(f"API docs: http://localhost:{port}/docs")
    log.info("Ctrl+C pour arrêter")
    log.info("-" * 50)

    # Open browser after 1 second
    threading.Timer(1, lambda: webbrowser.open(f"http://localhost:{port}")).start()

    uvicorn.run(app, host="localhost", port=port, log_level="warning")


if __name__ == "__main__":
    main()

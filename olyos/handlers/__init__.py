"""HTTP Route Handlers

This package contains modular handlers for the Olyos application.

Modules:
    api: API endpoint handlers (JSON responses)
    pages: Page rendering handlers (HTML responses)
"""

from .api import (
    # Response helpers
    json_response,
    json_success,
    json_error,
    # POST handlers
    handle_create_memo,
    handle_generate_ai_memo,
    handle_run_backtest,
    handle_download_data,
    handle_ai_optimize,
    handle_clear_cache,
    handle_rename_backtest,
    handle_delete_backtest,
    # GET API handlers
    handle_cache_stats,
    handle_get_backtest_history,
    handle_add_watchlist,
    handle_remove_watchlist,
    handle_add_portfolio,
    handle_edit_portfolio,
    handle_remove_portfolio,
    handle_file_download,
    handle_refresh_screener_data,
    handle_refresh_status,
    handle_screener_json,
)

from .pages import (
    # Response helpers
    html_response,
    json_file_response,
    # Page handlers
    handle_screener_page,
    handle_screener_cache_file,
    handle_detail_page,
    handle_home_page,
    handle_backtest_page,
    handle_ai_optimization_page,
    # Route matching helpers
    is_screener_path,
    is_screener_cache_path,
    is_backtest_path,
    is_ai_optimization_path,
    has_detail_param,
)

__all__ = [
    # API response helpers
    'json_response',
    'json_success',
    'json_error',
    # POST handlers
    'handle_create_memo',
    'handle_generate_ai_memo',
    'handle_run_backtest',
    'handle_download_data',
    'handle_ai_optimize',
    'handle_clear_cache',
    'handle_rename_backtest',
    'handle_delete_backtest',
    # GET API handlers
    'handle_cache_stats',
    'handle_get_backtest_history',
    'handle_add_watchlist',
    'handle_remove_watchlist',
    'handle_add_portfolio',
    'handle_edit_portfolio',
    'handle_remove_portfolio',
    'handle_file_download',
    'handle_refresh_screener_data',
    'handle_refresh_status',
    'handle_screener_json',
    # Page response helpers
    'html_response',
    'json_file_response',
    # Page handlers
    'handle_screener_page',
    'handle_screener_cache_file',
    'handle_detail_page',
    'handle_home_page',
    'handle_backtest_page',
    'handle_ai_optimization_page',
    # Route matching helpers
    'is_screener_path',
    'is_screener_cache_path',
    'is_backtest_path',
    'is_ai_optimization_path',
    'has_detail_param',
]

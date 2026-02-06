"""
Page Rendering Handlers

This module contains handler functions for page rendering.
Each function returns HTML content or response data.
"""

import os


# ============================================================================
# Response Helpers
# ============================================================================

def html_response(content, status=200, cache_control=None):
    """Create an HTML response dict."""
    response = {
        'status': status,
        'content_type': 'text/html; charset=utf-8',
        'body': content
    }
    if cache_control:
        response['headers'] = {'Cache-Control': cache_control}
    return response


def json_file_response(filepath, cache_control='public, max-age=1800'):
    """Create a JSON file response dict."""
    if os.path.exists(filepath):
        with open(filepath, 'rb') as f:
            content = f.read()
        return {
            'status': 200,
            'content_type': 'application/json',
            'headers': {'Cache-Control': cache_control},
            'body': content,
            'binary': True
        }
    return {'status': 404, 'body': None}


# ============================================================================
# Page Handlers
# ============================================================================

def handle_screener_page():
    """
    Handle screener page request.

    Returns:
        HTML response with screener page content
    """
    screener_html = 'screener_v2.html'
    if os.path.exists(screener_html):
        with open(screener_html, 'r', encoding='utf-8') as f:
            content = f.read()
        return html_response(content, cache_control='no-cache')
    return {'status': 404, 'body': None}


def handle_screener_cache_file(config):
    """
    Handle screener cache file request.

    Args:
        config: Configuration dict

    Returns:
        JSON file response
    """
    cache_file = config['screener_cache_file']
    return json_file_response(cache_file)


def handle_detail_page(query_params, get_security_data, gen_detail_html):
    """
    Handle security detail page request.

    Args:
        query_params: URL query parameters
        get_security_data: Function to get security data
        gen_detail_html: Function to generate detail HTML

    Returns:
        HTML response with detail page content
    """
    ticker = query_params['detail'][0].upper()
    html_content = gen_detail_html(get_security_data(ticker))
    return html_response(html_content)


def handle_home_page(query_params, load_portfolio, update_portfolio, run_screener,
                     load_watchlist, calc_scores, gen_html, yfinance_ok):
    """
    Handle home page request.

    Args:
        query_params: URL query parameters
        load_portfolio: Function to load portfolio
        update_portfolio: Function to update portfolio
        run_screener: Function to run screener
        load_watchlist: Function to load watchlist
        calc_scores: Function to calculate scores
        gen_html: Function to generate HTML
        yfinance_ok: Whether yfinance is available

    Returns:
        HTML response with home page content
    """
    df, err = load_portfolio()
    if err:
        return html_response(f"<h1>Erreur: {err}</h1>")

    do_refresh = 'refresh' in query_params and yfinance_ok
    if do_refresh:
        print("Refreshing portfolio data...")
        df = update_portfolio(df)

    # Screener with scope and mode support
    screener_scope = query_params.get('scope', ['france'])[0] if 'screener' in query_params else 'france'
    screener_mode = query_params.get('mode', ['standard'])[0] if 'screener' in query_params else 'standard'
    screener_data = run_screener(force='screener' in query_params, scope=screener_scope, mode=screener_mode)

    df = calc_scores(df)
    html_content = gen_html(df, screener_data, load_watchlist(), update_history=do_refresh)
    return html_response(html_content)


def handle_backtest_page():
    """
    Handle backtest page request.

    Returns:
        HTML response with backtest page content or redirect info
    """
    # This would serve a dedicated backtest.html if it exists
    backtest_html = 'backtest.html'
    if os.path.exists(backtest_html):
        with open(backtest_html, 'r', encoding='utf-8') as f:
            content = f.read()
        return html_response(content, cache_control='no-cache')
    # Fallback - page not found or handled by home page
    return None


def handle_ai_optimization_page():
    """
    Handle AI optimization page request.

    Returns:
        HTML response with AI optimization page content or redirect info
    """
    # This would serve a dedicated ai_optimization.html if it exists
    ai_html = 'ai_optimization.html'
    if os.path.exists(ai_html):
        with open(ai_html, 'r', encoding='utf-8') as f:
            content = f.read()
        return html_response(content, cache_control='no-cache')
    # Fallback - page not found or handled by home page
    return None


# ============================================================================
# Route Matching Helpers
# ============================================================================

def is_screener_path(path):
    """Check if path matches screener page."""
    return path in ('/screener', '/screener/')


def is_screener_cache_path(path):
    """Check if path matches screener cache file."""
    return path == '/screener_cache.json'


def is_backtest_path(path):
    """Check if path matches backtest page."""
    return path in ('/backtest', '/backtest/')


def is_ai_optimization_path(path):
    """Check if path matches AI optimization page."""
    return path in ('/ai-optimization', '/ai-optimization/')


def has_detail_param(query_params):
    """Check if query has detail parameter."""
    return 'detail' in query_params

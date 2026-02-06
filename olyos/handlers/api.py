"""
API Endpoint Handlers

This module contains handler functions for all API endpoints.
Each function takes request data and returns response data.
"""

import json
import os
import urllib.parse
from datetime import datetime


# ============================================================================
# JSON Response Helpers
# ============================================================================

def json_response(data, status=200):
    """Create a JSON response dict with status code."""
    return {
        'status': status,
        'content_type': 'application/json',
        'body': json.dumps(data)
    }


def json_success(data=None, **kwargs):
    """Create a success JSON response."""
    response = {'success': True}
    if data is not None:
        response.update(data)
    response.update(kwargs)
    return json_response(response)


def json_error(error_message, status=200):
    """Create an error JSON response."""
    return json_response({'success': False, 'error': error_message}, status)


# ============================================================================
# POST API Handlers
# ============================================================================

def handle_create_memo(params, create_memo_docx):
    """
    Handle memo creation from form data.

    Args:
        params: Parsed form data dict
        create_memo_docx: Function to create the memo document

    Returns:
        JSON response with filepath or error
    """
    ticker = params.get('ticker', [''])[0]
    name = params.get('name', [''])[0]
    sector = params.get('sector', [''])[0]
    country = params.get('country', [''])[0]
    signal = params.get('signal', ['Surveillance'])[0]
    target_price = params.get('target_price', [''])[0]
    thesis = params.get('thesis', [''])[0]
    strengths = params.get('strengths', [''])[0]
    risks = params.get('risks', [''])[0]
    valuation = params.get('valuation', [''])[0]
    notes = params.get('notes', [''])[0]

    filepath, error = create_memo_docx(
        ticker, name, sector, country, signal, target_price,
        thesis, strengths, risks, valuation, notes
    )

    if filepath:
        return json_success(filepath=filepath)
    else:
        return json_error(error)


def handle_generate_ai_memo(query_params, get_security_data, generate_memo_with_ai):
    """
    Handle AI-generated memo creation.

    Args:
        query_params: URL query parameters
        get_security_data: Function to get security data
        generate_memo_with_ai: Function to generate memo with AI

    Returns:
        JSON response with filepath or error
    """
    ticker = query_params.get('ticker', [''])[0]
    security_data = get_security_data(ticker)
    filepath, error = generate_memo_with_ai(security_data)

    if filepath:
        return json_success(filepath=filepath)
    else:
        return json_error(error or 'Unknown error')


def handle_run_backtest(post_data, run_backtest, save_backtest_result):
    """
    Handle backtest execution.

    Args:
        post_data: Raw POST body string
        run_backtest: Function to run the backtest
        save_backtest_result: Function to save backtest results

    Returns:
        JSON response with backtest results
    """
    try:
        params = json.loads(post_data)

        # Parse universe from comma-separated string (for custom mode)
        universe_str = params.get('universe', '')
        universe = [t.strip() for t in universe_str.split(',') if t.strip()]

        backtest_params = {
            'start_date': params.get('start_date', '2015-01-01'),
            'end_date': params.get('end_date', datetime.now().strftime('%Y-%m-%d')),
            'universe_scope': params.get('universe_scope', 'france'),
            'universe': universe if universe else [],
            'pe_max': params.get('pe_max', 12),
            'roe_min': params.get('roe_min', 10),
            'pe_sell': params.get('pe_sell', 17),
            'roe_min_hold': params.get('roe_min_hold', 8),
            'debt_equity_max': params.get('debt_equity_max', 100),
            'rebalance_freq': params.get('rebalance_freq', 'quarterly'),
            'initial_capital': params.get('initial_capital', 100000),
            'max_positions': params.get('max_positions', 20),
            'benchmark': params.get('benchmark', '^FCHI')
        }

        print(f"[BACKTEST] Starting with params:")
        print(f"   Scope: {backtest_params['universe_scope']}")
        print(f"   Period: {backtest_params['start_date']} to {backtest_params['end_date']}")
        print(f"   BUY: PE <= {backtest_params['pe_max']}, ROE >= {backtest_params['roe_min']}%")
        print(f"   SELL: PE > {backtest_params['pe_sell']} or ROE < {backtest_params['roe_min_hold']}%")

        results = run_backtest(backtest_params)

        # Auto-save backtest to history
        if results.get('metrics'):
            bt_id = save_backtest_result(results)
            results['saved_id'] = bt_id
            print(f"[BACKTEST] Saved to history with ID: {bt_id}")

        return json_response(results)

    except Exception as e:
        print(f"[BACKTEST ERROR] {e}")
        return json_response({'error': 'Backtest error occurred'})


def handle_download_data(query_params, download_all_data):
    """
    Handle data download request.

    Args:
        query_params: URL query parameters
        download_all_data: Function to download all data

    Returns:
        JSON response with download result
    """
    scope = query_params.get('scope', ['france'])[0]
    print(f"[CACHE] Downloading all data for {scope}...")

    try:
        result = download_all_data(scope, start_date='2010-01-01')
        return json_response(result)
    except Exception as e:
        print(f"[DOWNLOAD ERROR] {e}")
        return json_response({'error': 'Download error occurred'})


def handle_ai_optimize(query_params, run_ai_optimization):
    """
    Handle AI optimization request.

    Args:
        query_params: URL query parameters
        run_ai_optimization: Function to run AI optimization

    Returns:
        JSON response with optimization result
    """
    scope = query_params.get('scope', ['france'])[0]
    goal = query_params.get('goal', ['balanced'])[0]
    print(f"[AI OPTIMIZER] Starting optimization for {scope} with goal: {goal}")

    try:
        result = run_ai_optimization(scope, goal)
        return json_response(result)
    except Exception as e:
        print(f"[AI OPTIMIZE ERROR] {e}")
        return json_response({'error': 'Optimization error occurred'})


def handle_clear_cache(cache_dir, ensure_cache_dir):
    """
    Handle cache clearing request.

    Args:
        cache_dir: Path to cache directory
        ensure_cache_dir: Function to recreate cache dir

    Returns:
        JSON response with result
    """
    try:
        import shutil
        if os.path.exists(cache_dir):
            shutil.rmtree(cache_dir)
        ensure_cache_dir()
        return json_response({'message': 'Cache cleared successfully'})
    except Exception as e:
        print(f"[CLEAR CACHE ERROR] {e}")
        return json_response({'error': 'Cache clear error occurred'})


def handle_rename_backtest(query_params, rename_backtest):
    """
    Handle backtest rename request.

    Args:
        query_params: URL query parameters
        rename_backtest: Function to rename backtest

    Returns:
        JSON response with success status
    """
    bt_id = query_params.get('id', [''])[0]
    new_name = urllib.parse.unquote(query_params.get('name', [''])[0])
    rename_backtest(bt_id, new_name)
    return json_success()


def handle_delete_backtest(query_params, delete_backtest):
    """
    Handle backtest deletion request.

    Args:
        query_params: URL query parameters
        delete_backtest: Function to delete backtest

    Returns:
        JSON response with success status
    """
    bt_id = query_params.get('id', [''])[0]
    delete_backtest(bt_id)
    return json_success()


# ============================================================================
# GET API Handlers
# ============================================================================

def handle_cache_stats(get_cache_stats):
    """
    Handle cache stats request.

    Args:
        get_cache_stats: Function to get cache statistics

    Returns:
        JSON response with cache stats
    """
    stats = get_cache_stats()
    return json_response(stats)


def handle_get_backtest_history(load_backtest_history, config):
    """
    Handle backtest history request.

    Args:
        load_backtest_history: Function to load backtest history
        config: Configuration dict

    Returns:
        JSON response with backtest history
    """
    history = load_backtest_history()
    print(f"[HISTORY] Loading backtest history: {len(history)} items from {config['backtest_history_file']}")
    return json_response(history)


def handle_add_watchlist(query_params, add_to_watchlist):
    """
    Handle add to watchlist request.

    Args:
        query_params: URL query parameters
        add_to_watchlist: Function to add to watchlist

    Returns:
        Simple success response
    """
    add_to_watchlist(
        query_params.get('ticker', [''])[0],
        urllib.parse.unquote(query_params.get('name', [''])[0]),
        query_params.get('country', [''])[0],
        urllib.parse.unquote(query_params.get('sector', [''])[0])
    )
    return {'status': 200, 'body': None}


def handle_remove_watchlist(query_params, remove_from_watchlist):
    """
    Handle remove from watchlist request.

    Args:
        query_params: URL query parameters
        remove_from_watchlist: Function to remove from watchlist

    Returns:
        Simple success response
    """
    remove_from_watchlist(query_params.get('ticker', [''])[0])
    return {'status': 200, 'body': None}


def handle_add_portfolio(query_params, add_portfolio_position):
    """
    Handle add portfolio position request.

    Args:
        query_params: URL query parameters
        add_portfolio_position: Function to add portfolio position

    Returns:
        Response with status and message
    """
    ticker = query_params.get('ticker', [''])[0]
    name = urllib.parse.unquote(query_params.get('name', [''])[0])
    qty = query_params.get('qty', ['0'])[0]
    avg_cost = query_params.get('avg_cost', ['0'])[0]
    success, err = add_portfolio_position(ticker, name, qty, avg_cost)

    return {
        'status': 200 if success else 400,
        'content_type': 'text/plain',
        'body': err or 'OK'
    }


def handle_edit_portfolio(query_params, edit_portfolio_position):
    """
    Handle edit portfolio position request.

    Args:
        query_params: URL query parameters
        edit_portfolio_position: Function to edit portfolio position

    Returns:
        Response with status and message
    """
    ticker = query_params.get('ticker', [''])[0]
    qty = query_params.get('qty', ['0'])[0]
    avg_cost = query_params.get('avg_cost', ['0'])[0]
    success, err = edit_portfolio_position(ticker, qty, avg_cost)

    return {
        'status': 200 if success else 400,
        'content_type': 'text/plain',
        'body': err or 'OK'
    }


def handle_remove_portfolio(query_params, remove_portfolio_position):
    """
    Handle remove portfolio position request.

    Args:
        query_params: URL query parameters
        remove_portfolio_position: Function to remove portfolio position

    Returns:
        Response with status and message
    """
    ticker = query_params.get('ticker', [''])[0]
    success, err = remove_portfolio_position(ticker)

    return {
        'status': 200 if success else 400,
        'content_type': 'text/plain',
        'body': err or 'OK'
    }


def handle_file_download(query_params, config):
    """
    Handle file download request.

    Args:
        query_params: URL query parameters
        config: Configuration dict

    Returns:
        Response with file content or error
    """
    fp = urllib.parse.unquote(query_params['download'][0])
    # Security: Validate path is within allowed directory (prevent path traversal)
    fp = os.path.abspath(fp)
    safe_dir = os.path.abspath(config.get('memo_dir', '.'))

    if not fp.startswith(safe_dir):
        print(f"[SECURITY] Blocked path traversal attempt: {fp}")
        return {'status': 403, 'body': None}

    if os.path.exists(fp):
        with open(fp, 'rb') as f:
            content = f.read()
        return {
            'status': 200,
            'content_type': 'application/vnd.openxmlformats-officedocument.wordprocessingml.document',
            'headers': {'Content-Disposition': f'attachment; filename="{os.path.basename(fp)}"'},
            'body': content,
            'binary': True
        }

    return {'status': 404, 'body': None}


def handle_refresh_screener_data(query_params, refresh_status, refresh_screener_data_background):
    """
    Handle screener data refresh request.

    Args:
        query_params: URL query parameters
        refresh_status: Status dict for refresh operation
        refresh_screener_data_background: Function to refresh data in background

    Returns:
        JSON response with status
    """
    import threading

    scope = query_params.get('scope', ['france'])[0]

    # Check if already running
    if refresh_status['running']:
        return json_response({'error': 'Refresh already running'}, 400)

    # Start background refresh in a separate thread
    threading.Thread(target=refresh_screener_data_background, args=(scope,), daemon=True).start()

    return json_response({'status': 'started'})


def handle_refresh_status(refresh_status):
    """
    Handle refresh status request.

    Args:
        refresh_status: Status dict for refresh operation

    Returns:
        JSON response with status
    """
    return json_response(refresh_status)


def handle_screener_json(query_params, run_screener, load_watchlist):
    """
    Handle screener JSON API request.

    Args:
        query_params: URL query parameters
        run_screener: Function to run screener
        load_watchlist: Function to load watchlist

    Returns:
        JSON response with screener data
    """
    scope = query_params.get('scope', ['france'])[0]
    mode = query_params.get('mode', ['standard'])[0]
    force = 'force' in query_params

    screener_data = run_screener(force=force, scope=scope, mode=mode)
    watchlist = load_watchlist()
    wl_tickers = [w.get('ticker', '') for w in watchlist] if isinstance(watchlist, list) and watchlist and isinstance(watchlist[0], dict) else (watchlist or [])

    response = {
        'screener': screener_data,
        'watchlist': wl_tickers,
        'meta': {
            'scope': scope,
            'mode': mode,
            'count': len(screener_data),
            'timestamp': datetime.now().isoformat(),
            'cached': not force
        }
    }

    return {
        'status': 200,
        'content_type': 'application/json',
        'headers': {
            'Cache-Control': 'public, max-age=3600',
            'Access-Control-Allow-Origin': '*'
        },
        'body': json.dumps(response)
    }

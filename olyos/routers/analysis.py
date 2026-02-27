"""Analysis API Router - AI analysis, memos, portfolio advisor, optimization."""

import json
import tempfile
import os

from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import JSONResponse

from olyos.dependencies import ANTHROPIC_OK, ANTHROPIC_API_KEY, YFINANCE_OK, get_portfolio_service
from olyos.services.portfolio_service import PortfolioService
from olyos.logger import get_logger

log = get_logger('router.analysis')
router = APIRouter(prefix="/api/analysis", tags=["analysis"])


@router.post("/memo/create")
async def create_memo(request: Request):
    """Create an investment memo (manual)."""
    try:
        from olyos.dependencies import _get_app_module
        app = _get_app_module()

        form = await request.form()
        ticker = form.get('ticker', '')
        name = form.get('name', '')
        sector = form.get('sector', '')
        country = form.get('country', '')
        signal = form.get('signal', 'Surveillance')
        target_price = form.get('target_price', '')
        thesis = form.get('thesis', '')
        strengths = form.get('strengths', '')
        risks = form.get('risks', '')
        valuation = form.get('valuation', '')
        notes = form.get('notes', '')

        filepath, error = app.create_memo_docx(
            ticker, name, sector, country, signal, target_price,
            thesis, strengths, risks, valuation, notes,
        )

        if filepath:
            return {'success': True, 'filepath': filepath}
        return {'success': False, 'error': error}
    except Exception as e:
        log.error(f"Error creating memo: {e}")
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})


@router.post("/memo/generate")
async def generate_ai_memo(ticker: str = Query("")):
    """Generate investment memo with AI."""
    try:
        from olyos.dependencies import _get_app_module
        app = _get_app_module()

        security_data = app.get_security_data(ticker)
        filepath, error = app.generate_memo_with_ai(security_data)

        if filepath:
            return {'success': True, 'filepath': filepath}
        return {'success': False, 'error': error}
    except Exception as e:
        log.error(f"Error generating AI memo: {e}")
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})


@router.post("/stock")
async def analyze_stock(request: Request):
    """Run AI equity research analysis on a stock."""
    try:
        from olyos.dependencies import _get_app_module
        from olyos.services.ai_analysis import run_analysis as run_ai_analysis
        app = _get_app_module()

        body = await request.json()
        ticker = body.get('ticker', '')
        force_refresh = body.get('force_refresh', False)

        if not ticker:
            return {'success': False, 'error': 'Ticker manquant'}
        if not ANTHROPIC_OK:
            return {'success': False, 'error': 'API Anthropic non configurée. Définir ANTHROPIC_API_KEY.'}

        result = run_ai_analysis(
            ticker=ticker,
            get_security_data_func=app.get_security_data,
            yfinance_ok=YFINANCE_OK,
            api_key=ANTHROPIC_API_KEY,
            force_refresh=force_refresh,
        )
        return result
    except Exception as e:
        log.error(f"Error analyzing stock: {e}")
        return JSONResponse(status_code=500, content={'success': False, 'error': str(e)})


@router.post("/portfolio_advisor")
async def portfolio_advisor(
    request: Request,
    portfolio_svc: PortfolioService = Depends(get_portfolio_service),
):
    """Run portfolio advisor analysis."""
    try:
        from olyos.dependencies import _get_app_module
        app = _get_app_module()

        if not hasattr(app, 'run_portfolio_advisor_analysis') or app.run_portfolio_advisor_analysis is None:
            try:
                from olyos.olyos_portfolio_advisor import run_analysis as run_portfolio_advisor_analysis
            except Exception:
                return {'success': False, 'error': 'Portfolio advisor indisponible.'}
        else:
            run_portfolio_advisor_analysis = app.run_portfolio_advisor_analysis

        body = await request.json() if await request.body() else {}

        df = portfolio_svc.load_dataframe_or_raise()

        use_llm = bool(body.get('use_llm', True)) and ANTHROPIC_OK
        refresh_prices = bool(body.get('refresh_prices', False))
        cash = float(body.get('cash', 0.0) or 0.0)
        currency = str(body.get('currency', 'EUR') or 'EUR').upper()

        payload = app.build_advisor_portfolio_payload(df, cash=cash, currency=currency)
        if not payload.get('portfolio'):
            raise Exception("No active positions found in portfolio")

        temp_json_path = None
        try:
            with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False, encoding='utf-8') as tmpf:
                json.dump(payload, tmpf, ensure_ascii=False, indent=2)
                temp_json_path = tmpf.name

            result = run_portfolio_advisor_analysis(
                portfolio_path=temp_json_path,
                use_llm=use_llm,
                verbose=False,
                render_output=False,
                fetch_prices_enabled=refresh_prices,
            )

            return {
                'success': True,
                'report_markdown': result.get('report_markdown', ''),
                'report_path': result.get('report_path'),
                'scratchpad_path': result.get('scratchpad_path'),
                'llm_used': bool(result.get('llm_used', False)),
                'refresh_prices': refresh_prices,
            }
        finally:
            if temp_json_path and os.path.exists(temp_json_path):
                try:
                    os.remove(temp_json_path)
                except Exception:
                    pass
    except Exception as e:
        log.error(f"Portfolio advisor error: {e}")
        return {'success': False, 'error': str(e)}


@router.post("/optimize")
async def ai_optimize(
    scope: str = Query("france"),
    goal: str = Query("balanced"),
):
    """AI-powered optimization."""
    try:
        from olyos.dependencies import _get_app_module
        app = _get_app_module()
        log.info(f"AI OPTIMIZER: Starting for {scope} with goal: {goal}")
        result = app.run_ai_optimization(scope, goal)
        return result
    except Exception as e:
        log.error(f"AI OPTIMIZE error: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})


@router.post("/download_data")
async def download_data(scope: str = Query("france")):
    """Bulk data download for a scope."""
    try:
        from olyos.dependencies import _get_app_module
        app = _get_app_module()
        log.info(f"Downloading all data for {scope}...")
        result = app.download_all_data(scope, start_date='2010-01-01')
        return result
    except Exception as e:
        log.error(f"Download error: {e}")
        return JSONResponse(status_code=500, content={'error': str(e)})

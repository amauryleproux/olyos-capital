"""Pages Router - HTML page rendering (dashboard, detail, screener, advisor).

The router now uses Jinja2 templates for rendering.
"""

import json
import html
import math
from datetime import datetime
from typing import Any, Dict, List

from fastapi import APIRouter, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates

from olyos.dependencies import YFINANCE_OK, ANTHROPIC_OK
from olyos.logger import get_logger

log = get_logger('router.pages')
router = APIRouter(tags=["pages"])


def _get_templates():
    """Lazy import to avoid circular dependency with main.py."""
    from olyos.main import templates
    return templates


def fmt_val(val: float, decimals: int = 2) -> str:
    """Format a value with thousand separators."""
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return '-'
    if val == 0:
        return '0'
    if abs(val) >= 1e9:
        return f"{val/1e9:.{decimals}f}B"
    if abs(val) >= 1e6:
        return f"{val/1e6:.{decimals}f}M"
    if abs(val) >= 1e3:
        return f"{val/1e3:,.{decimals}f}"
    return f"{val:,.{decimals}f}"


def safe_float(val: Any) -> float:
    """Safely convert value to float."""
    try:
        if val is None:
            return 0.0
        if isinstance(val, float):
            return 0.0 if math.isnan(val) else val
        return float(val)
    except (ValueError, TypeError):
        return 0.0


@router.get("/", response_class=HTMLResponse)
def home_page(
    request: Request,
    refresh: str = Query(None),
    screener: str = Query(None),
    scope: str = Query("france"),
    mode: str = Query("standard"),
):
    """Main portfolio dashboard."""
    try:
        from olyos.dependencies import _get_app_module

        app = _get_app_module()

        # Get PORTFOLIO_ADVISOR_OK from app module
        try:
            PORTFOLIO_ADVISOR_OK = app.PORTFOLIO_ADVISOR_OK
        except AttributeError:
            PORTFOLIO_ADVISOR_OK = False

        df, err = app.load_portfolio()
        if err:
            return HTMLResponse(f"<h1>Erreur: {err}</h1>", status_code=500)

        do_refresh = refresh is not None and YFINANCE_OK
        if do_refresh:
            log.info("Refreshing portfolio data...")
            df = app.update_portfolio(df)

        screener_scope = scope if screener is not None else 'france'
        screener_mode = mode if screener is not None else 'standard'
        screener_data = app.run_screener(force=screener is not None, scope=screener_scope, mode=screener_mode)

        df = app.calc_scores(df)

        # Load watchlist and convert to list
        watchlist = app.load_watchlist()
        if not isinstance(watchlist, list):
            watchlist = list(watchlist) if watchlist else []

        # Convert to records
        pos = df.to_dict('records')
        active = [p for p in pos if (p.get('qty') or 0) > 0]

        # Calculate totals
        tv = 0.0
        tc = 0.0
        for p in active:
            price = safe_float(p.get('price_eur')) or 0
            qty = safe_float(p.get('qty')) or 0
            cost = safe_float(p.get('avg_cost_eur')) or 0
            tv += price * qty
            tc += cost * qty

        pnl = tv - tc
        pnl_pct = (tv / tc - 1) * 100 if tc > 0 else 0
        pnl_sign = '+' if pnl >= 0 else ''
        pnl_is_negative = pnl < 0
        pnl_is_positive = pnl >= 0

        # Opportunities count
        opps = len([s for s in screener_data if s.get('signal') == 'ACHAT'])

        # Get realized PnL
        total_realized_pnl = 0.0
        try:
            price_data = {p.get('ticker', '').upper(): safe_float(p.get('price_eur')) or 0 for p in pos}
            name_data = {p.get('ticker', '').upper(): p.get('name', '') for p in pos}
            manager = app.get_position_manager()
            pnl_summary = manager.get_all_positions(price_data, name_data)
            total_realized_pnl = pnl_summary.total_realized_pnl
        except Exception as e:
            log.warning(f"Could not get realized PnL: {e}")

        # NAV calculation
        nav_total = tv + total_realized_pnl
        total_pnl = pnl + total_realized_pnl
        total_pnl_pct = (total_pnl / tc * 100) if tc > 0 else 0

        # Update NAV history if requested
        if do_refresh and nav_total > 0:
            nav_history = app.update_nav_history(nav_total, tc, total_pnl, total_pnl_pct, total_realized_pnl)
        else:
            nav_history = app.load_nav_history()

        # Calculate performance stats
        if nav_history and len(nav_history) > 1:
            first_nav = nav_history[0]['nav']
            last_nav = nav_history[-1]['nav']
            total_perf = ((last_nav / first_nav) - 1) * 100 if first_nav > 0 else 0
            nav_high = max(h['nav'] for h in nav_history)
            nav_low = min(h['nav'] for h in nav_history)

            if len(nav_history) >= 5:
                week_ago = nav_history[-5]['nav']
                perf_1w = ((last_nav / week_ago) - 1) * 100 if week_ago > 0 else 0
            else:
                perf_1w = 0

            if len(nav_history) >= 22:
                month_ago = nav_history[-22]['nav']
                perf_1m = ((last_nav / month_ago) - 1) * 100 if month_ago > 0 else 0
            else:
                perf_1m = total_perf
        else:
            total_perf = pnl_pct
            perf_1w = 0
            perf_1m = 0
            nav_high = tv
            nav_low = tv

        perf_1w_is_positive = perf_1w >= 0
        perf_1m_is_positive = perf_1m >= 0
        total_perf_is_positive = total_perf >= 0

        nav_history_json = json.dumps(nav_history)

        # Build portfolio positions data for Jinja2 template
        positions = []
        for p in active:
            price = safe_float(p.get('price_eur')) or 0
            cost = safe_float(p.get('avg_cost_eur')) or 1
            qty = safe_float(p.get('qty')) or 0
            val = price * qty
            pp = (price / cost - 1) * 100 if cost > 0 else 0
            poids = (val / tv * 100) if tv > 0 else 0

            pe = safe_float(p.get('pe_ttm'))
            pcf = safe_float(p.get('pcf')) or safe_float(p.get('price_to_cashflow'))
            roe = safe_float(p.get('roe_ttm'))
            sig = str(p.get('signal', 'HOLD')).strip()

            # Signal class
            sig_lower = sig.lower()
            if sig_lower in ['buy', 'achat']:
                sc = 'sig-achat'
            elif sig_lower in ['sell', 'ecarter']:
                sc = 'sig-ecarter'
            elif sig_lower in ['watch', 'surveillance']:
                sc = 'sig-surveillance'
            else:
                sc = 'sig-neutre'

            # Color coding
            if pe:
                pe_color = '#00ff00' if pe <= 10 else '#ffff00' if pe <= 12 else '#fff'
                pe_weight = '700' if pe <= 10 else '600' if pe <= 12 else '400'
            else:
                pe_color, pe_weight = '#666', '400'

            if pcf:
                pcf_color = '#00ff00' if pcf <= 8 else '#ffff00' if pcf <= 12 else '#ff4444'
                pcf_weight = '700' if pcf <= 8 else '600' if pcf <= 12 else '400'
            else:
                pcf_color, pcf_weight = '#666', '400'

            if roe:
                roe_pct = roe * 100
                roe_color = '#00ff00' if roe_pct >= 15 else '#ffff00' if roe_pct >= 10 else '#fff'
            else:
                roe_color = '#666'

            ticker = p['ticker']
            name = str(p.get('name', ''))[:16]
            ps = '+' if pp >= 0 else ''

            positions.append({
                'ticker': ticker,
                'name': name,
                'qty': f"{int(qty)}" if qty == int(qty) else f"{qty:.2f}",
                'qty_raw': qty,
                'cost_raw': cost,
                'price_str': fmt_val(price) if price > 0 else '-',
                'val_str': fmt_val(val, 0) if val > 0 else '-',
                'poids_str': f"{poids:.1f}%" if val > 0 else '-',
                'chg_str': f"{ps}{pp:.1f}%" if price > 0 else '-',
                'chg_class': 'pos' if pp >= 0 else 'neg',
                'pe_str': fmt_val(pe, 1) if pe else '-',
                'pe_color': pe_color,
                'pe_weight': pe_weight,
                'pcf_str': fmt_val(pcf, 1) if pcf else '-',
                'pcf_color': pcf_color,
                'pcf_weight': pcf_weight,
                'roe_str': f"{roe*100:.0f}%" if roe else '-',
                'roe_color': roe_color,
                'sig': sig,
                'sig_class': sc,
            })

        # Prepare template context
        context = {
            "request": request,
            # Basic portfolio info
            "tv": tv,
            "tv_formatted": f"{tv:,.0f}",
            "tc": tc,
            "pnl": pnl,
            "pnl_abs": f"{abs(pnl):,.0f}",
            "pnl_formatted": f"{pnl:,.0f}",
            "pnl_sign": pnl_sign,
            "pnl_pct": f"{pnl_pct:.1f}",
            "pnl_is_negative": pnl_is_negative,
            "pnl_is_positive": pnl_is_positive,
            # NAV and performance
            "nav_total": f"{nav_total:,.0f}",
            "total_pnl": f"{total_pnl:,.0f}",
            "total_pnl_pct": f"{total_pnl_pct:.1f}",
            "perf_1w": f"{perf_1w:.1f}",
            "perf_1m": f"{perf_1m:.1f}",
            "total_perf": f"{total_perf:.1f}",
            "perf_1w_is_positive": perf_1w_is_positive,
            "perf_1m_is_positive": perf_1m_is_positive,
            "total_perf_is_positive": total_perf_is_positive,
            "nav_high": f"{nav_high:,.0f}",
            "nav_low": f"{nav_low:,.0f}",
            "nav_history_json": nav_history_json,
            "nav_days": len(nav_history) if nav_history else 0,
            # Counts
            "active_count": len(active),
            "watchlist_count": len(watchlist),
            "opps": opps,
            # Data for Jinja2 loops
            "positions": positions,
            "watchlist": watchlist,
            # DateTime
            "datetime_formatted": datetime.now().strftime('%H:%M:%S'),
            "datetime_formatted_long": datetime.now().strftime('%d-%b %H:%M').upper(),
            # Feature flags
            "portfolio_advisor_ok": PORTFOLIO_ADVISOR_OK,
            "anthropic_ok": ANTHROPIC_OK,
            # Other flags (dummy values for now)
            "eod_available": False,
            "eod_api_ok": False,
            # JSON data for JavaScript
            "screener_json": json.dumps(screener_data),
            "watchlist_tickers_json": json.dumps([w.get('ticker', '') for w in watchlist]),
            "screener_count": len(screener_data),
        }

        return _get_templates().TemplateResponse("dashboard.html", context)
    except Exception as e:
        log.error(f"Error rendering home page: {e}", exc_info=True)
        return HTMLResponse(f"<h1>Error: {e}</h1>", status_code=500)


@router.get("/detail", response_class=HTMLResponse)
def detail_page(request: Request):
    """Security detail page — rendered via Jinja2 template."""
    try:
        import json
        import math
        import os
        from datetime import datetime
        from olyos.dependencies import _get_app_module
        from olyos.main import templates

        app = _get_app_module()

        # Get ticker from query string (the old code used raw query string)
        ticker = str(request.query_params).split('=')[0] if request.query_params else ''
        if not ticker or ticker.startswith('action'):
            # Try to get it from the query params dict
            for key in request.query_params:
                if key not in ('action',):
                    ticker = key
                    break

        if not ticker:
            return HTMLResponse("<h1>Ticker manquant</h1>", status_code=400)

        security_data = app.get_security_data(ticker)

        # Helper functions to format data
        def fmt(v, pre='', suf='', dec=2):
            if v is None or (isinstance(v, float) and math.isnan(v)):
                return '-'
            if isinstance(v, (int, float)):
                if abs(v) >= 1e9:
                    return f"{pre}{v/1e9:.1f}B{suf}"
                if abs(v) >= 1e6:
                    return f"{pre}{v/1e6:.1f}M{suf}"
                return f"{pre}{v:,.{dec}f}{suf}".replace(",", " ")
            return f"{pre}{v}{suf}"

        def pct(v):
            if v is None or (isinstance(v, float) and math.isnan(v)):
                return '-'
            return f"{v*100:+.2f}%" if abs(v) < 1 else f"{v:+.2f}%"

        # Prepare change indicators
        change = security_data.get('change', 0) or 0
        chg_sign = '+' if change >= 0 else ''

        # Price history and performance calculations
        price_history = security_data.get('price_history', [])
        perf_1y = perf_1m = perf_3m = 0
        high_1y = low_1y = security_data.get('price', 0)

        if price_history and len(price_history) > 1:
            first_price = price_history[0]['close']
            last_price = price_history[-1]['close']
            perf_1y = ((last_price / first_price) - 1) * 100 if first_price > 0 else 0
            high_1y = max(p['close'] for p in price_history)
            low_1y = min(p['close'] for p in price_history)

            if len(price_history) > 22:
                perf_1m = ((last_price / price_history[-22]['close']) - 1) * 100
            else:
                perf_1m = perf_1y

            if len(price_history) > 66:
                perf_3m = ((last_price / price_history[-66]['close']) - 1) * 100
            else:
                perf_3m = perf_1y

        # Prepare memo section
        if security_data.get('memo_content'):
            from urllib.parse import quote
            memo_html = f'''
<div class="bb-memo-header" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">
<span style="color:#ff9500;font-size:10px;text-transform:uppercase;letter-spacing:1px">🔍„ {os.path.basename(security_data['memo_file'])}</span>
<a href="/?download={quote(security_data['memo_file'])}" class="bb-btn" style="padding:4px 8px;font-size:9px">
↓ Download
</a>
</div>
<div class="bb-memo-content">
{security_data['memo_content']}
</div>'''
        elif security_data.get('memo_file'):
            from urllib.parse import quote
            memo_html = f'''<a href="/?download={quote(security_data['memo_file'])}" class="bb-memo-btn"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm4 18H6V4h7v5h5v11z"/><path d="M12 18l4-4h-3v-4h-2v4H8l4 4z"/></svg>Download: {os.path.basename(security_data['memo_file'])}</a>'''
        else:
            from olyos.dependencies import ANTHROPIC_OK
            ai_button = f'''<button class="bb-create-memo-btn" style="background:linear-gradient(180deg,#1a0033,#0d001a);border-color:#9933ff;color:#9933ff" onclick="generateAIMemo()" id="aiGenBtn">
<svg viewBox="0 0 24 24" fill="currentColor" width="16" height="16"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg>
🤖 Generate with AI
</button>''' if ANTHROPIC_OK else '<div style="color:#666;font-size:10px;margin-top:8px">AI generation requires ANTHROPIC_API_KEY environment variable</div>'

            memo_html = f'''
<div class="bb-no-memo">No investment memo available for this security.</div>
{ai_button}
<button class="bb-create-memo-btn" onclick="toggleMemoForm()">
<svg viewBox="0 0 24 24" fill="currentColor" width="16" height="16"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>
✏️ Create Manual Memo
</button>
<div class="bb-memo-form" id="memoForm">
<h4>🔍 New Investment Memo - {security_data['ticker']}</h4>
<form id="createMemoForm" action="/?action=create_memo" method="POST">
<input type="hidden" name="ticker" value="{security_data['ticker']}">
<input type="hidden" name="name" value="{security_data.get('name', '')}">
<input type="hidden" name="sector" value="{security_data.get('sector', '')}">
<input type="hidden" name="country" value="{security_data.get('country', '')}">

<div class="bb-memo-form-row">
<div class="bb-memo-form-group">
<label>Signal / Recommendation</label>
<select name="signal">
<option value="Achat">ACHAT (Buy)</option>
<option value="Surveillance" selected>SURVEILLANCE (Watch)</option>
<option value="Neutre">NEUTRE (Hold)</option>
<option value="Ecarter">ECARTER (Sell)</option>
</select>
</div>
<div class="bb-memo-form-group">
<label>Target Price (EUR)</label>
<input type="number" name="target_price" step="0.01" placeholder="Ex: 25.50" value="{security_data.get('target_price', '') or ''}">
</div>
</div>

<div class="bb-memo-form-group">
<label>Investment Thesis (Why invest?)</label>
<textarea name="thesis" placeholder="Describe the main reasons to invest in this company..."></textarea>
</div>

<div class="bb-memo-form-group">
<label>Key Strengths / Catalysts</label>
<textarea name="strengths" placeholder="List the key strengths and potential catalysts..."></textarea>
</div>

<div class="bb-memo-form-group">
<label>Risks / Concerns</label>
<textarea name="risks" placeholder="List the main risks and concerns..."></textarea>
</div>

<div class="bb-memo-form-row">
<div class="bb-memo-form-group">
<label>Valuation Notes</label>
<textarea name="valuation" placeholder="PE, ROE, comparison with peers..." style="min-height:60px"></textarea>
</div>
<div class="bb-memo-form-group">
<label>Additional Notes</label>
<textarea name="notes" placeholder="Any other relevant information..." style="min-height:60px"></textarea>
</div>
</div>

<div class="bb-memo-form-actions">
<button type="submit" class="btn-save">💾 Save Memo</button>
<button type="button" class="btn-cancel" onclick="toggleMemoForm()">Cancel</button>
</div>
</form>
</div>'''

        # Prepare template context
        context = {
            "request": request,
            "ticker": security_data.get('ticker', ''),
            "name": security_data.get('name', ''),
            "sector": security_data.get('sector', ''),
            "country": security_data.get('country', ''),
            "industry": security_data.get('industry', ''),
            "price": security_data.get('price', 0),
            "price_display": fmt(security_data.get('price', 0)),
            "change": change,
            "change_display": fmt(change),
            "change_pct_display": fmt(security_data.get('change_pct', 0)),
            "change_sign": chg_sign,
            "pe": security_data.get('pe'),
            "forward_pe": security_data.get('forward_pe'),
            "eps": security_data.get('eps'),
            "book_value": security_data.get('book_value'),
            "target_price": security_data.get('target_price'),
            "roe": security_data.get('roe'),
            "profit_margin": security_data.get('profit_margin'),
            "dividend_yield": security_data.get('dividend_yield'),
            "beta": security_data.get('beta'),
            "market_cap": security_data.get('market_cap'),
            "high_52w": security_data.get('high_52w'),
            "low_52w": security_data.get('low_52w'),
            "volume": security_data.get('volume'),
            "avg_volume": security_data.get('avg_volume'),
            "revenue": security_data.get('revenue'),
            "debt_equity": security_data.get('debt_equity'),
            "current_ratio": security_data.get('current_ratio'),
            "employees": security_data.get('employees'),
            "description": security_data.get('description', ''),
            "website": security_data.get('website', ''),
            "perf_1y": perf_1y,
            "perf_1m": perf_1m,
            "perf_3m": perf_3m,
            "high_1y": high_1y,
            "low_1y": low_1y,
            "price_history_json": json.dumps(price_history),
            "memo_html": memo_html,
            "current_time": datetime.now().strftime('%H:%M:%S'),
            "current_datetime": datetime.now().strftime('%d-%b-%Y %H:%M:%S').upper(),
            "fmt": fmt,
            "pct": pct,
        }

        return _get_templates().TemplateResponse("detail.html", context)
    except Exception as e:
        log.error(f"Error rendering detail page: {e}")
        return HTMLResponse(f"<h1>Error: {e}</h1>", status_code=500)


@router.get("/advisor", response_class=HTMLResponse)
def advisor_page(request: Request):
    """Portfolio advisor page — rendered via Jinja2 template."""
    try:
        from datetime import datetime
        from olyos.dependencies import ANTHROPIC_OK
        from olyos.main import templates

        # Check if portfolio advisor module is available
        try:
            from olyos.olyos_portfolio_advisor import run_analysis
            advisor_ok = True
        except Exception:
            advisor_ok = False

        return _get_templates().TemplateResponse("advisor.html", {
            "request": request,
            "advisor_ok": advisor_ok,
            "anthropic_ok": ANTHROPIC_OK,
            "current_time": datetime.now().strftime('%H:%M:%S'),
        })
    except Exception as e:
        log.error(f"Error rendering advisor page: {e}")
        return HTMLResponse(f"<h1>Error: {e}</h1>", status_code=500)


@router.get("/screener", response_class=HTMLResponse)
def screener_page():
    """Screener V2 page (loads from template file)."""
    try:
        import os
        from olyos.dependencies import _get_app_module
        app = _get_app_module()

        template_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'olyos', 'templates')
        # Try the templates directory relative to the olyos package
        for candidate in [
            os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'templates', 'screener_v2.html'),
            os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'templates', 'screener_v2.html'),
        ]:
            path = os.path.normpath(candidate)
            if os.path.exists(path):
                with open(path, 'r', encoding='utf-8') as f:
                    return HTMLResponse(f.read())

        return HTMLResponse("<h1>Screener template not found</h1>", status_code=404)
    except Exception as e:
        log.error(f"Error rendering screener page: {e}")
        return HTMLResponse(f"<h1>Error: {e}</h1>", status_code=500)

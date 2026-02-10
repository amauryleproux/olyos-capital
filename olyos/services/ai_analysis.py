"""
AI Equity Research Analysis Service

Generates Bloomberg-style equity research reports using Claude API,
evaluating stocks against the William Higgons methodology.
"""

import os
import json
import math
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, Tuple

from olyos.logger import get_logger

log = get_logger('ai_analysis')

# Cache directory for analyses
_DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'data')
ANALYSIS_CACHE_DIR = os.path.join(_DATA_DIR, 'cache', 'analyses')


def get_stock_analysis_data(ticker: str, get_security_data_func, yfinance_ok: bool) -> Optional[Dict[str, Any]]:
    """
    Collects all financial data needed for the AI equity research analysis.
    Uses yfinance for comprehensive data fetching.
    Returns a structured dict or None if data is unavailable.
    """
    try:
        # Get base data from existing function
        base_data = get_security_data_func(ticker)
        if not base_data or not base_data.get('price'):
            log.warning(f"No base data available for {ticker}")
            return None

        data = {}

        # --- Market data ---
        data['market'] = {
            'ticker': ticker,
            'name': base_data.get('name', ''),
            'exchange': _detect_exchange(ticker),
            'isin': '',
            'sector': base_data.get('sector', ''),
            'industry': base_data.get('industry', ''),
            'currency': _detect_currency(ticker),
            'price': base_data.get('price', 0),
            'price_change_1d': round(base_data.get('change_pct', 0), 2),
            'high_52w': base_data.get('high_52w', 0) or 0,
            'low_52w': base_data.get('low_52w', 0) or 0,
            'market_cap': base_data.get('market_cap', 0) or 0,
            'shares_outstanding': 0,
            'beta': base_data.get('beta', 0) or 0,
            'volume_avg': base_data.get('avg_volume', 0) or 0,
        }

        # --- Valuation ratios ---
        data['valuation'] = {
            'per_ttm': base_data.get('pe') or 0,
            'per_forward': base_data.get('forward_pe') or 0,
            'price_to_book': 0,
            'price_to_sales': 0,
            'ev_ebitda': 0,
            'price_to_fcf': 0,
        }

        # --- Profitability ---
        roe_raw = base_data.get('roe')
        roe_pct = (roe_raw * 100) if roe_raw and abs(roe_raw) < 1 else (roe_raw or 0)
        profit_margin_raw = base_data.get('profit_margin')
        profit_margin_pct = (profit_margin_raw * 100) if profit_margin_raw and abs(profit_margin_raw) < 1 else (profit_margin_raw or 0)

        data['profitability'] = {
            'roe': round(roe_pct, 2),
            'roa': 0,
            'roic': 0,
            'gross_margin': 0,
            'operating_margin': 0,
            'net_margin': round(profit_margin_pct, 2),
        }

        # --- Balance sheet ---
        data['balance_sheet'] = {
            'total_assets': 0,
            'total_liabilities': 0,
            'total_equity': 0,
            'total_debt': 0,
            'net_cash': 0,
            'debt_to_equity': base_data.get('debt_equity', 0) or 0,
            'current_ratio': base_data.get('current_ratio', 0) or 0,
        }

        # --- Income history ---
        data['income_history'] = []

        # --- Dividends ---
        div_yield_raw = base_data.get('dividend_yield')
        div_yield_pct = (div_yield_raw * 100) if div_yield_raw and abs(div_yield_raw) < 1 else (div_yield_raw or 0)

        data['dividends'] = {
            'dividend_per_share': 0,
            'dividend_yield': round(div_yield_pct, 2),
            'payout_ratio': 0,
        }

        # --- Momentum ---
        price_history = base_data.get('price_history', [])
        data['momentum'] = _calculate_momentum(price_history, base_data.get('price', 0))

        # --- Enrich with yfinance extended data ---
        if yfinance_ok:
            _enrich_with_yfinance(ticker, data)

        # Format market cap for display
        mc = data['market']['market_cap']
        if mc and mc > 0:
            data['market']['market_cap'] = round(mc / 1e6, 1)  # Convert to millions

        return data

    except Exception as e:
        log.error(f"Error collecting analysis data for {ticker}: {e}", exc_info=True)
        return None


def _detect_exchange(ticker: str) -> str:
    """Detect exchange from ticker suffix."""
    if ticker.endswith('.PA'):
        return 'Euronext Paris'
    elif ticker.endswith('.AS'):
        return 'Euronext Amsterdam'
    elif ticker.endswith('.BR'):
        return 'Euronext Brussels'
    elif ticker.endswith('.MI'):
        return 'Borsa Italiana'
    elif ticker.endswith('.DE'):
        return 'XETRA Frankfurt'
    elif ticker.endswith('.L'):
        return 'London Stock Exchange'
    elif ticker.endswith('.MC'):
        return 'Bolsa de Madrid'
    return 'Euronext Paris'


def _detect_currency(ticker: str) -> str:
    """Detect currency from ticker suffix."""
    if ticker.endswith('.L'):
        return 'GBP'
    return 'EUR'


def _calculate_momentum(price_history: list, current_price: float) -> Dict[str, Any]:
    """Calculate momentum metrics from price history."""
    momentum = {
        'perf_1m': 0, 'perf_3m': 0, 'perf_6m': 0,
        'perf_1y': 0, 'perf_ytd': 0,
        'vs_sma50': 0, 'vs_sma200': 0,
        'trend': 'neutral',
    }

    if not price_history or len(price_history) < 2:
        return momentum

    closes = [p['close'] for p in price_history]
    last = closes[-1]

    # Performance calculations
    if len(closes) > 22 and closes[-22] > 0:
        momentum['perf_1m'] = round(((last / closes[-22]) - 1) * 100, 2)
    if len(closes) > 66 and closes[-66] > 0:
        momentum['perf_3m'] = round(((last / closes[-66]) - 1) * 100, 2)
    if len(closes) > 132 and closes[-132] > 0:
        momentum['perf_6m'] = round(((last / closes[-132]) - 1) * 100, 2)
    if closes[0] > 0:
        momentum['perf_1y'] = round(((last / closes[0]) - 1) * 100, 2)

    # YTD performance
    current_year = datetime.now().year
    ytd_prices = [p for p in price_history if p['date'].startswith(str(current_year))]
    if ytd_prices and ytd_prices[0]['close'] > 0:
        momentum['perf_ytd'] = round(((last / ytd_prices[0]['close']) - 1) * 100, 2)

    # SMA calculations
    if len(closes) >= 50:
        sma50 = sum(closes[-50:]) / 50
        if sma50 > 0:
            momentum['vs_sma50'] = round(((last / sma50) - 1) * 100, 2)
    if len(closes) >= 200:
        sma200 = sum(closes[-200:]) / 200
        if sma200 > 0:
            momentum['vs_sma200'] = round(((last / sma200) - 1) * 100, 2)

    # Trend determination
    bullish_count = 0
    if momentum['perf_1m'] > 0: bullish_count += 1
    if momentum['perf_3m'] > 0: bullish_count += 1
    if momentum['vs_sma50'] > 0: bullish_count += 1
    if momentum['vs_sma200'] > 0: bullish_count += 1

    if bullish_count >= 3:
        momentum['trend'] = 'bullish'
    elif bullish_count <= 1:
        momentum['trend'] = 'bearish'
    else:
        momentum['trend'] = 'neutral'

    return momentum


def _enrich_with_yfinance(ticker: str, data: Dict[str, Any]) -> None:
    """Enrich analysis data with extended yfinance fields."""
    try:
        import yfinance as yf

        # Convert ticker format if needed
        yf_ticker = ticker if '.' in ticker else ticker + '.PA'
        t = yf.Ticker(yf_ticker)
        info = t.info

        # ISIN
        data['market']['isin'] = info.get('isin', '')

        # Shares outstanding
        data['market']['shares_outstanding'] = info.get('sharesOutstanding', 0) or 0

        # Valuation enrichment
        price = data['market']['price']
        book_val = info.get('bookValue')
        if book_val and book_val > 0 and price > 0:
            data['valuation']['price_to_book'] = round(price / book_val, 2)

        data['valuation']['price_to_sales'] = info.get('priceToSalesTrailing12Months') or 0
        data['valuation']['ev_ebitda'] = info.get('enterpriseToEbitda') or 0

        fcf = info.get('freeCashflow')
        mc = info.get('marketCap')
        if fcf and fcf > 0 and mc and mc > 0:
            data['valuation']['price_to_fcf'] = round(mc / fcf, 2)

        # Profitability enrichment
        roa = info.get('returnOnAssets')
        if roa:
            data['profitability']['roa'] = round(roa * 100 if abs(roa) < 1 else roa, 2)

        gross_margin = info.get('grossMargins')
        if gross_margin:
            data['profitability']['gross_margin'] = round(gross_margin * 100 if abs(gross_margin) < 1 else gross_margin, 2)

        op_margin = info.get('operatingMargins')
        if op_margin:
            data['profitability']['operating_margin'] = round(op_margin * 100 if abs(op_margin) < 1 else op_margin, 2)

        # Balance sheet enrichment
        data['balance_sheet']['total_assets'] = round((info.get('totalAssets') or 0) / 1e6, 1)
        data['balance_sheet']['total_equity'] = round(
            ((info.get('bookValue') or 0) * (info.get('sharesOutstanding') or 0)) / 1e6, 1
        )
        total_debt = info.get('totalDebt') or 0
        total_cash = info.get('totalCash') or 0
        data['balance_sheet']['total_debt'] = round(total_debt / 1e6, 1)
        data['balance_sheet']['net_cash'] = round((total_cash - total_debt) / 1e6, 1)

        # Dividends enrichment
        data['dividends']['dividend_per_share'] = info.get('dividendRate') or 0
        payout = info.get('payoutRatio')
        if payout:
            data['dividends']['payout_ratio'] = round(payout * 100 if abs(payout) < 1 else payout, 2)

        # Income history from financials
        try:
            financials = t.financials
            if financials is not None and not financials.empty:
                for col in financials.columns[:5]:  # Last 5 years
                    year = col.year if hasattr(col, 'year') else int(str(col)[:4])
                    revenue = financials.loc['Total Revenue', col] if 'Total Revenue' in financials.index else None
                    ebitda_val = financials.loc['EBITDA', col] if 'EBITDA' in financials.index else None
                    ebit = financials.loc['EBIT', col] if 'EBIT' in financials.index else None
                    net_income = financials.loc['Net Income', col] if 'Net Income' in financials.index else None

                    entry = {
                        'year': year,
                        'revenue': round(revenue / 1e6, 1) if revenue else 0,
                        'revenue_growth': 0,
                        'ebitda': round(ebitda_val / 1e6, 1) if ebitda_val else 0,
                        'ebit': round(ebit / 1e6, 1) if ebit else 0,
                        'net_income': round(net_income / 1e6, 1) if net_income else 0,
                        'eps': 0,
                        'fcf': 0,
                    }

                    # EPS
                    shares = data['market']['shares_outstanding']
                    if net_income and shares and shares > 0:
                        entry['eps'] = round(net_income / shares, 2)

                    data['income_history'].append(entry)

                # Calculate YoY revenue growth
                data['income_history'].sort(key=lambda x: x['year'])
                for i in range(1, len(data['income_history'])):
                    prev_rev = data['income_history'][i - 1]['revenue']
                    curr_rev = data['income_history'][i]['revenue']
                    if prev_rev and prev_rev > 0:
                        data['income_history'][i]['revenue_growth'] = round(
                            ((curr_rev / prev_rev) - 1) * 100, 1
                        )

            # Free cash flow from cashflow statement
            cashflow = t.cashflow
            if cashflow is not None and not cashflow.empty:
                for entry in data['income_history']:
                    for col in cashflow.columns:
                        col_year = col.year if hasattr(col, 'year') else int(str(col)[:4])
                        if col_year == entry['year']:
                            fcf_val = cashflow.loc['Free Cash Flow', col] if 'Free Cash Flow' in cashflow.index else None
                            if fcf_val:
                                entry['fcf'] = round(fcf_val / 1e6, 1)
                            break

        except Exception as e:
            log.warning(f"Could not fetch financial history for {ticker}: {e}")

    except Exception as e:
        log.warning(f"Could not enrich data with yfinance for {ticker}: {e}")


def build_analysis_prompt(stock_data: Dict[str, Any]) -> Tuple[str, str]:
    """
    Builds the system prompt and user prompt for Claude API analysis.
    Returns (system_prompt, user_prompt).
    """

    system_prompt = """Tu es un analyste equity research senior travaillant pour Olyos Capital, un fonds d'investissement value inspiré de la méthode William Higgons.

MÉTHODE HIGGONS — CRITÈRES DE SÉLECTION :
1. PER très faible : idéalement < 10, acceptable < 12
2. Petite capitalisation : small/mid cap européennes
3. ROE élevé : > 15% idéalement, > 12% acceptable
4. Dette faible : dette/equity < 50%, idéalement trésorerie nette positive
5. Momentum haussier : tendance technique positive, au-dessus des moyennes mobiles

MISSION : Générer un rapport d'equity research COMPLET au format HTML Bloomberg Terminal pour la valeur fournie.

FORMAT DE SORTIE OBLIGATOIRE :
Tu dois retourner UNIQUEMENT du HTML valide (pas de markdown, pas de ```html), qui sera injecté directement dans un conteneur.

Le HTML doit utiliser le design system suivant :
- Font : 'JetBrains Mono', monospace (déjà chargée dans la page parente)
- Background : transparent (le conteneur parent gère le fond #0a0e14)
- Couleurs CSS variables disponibles dans le parent :
  --bg-primary: #0a0e14
  --bg-secondary: #111822
  --bg-tertiary: #1a2332
  --border: #1e2d3d
  --text-primary: #e6edf3
  --text-secondary: #8b949e
  --text-muted: #484f58
  --green: #00ff88
  --red: #ff4444
  --orange: #ff9500
  --yellow: #ffd700
  --blue: #58a6ff
  --cyan: #00d4ff

STRUCTURE DU RAPPORT (toutes les sections sont OBLIGATOIRES) :

1. **HEADER TICKER** : Nom société, ticker, exchange, ISIN, secteur, tags (recommendation + type cap + type secteur), prix actuel avec variation

2. **VERDICT HIGGONS** (bannière colorée) : Résumé en 3-4 lignes avec score X/5 et conclusion claire (Éligible / Watchlist / Non éligible)

3. **MÉTRIQUES CLÉS** (panel gauche) : Capitalisation, cours vs 52w, PER, P/B, P/S, EV/EBITDA, ROE, ROIC, trésorerie nette, FCF, marge nette, beta, dividende

4. **SCORE HIGGONS DÉTAILLÉ** (panel droit) : Les 5 critères avec ✓/✗/~ et valeurs cibles vs réelles, score badge X/5, note explicative

5. **ÉVOLUTION FINANCIÈRE** (tableau) : 3-5 ans de CA, croissance, EBITDA, résultat op, marge, résultat net, FCF, trésorerie nette avec code couleur vert/rouge

6. **CONSENSUS ANALYSTES** (si disponible) : Objectif moyen/haut/bas, répartition achat/neutre/vente, valorisation par les actifs

7. **ANALYSE SWOT** (grille 2x2) : Forces, Faiblesses, Opportunités, Menaces — minimum 5 points par catégorie

8. **ANALYSE NARRATIVE** : 4-6 paragraphes d'analyse approfondie couvrant :
   - Situation actuelle de la société
   - Évaluation méthode Higgons détaillée
   - Points de blocage ou critères manquants
   - Catalyseurs de retournement
   - Target de prix (approche par les actifs, par les multiples, par DCF simplifié)
   - Recommandation finale Olyos Capital

9. **CATALYSEURS HAUSSIERS & RISQUES BAISSIERS** (2 panels côte à côte) : 5-6 points chacun

10. **ÉVÉNEMENTS CLÉS** : Prochaines dates à surveiller (résultats, dividendes, salons, etc.)

CLASSES CSS À UTILISER (définies dans le parent) :
- .panel, .panel-title, .panel-body
- .metric-row, .metric-label, .metric-value (.good/.warning/.bad/.neutral)
- .higgons-criteria (.pass/.fail/.partial)
- .criteria-icon (.pass/.fail/.partial)
- .tag (.buy/.hold/.sell/.info)
- .swot-grid, .swot-box (.strength/.weakness/.opportunity/.threat)
- .fin-table pour les tableaux financiers
- .grid-2, .grid-3 pour les layouts en grille
- .narrative pour le texte d'analyse
- .score-badge pour le score Higgons
- .verdict-banner pour la bannière de verdict
- .sep pour les séparateurs
- .progress-container, .progress-bar, .progress-fill
- .ticker-header, .ticker-info, .price-block
- .section-title, .full-width
- .footer, .disclaimer

RÈGLES IMPÉRATIVES :
- Sois FACTUEL : ne pas inventer de données. Si une donnée manque, indique "N/D"
- Sois CRITIQUE : ne pas hésiter à déconseiller une valeur si elle ne valide pas la méthode
- Utilise le code couleur de manière cohérente : vert = positif, rouge = négatif, orange = attention
- Les chiffres doivent être formatés avec séparateurs de milliers et symboles €/%
- Toute recommandation doit être "Éligible", "Watchlist", ou "Non éligible" selon Higgons
- Le rapport doit être directement actionable pour un gérant de fonds
- N'ajoute PAS de balises <html>, <head>, <body> — retourne uniquement le contenu interne
- N'ajoute PAS de <style> — toutes les classes CSS sont déjà définies dans le parent
- Ajoute un footer disclaimer Olyos Capital en bas du rapport"""

    # Build user prompt with data
    user_prompt = f"""Génère le rapport d'equity research complet pour la valeur suivante :

## DONNÉES DE MARCHÉ
- Ticker : {stock_data['market']['ticker']}
- Nom : {stock_data['market']['name']}
- Exchange : {stock_data['market']['exchange']}
- ISIN : {stock_data['market'].get('isin', 'N/D')}
- Secteur : {stock_data['market']['sector']}
- Industrie : {stock_data['market'].get('industry', 'N/D')}
- Devise : {stock_data['market']['currency']}
- Cours actuel : {stock_data['market']['price']}
- Variation jour : {stock_data['market']['price_change_1d']}%
- Plus haut 52s : {stock_data['market']['high_52w']}
- Plus bas 52s : {stock_data['market']['low_52w']}
- Capitalisation : {stock_data['market']['market_cap']} M
- Actions en circulation : {stock_data['market']['shares_outstanding']}
- Beta : {stock_data['market']['beta']}
- Volume moyen : {stock_data['market']['volume_avg']}

## RATIOS DE VALORISATION
- PER TTM : {stock_data['valuation']['per_ttm']}
- PER Forward : {stock_data['valuation']['per_forward']}
- Price / Book : {stock_data['valuation']['price_to_book']}
- Price / Sales : {stock_data['valuation']['price_to_sales']}
- EV / EBITDA : {stock_data['valuation']['ev_ebitda']}
- Price / FCF : {stock_data['valuation'].get('price_to_fcf', 'N/D')}

## RENTABILITÉ
- ROE : {stock_data['profitability']['roe']}%
- ROA : {stock_data['profitability']['roa']}%
- ROIC : {stock_data['profitability']['roic']}%
- Marge brute : {stock_data['profitability']['gross_margin']}%
- Marge opérationnelle : {stock_data['profitability']['operating_margin']}%
- Marge nette : {stock_data['profitability']['net_margin']}%

## BILAN
- Actif total : {stock_data['balance_sheet']['total_assets']} M
- Passif total : {stock_data['balance_sheet']['total_liabilities']} M
- Fonds propres : {stock_data['balance_sheet']['total_equity']} M
- Dette totale : {stock_data['balance_sheet']['total_debt']} M
- Trésorerie nette : {stock_data['balance_sheet']['net_cash']} M
- Dette / Equity : {stock_data['balance_sheet']['debt_to_equity']}%
- Current ratio : {stock_data['balance_sheet']['current_ratio']}

## HISTORIQUE COMPTE DE RÉSULTAT
{format_income_history(stock_data['income_history'])}

## DIVIDENDES
- DPS : {stock_data['dividends']['dividend_per_share']}
- Rendement : {stock_data['dividends']['dividend_yield']}%
- Payout ratio : {stock_data['dividends']['payout_ratio']}%

## MOMENTUM
- Perf 1 mois : {stock_data['momentum']['perf_1m']}%
- Perf 3 mois : {stock_data['momentum']['perf_3m']}%
- Perf 6 mois : {stock_data['momentum']['perf_6m']}%
- Perf 1 an : {stock_data['momentum']['perf_1y']}%
- Perf YTD : {stock_data['momentum']['perf_ytd']}%
- vs SMA50 : {stock_data['momentum']['vs_sma50']}%
- vs SMA200 : {stock_data['momentum']['vs_sma200']}%
- Tendance : {stock_data['momentum']['trend']}

Génère le rapport complet maintenant. Retourne UNIQUEMENT le HTML."""

    return system_prompt, user_prompt


def format_income_history(history: list) -> str:
    """Format income history as text for the prompt."""
    if not history:
        return "Aucune donnée historique disponible."

    lines = []
    for year_data in history:
        lines.append(f"""Année {year_data['year']}:
  - CA : {year_data['revenue']} M | Croissance : {year_data['revenue_growth']}%
  - EBITDA : {year_data['ebitda']} M
  - EBIT : {year_data['ebit']} M
  - Résultat net : {year_data['net_income']} M
  - BPA : {year_data['eps']}
  - FCF : {year_data.get('fcf', 'N/D')} M""")

    return '\n'.join(lines)


def call_claude_analysis(system_prompt: str, user_prompt: str, api_key: str) -> str:
    """
    Calls the Claude API to generate the equity research report.
    Returns the HTML content string.
    """
    import anthropic

    client = anthropic.Anthropic(api_key=api_key)

    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=12000,
        system=system_prompt,
        messages=[
            {"role": "user", "content": user_prompt}
        ]
    )

    # Extract HTML content from response
    html_content = message.content[0].text

    # Clean up potential markdown wrapping
    html_content = html_content.strip()
    if html_content.startswith('```html'):
        html_content = html_content[7:]
    if html_content.startswith('```'):
        html_content = html_content[3:]
    if html_content.endswith('```'):
        html_content = html_content[:-3]

    return html_content.strip()


def get_cached_analysis(ticker: str) -> Optional[str]:
    """Returns cached analysis HTML if it's less than 24 hours old."""
    cache_file = os.path.join(ANALYSIS_CACHE_DIR, f'{ticker}_analysis.json')

    if os.path.exists(cache_file):
        try:
            with open(cache_file, 'r', encoding='utf-8') as f:
                cached = json.load(f)

            cached_time = datetime.fromisoformat(cached['timestamp'])
            if datetime.now() - cached_time < timedelta(hours=24):
                log.info(f"Cache hit for analysis of {ticker}")
                return cached['html']
            else:
                log.info(f"Cache expired for analysis of {ticker}")
        except Exception as e:
            log.warning(f"Error reading analysis cache for {ticker}: {e}")

    return None


def cache_analysis(ticker: str, html: str) -> None:
    """Saves analysis HTML to cache."""
    try:
        os.makedirs(ANALYSIS_CACHE_DIR, exist_ok=True)
        cache_file = os.path.join(ANALYSIS_CACHE_DIR, f'{ticker}_analysis.json')

        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump({
                'ticker': ticker,
                'html': html,
                'timestamp': datetime.now().isoformat()
            }, f, ensure_ascii=False)

        log.info(f"Cached analysis for {ticker}")
    except Exception as e:
        log.warning(f"Error caching analysis for {ticker}: {e}")


def run_analysis(ticker: str, get_security_data_func, yfinance_ok: bool,
                 api_key: str, force_refresh: bool = False) -> Dict[str, Any]:
    """
    Main entry point: runs the full analysis pipeline.
    Returns a dict with success, html, ticker, from_cache, timestamp.
    """
    # Check cache first
    if not force_refresh:
        cached = get_cached_analysis(ticker)
        if cached:
            return {
                'success': True,
                'html': cached,
                'ticker': ticker,
                'from_cache': True,
                'timestamp': datetime.now().isoformat()
            }

    # Collect data
    log.info(f"Collecting analysis data for {ticker}...")
    stock_data = get_stock_analysis_data(ticker, get_security_data_func, yfinance_ok)

    if not stock_data:
        return {
            'success': False,
            'error': f'Données financières indisponibles pour {ticker}',
            'ticker': ticker
        }

    # Build prompt
    log.info(f"Building analysis prompt for {ticker}...")
    system_prompt, user_prompt = build_analysis_prompt(stock_data)

    # Call Claude API
    log.info(f"Calling Claude API for {ticker} analysis...")
    try:
        analysis_html = call_claude_analysis(system_prompt, user_prompt, api_key)
    except Exception as e:
        log.error(f"Claude API error for {ticker}: {e}", exc_info=True)
        return {
            'success': False,
            'error': f'Erreur API Claude : {str(e)}',
            'ticker': ticker
        }

    # Cache the result
    cache_analysis(ticker, analysis_html)

    log.info(f"Analysis complete for {ticker}")
    return {
        'success': True,
        'html': analysis_html,
        'ticker': ticker,
        'from_cache': False,
        'timestamp': datetime.now().isoformat()
    }

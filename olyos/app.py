#!/usr/bin/env python3

"""PORTFOLIO TERMINAL v4.0 - Bloomberg Style with Backtesting"""

import os, sys

# Add parent directory to path for module imports when running directly
_current_dir = os.path.dirname(os.path.abspath(__file__))
_parent_dir = os.path.dirname(_current_dir)
if _parent_dir not in sys.path:
    sys.path.insert(0, _parent_dir)

import json, webbrowser, threading, math, glob, html, tempfile

from datetime import datetime, timedelta

from http.server import HTTPServer, SimpleHTTPRequestHandler

import urllib.parse

from typing import List, Dict, Any, Optional, Tuple

try:
    import requests
    REQUESTS_OK = True
except ImportError:
    REQUESTS_OK = False

from olyos.logger import get_logger, configure as configure_logging
from olyos.services.api_client import ParallelAPIClient, BatchProgress
from olyos.services.alerts import AlertsService, AlertConfig, create_alerts_service
from olyos.services.benchmark import BenchmarkService, BENCHMARKS, create_benchmark_service
from olyos.services.dividends import DividendsService, create_dividends_service
from olyos.services.position_manager import PositionManager, create_position_manager
from olyos.services.pdf_report import PDFReportService, create_pdf_report_service
from olyos.services.insider import InsiderService, InsiderTransaction, TransactionType, create_insider_service
from olyos.services.rebalancing import RebalancingService, RebalanceConfig, create_rebalancing_service
from olyos.services.ai_analysis import run_analysis as run_ai_analysis
try:
    from olyos.olyos_portfolio_advisor import run_analysis as run_portfolio_advisor_analysis
    PORTFOLIO_ADVISOR_OK = True
except Exception:
    run_portfolio_advisor_analysis = None
    PORTFOLIO_ADVISOR_OK = False

# Initialize loggers for different components
log = get_logger('main')
log_api = get_logger('api')
log_cache = get_logger('cache')
log_backtest = get_logger('backtest')
log_screener = get_logger('screener')
log_portfolio = get_logger('portfolio')



# Data directory (relative to project root)
_DATA_DIR = os.path.join(_parent_dir, 'data')

CONFIG = {
    'portfolio_file': os.path.join(_DATA_DIR, 'portfolio.xlsx'),
    'transactions_file': os.path.join(_DATA_DIR, 'transactions.json'),
    'watchlist_file': os.path.join(_DATA_DIR, 'watchlist.json'),
    'screener_cache_file': os.path.join(_DATA_DIR, 'screener_cache.json'),
    'nav_history_file': os.path.join(_DATA_DIR, 'nav_history.json'),
    'backtest_cache_dir': os.path.join(_DATA_DIR, 'backtest_cache'),
    'backtest_history_file': os.path.join(_DATA_DIR, 'backtest_history.json'),
    'memo_dir': _DATA_DIR,
    'reports_dir': os.path.join(_parent_dir, 'docs', 'reports'),
    'port': 8080,
    'cache_days': 30
}



# EOD Historical Data API

EOD_API_KEY = os.environ.get('EOD_API_KEY')

EOD_OK = EOD_API_KEY is not None and REQUESTS_OK



# Global variable to track data refresh progress

REFRESH_STATUS = {

    'running': False,

    'progress': 0,

    'total': 0,

    'current_ticker': '',

    'message': ''

}

# Global alerts service (initialized lazily)
_ALERTS_SERVICE = None

def get_alerts_service():
    """Get or create the alerts service singleton"""
    global _ALERTS_SERVICE
    if _ALERTS_SERVICE is None:
        _ALERTS_SERVICE = AlertsService(
            watchlist_file=CONFIG['watchlist_file'],
            get_fundamentals_func=eod_get_fundamentals,
            get_prices_func=eod_get_historical_prices
        )
    return _ALERTS_SERVICE

# Global benchmark service (initialized lazily)
_BENCHMARK_SERVICE = None

def get_benchmark_service():
    """Get or create the benchmark service singleton"""
    global _BENCHMARK_SERVICE
    if _BENCHMARK_SERVICE is None:
        benchmark_cache_dir = os.path.join(_DATA_DIR, 'benchmark_cache')
        _BENCHMARK_SERVICE = BenchmarkService(
            cache_dir=benchmark_cache_dir,
            nav_history_file=CONFIG['nav_history_file'],
            get_prices_func=eod_get_historical_prices
        )
    return _BENCHMARK_SERVICE

# Global dividends service (initialized lazily)
_DIVIDENDS_SERVICE = None

def get_dividends_service():
    """Get or create the dividends service singleton"""
    global _DIVIDENDS_SERVICE
    if _DIVIDENDS_SERVICE is None:
        dividends_cache_file = os.path.join(_DATA_DIR, 'dividends_cache.json')
        _DIVIDENDS_SERVICE = DividendsService(
            cache_file=dividends_cache_file,
            get_dividends_func=eod_get_dividends,
            get_fundamentals_func=eod_get_fundamentals
        )
    return _DIVIDENDS_SERVICE

# Global position manager (initialized lazily)
_POSITION_MANAGER = None

def get_position_manager():
    """Get or create the position manager singleton"""
    global _POSITION_MANAGER
    if _POSITION_MANAGER is None:
        def get_current_price(ticker: str) -> float:
            """Get current price for a ticker from cache or API"""
            try:
                fund, err = eod_get_fundamentals(ticker, use_cache=True)
                if fund and not err:
                    price = fund.get('General', {}).get('LastClose')
                    if price:
                        return float(price)
            except:
                pass
            return 0.0

        _POSITION_MANAGER = PositionManager(
            transactions_file=CONFIG['transactions_file'],
            get_price_func=get_current_price
        )
    return _POSITION_MANAGER

# Global PDF report service (initialized lazily)
_PDF_REPORT_SERVICE = None

def get_pdf_report_service():
    """Get or create the PDF report service singleton"""
    global _PDF_REPORT_SERVICE
    if _PDF_REPORT_SERVICE is None:
        # Ensure reports directory exists
        os.makedirs(CONFIG['reports_dir'], exist_ok=True)

        _PDF_REPORT_SERVICE = PDFReportService(
            reports_dir=CONFIG['reports_dir'],
            nav_history_file=CONFIG['nav_history_file'],
            portfolio_func=load_portfolio,
            benchmark_service=get_benchmark_service(),
            position_manager=get_position_manager()
        )
    return _PDF_REPORT_SERVICE

# Global Insider service (initialized lazily)
_INSIDER_SERVICE = None

def get_insider_service():
    """Get or create the Insider service singleton"""
    global _INSIDER_SERVICE
    if _INSIDER_SERVICE is None:
        cache_file = os.path.join(_DATA_DIR, 'insider_cache.json')
        _INSIDER_SERVICE = InsiderService(
            eod_api_key=EOD_API_KEY or '',
            cache_file=cache_file,
            cache_days=3
        )
    return _INSIDER_SERVICE

# Global Rebalancing service (initialized lazily)
_REBALANCING_SERVICE = None

def get_rebalancing_service():
    """Get or create the Rebalancing service singleton"""
    global _REBALANCING_SERVICE
    if _REBALANCING_SERVICE is None:
        _REBALANCING_SERVICE = RebalancingService(
            config=RebalanceConfig(
                max_position_weight=10.0,
                min_position_weight=2.0,
                max_sector_weight=30.0,
                min_higgons_score=4,
                max_pe=17.0
            )
        )
    return _REBALANCING_SERVICE


# Universe of tickers for backtesting

UNIVERSE_FRANCE = []

UNIVERSE_EUROPE = []



def load_universe_from_eod(exchange: str = 'PA', max_market_cap: float = 10e9, min_market_cap: float = 50e6) -> List[str]:

    """Load list of tickers from EOD for a given exchange"""

    if not EOD_OK:

        return []

    

    cache_file = os.path.join(CONFIG['backtest_cache_dir'], f'universe_{exchange}.json')

    os.makedirs(CONFIG['backtest_cache_dir'], exist_ok=True)

    

    # Check cache (valid for 30 days)

    if os.path.exists(cache_file):

        try:

            cache_data = json.load(open(cache_file, encoding='utf-8'))

            cache_date = datetime.strptime(cache_data.get('_cache_date', '2000-01-01'), '%Y-%m-%d')

            if (datetime.now() - cache_date).days < 30:

                return cache_data.get('tickers', [])

        except Exception:
            pass

    

    try:

        # Get list of all tickers on exchange

        url = f"https://eodhd.com/api/exchange-symbol-list/{exchange}?api_token={EOD_API_KEY}&fmt=json"

        log_api.info(f"Loading universe for {exchange}...")

        response = requests.get(url, timeout=60)

        

        if response.status_code != 200:

            log_api.error(f"Error loading universe: {response.status_code}")

            return []

        

        all_tickers = response.json()

        

        # Filter for stocks only (not ETFs, bonds, etc.)

        stocks = [t for t in all_tickers if t.get('Type') == 'Common Stock']

        

        # IMPORTANT: Filter out ADRs, secondary listings, and garbage tickers

        filtered_stocks = []

        for s in stocks:

            code = s.get('Code', '')

            name = s.get('Name', '')

            

            # Skip tickers starting with numbers (usually ADRs on LSE like 0ABC)

            if code and code[0].isdigit():

                continue

            

            # Skip very short tickers (often indices or special instruments)

            if len(code) < 2:

                continue

            

            # Skip tickers with special characters

            if any(c in code for c in ['$', '#', '&', ' ', '=']):

                continue

            

            # Skip common ADR/GDR patterns

            name_upper = name.upper() if name else ''

            if any(x in name_upper for x in ['ADR', 'GDR', 'DEPOSITARY', 'RECEIPT', 'SPONSORED']):

                continue

            

            # Skip ETFs, funds, warrants, etc.

            if any(x in name_upper for x in ['ETF', 'FUND', 'WARRANT', 'TRACKER', 'CERTIFICATE', 'REIT', 'TRUST']):

                continue

            

            filtered_stocks.append(s)

        

        # Build list with basic info

        tickers = []

        for s in filtered_stocks:

            tickers.append({

                'ticker': f"{s['Code']}.{exchange}",

                'name': s.get('Name', ''),

                'exchange': exchange,

                'isin': s.get('Isin', '')

            })

        

        # Save to cache

        cache_data = {

            '_cache_date': datetime.now().strftime('%Y-%m-%d'),

            'tickers': tickers

        }

        with open(cache_file, 'w', encoding='utf-8') as f:

            json.dump(cache_data, f)

        

        log_api.info(f"Found {len(tickers)} stocks on {exchange} (filtered from {len(all_tickers)} total)")

        return tickers

        

    except Exception as e:

        log_api.error(f"Error: {e}")

        return []



def init_universes():

    """Initialize France and Europe universes"""

    global UNIVERSE_FRANCE, UNIVERSE_EUROPE

    

    # France (Euronext Paris)

    UNIVERSE_FRANCE = load_universe_from_eod('PA')

    

    # Europe - major exchanges

    europe_exchanges = ['PA', 'AS', 'BR', 'MI', 'MC', 'XETRA', 'SW', 'LSE']

    

    all_europe = []

    for ex in europe_exchanges:

        tickers = load_universe_from_eod(ex)

        all_europe.extend(tickers)

    

    UNIVERSE_EUROPE = all_europe

    

    log.info(f"Universe loaded: France: {len(UNIVERSE_FRANCE)} tickers, Europe: {len(UNIVERSE_EUROPE)} tickers")



MEMO_PATTERNS = {

    'CARM.PA': ['Memo_Carmila*', 'Investment_Memo_Carmila*'],

    'MAU.PA': ['Memo_Maurel*', 'Investment_Memo_Maurel*'],

    'STF.PA': ['Memo_STEF*', 'Investment_Memo_STEF*', 'Memo_Stef*'],

    'ALCAT.PA': ['Memo_Catana*', 'Investment_Memo_Catana*'],

    'GTT.PA': ['Memo_GTT*', 'Investment_Memo_GTT*'],

    'ARG.PA': ['Memo_Argan*', 'Investment_Memo_ARGAN*'],

    'ICAD.PA': ['Memo_Icade*', 'Investment_Memo_ICADE*'],

    'ALREW.PA': ['Memo_Reworld*', 'Investment_Memo_Reworld*'],

    'ALHOP.PA': ['Memo_Hopscotch*', 'Investment_Memo_HOPSCOTCH*'],

    'STF': ['Memo_STEF*', 'Memo_Stef*'],

    'ALREW': ['Memo_Reworld*'],

    'ALHOP': ['Memo_Hopscotch*', 'Investment_Memo_HOPSCOTCH*'],

}



EUROPE_DB = [

    {"ticker": "VCT.PA", "name": "Vicat", "sector": "Materiaux", "country": "France"},

    {"ticker": "FGR.PA", "name": "Eiffage", "sector": "Construction", "country": "France"},

    {"ticker": "SPIE.PA", "name": "Spie", "sector": "Services", "country": "France"},

    {"ticker": "GTT.PA", "name": "GTT", "sector": "Energie", "country": "France"},

    {"ticker": "TRI.PA", "name": "Trigano", "sector": "Automobile", "country": "France"},

    {"ticker": "BEN.PA", "name": "Beneteau", "sector": "Nautisme", "country": "France"},

    {"ticker": "ELIS.PA", "name": "Elis", "sector": "Services", "country": "France"},

    {"ticker": "STF.PA", "name": "Stef", "sector": "Transport", "country": "France"},

    {"ticker": "DBG.PA", "name": "Derichebourg", "sector": "Services", "country": "France"},

    {"ticker": "AUB.PA", "name": "Aubay", "sector": "IT", "country": "France"},

    {"ticker": "ARG.PA", "name": "Argan", "sector": "Immobilier", "country": "France"},

    {"ticker": "CARM.PA", "name": "Carmila", "sector": "Immobilier", "country": "France"},

    {"ticker": "ICAD.PA", "name": "Icade", "sector": "Immobilier", "country": "France"},

    {"ticker": "ALREW.PA", "name": "Reworld Media", "sector": "Medias", "country": "France"},

    {"ticker": "ALHOP.PA", "name": "Hopscotch", "sector": "Communication", "country": "France"},

    {"ticker": "FNAC.PA", "name": "Fnac Darty", "sector": "Distribution", "country": "France"},

    {"ticker": "MAU.PA", "name": "Maurel Prom", "sector": "Energie", "country": "France"},

    {"ticker": "RUI.PA", "name": "Rubis", "sector": "Energie", "country": "France"},

    {"ticker": "VK.PA", "name": "Vallourec", "sector": "Energie", "country": "France"},

    {"ticker": "TE.PA", "name": "Technip Energies", "sector": "Energie", "country": "France"},

    {"ticker": "NEX.PA", "name": "Nexans", "sector": "Industrie", "country": "France"},

    {"ticker": "SK.PA", "name": "SEB", "sector": "Consommation", "country": "France"},

    {"ticker": "ERA.PA", "name": "Eramet", "sector": "Materiaux", "country": "France"},

    {"ticker": "COFA.PA", "name": "Coface", "sector": "Finance", "country": "France"},

    {"ticker": "SW.PA", "name": "Sodexo", "sector": "Services", "country": "France"},

    {"ticker": "RI.PA", "name": "Pernod Ricard", "sector": "Consommation", "country": "France"},

    {"ticker": "TTE.PA", "name": "TotalEnergies", "sector": "Energie", "country": "France"},

    {"ticker": "WBD.MI", "name": "Webuild", "sector": "Construction", "country": "Italie"},

    {"ticker": "DAN.MI", "name": "Danieli", "sector": "Industrie", "country": "Italie"},

    {"ticker": "MAIRE.MI", "name": "Maire Tecnimont", "sector": "Ingenierie", "country": "Italie"},

    {"ticker": "BZU.MI", "name": "Buzzi", "sector": "Materiaux", "country": "Italie"},

    {"ticker": "CEM.MI", "name": "Cementir", "sector": "Materiaux", "country": "Italie"},

    {"ticker": "CAF.MC", "name": "CAF", "sector": "Transport", "country": "Espagne"},

    {"ticker": "TRE.MC", "name": "Tecnicas Reunidas", "sector": "Ingenierie", "country": "Espagne"},

    {"ticker": "IDR.MC", "name": "Indra Sistemas", "sector": "IT", "country": "Espagne"},

    {"ticker": "CIE.MC", "name": "CIE Automotive", "sector": "Automobile", "country": "Espagne"},

    {"ticker": "SCYR.MC", "name": "Sacyr", "sector": "Construction", "country": "Espagne"},

    {"ticker": "BAMNB.AS", "name": "Royal BAM", "sector": "Construction", "country": "Pays-Bas"},

    {"ticker": "HEIJM.AS", "name": "Heijmans", "sector": "Construction", "country": "Pays-Bas"},

    {"ticker": "HBH.DE", "name": "Hornbach", "sector": "Distribution", "country": "Allemagne"},

    {"ticker": "WAC.DE", "name": "Wacker Neuson", "sector": "Industrie", "country": "Allemagne"},

    {"ticker": "NDA.DE", "name": "Aurubis", "sector": "Materiaux", "country": "Allemagne"},

    {"ticker": "SZG.DE", "name": "Salzgitter", "sector": "Materiaux", "country": "Allemagne"},

    {"ticker": "BEKB.BR", "name": "Bekaert", "sector": "Industrie", "country": "Belgique"},

    {"ticker": "SIP.BR", "name": "Sipef", "sector": "Agriculture", "country": "Belgique"},

    {"ticker": "KLR.L", "name": "Keller Group", "sector": "Construction", "country": "UK"},

    {"ticker": "MGNS.L", "name": "Morgan Sindall", "sector": "Construction", "country": "UK"},

    {"ticker": "IMB.L", "name": "Imperial Brands", "sector": "Consommation", "country": "UK"},

    {"ticker": "METLEN.AT", "name": "Metlen Energy", "sector": "Energie", "country": "Grece"},

    {"ticker": "MOH.AT", "name": "Motor Oil", "sector": "Energie", "country": "Grece"},

    {"ticker": "BELA.AT", "name": "Jumbo", "sector": "Distribution", "country": "Grece"},

    {"ticker": "IMPN.SW", "name": "Implenia", "sector": "Construction", "country": "Suisse"},

    {"ticker": "EGL.LS", "name": "Mota-Engil", "sector": "Construction", "country": "Portugal"},

    {"ticker": "POS.VI", "name": "PORR", "sector": "Construction", "country": "Autriche"},

    {"ticker": "PNDORA.CO", "name": "Pandora", "sector": "Luxe", "country": "Danemark"},

    {"ticker": "ALCAT.PA", "name": "Catana Group", "sector": "Nautisme", "country": "France"},

]



try:

    import pandas as pd

    PANDAS_OK = True

except Exception:
    PANDAS_OK = False



try:

    import yfinance as yf

    YFINANCE_OK = True

except Exception:
    YFINANCE_OK = False



try:

    import anthropic

    ANTHROPIC_API_KEY = os.environ.get('ANTHROPIC_API_KEY')

    ANTHROPIC_OK = ANTHROPIC_API_KEY is not None

except Exception:
    ANTHROPIC_OK = False

    ANTHROPIC_API_KEY = None



def load_json(f, default):

    try:

        return json.load(open(f, encoding='utf-8')) if os.path.exists(f) else default

    except Exception:
        return default



def save_json(f, data):

    json.dump(data, open(f, 'w', encoding='utf-8'), indent=2)



def read_memo_content(filepath):

    """Read content from a .docx memo file and return as styled HTML"""

    if not filepath or not os.path.exists(filepath):

        return None

    

    try:

        from docx import Document

        from docx.table import Table

        doc = Document(filepath)

        

        html_parts = []

        

        for element in doc.element.body:

            # Handle tables

            if element.tag.endswith('tbl'):

                for table in doc.tables:

                    if table._element == element:

                        html_parts.append(render_table_html(table))

                        break

            # Handle paragraphs

            elif element.tag.endswith('p'):

                for para in doc.paragraphs:

                    if para._element == element:

                        html = render_paragraph_html(para)

                        if html:

                            html_parts.append(html)

                        break

        

        return '\n'.join(html_parts) if html_parts else None

        

    except ImportError:

        # python-docx not installed, try basic extraction

        try:

            import zipfile

            import xml.etree.ElementTree as ET

            

            with zipfile.ZipFile(filepath) as z:

                xml_content = z.read('word/document.xml')

            

            tree = ET.fromstring(xml_content)

            ns = {'w': 'http://schemas.openxmlformats.org/wordprocessingml/2006/main'}

            

            paragraphs = []

            for para in tree.findall('.//w:p', ns):

                texts = [node.text for node in para.findall('.//w:t', ns) if node.text]

                if texts:

                    full_text = ''.join(texts).strip()

                    if full_text:

                        # Detect headers by keywords

                        if any(kw in full_text.upper() for kw in ['SIGNAL', 'RESUME', 'SUMMARY', 'THESIS', 'RISQUES', 'VALORISATION', 'FINANCIER', 'CONCLUSION', 'PROFIL', 'ACTIONNARIAT', 'GEOGRAPHIE']):

                            paragraphs.append(f'<div class="memo-section-title">{full_text}</div>')

                        else:

                            paragraphs.append(f'<p class="memo-text">{full_text}</p>')

            

            return '\n'.join(paragraphs) if paragraphs else None

            

        except Exception as e:

            log.error(f"Error reading memo: {e}")

            return None

    except Exception as e:

        log.error(f"Error reading memo: {e}")

        return None





def render_paragraph_html(para):

    """Convert a docx paragraph to styled HTML"""

    text = para.text.strip()

    if not text:

        return None

    

    # Detect style

    style_name = para.style.name if para.style else ''

    

    # Check if bold (title/header)

    is_bold = False

    is_all_caps = text.isupper() and len(text) > 3

    if para.runs:

        is_bold = para.runs[0].bold

    

    # Section titles (detect by keywords or style)

    section_keywords = ['SIGNAL', 'RESUME', 'SUMMARY', 'THESIS', 'RISQUES', 'RISK', 'VALORISATION', 

                        'VALUATION', 'FINANCIER', 'FINANCIAL', 'CONCLUSION', 'PROFIL', 'PROFILE',

                        'ACTIONNARIAT', 'SHAREHOLDERS', 'GEOGRAPHIE', 'GEOGRAPHY', 'CATALYSTS',

                        'CATALYSEURS', 'POINTS FORTS', 'STRENGTHS', 'POINTS FAIBLES', 'WEAKNESSES',

                        'RECOMMENDATION', 'RECOMMANDATION', 'OVERVIEW', 'APERÃ‡U', 'DESCRIPTION',

                        'STRUCTURE', 'STRATEGIE', 'STRATEGY', 'HISTORIQUE', 'HISTORY', 'ACQUISITION']

    

    is_section_title = any(kw in text.upper() for kw in section_keywords) or 'Heading' in style_name

    

    # Signal/Verdict detection

    signal_keywords = {'ACHAT': 'buy', 'BUY': 'buy', 'STRONG BUY': 'buy', 

                       'VENTE': 'sell', 'SELL': 'sell', 'ECARTER': 'sell',

                       'SURVEILLANCE': 'watch', 'WATCH': 'watch', 'HOLD': 'hold',

                       'NEUTRE': 'hold', 'NEUTRAL': 'hold'}

    

    for kw, cls in signal_keywords.items():

        if kw in text.upper():

            return f'<div class="memo-signal memo-signal-{cls}">{text}</div>'

    

    # Format based on type

    if is_section_title or is_all_caps:

        return f'<div class="memo-section-title">{text}</div>'

    elif is_bold:

        return f'<div class="memo-subtitle">{text}</div>'

    elif text.startswith(' - ') or text.startswith('-') or text.startswith(' - '):

        return f'<div class="memo-bullet">{text}</div>'

    elif ':' in text and len(text.split(':')[0]) < 30:

        # Key-value pair

        parts = text.split(':', 1)

        return f'<div class="memo-kv"><span class="memo-key">{parts[0]}:</span><span class="memo-value">{parts[1].strip()}</span></div>'

    else:

        return f'<p class="memo-text">{text}</p>'





def render_table_html(table):

    """Convert a docx table to styled HTML"""

    html = ['<table class="memo-table">']

    

    for i, row in enumerate(table.rows):

        if i == 0:

            html.append('<thead><tr>')

            for cell in row.cells:

                html.append(f'<th>{cell.text.strip()}</th>')

            html.append('</tr></thead><tbody>')

        else:

            html.append('<tr>')

            for j, cell in enumerate(row.cells):

                cell_text = cell.text.strip()

                # Detect numeric values for alignment

                cell_class = 'num' if any(c.isdigit() for c in cell_text) and j > 0 else ''

                # Detect positive/negative

                if cell_class == 'num':

                    if cell_text.startswith('+') or (cell_text.replace(',', '').replace('.', '').replace('%', '').replace(' ', '').isdigit() and not cell_text.startswith('-')):

                        cell_class += ' pos'

                    elif cell_text.startswith('-'):

                        cell_class += ' neg'

                html.append(f'<td class="{cell_class}">{cell_text}</td>')

            html.append('</tr>')

    

    html.append('</tbody></table>')

    return '\n'.join(html)



def get_yf_ticker(ticker):

    """Convert ticker to Yahoo Finance format"""

    # Already has a suffix

    if '.' in ticker:

        return ticker

    

    # Special tickers mapping (non-French or special cases)

    TICKER_MAP = {

        # Belgian stocks

        'SIP': 'SIP.BR',           # Sipef

        'BEKB': 'BEKB.BR',         # Bekaert

        

        # Danish stocks  

        'PNDORA': 'PNDORA.CO',     # Pandora

        

        # German stocks

        'NEAG': 'NEAG.DE',         # Nagarro

        'HBH': 'HBH.DE',           # Hornbach

        'WAC': 'WAC.DE',           # Wacker Neuson

        'NDA': 'NDA.DE',           # Aurubis

        'SZG': 'SZG.DE',           # Salzgitter

        

        # Swiss stocks

        'ZURN': 'ZURN.SW',         # Zurich Insurance

        'IMPN': 'IMPN.SW',         # Implenia

        

        # US stocks (no suffix needed)

        'FCX': 'FCX',              # Freeport McMoran

        

        # Dutch stocks

        'BAMNB': 'BAMNB.AS',       # Royal BAM

        'HEIJM': 'HEIJM.AS',       # Heijmans

        

        # Italian stocks

        'WBD': 'WBD.MI',           # Webuild

        'DAN': 'DAN.MI',           # Danieli

        'MAIRE': 'MAIRE.MI',       # Maire Tecnimont

        'BZU': 'BZU.MI',           # Buzzi

        'CEM': 'CEM.MI',           # Cementir

        

        # Spanish stocks

        'CAF': 'CAF.MC',           # CAF

        'TRE': 'TRE.MC',           # Tecnicas Reunidas

        'IDR': 'IDR.MC',           # Indra

        'CIE': 'CIE.MC',           # CIE Automotive

        'SCYR': 'SCYR.MC',         # Sacyr

        

        # Greek stocks

        'METLEN': 'METLEN.AT',     # Metlen

        'MOH': 'MOH.AT',           # Motor Oil

        'BELA': 'BELA.AT',         # Jumbo

        

        # Portuguese stocks

        'EGL': 'EGL.LS',           # Mota-Engil

        

        # Austrian stocks

        'POS': 'POS.VI',           # PORR

        

        # UK stocks

        'KLR': 'KLR.L',            # Keller

        'MGNS': 'MGNS.L',          # Morgan Sindall

        'IMB': 'IMB.L',            # Imperial Brands

        'RIO': 'RIO.L',            # Rio Tinto

        'BA': 'BA.L',              # BAE Systems

        

        # French stocks (explicit mapping for safety)

        'MC': 'MC.PA',             # LVMH

        'VIE': 'VIE.PA',           # Veolia

        'GFC': 'GFC.PA',           # Gecina

        'ALVAP': 'ALVAP.PA',       # Valneva

        'ALWEC': 'ALWEC.PA',       # We.Connect

        'NXI': 'NXI.PA',           # Nexity

        'SK': 'SK.PA',             # SEB

        'ALCAT': 'ALCAT.PA',       # Catana Group

        'CATG': 'ALCAT.PA',        # Catana Group (old ticker)

    }

    

    ticker_upper = ticker.upper()

    if ticker_upper in TICKER_MAP:

        return TICKER_MAP[ticker_upper]

    

    # Default: assume French stock

    return ticker + '.PA'



def find_memo(ticker):

    """Find memo file for a given ticker"""

    # Try with and without .PA suffix

    tickers_to_try = [ticker, ticker.replace('.PA', ''), ticker.split('.')[0]]

    

    for t in tickers_to_try:

        patterns = MEMO_PATTERNS.get(t, [])

        for pattern in patterns:

            matches = glob.glob(os.path.join(CONFIG['memo_dir'], pattern))

            if matches:

                return matches[0]

    

    # Generic patterns

    ticker_base = ticker.split('.')[0]

    generic_patterns = [f'Memo_{ticker_base}*', f'Investment_Memo_{ticker_base}*', f'Memo_*{ticker_base}*']

    for pattern in generic_patterns:

        matches = glob.glob(os.path.join(CONFIG['memo_dir'], pattern))

        if matches:

            return matches[0]

    return None



def load_watchlist() -> List[str]:

    return load_json(CONFIG['watchlist_file'], [])



def save_watchlist(w: List[str]) -> None:

    save_json(CONFIG['watchlist_file'], w)



# =============================================================================

# EOD HISTORICAL DATA API FUNCTIONS + SMART CACHING

# =============================================================================



# Cache settings

CACHE_DIR = 'backtest_cache'

FUNDAMENTALS_CACHE_DAYS = 30  # Refresh fundamentals monthly

PRICES_CACHE_DAYS = 1  # Refresh prices daily (only if online)

UNIVERSE_CACHE_DAYS = 30  # Refresh universe monthly



def ensure_cache_dir():

    """Ensure cache directory exists"""

    os.makedirs(CACHE_DIR, exist_ok=True)

    os.makedirs(os.path.join(CACHE_DIR, 'fundamentals'), exist_ok=True)

    os.makedirs(os.path.join(CACHE_DIR, 'prices'), exist_ok=True)

    os.makedirs(os.path.join(CACHE_DIR, 'universe'), exist_ok=True)

    os.makedirs(os.path.join(CACHE_DIR, 'dividends'), exist_ok=True)



def get_cache_path(category, key):

    """Get cache file path for a given category and key"""

    ensure_cache_dir()

    safe_key = key.replace('.', '_').replace('^', '_').replace('/', '_')

    return os.path.join(CACHE_DIR, category, f'{safe_key}.json')



def is_cache_valid(cache_file, max_days):

    """Check if cache file exists and is not too old"""

    if not os.path.exists(cache_file):

        return False

    try:

        with open(cache_file, 'r', encoding='utf-8') as f:

            data = json.load(f)

        cache_date = datetime.strptime(data.get('_cache_date', '2000-01-01'), '%Y-%m-%d')

        return (datetime.now() - cache_date).days < max_days

    except Exception:
        return False



def load_from_cache(cache_file):

    """Load data from cache file"""

    try:

        with open(cache_file, 'r', encoding='utf-8') as f:

            return json.load(f)

    except Exception:
        return None



def save_to_cache(cache_file, data):

    """Save data to cache file with timestamp"""

    ensure_cache_dir()

    data['_cache_date'] = datetime.now().strftime('%Y-%m-%d')

    with open(cache_file, 'w', encoding='utf-8') as f:

        json.dump(data, f)



def get_cache_stats():

    """Get statistics about cached data"""

    ensure_cache_dir()

    stats = {

        'fundamentals': 0,

        'prices': 0,

        'universe': 0,

        'total_size_mb': 0

    }

    

    for category in ['fundamentals', 'prices', 'universe']:

        cat_path = os.path.join(CACHE_DIR, category)

        if os.path.exists(cat_path):

            files = [f for f in os.listdir(cat_path) if f.endswith('.json')]

            stats[category] = len(files)

            for f in files:

                stats['total_size_mb'] += os.path.getsize(os.path.join(cat_path, f)) / (1024*1024)

    

    stats['total_size_mb'] = round(stats['total_size_mb'], 2)

    return stats



# =============================================================================

# BACKTEST HISTORY MANAGEMENT

# =============================================================================



def load_backtest_history():

    """Load saved backtests history"""

    return load_json(CONFIG['backtest_history_file'], [])



def save_backtest_history(history):

    """Save backtests history"""

    log_backtest.info(f"Saving {len(history)} backtests to {CONFIG['backtest_history_file']}")

    save_json(CONFIG['backtest_history_file'], history)



def save_backtest_result(results, name=None):

    """Save a backtest result to history"""

    history = load_backtest_history()

    

    # Generate name if not provided

    if not name:

        params = results.get('params', {})

        scope = params.get('universe_scope', 'custom')

        pe = params.get('pe_max', '?')

        roe = params.get('roe_min', '?')

        name = f"{scope.upper()} PE<={pe} ROE>={roe}%"

    

    # Create summary (don't save full trade history to keep file small)

    summary = {

        'id': datetime.now().strftime('%Y%m%d_%H%M%S'),

        'name': name,

        'date': datetime.now().strftime('%Y-%m-%d %H:%M'),

        'params': results.get('params', {}),

        'metrics': results.get('metrics', {}),

        'yearly_returns': results.get('yearly_returns', []),

        'equity_curve_summary': {

            'start': results.get('equity_curve', [{}])[0] if results.get('equity_curve') else {},

            'end': results.get('equity_curve', [{}])[-1] if results.get('equity_curve') else {},

            'points': len(results.get('equity_curve', []))

        },

        'trades_count': len(results.get('trades', [])),

        'errors_count': len(results.get('errors', []))

    }

    

    # Add to history (keep last 50 backtests)

    history.insert(0, summary)

    history = history[:50]

    

    save_backtest_history(history)

    return summary['id']



def delete_backtest(backtest_id):

    """Delete a backtest from history"""

    history = load_backtest_history()

    history = [h for h in history if h.get('id') != backtest_id]

    save_backtest_history(history)



def rename_backtest(backtest_id, new_name):

    """Rename a backtest"""

    history = load_backtest_history()

    for h in history:

        if h.get('id') == backtest_id:

            h['name'] = new_name

            break

    save_backtest_history(history)



# =============================================================================

# AI OPTIMIZER - Find optimal investment criteria

# =============================================================================



def run_ai_optimization(scope='france', optimization_goal='balanced'):

    """

    Use Claude AI to find optimal investment criteria through iterative backtesting

    

    optimization_goal: 'max_return', 'max_sharpe', 'min_drawdown', 'balanced'

    """

    

    if not ANTHROPIC_OK:

        return {'error': 'Anthropic API not configured. Set ANTHROPIC_API_KEY.'}

    

    log_backtest.info("AI OPTIMIZER: Starting optimization...")

    log_backtest.info(f"Scope: {scope}")

    log_backtest.info(f"Goal: {optimization_goal}")

    

    results = {

        'iterations': [],

        'best_params': None,

        'best_metrics': None,

        'ai_analysis': '',

        'recommendation': ''

    }

    

    # Phase 1: Grid search with key parameter combinations

    log_backtest.info("AI OPTIMIZER: Phase 1: Running grid search...")

    

    param_grid = [

        # PE variations

        {'pe_max': 8, 'roe_min': 10, 'pe_sell': 15, 'debt_equity_max': 100, 'max_positions': 20},

        {'pe_max': 10, 'roe_min': 10, 'pe_sell': 17, 'debt_equity_max': 100, 'max_positions': 20},

        {'pe_max': 12, 'roe_min': 10, 'pe_sell': 20, 'debt_equity_max': 100, 'max_positions': 20},

        {'pe_max': 15, 'roe_min': 10, 'pe_sell': 25, 'debt_equity_max': 100, 'max_positions': 20},

        

        # ROE variations

        {'pe_max': 12, 'roe_min': 8, 'pe_sell': 17, 'debt_equity_max': 100, 'max_positions': 20},

        {'pe_max': 12, 'roe_min': 12, 'pe_sell': 17, 'debt_equity_max': 100, 'max_positions': 20},

        {'pe_max': 12, 'roe_min': 15, 'pe_sell': 17, 'debt_equity_max': 100, 'max_positions': 20},

        

        # Debt variations

        {'pe_max': 12, 'roe_min': 10, 'pe_sell': 17, 'debt_equity_max': 50, 'max_positions': 20},

        {'pe_max': 12, 'roe_min': 10, 'pe_sell': 17, 'debt_equity_max': 150, 'max_positions': 20},

        

        # Position count variations

        {'pe_max': 12, 'roe_min': 10, 'pe_sell': 17, 'debt_equity_max': 100, 'max_positions': 10},

        {'pe_max': 12, 'roe_min': 10, 'pe_sell': 17, 'debt_equity_max': 100, 'max_positions': 15},

        {'pe_max': 12, 'roe_min': 10, 'pe_sell': 17, 'debt_equity_max': 100, 'max_positions': 30},

        

        # Combined aggressive value

        {'pe_max': 8, 'roe_min': 12, 'pe_sell': 12, 'debt_equity_max': 50, 'max_positions': 15},

        

        # Combined moderate

        {'pe_max': 15, 'roe_min': 8, 'pe_sell': 25, 'debt_equity_max': 150, 'max_positions': 25},

    ]

    

    grid_results = []

    

    for i, params in enumerate(param_grid):

        log_backtest.info(f"[{i+1}/{len(param_grid)}] Testing PE<={params['pe_max']}, ROE>={params['roe_min']}%, {params['max_positions']} positions...")

        

        backtest_params = {

            'start_date': '2014-01-01',

            'end_date': datetime.now().strftime('%Y-%m-%d'),

            'universe_scope': scope,

            'universe': [],

            'pe_max': params['pe_max'],

            'roe_min': params['roe_min'],

            'pe_sell': params['pe_sell'],

            'roe_min_hold': 8,

            'debt_equity_max': params['debt_equity_max'],

            'rebalance_freq': 'quarterly',

            'initial_capital': 100000,

            'max_positions': params['max_positions'],

            'benchmark': '^FCHI'

        }

        

        try:

            bt_result = run_backtest(backtest_params)

            metrics = bt_result.get('metrics', {})

            

            grid_results.append({

                'params': params,

                'metrics': {

                    'total_return': metrics.get('total_return', 0),

                    'cagr': metrics.get('cagr', 0),

                    'sharpe': metrics.get('sharpe', 0),

                    'max_drawdown': metrics.get('max_drawdown', 0),

                    'win_rate': metrics.get('win_rate', 0),

                    'total_trades': metrics.get('total_trades', 0),

                    'alpha': metrics.get('alpha', 0)

                },

                'errors_count': len(bt_result.get('errors', []))

            })

        except Exception as e:

            log_backtest.error(f"Error: {e}")

            continue

    

    results['iterations'] = grid_results

    

    if not grid_results:

        return {'error': 'No successful backtests completed'}

    

    # Phase 2: Send results to Claude for analysis

    log_backtest.info("AI OPTIMIZER: Phase 2: AI Analysis...")

    

    try:

        import anthropic

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        

        # Prepare data summary for Claude

        results_summary = "BACKTEST RESULTS GRID:\n\n"

        for i, r in enumerate(grid_results):

            p = r['params']

            m = r['metrics']

            results_summary += f"""Test {i+1}: PE<={p['pe_max']}, ROE>={p['roe_min']}%, Debt<={p['debt_equity_max']}%, {p['max_positions']} positions, Sell@PE>{p['pe_sell']}

  â†’ Return: {m['total_return']:.1f}%, CAGR: {m['cagr']:.2f}%, Sharpe: {m['sharpe']:.2f}, MaxDD: -{m['max_drawdown']:.1f}%, WinRate: {m['win_rate']:.0f}%, Trades: {m['total_trades']}, Alpha: {m['alpha']:.1f}%



"""

        

        optimization_prompt = f"""Tu es un expert en investissement value et en analyse quantitative. Tu analyses les resultats de backtests d'une strategie d'investissement style "William Higgons" sur les small/mid caps {scope.upper()}.



{results_summary}



OBJECTIF D'OPTIMISATION: {optimization_goal}

- max_return: Maximiser le rendement total

- max_sharpe: Maximiser le ratio de Sharpe (rendement ajuste du risque)

- min_drawdown: Minimiser le drawdown maximum

- balanced: Trouver le meilleur equilibre rendement/risque



ANALYSE DEMANDEE:



1. ANALYSE DES RESULTATS

Analyse les patterns dans les donnees:

- Quel impact a le PE max sur les rendements?

- Quel impact a le ROE min sur les rendements?

- Quel impact a le nombre de positions?

- Y a-t-il des combinaisons clairement superieures?



2. PARAMÃˆTRES OPTIMAUX

Base sur ton analyse et l'objectif "{optimization_goal}", recommande les parametres optimaux:

- PE_MAX: (valeur entre 5 et 20)

- ROE_MIN: (valeur entre 5 et 20)

- PE_SELL: (valeur entre 12 et 30)

- DEBT_EQUITY_MAX: (valeur entre 30 et 200)

- MAX_POSITIONS: (valeur entre 8 et 30)



3. EXPLICATION

Explique pourquoi ces parametres sont optimaux et quels compromis tu as faits.



4. AVERTISSEMENTS

Mentionne les limites de cette optimisation (survivorship bias, periode testee, etc.)



Reponds en JSON avec cette structure exacte:

{{

  "analysis": "ton analyse detaillee",

  "optimal_params": {{

    "pe_max": X,

    "roe_min": X,

    "pe_sell": X,

    "debt_equity_max": X,

    "max_positions": X

  }},

  "expected_metrics": {{

    "cagr_estimate": "X-Y%",

    "sharpe_estimate": "X-Y",

    "max_drawdown_estimate": "X-Y%"

  }},

  "explanation": "explication des choix",

  "warnings": ["warning1", "warning2"],

  "confidence": "high/medium/low"

}}"""



        response = client.messages.create(

            model="claude-sonnet-4-20250514",

            max_tokens=4096,

            messages=[{"role": "user", "content": optimization_prompt}]

        )

        

        ai_response = response.content[0].text

        

        # Parse JSON response

        import re

        json_match = re.search(r'\{[\s\S]*\}', ai_response)

        if json_match:

            ai_data = json.loads(json_match.group())

            results['ai_analysis'] = ai_data.get('analysis', '')

            results['best_params'] = ai_data.get('optimal_params', {})

            results['expected_metrics'] = ai_data.get('expected_metrics', {})

            results['explanation'] = ai_data.get('explanation', '')

            results['warnings'] = ai_data.get('warnings', [])

            results['confidence'] = ai_data.get('confidence', 'medium')

        else:

            results['ai_analysis'] = ai_response

            results['best_params'] = find_best_from_grid(grid_results, optimization_goal)

        

        # Phase 3: Run final backtest with optimal params

        if results['best_params']:

            log_backtest.info("AI OPTIMIZER: Phase 3: Running optimal backtest...")

            

            optimal_bt_params = {

                'start_date': '2014-01-01',

                'end_date': datetime.now().strftime('%Y-%m-%d'),

                'universe_scope': scope,

                'universe': [],

                'pe_max': results['best_params'].get('pe_max', 12),

                'roe_min': results['best_params'].get('roe_min', 10),

                'pe_sell': results['best_params'].get('pe_sell', 17),

                'roe_min_hold': 8,

                'debt_equity_max': results['best_params'].get('debt_equity_max', 100),

                'rebalance_freq': 'quarterly',

                'initial_capital': 100000,

                'max_positions': results['best_params'].get('max_positions', 20),

                'benchmark': '^FCHI'

            }

            

            optimal_result = run_backtest(optimal_bt_params)

            results['best_metrics'] = optimal_result.get('metrics', {})

            results['best_equity_curve'] = optimal_result.get('equity_curve', [])

            results['best_yearly_returns'] = optimal_result.get('yearly_returns', [])

            

            # Save to history

            save_backtest_result(optimal_result, f"🤖 AI OPTIMAL ({scope})")

        

        log_backtest.info("AI OPTIMIZER: Optimization complete!")

        return results

        

    except Exception as e:

        log_backtest.error(f"AI OPTIMIZER: Error in AI analysis: {e}")

        # Fallback: find best from grid without AI

        results['best_params'] = find_best_from_grid(grid_results, optimization_goal)

        results['ai_analysis'] = f"AI analysis failed: {e}. Using grid search best result."

        return results





def find_best_from_grid(grid_results, goal):

    """Find best parameters from grid search results"""

    if not grid_results:

        return None

    

    if goal == 'max_return':

        best = max(grid_results, key=lambda x: x['metrics'].get('total_return', 0))

    elif goal == 'max_sharpe':

        best = max(grid_results, key=lambda x: x['metrics'].get('sharpe', 0))

    elif goal == 'min_drawdown':

        best = min(grid_results, key=lambda x: x['metrics'].get('max_drawdown', 100))

    else:  # balanced

        # Score = CAGR * Sharpe / (MaxDD + 1)

        def score(r):

            m = r['metrics']

            cagr = m.get('cagr', 0)

            sharpe = max(m.get('sharpe', 0), 0.01)

            dd = m.get('max_drawdown', 50)

            return (cagr * sharpe) / (dd + 1) if dd > 0 else cagr * sharpe

        

        best = max(grid_results, key=score)

    

    return best['params']



def get_eod_ticker(ticker):

    """Convert ticker to EOD format"""

    

    # Pour les benchmarks, utiliser des ETFs qui trackent les indices

    # Car les indices purs (.INDX) ne sont pas toujours disponibles sur EOD

    BENCHMARK_ETF_MAP = {

        # Utiliser des ETFs populaires qui trackent les indices

        '^FCHI': 'CAC.PA',             # Lyxor CAC 40 ETF

        '^STOXX50E': 'MSE.PA',         # Lyxor Euro Stoxx 50 ETF  

        '^STOXX': 'MEUD.PA',           # Lyxor Stoxx Europe 600 ETF

        '^GDAXI': 'DAX.PA',            # Lyxor DAX ETF

        '^FTSE': 'VUKE.LSE',           # Vanguard FTSE 100 ETF

        '^AEX': 'IAEX.AS',             # iShares AEX ETF

    }

    

    if ticker in BENCHMARK_ETF_MAP:

        return BENCHMARK_ETF_MAP[ticker]

    

    if '.' in ticker:

        return ticker

    return ticker + '.PA'



def eod_get_fundamentals(ticker: str, use_cache: bool = True, force_refresh: bool = False) -> Tuple[Optional[Dict[str, Any]], Optional[str]]:

    """Get fundamental data from EOD Historical Data API with smart caching"""

    cache_file = get_cache_path('fundamentals', ticker)

    

    # Try cache first (unless force refresh)

    if use_cache and not force_refresh and is_cache_valid(cache_file, FUNDAMENTALS_CACHE_DAYS):

        cached = load_from_cache(cache_file)

        if cached:

            return cached, None

    

    # If no API key, try to use cache even if expired

    if not EOD_OK:

        cached = load_from_cache(cache_file)

        if cached:

            log_cache.info(f"Using offline cache for {ticker} fundamentals")

            return cached, None

        return None, "EOD API not configured and no cached data available"

    

    try:

        eod_ticker = get_eod_ticker(ticker)

        url = f"https://eodhd.com/api/fundamentals/{eod_ticker}?api_token={EOD_API_KEY}&fmt=json"

        log_api.info(f"Fetching fundamentals: {ticker}")

        response = requests.get(url, timeout=30)

        

        if response.status_code == 200:

            data = response.json()

            save_to_cache(cache_file, data)

            return data, None

        else:

            # Try cache on API error

            cached = load_from_cache(cache_file)

            if cached:

                log_cache.info(f"API error, using cached data for {ticker}")

                return cached, None

            return None, f"API error: {response.status_code}"

            

    except Exception as e:

        # Try cache on exception

        cached = load_from_cache(cache_file)

        if cached:

            log_cache.info(f"Exception, using cached data for {ticker}")

            return cached, None

        return None, str(e)



def eod_get_historical_prices(ticker: str, start_date: str, end_date: str, use_cache: bool = True, force_refresh: bool = False) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:

    """Get historical prices from EOD with smart caching"""

    # Create cache key that includes date range

    cache_key = f"{ticker}_{start_date}_{end_date}"

    cache_file = get_cache_path('prices', cache_key)

    

    # Try cache first

    if use_cache and not force_refresh and is_cache_valid(cache_file, PRICES_CACHE_DAYS):

        cached = load_from_cache(cache_file)

        if cached and cached.get('prices'):

            return cached['prices'], None

    

    # For historical backtests, cache is always valid (history doesn't change)

    # Only refresh if end_date is recent (within 7 days)

    end_dt = datetime.strptime(end_date, '%Y-%m-%d')

    is_historical = (datetime.now() - end_dt).days > 7

    

    if is_historical and use_cache:

        cached = load_from_cache(cache_file)

        if cached and cached.get('prices'):

            return cached['prices'], None

    

    # If no API key, try to use cache

    if not EOD_OK:

        cached = load_from_cache(cache_file)

        if cached and cached.get('prices'):

            log_cache.info(f"Using offline cache for {ticker} prices")

            return cached['prices'], None

        return None, "EOD API not configured and no cached data available"

    

    try:

        eod_ticker = get_eod_ticker(ticker)

        url = f"https://eodhd.com/api/eod/{eod_ticker}?api_token={EOD_API_KEY}&fmt=json&from={start_date}&to={end_date}"

        log_api.info(f"Fetching prices: {ticker} ({start_date} to {end_date})")

        response = requests.get(url, timeout=30)

        

        if response.status_code == 200:

            data = response.json()

            save_to_cache(cache_file, {'prices': data})

            return data, None

        else:

            cached = load_from_cache(cache_file)

            if cached and cached.get('prices'):

                log_cache.info(f"API error, using cached data for {ticker}")

                return cached['prices'], None

            return None, f"API error: {response.status_code}"

            

    except Exception as e:

        cached = load_from_cache(cache_file)

        if cached and cached.get('prices'):

            log_cache.info(f"Exception, using cached data for {ticker}")

            return cached['prices'], None

        return None, str(e)


def eod_get_dividends(ticker: str, start_date: str, end_date: str, use_cache: bool = True) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:
    """Get dividend history from EOD API"""
    cache_key = f"div_{ticker}_{start_date}_{end_date}"
    cache_file = get_cache_path('dividends', cache_key)

    # Try cache first
    if use_cache and is_cache_valid(cache_file, 7):  # 7 days cache for dividends
        cached = load_from_cache(cache_file)
        if cached and cached.get('dividends') is not None:
            return cached['dividends'], None

    if not EOD_OK:
        cached = load_from_cache(cache_file)
        if cached and cached.get('dividends') is not None:
            return cached['dividends'], None
        return None, "EOD API not configured"

    try:
        eod_ticker = get_eod_ticker(ticker)
        url = f"https://eodhd.com/api/div/{eod_ticker}?api_token={EOD_API_KEY}&fmt=json&from={start_date}&to={end_date}"
        log_api.info(f"Fetching dividends: {ticker} ({start_date} to {end_date})")
        response = requests.get(url, timeout=30)

        if response.status_code == 200:
            data = response.json()
            save_to_cache(cache_file, {'dividends': data})
            return data, None
        else:
            cached = load_from_cache(cache_file)
            if cached and cached.get('dividends') is not None:
                return cached['dividends'], None
            return [], None  # Return empty list if no dividends

    except Exception as e:
        cached = load_from_cache(cache_file)
        if cached and cached.get('dividends') is not None:
            return cached['dividends'], None
        return None, str(e)


def download_all_data(scope='france', start_date='2010-01-01', progress_callback=None):

    """

    Pre-download all data for offline use

    Returns dict with success count, error count, and errors list

    """

    result = {

        'success': 0,

        'errors': 0,

        'error_list': [],

        'total': 0

    }

    

    if not EOD_OK:

        result['error_list'].append("EOD API not configured")

        return result

    

    # Get universe

    if scope == 'europe':

        exchanges = ['PA', 'AS', 'BR', 'MI', 'MC', 'XETRA', 'SW', 'LSE']

    else:

        exchanges = ['PA']

    

    all_tickers = []

    for exchange in exchanges:

        tickers = load_universe_from_eod(exchange)

        all_tickers.extend([t['ticker'] for t in tickers])

    

    result['total'] = len(all_tickers)

    end_date = datetime.now().strftime('%Y-%m-%d')

    

    for i, ticker in enumerate(all_tickers):

        if progress_callback:

            progress_callback(i + 1, len(all_tickers), ticker)

        

        # Download fundamentals

        fund, err = eod_get_fundamentals(ticker, use_cache=True)

        if err:

            result['errors'] += 1

            result['error_list'].append(f"{ticker} fundamentals: {err}")

            continue

        

        # Download prices

        prices, err = eod_get_historical_prices(ticker, start_date, end_date, use_cache=True)

        if err:

            result['errors'] += 1

            result['error_list'].append(f"{ticker} prices: {err}")

            continue

        

        result['success'] += 1

    

    return result

    

    # Par defaut, ajouter .PA pour Paris

    return ticker + '.PA'



def eod_get_historical_prices(ticker: str, start_date: str, end_date: str, use_cache: bool = True) -> Tuple[Optional[List[Dict[str, Any]]], Optional[str]]:

    """Get historical prices from EOD"""

    if not EOD_OK:

        return None, "EOD API not configured. Set EOD_API_KEY environment variable."

    

    cache_dir = CONFIG['backtest_cache_dir']

    os.makedirs(cache_dir, exist_ok=True)

    cache_file = os.path.join(cache_dir, f"prices_{ticker.replace('.', '_')}_{start_date}_{end_date}.json")

    

    if use_cache and os.path.exists(cache_file):

        try:

            return json.load(open(cache_file, encoding='utf-8')), None

        except Exception:
            pass

    

    try:

        eod_ticker = get_eod_ticker(ticker)

        url = f"https://eodhd.com/api/eod/{eod_ticker}?api_token={EOD_API_KEY}&fmt=json&from={start_date}&to={end_date}"

        log_api.info(f"Fetching prices: {eod_ticker} from {start_date} to {end_date}")

        response = requests.get(url, timeout=30)

        

        if response.status_code == 200:

            data = response.json()

            if data:  # Only cache if we got data

                with open(cache_file, 'w', encoding='utf-8') as f:

                    json.dump(data, f)

            return data, None

        else:

            return None, f"API error: {response.status_code} - {response.text[:100]}"

            

    except Exception as e:

        return None, str(e)



def extract_historical_fundamentals(fundamentals):

    """Extract historical PE, ROE, margins from EOD fundamentals"""

    history = []

    

    if not fundamentals:

        return history

    

    # Financials historiques

    financials = fundamentals.get('Financials', {})

    

    # Income Statement

    income = financials.get('Income_Statement', {}).get('yearly', {})

    # Balance Sheet

    balance = financials.get('Balance_Sheet', {}).get('yearly', {})

    # Cash Flow Statement

    cashflow = financials.get('Cash_Flow', {}).get('yearly', {})

    

    years = sorted(set(list(income.keys()) + list(balance.keys()) + list(cashflow.keys())), reverse=True)

    

    for year in years:

        try:

            inc = income.get(year, {})

            bal = balance.get(year, {})

            

            # Net Income

            net_income = float(inc.get('netIncome', 0) or 0)

            

            # Revenue

            revenue = float(inc.get('totalRevenue', 0) or 0)

            

            # Total Equity

            equity = float(bal.get('totalStockholderEquity', 0) or 0)

            

            # Total Assets

            assets = float(bal.get('totalAssets', 0) or 0)

            

            # Calculs

            roe = net_income / equity if equity > 0 else None

            roa = net_income / assets if assets > 0 else None

            net_margin = net_income / revenue if revenue > 0 else None

            

            # Operating Income

            op_income = float(inc.get('operatingIncome', 0) or 0)

            op_margin = op_income / revenue if revenue > 0 else None

            

            # Debt

            total_debt = float(bal.get('longTermDebt', 0) or 0) + float(bal.get('shortTermDebt', 0) or 0)

            debt_equity = total_debt / equity if equity > 0 else None

            

            # Current Ratio

            current_assets = float(bal.get('totalCurrentAssets', 0) or 0)

            current_liab = float(bal.get('totalCurrentLiabilities', 0) or 0)

            current_ratio = current_assets / current_liab if current_liab > 0 else None

            

            # EBITDA

            ebitda = float(inc.get('ebitda', 0) or 0)

            

            # Free Cash Flow (approximation)

            fcf = float(inc.get('freeCashFlow', 0) or 0) if 'freeCashFlow' in inc else None



            # Operating Cash Flow from Cash Flow Statement

            cf = cashflow.get(year, {})

            operating_cashflow = float(cf.get('totalCashFromOperatingActivities', 0) or 0)

            if operating_cashflow == 0:

                operating_cashflow = float(cf.get('operatingCashFlow', 0) or 0)



            history.append({

                'year': year[:4] if len(year) >= 4 else year,

                'date': year,

                'revenue': revenue,

                'net_income': net_income,

                'ebitda': ebitda,

                'equity': equity,

                'total_assets': assets,

                'total_debt': total_debt,

                'roe': roe,

                'roa': roa,

                'net_margin': net_margin,

                'op_margin': op_margin,

                'debt_equity': debt_equity,

                'current_ratio': current_ratio,

                'fcf': fcf,

                'operating_cashflow': operating_cashflow

            })

            

        except Exception as e:

            log.error(f"Error parsing year {year}: {e}")

            continue

    

    return history



def get_market_cap_history(ticker, prices, shares_outstanding):

    """Calculate historical market cap from prices and shares"""

    if not prices or not shares_outstanding:

        return []

    

    return [

        {

            'date': p['date'],

            'market_cap': p['close'] * shares_outstanding,

            'price': p['close']

        }

        for p in prices

    ]



# =============================================================================

# BACKTEST ENGINE

# =============================================================================



def run_backtest(params: Dict[str, Any]) -> Dict[str, Any]:

    """

    Run a DYNAMIC Higgons-style value investing backtest

    

    At each rebalancing:

    1. Screen the ENTIRE universe for stocks meeting criteria

    2. Rank by Higgons score

    3. Sell positions that no longer qualify (PE > sell_pe, ROE degraded, etc.)

    4. Buy best new opportunities to maintain target position count

    """

    

    results = {

        'params': params,

        'trades': [],

        'equity_curve': [],

        'positions_history': [],

        'metrics': {},

        'yearly_returns': [],

        'benchmark_curve': [],

        'screening_history': [],

        'errors': []

    }

    

    if not EOD_OK:

        results['errors'].append("EOD API not configured. Set EOD_API_KEY environment variable.")

        return results

    

    # Parse parameters

    start_date = params.get('start_date', '2015-01-01')

    end_date = params.get('end_date', datetime.now().strftime('%Y-%m-%d'))

    universe_scope = params.get('universe_scope', 'france')  # 'france' or 'europe'

    

    # Higgons BUY criteria

    pe_max_buy = float(params.get('pe_max', 12))

    roe_min_buy = float(params.get('roe_min', 10)) / 100

    debt_equity_max = float(params.get('debt_equity_max', 100)) / 100

    pcf_max_buy = float(params.get('pcf_max', 10))  # P/CF maximum for buying



    # Higgons SELL criteria

    pe_sell_threshold = float(params.get('pe_sell', 17))  # Sell if PE > 17

    roe_min_hold = float(params.get('roe_min_hold', 8)) / 100  # Sell if ROE < 8%

    

    rebalance_freq = params.get('rebalance_freq', 'quarterly')

    initial_capital = float(params.get('initial_capital', 100000))

    max_positions = int(params.get('max_positions', 20))

    benchmark = params.get('benchmark', '^FCHI')

    

    # Get universe of tickers to scan

    if universe_scope == 'europe':

        if not UNIVERSE_EUROPE:

            init_universes()

        universe_tickers = [t['ticker'] for t in UNIVERSE_EUROPE]

    else:

        if not UNIVERSE_FRANCE:

            init_universes()

        universe_tickers = [t['ticker'] for t in UNIVERSE_FRANCE]

    

    # If custom universe provided, use that instead

    custom_universe = params.get('universe', [])

    if custom_universe and len(custom_universe) > 0:

        universe_tickers = custom_universe

    

    log_backtest.info(f"Universe: {len(universe_tickers)} tickers ({universe_scope})")

    log_backtest.info(f"Period: {start_date} to {end_date}")

    log_backtest.info(f"Buy criteria: PE <= {pe_max_buy}, ROE >= {roe_min_buy*100}%, P/CF <= {pcf_max_buy}")

    log_backtest.info(f"Sell criteria: PE > {pe_sell_threshold} or ROE < {roe_min_hold*100}%")

    

    # Pre-load fundamental data for all tickers (with caching)

    log_backtest.info("Loading fundamental data...")

    ticker_fundamentals = {}

    loaded_count = 0

    

    for ticker in universe_tickers[:200]:  # Limit to 200 for now to avoid API overload

        fund, err = eod_get_fundamentals(ticker, use_cache=True)

        if fund and not err:

            hist = extract_historical_fundamentals(fund)

            if hist:

                ticker_fundamentals[ticker] = {

                    'name': fund.get('General', {}).get('Name', ticker),

                    'sector': fund.get('General', {}).get('Sector', 'Unknown'),

                    'fundamentals': hist,

                    'fund_by_year': {f['year']: f for f in hist}

                }

                loaded_count += 1

        

        if loaded_count % 20 == 0:

            log_backtest.info(f"Loaded {loaded_count} tickers with valid data...")

    

    log_backtest.info(f"Loaded fundamentals for {loaded_count} tickers")

    

    if loaded_count == 0:

        results['errors'].append("No valid fundamental data found for any ticker")

        return results

    

    # Load price data for tickers with fundamentals

    log_backtest.info("Loading price data...")

    ticker_prices = {}

    

    for ticker in ticker_fundamentals.keys():

        prices, err = eod_get_historical_prices(ticker, start_date, end_date, use_cache=True)

        if prices and len(prices) > 0:

            ticker_prices[ticker] = {p['date']: p for p in prices}

    

    log_backtest.info(f"Loaded prices for {len(ticker_prices)} tickers")

    

    # Load benchmark

    eod_benchmark = get_eod_ticker(benchmark)

    log_backtest.info(f"Loading benchmark {benchmark} -> {eod_benchmark}...")

    bench_prices_raw, err = eod_get_historical_prices(benchmark, start_date, end_date)

    if bench_prices_raw and len(bench_prices_raw) > 0:

        results['benchmark_curve'] = [{'date': p['date'], 'price': p['close']} for p in bench_prices_raw]

        log_backtest.info(f"Benchmark loaded: {len(results['benchmark_curve'])} data points")

    else:

        log_backtest.warning(f"Could not load benchmark {benchmark}: {err}")

        results['errors'].append(f"Benchmark {benchmark} not loaded: {err}")

    

    # Generate rebalancing dates

    rebalance_dates = generate_rebalance_dates(start_date, end_date, rebalance_freq)

    log_backtest.info(f"{len(rebalance_dates)} rebalancing periods")

    

    # Simulation

    capital = initial_capital

    positions = {}  # ticker -> {'shares': n, 'entry_price': p, 'entry_date': d, 'entry_pe': pe, 'entry_roe': roe}

    equity_curve = []

    

    for rebal_idx, rebal_date in enumerate(rebalance_dates):

        year = rebal_date[:4]

        fund_year = str(int(year) - 1)  # Use previous year's fundamentals

        

        log_backtest.info(f"[{rebal_idx+1}/{len(rebalance_dates)}] Rebalancing {rebal_date}...")

        

        # ============================================

        # STEP 1: SCREEN ENTIRE UNIVERSE

        # ============================================

        screened = []

        

        for ticker, data in ticker_fundamentals.items():

            if ticker not in ticker_prices:

                continue

            

            # Get fundamentals for the relevant year

            fund = data['fund_by_year'].get(fund_year) or data['fund_by_year'].get(year)

            if not fund:

                continue

            

            # Get current price

            price = get_price_on_date(ticker_prices[ticker], rebal_date)

            if not price or price <= 0:

                continue

            

            # Extract metrics

            roe = fund.get('roe')

            net_margin = fund.get('net_margin')

            debt_eq = fund.get('debt_equity')

            net_income = fund.get('net_income', 0)

            equity = fund.get('equity', 0)

            operating_cashflow = fund.get('operating_cashflow', 0)

            

            # Calculate PE (approximation using earnings yield)

            # PE = Market Cap / Net Income

            # Since we don't have shares, use: PE â‰ˆ 1/ROE when P/B â‰ˆ 1

            # Better approximation: use net_margin and revenue trends

            if roe and roe > 0:

                pe_approx = 1 / roe  # Simplified PE proxy

            else:

                pe_approx = None



            # Calculate P/CF proxy: Book Value / Operating Cash Flow

            # Lower is better (similar to PE - lower means cheaper on cash flow basis)

            pcf_proxy = None

            if equity and equity > 0 and operating_cashflow and operating_cashflow > 0:

                pcf_proxy = equity / operating_cashflow



            # Check if meets BUY criteria

            if roe is None or roe < roe_min_buy:

                continue

            if pe_approx and pe_approx > pe_max_buy:

                continue

            if debt_eq and debt_eq > debt_equity_max:

                continue

            if pcf_proxy and pcf_proxy > pcf_max_buy:

                continue



            # Calculate Higgons Score (now includes P/CF)

            score = calculate_higgons_score_for_backtest(pe_approx, roe, debt_eq, net_margin, pcf_proxy)



            screened.append({

                'ticker': ticker,

                'name': data['name'],

                'sector': data['sector'],

                'price': price,

                'pe': pe_approx,

                'roe': roe,

                'debt_equity': debt_eq,

                'net_margin': net_margin,

                'pcf': pcf_proxy,

                'score': score

            })

        

        # Sort by score (best first)

        screened.sort(key=lambda x: x['score'], reverse=True)

        

        results['screening_history'].append({

            'date': rebal_date,

            'candidates': len(screened),

            'top_10': [{'ticker': s['ticker'], 'score': s['score'], 'pe': s['pe'], 'roe': s['roe'], 'pcf': s.get('pcf')} for s in screened[:10]]

        })

        

        # ============================================

        # STEP 2: CHECK EXISTING POSITIONS FOR SELL

        # ============================================

        positions_to_sell = []

        

        for ticker, pos in positions.items():

            should_sell = False

            sell_reason = ""

            

            if ticker not in ticker_fundamentals or ticker not in ticker_prices:

                should_sell = True

                sell_reason = "No data"

            else:

                # Get current fundamentals

                fund = ticker_fundamentals[ticker]['fund_by_year'].get(fund_year) or \
                       ticker_fundamentals[ticker]['fund_by_year'].get(year)

                

                if fund:

                    current_roe = fund.get('roe')

                    current_pe = 1 / current_roe if current_roe and current_roe > 0 else None

                    

                    # SELL if PE became too high

                    if current_pe and current_pe > pe_sell_threshold:

                        should_sell = True

                        sell_reason = f"PE too high ({current_pe:.1f} > {pe_sell_threshold})"

                    

                    # SELL if ROE degraded

                    elif current_roe and current_roe < roe_min_hold:

                        should_sell = True

                        sell_reason = f"ROE too low ({current_roe*100:.1f}% < {roe_min_hold*100}%)"

                    

                    # SELL if no longer in top candidates (underperformer)

                    elif ticker not in [s['ticker'] for s in screened[:max_positions * 2]]:

                        should_sell = True

                        sell_reason = "No longer top ranked"

            

            if should_sell:

                positions_to_sell.append((ticker, sell_reason))

        

        # Execute SELLS

        for ticker, reason in positions_to_sell:

            pos = positions[ticker]

            price = get_price_on_date(ticker_prices.get(ticker, {}), rebal_date)

            

            if price:

                sell_value = pos['shares'] * price

                pnl_pct = (price / pos['entry_price'] - 1) * 100

                capital += sell_value

                

                results['trades'].append({

                    'date': rebal_date,

                    'action': 'SELL',

                    'ticker': ticker,

                    'name': ticker_fundamentals.get(ticker, {}).get('name', ticker),

                    'shares': pos['shares'],

                    'price': price,

                    'value': sell_value,

                    'pnl_pct': pnl_pct,

                    'entry_price': pos['entry_price'],

                    'entry_date': pos['entry_date'],

                    'reason': reason

                })

            

            del positions[ticker]

        

        # ============================================

        # STEP 3: BUY NEW POSITIONS

        # ============================================

        positions_to_fill = max_positions - len(positions)

        

        if positions_to_fill > 0 and screened:

            # Filter out already held positions

            available = [s for s in screened if s['ticker'] not in positions]

            

            # Take top N available

            to_buy = available[:positions_to_fill]

            

            if to_buy and capital > 0:

                capital_per_position = capital / len(to_buy)

                

                for candidate in to_buy:

                    ticker = candidate['ticker']

                    price = candidate['price']

                    

                    shares = int(capital_per_position / price)

                    if shares > 0:

                        cost = shares * price

                        capital -= cost

                        

                        positions[ticker] = {

                            'shares': shares,

                            'entry_price': price,

                            'entry_date': rebal_date,

                            'entry_pe': candidate['pe'],

                            'entry_roe': candidate['roe']

                        }

                        

                        results['trades'].append({

                            'date': rebal_date,

                            'action': 'BUY',

                            'ticker': ticker,

                            'name': candidate['name'],

                            'shares': shares,

                            'price': price,

                            'value': cost,

                            'pe': candidate['pe'],

                            'roe': candidate['roe'],

                            'score': candidate['score']

                        })

        

        # ============================================

        # STEP 4: CALCULATE PORTFOLIO VALUE

        # ============================================

        total_value = capital

        pos_details = []

        

        for ticker, pos in positions.items():

            price = get_price_on_date(ticker_prices.get(ticker, {}), rebal_date)

            if price:

                val = pos['shares'] * price

                total_value += val

                pos_details.append({

                    'ticker': ticker,

                    'shares': pos['shares'],

                    'price': price,

                    'value': val,

                    'pnl_pct': (price / pos['entry_price'] - 1) * 100

                })

        

        equity_curve.append({

            'date': rebal_date,

            'value': total_value,

            'cash': capital,

            'invested': total_value - capital,

            'positions': len(positions),

            'sells': len(positions_to_sell),

            'buys': len([t for t in results['trades'] if t['date'] == rebal_date and t['action'] == 'BUY'])

        })

        

        results['positions_history'].append({

            'date': rebal_date,

            'positions': pos_details.copy(),

            'screened_count': len(screened)

        })

    

    results['equity_curve'] = equity_curve

    

    # Calculate final metrics

    if equity_curve:

        results['metrics'] = calculate_backtest_metrics(

            equity_curve, 

            results['benchmark_curve'],

            initial_capital,

            results['trades']

        )

    

    results['yearly_returns'] = calculate_yearly_returns(equity_curve)

    

    return results





def calculate_higgons_score_for_backtest(pe: Optional[float], roe: Optional[float], debt_equity: Optional[float], net_margin: Optional[float], pcf: Optional[float] = None) -> int:

    """Calculate Higgons-style score for ranking (max 115 points with P/CF)"""

    score = 0



    # PE Score (0-35 points) - lower is better

    if pe and pe > 0:

        if pe < 7: score += 35

        elif pe < 10: score += 30

        elif pe < 12: score += 25

        elif pe < 15: score += 15

        elif pe < 20: score += 5



    # P/CF Score (0-15 points) - lower is better

    if pcf and pcf > 0:

        if pcf <= 6: score += 15

        elif pcf <= 8: score += 12

        elif pcf <= 10: score += 9

        elif pcf <= 12: score += 6

        elif pcf <= 15: score += 3



    # ROE Score (0-30 points) - higher is better

    if roe and roe > 0:

        if roe >= 0.25: score += 30

        elif roe >= 0.20: score += 25

        elif roe >= 0.15: score += 20

        elif roe >= 0.12: score += 15

        elif roe >= 0.10: score += 10



    # Debt/Equity Score (0-20 points) - lower is better

    if debt_equity is not None:

        if debt_equity <= 0: score += 20  # Net cash

        elif debt_equity <= 0.3: score += 15

        elif debt_equity <= 0.5: score += 10

        elif debt_equity <= 1.0: score += 5



    # Net Margin Score (0-15 points) - higher is better

    if net_margin and net_margin > 0:

        if net_margin >= 0.15: score += 15

        elif net_margin >= 0.10: score += 10

        elif net_margin >= 0.05: score += 5



    return score





def generate_rebalance_dates(start_date, end_date, freq):

    """Generate list of rebalancing dates"""

    dates = []

    current = datetime.strptime(start_date, '%Y-%m-%d')

    end = datetime.strptime(end_date, '%Y-%m-%d')

    

    if freq == 'monthly':

        delta = 1

    elif freq == 'quarterly':

        delta = 3

    elif freq == 'semi-annual':

        delta = 6

    else:  # yearly

        delta = 12

    

    while current <= end:

        dates.append(current.strftime('%Y-%m-%d'))

        

        # Avancer de N mois

        month = current.month + delta

        year = current.year

        while month > 12:

            month -= 12

            year += 1

        

        try:

            current = current.replace(year=year, month=month)

        except ValueError:

            # Gerer les fins de mois

            current = current.replace(year=year, month=month, day=28)

    

    return dates





def get_price_on_date(prices_dict, target_date):

    """Get price on specific date or closest previous date"""

    if target_date in prices_dict:

        return prices_dict[target_date]['close']

    

    # Chercher la date la plus proche avant

    target = datetime.strptime(target_date, '%Y-%m-%d')

    closest_date = None

    closest_price = None

    

    for date_str, data in prices_dict.items():

        date = datetime.strptime(date_str, '%Y-%m-%d')

        if date <= target:

            if closest_date is None or date > closest_date:

                closest_date = date

                closest_price = data['close']

    

    return closest_price





def calculate_backtest_metrics(equity_curve, benchmark_curve, initial_capital, trades):

    """Calculate performance metrics"""

    metrics = {}

    

    if not equity_curve:

        return metrics

    

    # Total Return

    final_value = equity_curve[-1]['value']

    total_return = (final_value / initial_capital - 1) * 100

    metrics['total_return'] = total_return

    

    # CAGR

    start = datetime.strptime(equity_curve[0]['date'], '%Y-%m-%d')

    end = datetime.strptime(equity_curve[-1]['date'], '%Y-%m-%d')

    years = (end - start).days / 365.25

    

    if years > 0:

        cagr = ((final_value / initial_capital) ** (1 / years) - 1) * 100

        metrics['cagr'] = cagr

    else:

        metrics['cagr'] = 0

    

    # Max Drawdown

    peak = initial_capital

    max_dd = 0

    

    for point in equity_curve:

        value = point['value']

        if value > peak:

            peak = value

        dd = (peak - value) / peak * 100

        if dd > max_dd:

            max_dd = dd

    

    metrics['max_drawdown'] = max_dd

    

    # Volatility (annualized)

    returns = []

    for i in range(1, len(equity_curve)):

        ret = (equity_curve[i]['value'] / equity_curve[i-1]['value']) - 1

        returns.append(ret)

    

    if returns:

        import statistics

        vol = statistics.stdev(returns) * (12 ** 0.5) * 100  # Annualized (assuming monthly)

        metrics['volatility'] = vol

        

        # Sharpe Ratio (assuming 2% risk-free rate)

        rf = 0.02

        if vol > 0:

            sharpe = (metrics['cagr'] / 100 - rf) / (vol / 100)

            metrics['sharpe'] = sharpe

        else:

            metrics['sharpe'] = 0

    else:

        metrics['volatility'] = 0

        metrics['sharpe'] = 0

    

    # Win Rate

    winning_trades = [t for t in trades if t.get('action') == 'SELL' and t.get('pnl_pct', 0) > 0]

    losing_trades = [t for t in trades if t.get('action') == 'SELL' and t.get('pnl_pct', 0) <= 0]

    total_closed = len(winning_trades) + len(losing_trades)

    

    if total_closed > 0:

        metrics['win_rate'] = len(winning_trades) / total_closed * 100

        metrics['total_trades'] = total_closed

        

        # Average win/loss

        if winning_trades:

            metrics['avg_win'] = sum(t['pnl_pct'] for t in winning_trades) / len(winning_trades)

        else:

            metrics['avg_win'] = 0

            

        if losing_trades:

            metrics['avg_loss'] = sum(t['pnl_pct'] for t in losing_trades) / len(losing_trades)

        else:

            metrics['avg_loss'] = 0

    else:

        metrics['win_rate'] = 0

        metrics['total_trades'] = 0

        metrics['avg_win'] = 0

        metrics['avg_loss'] = 0

    

    # Benchmark comparison

    if benchmark_curve and len(benchmark_curve) >= 2:

        bench_start = benchmark_curve[0]['price']

        bench_end = benchmark_curve[-1]['price']

        bench_return = (bench_end / bench_start - 1) * 100

        metrics['benchmark_return'] = bench_return

        metrics['alpha'] = total_return - bench_return

    else:

        metrics['benchmark_return'] = 0

        metrics['alpha'] = total_return

    

    metrics['final_value'] = final_value

    metrics['initial_capital'] = initial_capital

    

    return metrics





def calculate_yearly_returns(equity_curve):

    """Calculate returns by year"""

    yearly = {}

    

    for point in equity_curve:

        year = point['date'][:4]

        if year not in yearly:

            yearly[year] = {'start': point['value'], 'end': point['value']}

        else:

            yearly[year]['end'] = point['value']

    

    returns = []

    prev_end = None

    

    for year in sorted(yearly.keys()):

        data = yearly[year]

        start = prev_end if prev_end else data['start']

        end = data['end']

        ret = (end / start - 1) * 100 if start > 0 else 0

        returns.append({'year': year, 'return': ret, 'end_value': end})

        prev_end = end

    

    return returns



def create_memo_docx(ticker, name, sector, country, signal, target_price, thesis, strengths, risks, valuation, notes):

    """Create a new investment memo as a .docx file"""

    try:

        from docx import Document

        from docx.shared import Inches, Pt

        from docx.enum.text import WD_ALIGN_PARAGRAPH

        

        doc = Document()

        

        # Title

        title = doc.add_heading(f'Investment Memo: {name}', 0)

        title.alignment = WD_ALIGN_PARAGRAPH.CENTER

        

        # Subtitle

        subtitle = doc.add_paragraph(f'{ticker} | {sector} | {country}')

        subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER

        

        # Signal

        doc.add_heading('SIGNAL', level=1)

        signal_para = doc.add_paragraph()

        signal_para.add_run(signal.upper()).bold = True

        if target_price:

            signal_para.add_run(f'  |  Target Price: {target_price} EUR')

        

        # Date

        doc.add_paragraph(f'Date: {datetime.now().strftime("%d %B %Y")}')

        doc.add_paragraph()

        

        # Thesis

        if thesis:

            doc.add_heading('INVESTMENT THESIS', level=1)

            doc.add_paragraph(thesis)

        

        # Strengths

        if strengths:

            doc.add_heading('KEY STRENGTHS / CATALYSTS', level=1)

            for line in strengths.split('\n'):

                if line.strip():

                    doc.add_paragraph(line.strip(), style='List Bullet')

        

        # Risks

        if risks:

            doc.add_heading('RISKS / CONCERNS', level=1)

            for line in risks.split('\n'):

                if line.strip():

                    doc.add_paragraph(line.strip(), style='List Bullet')

        

        # Valuation

        if valuation:

            doc.add_heading('VALUATION', level=1)

            doc.add_paragraph(valuation)

        

        # Notes

        if notes:

            doc.add_heading('ADDITIONAL NOTES', level=1)

            doc.add_paragraph(notes)

        

        # Save

        filename = f'Memo_{ticker.replace(".", "_")}.docx'

        filepath = os.path.join(CONFIG['memo_dir'], filename)

        doc.save(filepath)

        return filepath, None

        

    except ImportError:

        # python-docx not installed, create a simple text file instead

        try:

            filename = f'Memo_{ticker.replace(".", "_")}.txt'

            filepath = os.path.join(CONFIG['memo_dir'], filename)

            

            content = f"""INVESTMENT MEMO: {name}

{'='*50}

{ticker} | {sector} | {country}

Date: {datetime.now().strftime("%d %B %Y")}



SIGNAL: {signal.upper()}

Target Price: {target_price or 'N/A'} EUR



{'='*50}

INVESTMENT THESIS

{'='*50}

{thesis or 'N/A'}



{'='*50}

KEY STRENGTHS / CATALYSTS

{'='*50}

{strengths or 'N/A'}



{'='*50}

RISKS / CONCERNS

{'='*50}

{risks or 'N/A'}



{'='*50}

VALUATION

{'='*50}

{valuation or 'N/A'}



{'='*50}

ADDITIONAL NOTES

{'='*50}

{notes or 'N/A'}

"""

            with open(filepath, 'w', encoding='utf-8') as f:

                f.write(content)

            return filepath, None

            

        except Exception as e:

            return None, str(e)

    except Exception as e:

        return None, str(e)





def generate_memo_with_ai(security_data):

    """Generate investment memo using Claude AI"""

    if not ANTHROPIC_OK:

        return None, "Anthropic API not configured. Set ANTHROPIC_API_KEY environment variable."

    

    try:

        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

        

        # Build the prompt with all available data

        prompt = f"""Tu es un analyste financier senior specialise dans les small et mid caps europeennes. 

Analyse les donnees suivantes et genere un memo d'investissement professionnel et structure.



=== DONNEES DE LA SOCIETE ===

Nom: {security_data.get('name', 'N/A')}

Ticker: {security_data.get('ticker', 'N/A')}

Secteur: {security_data.get('sector', 'N/A')}

Industrie: {security_data.get('industry', 'N/A')}

Pays: {security_data.get('country', 'N/A')}



=== DONNEES DE PRIX ===

Prix actuel: {security_data.get('price', 'N/A')} EUR

Variation jour: {security_data.get('change_pct', 'N/A')}%

Plus haut 52 semaines: {security_data.get('high_52w', 'N/A')} EUR

Plus bas 52 semaines: {security_data.get('low_52w', 'N/A')} EUR

Target Price analystes: {security_data.get('target_price', 'N/A')} EUR



=== VALORISATION ===

P/E (TTM): {security_data.get('pe', 'N/A')}

P/E Forward: {security_data.get('forward_pe', 'N/A')}

EPS: {security_data.get('eps', 'N/A')}

Book Value: {security_data.get('book_value', 'N/A')}



=== RENTABILITE ===

ROE: {security_data.get('roe', 'N/A')}

Marge operationnelle: {security_data.get('profit_margin', 'N/A')}

Rendement dividende: {security_data.get('dividend_yield', 'N/A')}



=== BILAN ===

Market Cap: {security_data.get('market_cap', 'N/A')}

Revenue: {security_data.get('revenue', 'N/A')}

Debt/Equity: {security_data.get('debt_equity', 'N/A')}

Current Ratio: {security_data.get('current_ratio', 'N/A')}



=== DESCRIPTION ===

{security_data.get('description', 'N/A')[:1500]}



=== INSTRUCTIONS ===

Genere un memo d'investissement avec EXACTEMENT cette structure (utilise ces titres):



SIGNAL

[Donne une recommandation: ACHAT, SURVEILLANCE, NEUTRE, ou ECARTER avec un prix cible si possible]



RESUME EXECUTIF

[2-3 phrases resumant la these d'investissement]



THÃˆSE D'INVESTISSEMENT

[Paragraphe detaille expliquant pourquoi investir ou non]



POINTS FORTS

[Liste a puces des 4-5 principaux atouts]



RISQUES

[Liste a puces des 4-5 principaux risques]



ANALYSE DE VALORISATION

[Analyse du PE, ROE, comparaison avec le secteur, est-ce cher ou pas ?]



CATALYSEURS POTENTIELS

[Liste des evenements qui pourraient faire bouger le cours]



CONCLUSION

[Synthese finale avec la recommandation]



Sois precis, factuel et utilise les donnees fournies. Si une donnee est manquante (N/A), mentionne-le comme une limitation.

Ecris en francais."""



        message = client.messages.create(

            model="claude-sonnet-4-20250514",

            max_tokens=4096,

            messages=[

                {"role": "user", "content": prompt}

            ]

        )

        

        ai_response = message.content[0].text

        

        # Parse the AI response to extract sections

        sections = parse_ai_memo_response(ai_response)

        

        # Create the docx file

        filepath, error = create_ai_memo_docx(security_data, sections, ai_response)

        

        return filepath, error

        

    except Exception as e:

        return None, str(e)





def parse_ai_memo_response(response):

    """Parse AI response to extract sections"""

    sections = {

        'signal': '',

        'summary': '',

        'thesis': '',

        'strengths': '',

        'risks': '',

        'valuation': '',

        'catalysts': '',

        'conclusion': ''

    }

    

    # Simple parsing based on section headers

    current_section = None

    current_content = []

    

    for line in response.split('\n'):

        line_upper = line.upper().strip()

        

        if 'SIGNAL' in line_upper and len(line_upper) < 20:

            if current_section:

                sections[current_section] = '\n'.join(current_content).strip()

            current_section = 'signal'

            current_content = []

        elif 'RESUME' in line_upper or 'RESUME' in line_upper or 'EXECUTIF' in line_upper:

            if current_section:

                sections[current_section] = '\n'.join(current_content).strip()

            current_section = 'summary'

            current_content = []

        elif 'THÃˆSE' in line_upper or 'THESE' in line_upper or 'INVESTISSEMENT' in line_upper and 'THÃˆSE' in line_upper:

            if current_section:

                sections[current_section] = '\n'.join(current_content).strip()

            current_section = 'thesis'

            current_content = []

        elif 'POINTS FORTS' in line_upper or 'FORCES' in line_upper or 'ATOUTS' in line_upper:

            if current_section:

                sections[current_section] = '\n'.join(current_content).strip()

            current_section = 'strengths'

            current_content = []

        elif 'RISQUES' in line_upper or 'RISKS' in line_upper or 'FAIBLESSES' in line_upper:

            if current_section:

                sections[current_section] = '\n'.join(current_content).strip()

            current_section = 'risks'

            current_content = []

        elif 'VALORISATION' in line_upper or 'VALUATION' in line_upper:

            if current_section:

                sections[current_section] = '\n'.join(current_content).strip()

            current_section = 'valuation'

            current_content = []

        elif 'CATALYSEUR' in line_upper or 'CATALYST' in line_upper:

            if current_section:

                sections[current_section] = '\n'.join(current_content).strip()

            current_section = 'catalysts'

            current_content = []

        elif 'CONCLUSION' in line_upper:

            if current_section:

                sections[current_section] = '\n'.join(current_content).strip()

            current_section = 'conclusion'

            current_content = []

        else:

            if current_section:

                current_content.append(line)

    

    # Don't forget the last section

    if current_section:

        sections[current_section] = '\n'.join(current_content).strip()

    

    return sections





def create_ai_memo_docx(security_data, sections, full_response):

    """Create a docx file from AI-generated memo"""

    try:

        from docx import Document

        from docx.shared import Pt, RGBColor

        from docx.enum.text import WD_ALIGN_PARAGRAPH

        

        doc = Document()

        

        # Title

        title = doc.add_heading(f'Investment Memo: {security_data.get("name", "N/A")}', 0)

        title.alignment = WD_ALIGN_PARAGRAPH.CENTER

        

        # Subtitle

        subtitle = doc.add_paragraph(f'{security_data.get("ticker", "")} | {security_data.get("sector", "")} | {security_data.get("country", "")}')

        subtitle.alignment = WD_ALIGN_PARAGRAPH.CENTER

        

        # Date and AI notice

        doc.add_paragraph(f'Date: {datetime.now().strftime("%d %B %Y")}')

        ai_notice = doc.add_paragraph('📊 Memo generated with AI assistance (Claude)')

        ai_notice.runs[0].font.size = Pt(9)

        ai_notice.runs[0].font.italic = True

        doc.add_paragraph()

        

        # Signal section

        if sections.get('signal'):

            doc.add_heading('SIGNAL', level=1)

            signal_para = doc.add_paragraph()

            signal_text = sections['signal'].strip()

            run = signal_para.add_run(signal_text)

            run.bold = True

        

        # Summary

        if sections.get('summary'):

            doc.add_heading('RESUME EXECUTIF', level=1)

            doc.add_paragraph(sections['summary'])

        

        # Thesis

        if sections.get('thesis'):

            doc.add_heading('THÃˆSE D\'INVESTISSEMENT', level=1)

            doc.add_paragraph(sections['thesis'])

        

        # Strengths

        if sections.get('strengths'):

            doc.add_heading('POINTS FORTS', level=1)

            for line in sections['strengths'].split('\n'):

                line = line.strip()

                if line and not line.startswith('#'):

                    # Remove bullet points if already present

                    if line.startswith(('-', ' - ', '*')):

                        line = line[1:].strip()

                    if line:

                        doc.add_paragraph(line, style='List Bullet')

        

        # Risks

        if sections.get('risks'):

            doc.add_heading('RISQUES', level=1)

            for line in sections['risks'].split('\n'):

                line = line.strip()

                if line and not line.startswith('#'):

                    if line.startswith(('-', ' - ', '*')):

                        line = line[1:].strip()

                    if line:

                        doc.add_paragraph(line, style='List Bullet')

        

        # Valuation

        if sections.get('valuation'):

            doc.add_heading('ANALYSE DE VALORISATION', level=1)

            doc.add_paragraph(sections['valuation'])

        

        # Catalysts

        if sections.get('catalysts'):

            doc.add_heading('CATALYSEURS POTENTIELS', level=1)

            for line in sections['catalysts'].split('\n'):

                line = line.strip()

                if line and not line.startswith('#'):

                    if line.startswith(('-', ' - ', '*')):

                        line = line[1:].strip()

                    if line:

                        doc.add_paragraph(line, style='List Bullet')

        

        # Conclusion

        if sections.get('conclusion'):

            doc.add_heading('CONCLUSION', level=1)

            doc.add_paragraph(sections['conclusion'])

        

        # Key metrics table

        doc.add_heading('DONNEES CLES', level=1)

        table = doc.add_table(rows=6, cols=2)

        table.style = 'Table Grid'

        

        metrics = [

            ('Prix actuel', f"{security_data.get('price', 'N/A')} EUR"),

            ('P/E (TTM)', f"{security_data.get('pe', 'N/A')}"),

            ('ROE', f"{security_data.get('roe', 'N/A')}"),

            ('Market Cap', f"{security_data.get('market_cap', 'N/A')}"),

            ('Rendement div.', f"{security_data.get('dividend_yield', 'N/A')}"),

            ('52W Range', f"{security_data.get('low_52w', 'N/A')} - {security_data.get('high_52w', 'N/A')} EUR"),

        ]

        

        for i, (label, value) in enumerate(metrics):

            table.rows[i].cells[0].text = label

            table.rows[i].cells[1].text = str(value) if value else 'N/A'

        

        # Save

        ticker = security_data.get('ticker', 'UNKNOWN').replace('.', '_')

        filename = f'Memo_{ticker}_AI.docx'

        filepath = os.path.join(CONFIG['memo_dir'], filename)

        doc.save(filepath)

        

        return filepath, None

        

    except ImportError:

        # Fallback to text file

        try:

            ticker = security_data.get('ticker', 'UNKNOWN').replace('.', '_')

            filename = f'Memo_{ticker}_AI.txt'

            filepath = os.path.join(CONFIG['memo_dir'], filename)

            

            with open(filepath, 'w', encoding='utf-8') as f:

                f.write(f"INVESTMENT MEMO: {security_data.get('name', 'N/A')}\n")

                f.write(f"{'='*60}\n")

                f.write(f"Generated with AI (Claude) - {datetime.now().strftime('%d %B %Y')}\n\n")

                f.write(full_response)

            

            return filepath, None

        except Exception as e:

            return None, str(e)

    except Exception as e:

        return None, str(e)



def load_nav_history():

    """Load NAV history from JSON file"""

    return load_json(CONFIG['nav_history_file'], [])



def save_nav_history(history):

    """Save NAV history to JSON file"""

    save_json(CONFIG['nav_history_file'], history)



def update_nav_history(nav, total_cost, pnl, pnl_pct, realized_pnl=0.0):

    """Add today's NAV to history (one entry per day)



    NAV = market value of active positions + cumulative realized PnL

    This ensures that selling positions with gains doesn't show as a NAV drop.

    """

    history = load_nav_history()

    today = datetime.now().strftime('%Y-%m-%d')



    # Check if we already have an entry for today

    existing_idx = None

    for i, entry in enumerate(history):

        if entry['date'] == today:

            existing_idx = i

            break



    new_entry = {

        'date': today,

        'nav': round(nav, 2),

        'cost': round(total_cost, 2),

        'pnl': round(pnl, 2),

        'pnl_pct': round(pnl_pct, 2),

        'realized_pnl': round(realized_pnl, 2)

    }

    

    if existing_idx is not None:

        # Update today's entry

        history[existing_idx] = new_entry

    else:

        # Add new entry

        history.append(new_entry)

    

    # Keep only last 365 days

    history = history[-365:]

    

    save_nav_history(history)

    return history



def add_to_watchlist(ticker, name, country, sector):

    w = load_watchlist()

    if not any(x['ticker'] == ticker for x in w):

        w.append({'ticker': ticker, 'name': name, 'country': country, 'sector': sector, 'added': datetime.now().strftime('%Y-%m-%d')})

        save_watchlist(w)



def remove_from_watchlist(ticker):

    w = [x for x in load_watchlist() if x['ticker'] != ticker]

    save_watchlist(w)



def load_portfolio() -> Tuple[Optional[Any], Optional[str]]:

    if not PANDAS_OK:

        return None, "pandas manquant"

    try:

        df = pd.read_excel(CONFIG['portfolio_file'])

        df.columns = [c.lower().strip().replace(' ', '_') for c in df.columns]

        return df, None

    except Exception as e:

        return None, str(e)


def build_advisor_portfolio_payload(df: Any, cash: float = 0.0, currency: str = 'EUR') -> Dict[str, Any]:

    """Convert current portfolio dataframe to advisor JSON payload."""

    positions: List[Dict[str, Any]] = []

    for _, row in df.iterrows():

        ticker = str(row.get('ticker', '') or '').strip().upper()
        if not ticker:
            continue

        qty = safe_float(row.get('qty', row.get('shares', row.get('quantity', 0)))) or 0.0
        if qty <= 0:
            continue

        avg_price = (
            safe_float(row.get('avg_cost_eur', row.get('avg_price', row.get('average_price'))))
            or 0.0
        )
        current_price = safe_float(row.get('price_eur', row.get('current_price')))

        category = str(row.get('category', row.get('style', 'mixte')) or 'mixte').strip().lower()
        if category not in ['value', 'croissance', 'cyclique', 'mixte']:
            category = 'mixte'

        positions.append({
            'ticker': ticker,
            'name': str(row.get('name', '') or '').strip() or None,
            'isin': str(row.get('isin', '') or '').strip() or None,
            'category': category,
            'shares': qty,
            'avg_price': avg_price,
            'current_price': current_price,
            'sector': str(row.get('sector', '') or '').strip() or None,
            'country': str(row.get('country', '') or '').strip() or None,
            'notes': str(row.get('notes', row.get('thesis', '')) or '').strip() or None,
        })

    return {
        'portfolio': positions,
        'cash': float(cash or 0.0),
        'currency': str(currency or 'EUR').upper(),
    }


def save_portfolio(df):
    """Save portfolio DataFrame to Excel"""
    try:
        df.to_excel(CONFIG['portfolio_file'], index=False)
        return True, None
    except Exception as e:
        return False, str(e)


def add_portfolio_position(ticker, name, qty, avg_cost):
    """Add a new position to the portfolio"""
    df, err = load_portfolio()
    if err:
        return False, err

    # Check if ticker already exists
    if ticker.upper() in df['ticker'].str.upper().values:
        return False, f"{ticker} already exists in portfolio"

    # Create new row
    new_row = {
        'ticker': ticker.upper(),
        'name': name,
        'qty': float(qty),
        'avg_cost_eur': float(avg_cost),
        'price_eur': 0,
        'sector': '',
        'country': ''
    }

    # Add to DataFrame
    df = pd.concat([df, pd.DataFrame([new_row])], ignore_index=True)

    # Save
    success, err = save_portfolio(df)
    return success, err


def edit_portfolio_position(ticker, qty, avg_cost):
    """Edit an existing position in the portfolio"""
    df, err = load_portfolio()
    if err:
        return False, err

    # Find the position
    mask = df['ticker'].str.upper() == ticker.upper()
    if not mask.any():
        return False, f"{ticker} not found in portfolio"

    # Update values
    df.loc[mask, 'qty'] = float(qty)
    df.loc[mask, 'avg_cost_eur'] = float(avg_cost)

    # Save
    success, err = save_portfolio(df)
    return success, err


def remove_portfolio_position(ticker):
    """Remove a position from the portfolio"""
    df, err = load_portfolio()
    if err:
        return False, err

    # Remove the position
    original_len = len(df)
    df = df[df['ticker'].str.upper() != ticker.upper()]

    if len(df) == original_len:
        return False, f"{ticker} not found in portfolio"

    # Save
    success, err = save_portfolio(df)
    return success, err


def safe_float(val):

    """Safely convert to float, return None if invalid"""

    if val is None:

        return None

    if isinstance(val, float) and math.isnan(val):

        return None

    try:

        return float(val)

    except Exception:
        return None



def update_portfolio(df):

    """Update portfolio with ALL yfinance data for Higgons scoring"""

    if not YFINANCE_OK:

        return df

    

    for i, row in df.iterrows():

        try:

            ticker = row['ticker']

            yf_ticker = get_yf_ticker(ticker)

            log_portfolio.info(f"Fetching {yf_ticker}...")

            

            t = yf.Ticker(yf_ticker)

            info = t.info

            

            # === BASIC INFO ===

            # Name

            if pd.isna(row.get('name')) or not str(row.get('name', '')).strip():

                name = info.get('shortName') or info.get('longName')

                if name: df.at[i, 'name'] = name

            

            # Sector & Country

            if pd.isna(row.get('sector')) or not str(row.get('sector', '')).strip():

                sector = info.get('sector')

                if sector: df.at[i, 'sector'] = sector

            

            if pd.isna(row.get('country')) or not str(row.get('country', '')).strip():

                country = info.get('country')

                if country: df.at[i, 'country'] = country

            

            # === PRICE DATA ===

            new_price = info.get('currentPrice') or info.get('regularMarketPrice')

            if new_price and new_price > 0:

                df.at[i, 'price_eur'] = new_price

            

            # === VALUATION METRICS ===

            pe = info.get('trailingPE')

            if pe and pe > 0: df.at[i, 'pe_ttm'] = pe

            

            # === PROFITABILITY ===

            roe = info.get('returnOnEquity')

            if roe is not None: df.at[i, 'roe_ttm'] = roe

            

            roa = info.get('returnOnAssets')

            if roa is not None: df.at[i, 'roa_ttm'] = roa

            

            gross_margin = info.get('grossMargins')

            if gross_margin is not None: df.at[i, 'gross_margin'] = gross_margin

            

            op_margin = info.get('operatingMargins')

            if op_margin is not None: df.at[i, 'operating_margin'] = op_margin

            

            # === FINANCIAL DATA ===

            revenue = info.get('totalRevenue')

            if revenue: df.at[i, 'revenue'] = revenue / 1e6  # Convert to millions

            

            ebitda = info.get('ebitda')

            if ebitda: df.at[i, 'ebitda'] = ebitda

            

            net_income = info.get('netIncomeToCommon')

            if net_income: df.at[i, 'net_income'] = net_income

            

            # === CASH FLOW ===

            op_cashflow = info.get('operatingCashflow')

            if op_cashflow: df.at[i, 'operating_cashflow'] = op_cashflow

            

            free_cashflow = info.get('freeCashflow')

            if free_cashflow: df.at[i, 'free_cashflow'] = free_cashflow

            

            # FCF Yield = Free Cash Flow / Market Cap

            market_cap = info.get('marketCap')

            if free_cashflow and market_cap and market_cap > 0:

                df.at[i, 'fcf_yield'] = free_cashflow / market_cap


            # P/CF = Market Cap / Operating Cash Flow (Price to Cash Flow ratio)
            # Lower is better - indicates company generates cash relative to its valuation
            if op_cashflow and market_cap and op_cashflow > 0:
                pcf = market_cap / op_cashflow
                df.at[i, 'pcf'] = pcf
                df.at[i, 'price_to_cashflow'] = pcf  # Alias for compatibility

            # FCF to Net Income ratio

            if free_cashflow and net_income and net_income != 0:

                df.at[i, 'fcf_to_net_income'] = free_cashflow / abs(net_income)

            

            # === BALANCE SHEET ===

            total_debt = info.get('totalDebt')

            if total_debt is not None: df.at[i, 'total_debt'] = total_debt

            

            total_cash = info.get('totalCash')

            if total_cash is not None: df.at[i, 'total_cash'] = total_cash

            

            total_assets = info.get('totalAssets')

            if total_assets: df.at[i, 'total_assets'] = total_assets

            

            current_ratio = info.get('currentRatio')

            if current_ratio: df.at[i, 'current_ratio'] = current_ratio

            

            # Debt to Equity

            debt_equity = info.get('debtToEquity')

            if debt_equity is not None: df.at[i, 'debt_to_equity'] = debt_equity / 100 if debt_equity > 10 else debt_equity

            

            # Equity Ratio = Total Equity / Total Assets

            total_equity = info.get('totalStockholderEquity')

            if total_equity and total_assets and total_assets > 0:

                df.at[i, 'equity_ratio'] = total_equity / total_assets

            

            # Net Debt to EBITDA

            if total_debt is not None and total_cash is not None and ebitda and ebitda > 0:

                net_debt = total_debt - total_cash

                df.at[i, 'net_debt_to_ebitda'] = net_debt / ebitda

            

            # === SHARES ===

            shares = info.get('sharesOutstanding')

            if shares: df.at[i, 'shares_outstanding'] = shares

            

            # === MOMENTUM (52 week) ===

            high_52w = info.get('fiftyTwoWeekHigh')

            low_52w = info.get('fiftyTwoWeekLow')

            if new_price and high_52w and low_52w:

                # Momentum = where price is in 52w range (-1 to +1)

                if high_52w != low_52w:

                    momentum = (new_price - low_52w) / (high_52w - low_52w) * 2 - 1

                    df.at[i, 'momentum_12m'] = momentum

            

        except Exception as e:

            log_portfolio.error(f"Error {ticker}: {e}")

    

    # === CALCULATE HIGGONS SCORE ===

    df = calc_higgons_score(df)

    

    df.to_excel(CONFIG['portfolio_file'], index=False)

    log_portfolio.info("Portfolio saved!")

    return df





def calc_higgons_score(df):

    """Calculate Higgons score and verdict for each position - Updated logic"""

    for i, row in df.iterrows():

        try:

            pe = safe_float(row.get('pe_ttm')) or 0

            roe = safe_float(row.get('roe_ttm')) or 0

            debt_equity = safe_float(row.get('debt_to_equity')) or 0

            net_debt_ebitda = safe_float(row.get('net_debt_to_ebitda')) or 0

            fcf_yield = safe_float(row.get('fcf_yield')) or 0

            equity_ratio = safe_float(row.get('equity_ratio')) or 0

            momentum = safe_float(row.get('momentum_12m')) or 0

            

            # === HIGGONS GATES ===

            # 1. Profitable Required: PE > 0 and ROE > 0

            profitable = 1 if (pe > 0 and roe > 0) else 0

            df.at[i, 'higgins_profitable_required'] = profitable

            

            # 2. Quality Gate: ROE >= 10%

            quality = 1 if roe >= 0.10 else 0

            df.at[i, 'higgins_quality_gate_pass'] = quality

            

            # 3. Value Gate: PE <= 15 (assoupli)

            value = 1 if (pe > 0 and pe <= 15) else 0

            df.at[i, 'higgins_value_gate_pass'] = value

            

            # 4. Leverage Gate: Net Debt/EBITDA <= 3 or Equity Ratio >= 30%

            leverage = 1 if (net_debt_ebitda <= 3 or equity_ratio >= 0.30) else 0

            df.at[i, 'higgins_leverage_gate_pass'] = leverage

            

            # === HIGGONS SCORE (0-100) ===

            score = 0

            

            # PE Score (0-35 points) - UPDATED

            if pe > 0:

                if pe < 7: score += 35      # Parfait

                elif pe < 10: score += 30   # Top

                elif pe < 12: score += 25   # Bon

                elif pe < 15: score += 15   # Acceptable

                elif pe < 20: score += 5    # Cher

                # > 20 = 0 points (Tres cher)

            

            # ROE Score (0-30 points)

            if roe > 0:

                if roe >= 0.25: score += 30

                elif roe >= 0.20: score += 25

                elif roe >= 0.15: score += 20

                elif roe >= 0.12: score += 15

                elif roe >= 0.10: score += 10

                elif roe >= 0.05: score += 5

            

            # Leverage Score (0-20 points)

            if net_debt_ebitda <= 0: score += 20  # Net cash

            elif net_debt_ebitda <= 1: score += 15

            elif net_debt_ebitda <= 2: score += 10

            elif net_debt_ebitda <= 3: score += 5

            

            # FCF Yield Score (0-10 points)

            if fcf_yield >= 0.10: score += 10

            elif fcf_yield >= 0.05: score += 5

            

            # Equity Ratio Score (0-5 points)

            if equity_ratio >= 0.50: score += 5

            elif equity_ratio >= 0.30: score += 3

            

            df.at[i, 'score_higgins_wo_mom'] = score / 100

            

            # Add momentum adjustment (-10 to +10 points)

            mom_adj = momentum * 10  # -10 to +10

            final_score = (score + mom_adj) / 100

            df.at[i, 'score_higgins'] = max(0, min(1, final_score))

            

            # === CLASSIFY - UPDATED LOGIC ===

            

            # Deep Value Higgons: PE <= 12 and ROE >= 10% and all gates pass

            is_deep_value = 'Oui' if (pe > 0 and pe <= 12 and roe >= 0.10 and profitable and quality and leverage) else 'Non'

            df.at[i, 'is_deep_value_higgins'] = is_deep_value

            

            # Compounder on Sale: ROE >= 15% and PE <= 15

            is_compounder = 'Oui' if (roe >= 0.15 and pe > 0 and pe <= 15) else 'Non'

            df.at[i, 'is_compounder_on_sale'] = is_compounder

            

            # Quality Value (new): PE <= 15 and ROE >= 12%

            is_quality_value = (pe > 0 and pe <= 15 and roe >= 0.12)

            

            # === VERDICT - ALWAYS RECALCULATE ===

            # ACHAT: Deep Value OR Compounder OR (PE < 10 + ROE > 12%)

            if is_deep_value == 'Oui' or is_compounder == 'Oui' or (pe > 0 and pe < 10 and roe >= 0.12):

                verdict = 'Achat'

            

            # SURVEILLANCE: PE <= 15 + ROE >= 10% + profitable

            elif profitable and quality and value:

                verdict = 'Surveillance'

            

            # NEUTRE: Score > 40% but doesn't pass criteria

            elif final_score > 0.40:

                verdict = 'Neutre'

            

            # ECARTER: PE > 20 OR ROE < 5% OR score < 30%

            elif (pe > 20) or (roe > 0 and roe < 0.05) or final_score < 0.30:

                verdict = 'Ecarter'

            

            else:

                verdict = 'Neutre'

            

            df.at[i, 'verdict'] = verdict

            

        except Exception as e:

            log_portfolio.error(f"Error calculating Higgons for row {i}: {e}")

    

    return df



def calc_scores(df):

    """Calculate scores - but use existing 'verdict' column for signal"""

    for i, row in df.iterrows():

        try:

            pe = safe_float(row.get('pe_ttm')) or 0

            roe = safe_float(row.get('roe_ttm')) or 0

            

            # Calculate score for sorting/ranking

            sc = 50

            if pe > 0:

                if pe < 8: sc += 30

                elif pe < 12: sc += 20

                elif pe < 15: sc += 10

                elif pe > 25: sc -= 20

            if roe > 0:

                if roe > 0.20: sc += 20

                elif roe > 0.15: sc += 15

                elif roe > 0.10: sc += 10

            df.at[i, 'score'] = sc

            

            # Use existing verdict column if available, otherwise calculate

            verdict = row.get('verdict', '')

            if verdict and str(verdict).strip():

                df.at[i, 'signal'] = str(verdict).strip()

            else:

                # Fallback calculation only if no verdict

                df.at[i, 'signal'] = 'BUY' if (pe > 0 and pe <= 10 and roe >= 0.10) else ('HOLD' if pe <= 15 else 'SELL')

        except Exception:
            df.at[i, 'score'] = 50

            df.at[i, 'signal'] = row.get('verdict', 'HOLD')

    return df



def load_cache(cache_key='default'):

    """Load cache for a specific key (e.g., 'france_standard', 'europe_standard')"""

    cache_file = CONFIG['screener_cache_file'].replace('.json', f'_{cache_key}.json')

    c = load_json(cache_file, {'date': None, 'data': []})

    if c.get('date'):

        try:

            if (datetime.now() - datetime.strptime(c['date'], '%Y-%m-%d')).days < CONFIG['cache_days']:

                return c['data']

        except Exception:
            pass

    return None



def save_cache(data, cache_key='default'):

    """Save cache for a specific key"""

    cache_file = CONFIG['screener_cache_file'].replace('.json', f'_{cache_key}.json')

    save_json(cache_file, {'date': datetime.now().strftime('%Y-%m-%d'), 'data': data})



def run_screener(force=False, scope='france', use_eod=True, mode='standard'):

    """

    Run the screener on the full universe

    

    Priority:

    1. EOD Historical Data (if API configured or cached data available)

    2. Yahoo Finance (fallback)

    

    scope: 'france', 'europe', or 'legacy' (original 52 stocks)

    mode: 'standard' or 'ai_optimal' (strict criteria from AI optimization)

    """

    

    # AI Optimal criteria (from optimization results)

    AI_OPTIMAL_CRITERIA = {

        'pe_max': 8,

        'roe_min': 12,  # percentage

        'debt_equity_max': 50,  # percentage

        'max_positions': 18

    }

    

    # Check cache first (unless force refresh)

    cache_key = f"{scope}_{mode}"

    if not force:

        c = load_cache(cache_key)

        if c:

            log_screener.info(f"Using cached data for {cache_key}")

            # If AI optimal mode, filter cached results

            if mode == 'ai_optimal':

                return filter_ai_optimal(c, AI_OPTIMAL_CRITERIA)

            return c



    results = []



    # Determine which data source to use

    use_eod_data = use_eod and (EOD_OK or has_eod_cache())



    if use_eod_data and scope in ['france', 'europe']:

        # Use EOD data - scan full universe

        log_screener.info(f"Using EOD data for {scope} universe...")

        results = run_screener_eod(scope)

    else:

        # Fallback to Yahoo Finance with legacy database

        log_screener.info("Using Yahoo Finance with legacy database...")

        results = run_screener_yahoo()



    if results:

        save_cache(results, cache_key)

        log_screener.info(f"Saved {len(results)} results to cache {cache_key}")

    

    # Apply AI optimal filter if requested

    if mode == 'ai_optimal':

        results = filter_ai_optimal(results, AI_OPTIMAL_CRITERIA)

    

    return results





def filter_ai_optimal(results, criteria):

    """Filter results according to AI optimal criteria"""

    filtered = []

    

    for r in results:

        pe = r.get('pe')

        roe = r.get('roe')

        debt_eq = r.get('debt_equity')

        

        # Convert ROE to percentage if needed

        if roe and roe < 1:

            roe_pct = roe * 100

        else:

            roe_pct = roe or 0

        

        # Convert debt_equity to percentage if needed

        if debt_eq and debt_eq < 5:

            debt_pct = debt_eq * 100

        else:

            debt_pct = debt_eq or 0

        

        # Apply strict AI optimal criteria

        if pe and pe <= criteria['pe_max']:

            if roe_pct >= criteria['roe_min']:

                if debt_pct <= criteria['debt_equity_max']:

                    # Mark as AI OPTIMAL

                    r['signal'] = 'AI BUY'

                    filtered.append(r)

    

    # Sort by score and take top N

    filtered.sort(key=lambda x: x.get('score', 0), reverse=True)

    top_n = filtered[:criteria['max_positions']]

    

    # Re-rank within top N

    for i, r in enumerate(top_n):

        r['ai_rank'] = i + 1

    

    log_screener.info(f"AI Optimal: {len(top_n)} stocks match criteria (from {len(results)} scanned)")

    

    return top_n





def has_eod_cache():

    """Check if we have EOD cache data available"""

    fund_path = os.path.join(CACHE_DIR, 'fundamentals')

    if os.path.exists(fund_path):

        files = [f for f in os.listdir(fund_path) if f.endswith('.json')]

        return len(files) > 20  # At least 20 cached stocks

    return False





def safe_float(value, default=None):

    """Safely convert a value to float"""

    if value is None:

        return default

    try:

        return float(value)

    except (ValueError, TypeError):

        return default





def run_screener_eod(scope='france'):

    """Run screener using EOD Historical Data"""

    results = []

    

    # Get universe

    if scope == 'europe':

        exchanges = ['PA', 'AS', 'BR', 'MI', 'MC', 'XETRA']

    else:

        exchanges = ['PA']

    

    # Load tickers from universe cache or API

    all_tickers = []

    for exchange in exchanges:

        tickers = load_universe_from_eod(exchange)

        all_tickers.extend(tickers)

    

    # If no tickers loaded, try from fundamentals cache

    if not all_tickers:

        fund_path = os.path.join(CACHE_DIR, 'fundamentals')

        if os.path.exists(fund_path):

            for f in os.listdir(fund_path):

                if f.endswith('.json'):

                    ticker = f.replace('.json', '').replace('_', '.')

                    all_tickers.append({'ticker': ticker, 'name': '', 'exchange': ''})

    

    log_screener.info(f"Scanning {len(all_tickers)} tickers...")



    # Limit based on scope to avoid too long processing

    # France: 300 tickers (Euronext Paris)

    # Europe: 1000 tickers (6 exchanges)

    processed = 0

    max_tickers = 1000 if scope == 'europe' else 300



    log_screener.info(f"Processing up to {max_tickers} tickers for {scope}...")



    for stock in all_tickers:

        if processed >= max_tickers:

            log_screener.info(f"Reached limit of {max_tickers} tickers")

            break

            

        ticker = stock['ticker']

        

        # Get fundamentals from cache or API

        fund, err = eod_get_fundamentals(ticker, use_cache=True)

        if not fund or err:

            continue

        

        try:

            # Extract data

            general = fund.get('General', {})

            highlights = fund.get('Highlights', {})

            valuation = fund.get('Valuation', {})

            

            # Get latest financials

            financials = fund.get('Financials', {})

            income = financials.get('Income_Statement', {}).get('yearly', {})

            balance = financials.get('Balance_Sheet', {}).get('yearly', {})

            

            # Get most recent year data

            latest_year = None

            if income:

                years = sorted(income.keys(), reverse=True)

                if years:

                    latest_year = years[0]

            

            # Extract metrics with safe conversion

            pe = safe_float(highlights.get('PERatio')) or safe_float(valuation.get('TrailingPE'))

            roe = safe_float(highlights.get('ReturnOnEquityTTM'))

            profit_margin = safe_float(highlights.get('ProfitMargin'))

            

            # Get debt/equity from balance sheet

            debt_equity = None

            if latest_year and latest_year in balance:

                bs = balance[latest_year]

                total_debt = safe_float(bs.get('shortLongTermDebtTotal')) or safe_float(bs.get('longTermDebt')) or 0

                equity = safe_float(bs.get('totalStockholderEquity')) or safe_float(bs.get('totalEquity'))

                if equity and equity > 0:

                    debt_equity = total_debt / equity

            

            # Get current price and market cap

            market_cap = safe_float(highlights.get('MarketCapitalization'))

            price = None

            if market_cap:

                shares = safe_float(general.get('SharesOutstanding'))

                if shares and shares > 0:

                    price = market_cap / shares



            # Calculate 12-month momentum

            momentum_12m = None

            try:

                end_date = datetime.now().strftime('%Y-%m-%d')

                start_date = (datetime.now() - timedelta(days=380)).strftime('%Y-%m-%d')

                prices, err = eod_get_historical_prices(ticker, start_date, end_date, use_cache=True)



                if prices and len(prices) >= 2:

                    # Get oldest and newest price

                    oldest_price = safe_float(prices[0].get('close'))

                    newest_price = safe_float(prices[-1].get('close'))



                    if oldest_price and oldest_price > 0 and newest_price:

                        momentum_12m = (newest_price - oldest_price) / oldest_price

            except Exception:
                pass  # If momentum calculation fails, leave it as None



            # Calculate Higgons score

            score = calculate_higgons_score_for_screener(pe, roe, debt_equity, profit_margin)



            # Determine signal

            signal = determine_signal(pe, roe, score)



            # Determine country from exchange

            exchange = general.get('Exchange', stock.get('exchange', ''))

            country = get_country_from_exchange(exchange)



            results.append({

                'ticker': ticker,

                'name': general.get('Name', stock.get('name', ticker)),

                'country': country,

                'sector': general.get('Sector', 'Unknown'),

                'price': price,

                'market_cap': market_cap,

                'pe': pe,

                'roe': roe,

                'debt_equity': debt_equity,

                'profit_margin': profit_margin,

                'momentum_12m': momentum_12m,

                'score': score,

                'signal': signal,

                'source': 'EOD'

            })



            processed += 1



            # Debug log for first few tickers

            if processed <= 3:

                log_screener.debug(f"{ticker}: market_cap={market_cap}, momentum_12m={momentum_12m}")



            if processed % 50 == 0:

                log_screener.info(f"Processed {processed} tickers...")

                

        except Exception as e:

            log_screener.error(f"Error processing {ticker}: {e}")

            continue

    

    # Sort by score

    results.sort(key=lambda x: x.get('score', 0), reverse=True)

    

    log_screener.info(f"Found {len(results)} stocks with valid data")

    return results





def run_screener_yahoo():

    """Run screener using Yahoo Finance (legacy method)"""

    if not YFINANCE_OK:

        return []



    results = []

    for s in EUROPE_DB:

        r = s.copy()

        try:

            ticker_obj = yf.Ticker(s['ticker'])

            info = ticker_obj.info

            r['price'] = info.get('currentPrice') or info.get('regularMarketPrice')

            r['market_cap'] = info.get('marketCap')

            r['pe'] = info.get('trailingPE')

            r['roe'] = info.get('returnOnEquity')

            r['debt_equity'] = info.get('debtToEquity')

            if r['debt_equity']:

                r['debt_equity'] = r['debt_equity'] / 100  # Yahoo returns as percentage

            r['profit_margin'] = info.get('profitMargins')



            # Calculate 12-month momentum

            try:

                hist = ticker_obj.history(period='1y')

                if len(hist) >= 2:

                    oldest_price = hist['Close'].iloc[0]

                    newest_price = hist['Close'].iloc[-1]

                    if oldest_price > 0:

                        r['momentum_12m'] = (newest_price - oldest_price) / oldest_price

                    else:

                        r['momentum_12m'] = None

                else:

                    r['momentum_12m'] = None

            except Exception:
                r['momentum_12m'] = None



            r['score'] = calculate_higgons_score_for_screener(r['pe'], r['roe'], r['debt_equity'], r['profit_margin'])

            r['signal'] = determine_signal(r['pe'], r['roe'], r['score'])

            r['source'] = 'Yahoo'

        except Exception:
            r['score'] = 0

            r['signal'] = 'NEUTRE'

            r['source'] = 'Yahoo'

            r['market_cap'] = None

            r['momentum_12m'] = None

        results.append(r)



    results.sort(key=lambda x: x.get('score', 0), reverse=True)

    return results





def refresh_screener_data_background(scope='france'):

    """Refresh screener data in background by forcing API calls"""

    global REFRESH_STATUS



    REFRESH_STATUS['running'] = True

    REFRESH_STATUS['progress'] = 0

    REFRESH_STATUS['message'] = 'Initializing...'



    try:

        # Get universe

        if scope == 'europe':

            exchanges = ['PA', 'AS', 'BR', 'MI', 'MC', 'XETRA']

        else:

            exchanges = ['PA']



        # Load tickers from universe cache

        all_tickers = []

        for exchange in exchanges:

            tickers = load_universe_from_eod(exchange)

            all_tickers.extend(tickers)



        log_cache.info(f"REFRESH: Total universe: {len(all_tickers)} tickers for {scope}")



        # Filter tickers that need refresh (older than 7 days)

        tickers_to_refresh = []

        skipped = 0



        for stock in all_tickers:

            ticker = stock['ticker']



            # Check if fundamentals are fresh (< 7 days old)

            fund_cache_file = get_cache_path('fundamentals', ticker)

            needs_refresh = True



            if os.path.exists(fund_cache_file):

                try:

                    if is_cache_valid(fund_cache_file, 7):  # 7 days

                        needs_refresh = False

                        skipped += 1

                except Exception:
                    pass



            if needs_refresh:

                tickers_to_refresh.append(stock)



        log_cache.info(f"REFRESH: {len(tickers_to_refresh)} tickers need refresh, {skipped} already up-to-date")



        # Limit to reasonable number for Europe (500 max)

        max_refresh = 500 if scope == 'europe' else 300

        tickers_to_refresh = tickers_to_refresh[:max_refresh]



        REFRESH_STATUS['total'] = len(tickers_to_refresh)

        REFRESH_STATUS['message'] = f'Refreshing {len(tickers_to_refresh)} tickers ({skipped} skipped)...'



        log_cache.info(f"REFRESH: Starting PARALLEL refresh of {len(tickers_to_refresh)} tickers...")

        # Use ParallelAPIClient for faster fetching (10 workers, rate limited to 5/s for EOD API)
        client = ParallelAPIClient(max_workers=10, rate_limit=5.0)

        # Extract ticker strings for batch operations
        ticker_list = [stock['ticker'] for stock in tickers_to_refresh]

        # Batch fetch fundamentals in parallel
        REFRESH_STATUS['message'] = f'Fetching fundamentals ({len(ticker_list)} tickers)...'
        log_cache.info("REFRESH: Fetching fundamentals in parallel...")

        fund_results = client.fetch_fundamentals_batch(
            tickers=ticker_list,
            fetch_func=eod_get_fundamentals,
            use_cache=True,
            force_refresh=True
        )

        successful_funds = sum(1 for r in fund_results.values() if r.success)
        REFRESH_STATUS['progress'] = len(ticker_list) // 2  # 50% progress after fundamentals
        log_cache.info(f"REFRESH: Fundamentals complete: {successful_funds}/{len(ticker_list)} successful")

        # Batch fetch prices in parallel
        if REFRESH_STATUS['running']:
            REFRESH_STATUS['message'] = f'Fetching prices ({len(ticker_list)} tickers)...'
            log_cache.info("REFRESH: Fetching prices in parallel...")

            end_date = datetime.now().strftime('%Y-%m-%d')
            start_date = (datetime.now() - timedelta(days=380)).strftime('%Y-%m-%d')

            price_results = client.fetch_prices_batch(
                tickers=ticker_list,
                start_date=start_date,
                end_date=end_date,
                fetch_func=eod_get_historical_prices,
                use_cache=True
            )

            successful_prices = sum(1 for r in price_results.values() if r.success)
            REFRESH_STATUS['progress'] = len(ticker_list)  # 100% progress
            log_cache.info(f"REFRESH: Prices complete: {successful_prices}/{len(ticker_list)} successful")



        REFRESH_STATUS['message'] = 'Refresh complete! Running screener...'



        # Delete old screener caches to force full regeneration

        cache_base = CONFIG['screener_cache_file'].replace('.json', '')

        for cache_suffix in ['_default.json', f'_{scope}_standard.json', f'_{scope}_ai_optimal.json']:

            cache_file = cache_base + cache_suffix

            if os.path.exists(cache_file):

                os.remove(cache_file)

                log_cache.info(f"REFRESH: Deleted cache: {os.path.basename(cache_file)}")



        # Re-run screener to update cache

        log_cache.info("REFRESH: Regenerating screener cache with new data...")

        run_screener(force=True, scope=scope, mode='standard')



        REFRESH_STATUS['message'] = 'Done!'

        log_cache.info("REFRESH: Background refresh completed!")



    except Exception as e:

        REFRESH_STATUS['message'] = f'Error: {str(e)}'

        log_cache.error(f"REFRESH: Error during background refresh: {e}")

    finally:

        REFRESH_STATUS['running'] = False





def calculate_higgons_score_for_screener(pe: Optional[float], roe: Optional[float], debt_equity: Optional[float], profit_margin: Optional[float]) -> int:

    """Calculate Higgons-style score for screener"""

    score = 0

    

    # PE Score (0-35 points) - lower is better

    if pe and pe > 0:

        if pe < 7: score += 35

        elif pe < 10: score += 30

        elif pe < 12: score += 25

        elif pe < 15: score += 15

        elif pe < 20: score += 5

    

    # ROE Score (0-30 points) - higher is better

    if roe and roe > 0:

        roe_pct = roe if roe < 1 else roe / 100  # Handle both 0.15 and 15 formats

        if roe_pct >= 0.25: score += 30

        elif roe_pct >= 0.20: score += 25

        elif roe_pct >= 0.15: score += 20

        elif roe_pct >= 0.12: score += 15

        elif roe_pct >= 0.10: score += 10

    

    # Debt/Equity Score (0-20 points) - lower is better

    if debt_equity is not None:

        if debt_equity <= 0: score += 20  # Net cash

        elif debt_equity <= 0.3: score += 15

        elif debt_equity <= 0.5: score += 10

        elif debt_equity <= 1.0: score += 5

    

    # Profit Margin Score (0-15 points) - higher is better

    if profit_margin and profit_margin > 0:

        pm = profit_margin if profit_margin < 1 else profit_margin / 100

        if pm >= 0.15: score += 15

        elif pm >= 0.10: score += 10

        elif pm >= 0.05: score += 5

    

    return score





def determine_signal(pe, roe, score):

    """Determine investment signal based on criteria"""

    if pe and roe:

        roe_val = roe if roe < 1 else roe / 100

        

        # ACHAT: PE <= 12 AND ROE >= 10% AND score >= 50

        if pe <= 12 and roe_val >= 0.10 and score >= 50:

            return 'ACHAT'

        

        # WATCH: PE <= 15 AND ROE >= 8%

        if pe <= 15 and roe_val >= 0.08:

            return 'WATCH'

        

        # CHER: PE > 20 OR ROE < 5%

        if pe > 20 or roe_val < 0.05:

            return 'CHER'

    

    return 'NEUTRE'





def get_country_from_exchange(exchange):

    """Get country code from exchange"""

    exchange_map = {

        'PA': 'FR', 'XPAR': 'FR', 'Paris': 'FR',

        'AS': 'NL', 'XAMS': 'NL', 'Amsterdam': 'NL',

        'BR': 'BE', 'XBRU': 'BE', 'Brussels': 'BE',

        'MI': 'IT', 'XMIL': 'IT', 'Milan': 'IT',

        'MC': 'ES', 'XMAD': 'ES', 'Madrid': 'ES',

        'XETRA': 'DE', 'XFRA': 'DE', 'Frankfurt': 'DE',

        'LSE': 'UK', 'XLON': 'UK', 'London': 'UK',

        'SW': 'CH', 'XSWX': 'CH', 'Swiss': 'CH',

        'VI': 'AT', 'XWBO': 'AT', 'Vienna': 'AT',

        'HE': 'FI', 'XHEL': 'FI', 'Helsinki': 'FI',

        'ST': 'SE', 'XSTO': 'SE', 'Stockholm': 'SE',

        'OL': 'NO', 'XOSL': 'NO', 'Oslo': 'NO',

        'CO': 'DK', 'XCSE': 'DK', 'Copenhagen': 'DK',

        'LS': 'PT', 'XLIS': 'PT', 'Lisbon': 'PT',

        'AT': 'GR', 'XATH': 'GR', 'Athens': 'GR',

    }

    

    for key, country in exchange_map.items():

        if key.lower() in exchange.lower():

            return country

    

    return 'EU'



def get_security_data(ticker: str) -> Dict[str, Any]:

    """Get detailed security data for the detail page"""

    data = {'ticker': ticker, 'name': '', 'sector': '', 'country': '', 'price': 0, 'change': 0, 'change_pct': 0,

            'pe': None, 'forward_pe': None, 'roe': None, 'market_cap': None, 'dividend_yield': None, 'beta': None,

            'high_52w': None, 'low_52w': None, 'volume': None, 'avg_volume': None, 'eps': None, 'revenue': None,

            'profit_margin': None, 'debt_equity': None, 'current_ratio': None, 'book_value': None, 'target_price': None,

            'description': '', 'industry': '', 'website': '', 'employees': None, 'memo_file': None, 'memo_content': None,

            'price_history': [], 'volume_history': []}

    

    # Find in DB (try with and without .PA)

    for s in EUROPE_DB:

        if s['ticker'] == ticker or s['ticker'] == ticker + '.PA' or s['ticker'].replace('.PA', '') == ticker:

            data.update({k: s[k] for k in ['name', 'sector', 'country']})

            break

    

    # Find memo file and read content

    data['memo_file'] = find_memo(ticker)

    if data['memo_file']:

        data['memo_content'] = read_memo_content(data['memo_file'])

    

    if YFINANCE_OK:

        try:

            yf_ticker = get_yf_ticker(ticker)

            info = yf.Ticker(yf_ticker).info

            data.update({

                'name': info.get('shortName') or info.get('longName') or data['name'],

                'price': info.get('currentPrice') or info.get('regularMarketPrice') or 0,

                'change': info.get('regularMarketChange') or 0,

                'change_pct': info.get('regularMarketChangePercent') or 0,

                'pe': info.get('trailingPE'), 'forward_pe': info.get('forwardPE'),

                'roe': info.get('returnOnEquity'), 'market_cap': info.get('marketCap'),

                'dividend_yield': info.get('dividendYield'), 'beta': info.get('beta'),

                'high_52w': info.get('fiftyTwoWeekHigh'), 'low_52w': info.get('fiftyTwoWeekLow'),

                'volume': info.get('volume'), 'avg_volume': info.get('averageVolume'),

                'eps': info.get('trailingEps'), 'revenue': info.get('totalRevenue'),

                'profit_margin': info.get('profitMargins'), 'debt_equity': info.get('debtToEquity'),

                'current_ratio': info.get('currentRatio'), 'book_value': info.get('bookValue'),

                'target_price': info.get('targetMeanPrice'),

                'description': info.get('longBusinessSummary') or '',

                'sector': info.get('sector') or data['sector'],

                'industry': info.get('industry') or '',

                'website': info.get('website') or '',

                'employees': info.get('fullTimeEmployees')

            })

            

            # Get price history (1 year)

            try:

                t = yf.Ticker(yf_ticker)

                hist = t.history(period="1y")

                if not hist.empty:

                    data['price_history'] = [

                        {'date': d.strftime('%Y-%m-%d'), 'close': round(row['Close'], 2), 'volume': int(row['Volume'])}

                        for d, row in hist.iterrows()

                    ]

            except Exception as e:

                log_api.error(f"Error fetching history for {ticker}: {e}")

                

        except Exception as e:

            log_api.error(f"Error fetching {ticker}: {e}")

    return data



BLOOMBERG_CSS = '''

@import url('https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&display=swap');

*{margin:0;padding:0;box-sizing:border-box}

body{font-family:'JetBrains Mono',Consolas,monospace;background:#000;color:#ff9500;font-size:12px}

.bb-top{background:linear-gradient(180deg,#1a1a1a,#0d0d0d);padding:4px 12px;display:flex;justify-content:space-between;align-items:center;border-bottom:2px solid #ff9500}

.bb-logo{display:flex;align-items:center;gap:12px}

.bb-logo svg{width:24px;height:24px}

.bb-logo h1{font-size:14px;font-weight:700;color:#ff9500;letter-spacing:2px}

.bb-logo span{color:#666;font-size:10px;margin-left:8px}

.bb-time{color:#00ff00;font-size:11px;font-weight:600}

.bb-cmd{background:#000;border:1px solid #333;color:#ff9500;padding:4px 8px;font-family:inherit;font-size:11px;width:300px}

.bb-cmd:focus{outline:none;border-color:#ff9500}

.bb-fkeys{background:#1a1a1a;padding:2px 8px;display:flex;gap:4px;border-bottom:1px solid #333}

.fkey{background:#333;color:#fff;padding:2px 6px;font-size:9px;border:none;cursor:pointer}

.fkey:hover,.fkey.active{background:#ff9500;color:#000}

.bb-tabs{background:#0d0d0d;display:flex;border-bottom:1px solid #333}

.bb-tab{padding:8px 20px;cursor:pointer;color:#888;font-size:11px;text-transform:uppercase;letter-spacing:1px;border-right:1px solid #222;position:relative}

.bb-tab:hover{color:#ff9500;background:#111}

.bb-tab.active{color:#ff9500;background:#000}

.bb-tab.active::after{content:'';position:absolute;bottom:-1px;left:0;right:0;height:2px;background:#ff9500}

.bb-badge{background:#ff9500;color:#000;padding:1px 6px;font-size:9px;font-weight:700;margin-left:6px}

.bb-badge-g{background:#00ff00}

.tc{display:none}.tc.active{display:block}

.bb-kpis{background:#0a0a0a;padding:8px 12px;display:flex;gap:24px;border-bottom:1px solid #222}

.bb-kpi{display:flex;align-items:baseline;gap:8px}

.bb-kpi-label{color:#666;font-size:10px;text-transform:uppercase}

.bb-kpi-val{font-size:16px;font-weight:700;color:#00ff00}

.bb-kpi-val.down{color:#ff3b30}

.bb-kpi-chg{font-size:11px}.bb-kpi-chg.up{color:#00ff00}.bb-kpi-chg.down{color:#ff3b30}

.bb-panel{border:1px solid #333;margin:8px;background:#0a0a0a}

.bb-panel-hdr{background:linear-gradient(180deg,#1a1a1a,#111);padding:6px 10px;border-bottom:1px solid #333;display:flex;justify-content:space-between}

.bb-panel-title{color:#ff9500;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:1px}

.bb-panel-sub{color:#666;font-size:10px}

.bb-tbl{overflow:auto;max-height:420px}

table{width:100%;border-collapse:collapse;table-layout:fixed}

th,td{padding:6px 8px;font-size:11px;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}

th{background:#1a1a1a;text-align:left;font-size:9px;color:#ff9500;text-transform:uppercase;letter-spacing:1px;position:sticky;top:0;border-bottom:1px solid #ff9500}

th.sortable{cursor:pointer;user-select:none;transition:background 0.2s}

th.sortable:hover{background:#252525;color:#fff}

th.sortable::after{content:'';display:inline-block;margin-left:6px;opacity:0.3}

th.sortable.asc::after{content:'â–²';opacity:1}

th.sortable.desc::after{content:'â–¼';opacity:1}

td{border-bottom:1px solid #1a1a1a;color:#ccc}

tr:hover{background:#111}tr:hover td{color:#fff}

/* Column widths for Holdings table */

.col-ticker{width:10%}

.col-name{width:14%}

.col-qty{width:6%;text-align:right}

.col-last{width:8%;text-align:right}

.col-mktval{width:10%;text-align:right}

.col-weight{width:8%;text-align:right}

.col-chg{width:9%;text-align:right}

.col-pe{width:7%;text-align:right}

.col-roe{width:7%;text-align:right}

.col-signal{width:9%;text-align:center}

/* Align data cells */

.r{text-align:right}

.c{text-align:center}

.tk{color:#00bfff;font-weight:600;text-decoration:none}.tk:hover{color:#fff;text-decoration:underline}

.nm{color:#fff}

.pos{color:#00ff00}.neg{color:#ff3b30}

.wgt{color:#ff9500;font-weight:500}

.sig{padding:2px 6px;font-size:9px;font-weight:700}

.sig-buy,.sig-achat{background:#00ff00;color:#000}

.sig-sell,.sig-ecarter{background:#ff3b30;color:#fff}

.sig-hold,.sig-neutre{background:#ff9500;color:#000}

.sig-watch,.sig-surveillance{background:#333;color:#00bfff;border:1px solid #00bfff}

.bb-btn{background:#333;border:1px solid #555;color:#ff9500;padding:4px 12px;font-family:inherit;font-size:10px;cursor:pointer;text-transform:uppercase;text-decoration:none;display:inline-block}

.bb-btn:hover{background:#ff9500;color:#000}

.bb-btn-g{background:#00ff00;color:#000}

.bb-btn-r{background:#ff3b30;color:#fff;padding:2px 6px}

.btn-edit,.btn-del{background:transparent;border:none;cursor:pointer;padding:2px 4px;font-size:12px;opacity:0.6}
.btn-edit:hover,.btn-del:hover{opacity:1}
.btn-del:hover{color:#ff3b30}

.pf-modal-overlay{position:fixed;top:0;left:0;right:0;bottom:0;background:rgba(0,0,0,0.8);display:none;justify-content:center;align-items:center;z-index:9999}
.pf-modal{background:#1a1a1a;border:1px solid #ff9500;padding:20px;min-width:320px;max-width:400px}
.pf-modal h3{color:#ff9500;margin:0 0 16px 0;font-size:14px;text-transform:uppercase;letter-spacing:2px}
.pf-modal-row{margin-bottom:12px}
.pf-modal-row label{display:block;color:#888;font-size:10px;text-transform:uppercase;margin-bottom:4px}
.pf-modal-row input{width:100%;background:#000;border:1px solid #333;color:#fff;padding:8px;font-family:inherit;font-size:12px;box-sizing:border-box}
.pf-modal-row input:focus{border-color:#ff9500;outline:none}
.pf-modal-btns{display:flex;gap:10px;margin-top:16px}
.pf-modal-btns button{flex:1;padding:8px;font-family:inherit;font-size:11px;text-transform:uppercase;cursor:pointer;border:1px solid #333}
.pf-modal-btns .btn-save{background:#00ff00;color:#000;border-color:#00ff00}
.pf-modal-btns .btn-cancel{background:#333;color:#fff}

.bb-scr-hdr{background:#0d0d0d;padding:10px 12px;display:flex;justify-content:space-between;border-bottom:1px solid #333}

.bb-scr-stats{display:flex;gap:20px}

.bb-scr-stat span{color:#666;font-size:10px;text-transform:uppercase}

.bb-scr-stat b{color:#00ff00;font-size:14px;margin-left:6px}

.bb-filters{background:#111;padding:8px 12px;display:flex;gap:16px;border-bottom:1px solid #222}

.bb-filter label{color:#666;font-size:9px;text-transform:uppercase;margin-right:6px}

.bb-filter select,.bb-filter input{background:#000;border:1px solid #333;color:#ff9500;padding:4px 8px;font-family:inherit;font-size:11px}

.bb-status{background:#111;padding:4px 12px;display:flex;justify-content:space-between;border-top:1px solid #333;position:fixed;bottom:0;left:0;right:0}

.bb-status-l{color:#666;font-size:9px}.bb-status-r{color:#00ff00;font-size:9px}

@keyframes blink{0%,50%{opacity:1}51%,100%{opacity:0}}.blink{animation:blink 1s infinite}

.bb-detail{padding:8px 8px 60px}

.bb-detail-header{background:#0a0a0a;border:1px solid #333;padding:16px;margin-bottom:8px}

.bb-detail-title{display:flex;justify-content:space-between;align-items:flex-start}

.bb-detail-name{font-size:24px;font-weight:700;color:#fff}

.bb-detail-ticker{font-size:14px;color:#00bfff;margin-top:4px}

.bb-detail-sector{font-size:11px;color:#666;margin-top:4px}

.bb-detail-price{text-align:right}

.bb-detail-price-val{font-size:32px;font-weight:700;color:#00ff00}

.bb-detail-price-val.down{color:#ff3b30}

.bb-detail-change{font-size:14px;margin-top:4px}

.bb-detail-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:8px}

@media(max-width:1200px){.bb-detail-grid{grid-template-columns:repeat(2,1fr)}}

.bb-detail-card{background:#0a0a0a;border:1px solid #333;padding:12px}

.bb-detail-card h3{color:#ff9500;font-size:10px;text-transform:uppercase;letter-spacing:1px;margin-bottom:12px;border-bottom:1px solid #333;padding-bottom:6px}

.bb-metric{display:flex;justify-content:space-between;padding:4px 0;border-bottom:1px solid #1a1a1a}

.bb-metric:last-child{border-bottom:none}

.bb-metric-label{color:#888;font-size:10px}

.bb-metric-val{color:#fff;font-size:11px;font-weight:500}

.bb-metric-val.pos{color:#00ff00}.bb-metric-val.neg{color:#ff3b30}

.bb-detail-desc{grid-column:span 2}

.bb-detail-desc p{color:#ccc;font-size:11px;line-height:1.6;max-height:150px;overflow-y:auto}

.bb-memo-section{grid-column:span 4}

.bb-memo-btn{display:flex;align-items:center;gap:8px;padding:12px;background:#111;border:1px solid #ff9500;color:#ff9500;text-decoration:none;margin-top:8px}

.bb-memo-btn:hover{background:#ff9500;color:#000}

.bb-memo-btn svg{width:20px;height:20px}

.bb-no-memo{color:#666;font-style:italic;padding:12px;background:#111;border:1px dashed #333}

.bb-create-memo-btn{display:inline-flex;align-items:center;gap:8px;padding:12px 20px;background:linear-gradient(180deg,#1a1a1a,#111);border:1px solid #ff9500;color:#ff9500;text-decoration:none;cursor:pointer;font-family:inherit;font-size:11px;margin-top:12px}

.bb-create-memo-btn:hover{background:#ff9500;color:#000}

.bb-memo-form{display:none;margin-top:12px;padding:16px;background:#0d0d0d;border:1px solid #333}

.bb-memo-form.active{display:block}

.bb-memo-form h4{color:#ff9500;font-size:11px;text-transform:uppercase;letter-spacing:1px;margin-bottom:16px;padding-bottom:8px;border-bottom:1px solid #333}

.bb-memo-form-group{margin-bottom:12px}

.bb-memo-form-group label{display:block;color:#888;font-size:10px;text-transform:uppercase;margin-bottom:4px}

.bb-memo-form-group input,.bb-memo-form-group select,.bb-memo-form-group textarea{width:100%;background:#000;border:1px solid #333;color:#fff;padding:8px;font-family:inherit;font-size:11px}

.bb-memo-form-group input:focus,.bb-memo-form-group select:focus,.bb-memo-form-group textarea:focus{outline:none;border-color:#ff9500}

.bb-memo-form-group textarea{min-height:100px;resize:vertical}

.bb-memo-form-row{display:grid;grid-template-columns:1fr 1fr;gap:12px}

.bb-memo-form-actions{display:flex;gap:8px;margin-top:16px;padding-top:16px;border-top:1px solid #333}

.bb-memo-form-actions button{padding:8px 16px;font-family:inherit;font-size:11px;cursor:pointer;border:1px solid #333}

.bb-memo-form-actions .btn-save{background:#00ff00;color:#000;border-color:#00ff00}

.bb-memo-form-actions .btn-save:hover{background:#00cc00}

.bb-memo-form-actions .btn-cancel{background:#333;color:#fff}

.bb-memo-form-actions .btn-cancel:hover{background:#444}

.bb-back{display:inline-flex;align-items:center;gap:6px;color:#ff9500;text-decoration:none;padding:8px 0;font-size:11px;margin-bottom:8px}

.bb-back:hover{color:#fff}

/* Chart styles */

.bb-chart-container{grid-column:span 4;background:#0a0a0a;border:1px solid #333;padding:16px;margin-bottom:8px}

.bb-chart-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}

.bb-chart-title{color:#ff9500;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:1px}

.bb-chart-period{display:flex;gap:4px}

.bb-chart-period button{background:#1a1a1a;border:1px solid #333;color:#888;padding:4px 8px;font-size:9px;cursor:pointer;font-family:inherit}

.bb-chart-period button:hover,.bb-chart-period button.active{background:#ff9500;color:#000;border-color:#ff9500}

.bb-chart{position:relative;height:250px;border:1px solid #1a1a1a;background:linear-gradient(180deg,#0d0d0d 0%,#050505 100%)}

.bb-chart canvas{width:100%;height:100%}

.bb-chart-stats{display:flex;gap:24px;margin-top:12px;padding-top:12px;border-top:1px solid #222}

.bb-chart-stat{display:flex;flex-direction:column;gap:2px}

.bb-chart-stat-label{color:#666;font-size:9px;text-transform:uppercase}

.bb-chart-stat-value{color:#fff;font-size:12px;font-weight:600}

.bb-chart-stat-value.pos{color:#00ff00}

.bb-chart-stat-value.neg{color:#ff3b30}

/* Portfolio Chart */

.bb-portfolio-chart{background:#0a0a0a;border:1px solid #333;margin:8px;padding:16px}

.bb-portfolio-chart-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:12px}

.bb-portfolio-chart-title{color:#ff9500;font-size:11px;font-weight:600;text-transform:uppercase;letter-spacing:1px}

.bb-portfolio-chart-canvas{position:relative;height:200px;border:1px solid #1a1a1a;background:linear-gradient(180deg,#0d0d0d 0%,#050505 100%)}

.bb-portfolio-chart-canvas canvas{width:100%;height:100%}

.bb-portfolio-stats{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-top:12px;padding-top:12px;border-top:1px solid #222}

.bb-portfolio-stat{text-align:center}

.bb-portfolio-stat-label{color:#666;font-size:9px;text-transform:uppercase;display:block}

.bb-portfolio-stat-value{color:#fff;font-size:13px;font-weight:600;display:block;margin-top:2px}

.bb-portfolio-stat-value.pos{color:#00ff00}

.bb-portfolio-stat-value.neg{color:#ff3b30}

/* Backtest Styles */

.bb-backtest{padding:16px}

.bb-backtest-header{display:flex;justify-content:space-between;align-items:flex-start;margin-bottom:20px;padding-bottom:16px;border-bottom:2px solid #ff9500}

.bb-backtest-title h2{color:#ff9500;font-size:18px;margin:0 0 4px 0;letter-spacing:2px}

.bb-backtest-title p{color:#666;font-size:11px;margin:0}

.bb-api-ok{color:#00ff00;font-size:11px;padding:4px 8px;background:#001a00;border:1px solid #00ff00;border-radius:3px}

.bb-api-err{color:#ff3b30;font-size:11px;padding:4px 8px;background:#1a0000;border:1px solid #ff3b30;border-radius:3px}

.bb-backtest-config{display:grid;gap:16px}

.bb-backtest-section{background:#0a0a0a;border:1px solid #333;padding:16px}

.bb-backtest-section h3{color:#ff9500;font-size:11px;text-transform:uppercase;letter-spacing:1px;margin:0 0 12px 0;padding-bottom:8px;border-bottom:1px solid #333}

.bb-backtest-row{display:flex;gap:16px;flex-wrap:wrap}

.bb-backtest-field{display:flex;flex-direction:column;gap:4px;min-width:150px}

.bb-backtest-field label{color:#888;font-size:9px;text-transform:uppercase}

.bb-backtest-field input,.bb-backtest-field select,.bb-backtest-field textarea{background:#000;border:1px solid #333;color:#fff;padding:8px;font-family:inherit;font-size:12px}

.bb-backtest-field input:focus,.bb-backtest-field select:focus,.bb-backtest-field textarea:focus{outline:none;border-color:#ff9500}

.bb-backtest-field textarea{resize:vertical;font-size:11px}

.bb-backtest-actions{display:flex;gap:12px;margin-top:16px;flex-wrap:wrap}

.bb-btn-lg{padding:12px 24px;font-size:13px;font-weight:600}

.bb-btn-run{background:linear-gradient(180deg,#00cc00,#009900);border-color:#00ff00;color:#000}

.bb-btn-run:hover{background:linear-gradient(180deg,#00ff00,#00cc00)}

.bb-btn-run:disabled{opacity:0.5;cursor:not-allowed}

.bb-backtest-results{margin-top:24px;border-top:2px solid #333;padding-top:20px}

.bb-backtest-results-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px}

.bb-backtest-results-header h3{color:#00ff00;font-size:14px;margin:0}

.bb-backtest-period{color:#888;font-size:11px}

.bb-backtest-metrics{display:grid;grid-template-columns:repeat(6,1fr);gap:12px;margin-bottom:20px}

@media(max-width:1200px){.bb-backtest-metrics{grid-template-columns:repeat(3,1fr)}}

.bb-metric-card{background:#0a0a0a;border:1px solid #333;padding:12px;text-align:center}

.bb-metric-card.highlight{border-color:#ff9500;background:linear-gradient(180deg,#1a1200,#0a0a0a)}

.bb-metric-card-label{color:#888;font-size:9px;text-transform:uppercase;display:block}

.bb-metric-card-value{color:#fff;font-size:18px;font-weight:700;display:block;margin-top:4px}

.bb-metric-card-value.pos{color:#00ff00}

.bb-metric-card-value.neg{color:#ff3b30}

.bb-metric-card-sub{color:#666;font-size:9px;display:block;margin-top:2px}

.bb-backtest-chart-container{background:#0a0a0a;border:1px solid #333;padding:16px;margin-bottom:16px}

.bb-backtest-chart-container h4{color:#ff9500;font-size:11px;text-transform:uppercase;margin:0 0 12px 0}

.bb-backtest-chart{height:300px;border:1px solid #1a1a1a;background:#050505}

.bb-backtest-chart canvas{width:100%;height:100%}

.bb-backtest-legend{display:flex;gap:20px;margin-top:12px;justify-content:center}

.bt-legend-item{display:flex;align-items:center;gap:6px;color:#888;font-size:10px}

.bt-legend-color{width:12px;height:3px}

.bb-backtest-yearly{background:#0a0a0a;border:1px solid #333;padding:16px;margin-bottom:16px}

.bb-backtest-yearly h4{color:#ff9500;font-size:11px;text-transform:uppercase;margin:0 0 12px 0}

.bb-yearly-chart{height:200px}

.bb-yearly-chart canvas{width:100%;height:100%}

.bb-backtest-trades{background:#0a0a0a;border:1px solid #333;padding:16px;margin-bottom:16px}

.bb-backtest-trades h4{color:#ff9500;font-size:11px;text-transform:uppercase;margin:0 0 12px 0}

.bb-backtest-errors{background:#1a0000;border:1px solid #ff3b30;padding:16px;margin-top:16px}

.bb-backtest-errors h4{color:#ff3b30;font-size:11px;text-transform:uppercase;margin:0 0 8px 0}

/* Backtest History */

.bb-backtest-history{background:#0a0a0a;border:1px solid #333;padding:16px;margin-top:16px}

.bb-backtest-history h4{color:#ff9500;font-size:11px;text-transform:uppercase;margin:0 0 12px 0;display:flex;justify-content:space-between;align-items:center}

.bb-history-table{width:100%;border-collapse:collapse;font-size:11px}

.bb-history-table th{text-align:left;color:#888;font-weight:normal;padding:8px 4px;border-bottom:1px solid #333}

.bb-history-table td{padding:8px 4px;border-bottom:1px solid #1a1a1a}

.bb-history-table tr:hover{background:#111}

.bb-history-name{color:#00bfff;cursor:pointer}

.bb-history-name:hover{text-decoration:underline}

.bb-history-metric{font-weight:600}

.bb-history-metric.pos{color:#00ff00}

.bb-history-metric.neg{color:#ff3b30}

.bb-history-actions{display:flex;gap:4px}

.bb-history-actions button{padding:2px 6px;font-size:9px;cursor:pointer;background:#1a1a1a;border:1px solid #333;color:#888}

.bb-history-actions button:hover{border-color:#ff9500;color:#ff9500}

.bb-history-compare{display:flex;gap:8px;align-items:center;margin-bottom:12px}

.bb-history-compare button{padding:6px 12px}

.bb-compare-chart{margin-top:16px;padding:16px;background:#050505;border:1px solid #333}

.bb-compare-chart h5{color:#ff9500;font-size:10px;margin:0 0 12px 0}

/* AI Optimizer */

.bb-action-separator{width:1px;height:30px;background:#333;margin:0 8px}

.bb-btn-ai{background:linear-gradient(180deg,#6600cc,#4400aa);border-color:#9933ff;color:#fff}

.bb-btn-ai:hover{background:linear-gradient(180deg,#7700dd,#5500bb)}

.bb-btn-ai:disabled{opacity:0.5;cursor:not-allowed}

.bb-btn-advisor{background:linear-gradient(180deg,#005577,#003f5a);border-color:#00bfff;color:#fff}

.bb-btn-advisor:hover{background:linear-gradient(180deg,#00668d,#004b6a)}

.bb-btn-advisor:disabled{opacity:0.5;cursor:not-allowed}

.bb-opt-goal{background:#1a1a1a;border:1px solid #333;color:#fff;padding:8px 12px;font-family:inherit;font-size:11px;margin-left:8px}

.bb-ai-results{background:linear-gradient(180deg,#0d001a,#000);border:2px solid #9933ff;padding:20px;margin-top:16px}

.bb-ai-results-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:16px;padding-bottom:12px;border-bottom:1px solid #9933ff}

.bb-ai-results-header h3{color:#9933ff;margin:0;font-size:14px}

.bb-ai-confidence{padding:4px 12px;border-radius:12px;font-size:10px;font-weight:600}

.bb-ai-confidence.high{background:#003300;color:#00ff00;border:1px solid #00ff00}

.bb-ai-confidence.medium{background:#1a1a00;color:#ffff00;border:1px solid #ffff00}

.bb-ai-confidence.low{background:#1a0000;color:#ff6600;border:1px solid #ff6600}

.bb-ai-optimal{background:#1a0033;border:1px solid #6600cc;padding:16px;margin-bottom:16px}

.bb-ai-optimal h4{color:#cc99ff;font-size:12px;margin:0 0 12px 0}

.bb-ai-params{display:grid;grid-template-columns:repeat(5,1fr);gap:12px}

.bb-ai-param{text-align:center;padding:12px;background:#0d001a;border:1px solid #4400aa}

.bb-ai-param-label{color:#888;font-size:9px;display:block;margin-bottom:4px}

.bb-ai-param-value{color:#00ff00;font-size:18px;font-weight:700}

.bb-ai-expected{margin-top:12px;display:flex;gap:20px;justify-content:center}

.bb-ai-expected-item{color:#888;font-size:11px}

.bb-ai-expected-item span{color:#00bfff;font-weight:600}

.bb-ai-analysis,.bb-ai-explanation{background:#0a0a0a;border:1px solid #333;padding:16px;margin-bottom:16px}

.bb-ai-analysis h4,.bb-ai-explanation h4{color:#ff9500;font-size:11px;margin:0 0 12px 0}

.bb-ai-analysis-text,.bb-ai-explanation div{color:#ccc;font-size:12px;line-height:1.6}

.bb-advisor-report{
  white-space:pre-wrap;
  font-family:'JetBrains Mono',monospace;
  font-size:11px;
  line-height:1.6;
  color:#cfd8e3;
  background:#070b12;
  border:1px solid #1f2d3a;
  padding:14px;
  max-height:560px;
  overflow:auto
}

.bb-ai-warnings{background:#1a0a00;border:1px solid #ff6600;padding:16px;margin-bottom:16px}

.bb-ai-warnings h4{color:#ff6600;font-size:11px;margin:0 0 8px 0}

.bb-ai-warnings ul{margin:0;padding-left:20px;color:#ffaa66;font-size:11px}

.bb-ai-warnings li{margin-bottom:4px}

.bb-ai-grid-results{background:#0a0a0a;border:1px solid #333;padding:16px}

.bb-ai-grid-results h4{color:#ff9500;font-size:11px;margin:0 0 12px 0}

/* Screener improvements */

.bb-scr-hdr{display:flex;justify-content:space-between;align-items:center}

.bb-scr-actions{display:flex;gap:8px;align-items:center}

.bb-scope-select{background:#1a1a1a;border:1px solid #333;color:#fff;padding:8px 12px;font-family:inherit;font-size:11px}

/* AI Criteria Banner */

.bb-ai-criteria{background:linear-gradient(90deg,#1a0033,#0d001a);border:1px solid #9933ff;padding:8px 16px;display:flex;align-items:center;gap:16px;margin-bottom:8px}

.bb-ai-criteria b{color:#9933ff}

.bb-ai-crit{background:#0d001a;border:1px solid #6600cc;padding:4px 10px;color:#cc99ff;font-size:10px;border-radius:3px}

.sig-ai{background:#9933ff;color:#fff}

.bb-backtest-errors ul{margin:0;padding-left:20px;color:#ff6b6b;font-size:10px}

.bb-backtest-loading{display:flex;flex-direction:column;align-items:center;justify-content:center;padding:40px;color:#ff9500}

.bb-backtest-loading .spinner{width:40px;height:40px;border:3px solid #333;border-top-color:#ff9500;border-radius:50%;animation:spin 1s linear infinite}

@keyframes spin{to{transform:rotate(360deg)}}

.bb-scope-toggle{display:flex;gap:4px}

.bb-scope-btn{padding:8px 16px;background:#1a1a1a;border:1px solid #333;color:#888;cursor:pointer;font-family:inherit;font-size:11px;transition:all 0.2s}

.bb-scope-btn:hover{border-color:#ff9500;color:#ff9500}

.bb-scope-btn.active{background:#ff9500;border-color:#ff9500;color:#000;font-weight:600}

.bb-scope-info{margin-top:8px;padding:8px;background:#0d0d0d;border:1px solid #222;font-size:10px;color:#888}

/* Cache Panel */

.bb-cache-panel{display:flex;justify-content:space-between;align-items:center;background:#0a0a0a;border:1px solid #333;padding:12px 16px;margin-bottom:16px}

.bb-cache-info{display:flex;align-items:center;gap:12px}

.bb-cache-icon{font-size:24px}

.bb-cache-stats{font-size:11px;color:#888}

.bb-cache-stats span{color:#00ff00;font-weight:600}

.bb-cache-actions{display:flex;gap:8px}

.bb-api-warn{color:#ff9500;font-size:11px;padding:4px 8px;background:#1a0d00;border:1px solid #ff9500;border-radius:3px}

.bb-download-progress{margin-top:8px;padding:8px;background:#0d0d0d;border:1px solid #333}

.bb-download-progress-bar{height:4px;background:#333;margin-top:8px;border-radius:2px;overflow:hidden}

.bb-download-progress-fill{height:100%;background:#00ff00;transition:width 0.3s}

/* Memo Content Styles */

.bb-memo-content{max-height:500px;overflow-y:auto;padding:16px;background:linear-gradient(180deg,#0d0d0d,#0a0a0a);border:1px solid #333;margin-top:8px;color:#ccc;font-size:11px;line-height:1.7}

.bb-memo-content::-webkit-scrollbar{width:8px}

.bb-memo-content::-webkit-scrollbar-track{background:#111}

.bb-memo-content::-webkit-scrollbar-thumb{background:#333}

.bb-memo-content::-webkit-scrollbar-thumb:hover{background:#ff9500}

.memo-section-title{color:#ff9500;font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:2px;margin:20px 0 12px 0;padding:8px 0;border-bottom:2px solid #ff9500;border-top:1px solid #333}

.memo-section-title:first-child{margin-top:0;border-top:none}

.memo-subtitle{color:#fff;font-size:11px;font-weight:600;margin:14px 0 8px 0}

.memo-text{margin:8px 0;color:#bbb}

.memo-bullet{margin:4px 0 4px 16px;color:#bbb;position:relative}

.memo-bullet::before{content:'';position:absolute;left:-12px;top:6px;width:4px;height:4px;background:#ff9500;border-radius:50%}

.memo-kv{display:flex;margin:6px 0;padding:4px 0;border-bottom:1px solid #1a1a1a}

.memo-key{color:#888;min-width:140px;font-size:10px;text-transform:uppercase}

.memo-value{color:#fff;flex:1}

.memo-signal{padding:10px 16px;margin:12px 0;font-weight:700;font-size:12px;text-align:center;letter-spacing:1px;border-radius:4px}

.memo-signal-buy{background:linear-gradient(180deg,#00cc00,#009900);color:#000;border:1px solid #00ff00}

.memo-signal-sell{background:linear-gradient(180deg,#cc0000,#990000);color:#fff;border:1px solid #ff3b30}

.memo-signal-watch{background:linear-gradient(180deg,#0066cc,#004499);color:#fff;border:1px solid #00bfff}

.memo-signal-hold{background:linear-gradient(180deg,#cc6600,#994d00);color:#fff;border:1px solid #ff9500}

.memo-table{width:100%;border-collapse:collapse;margin:12px 0;font-size:10px}

.memo-table th{background:#1a1a1a;color:#ff9500;padding:8px;text-align:left;font-weight:600;text-transform:uppercase;letter-spacing:1px;border-bottom:2px solid #ff9500}

.memo-table td{padding:8px;border-bottom:1px solid #222;color:#ccc}

.memo-table tr:hover{background:#111}

.memo-table .num{text-align:right;font-family:monospace}

.memo-table .pos{color:#00ff00}

.memo-table .neg{color:#ff3b30}

/* ═══ BLOOMBERG LOADING OVERLAY ═══ */

.bbg-loading-overlay{

  position:fixed;

  top:0;left:0;right:0;bottom:0;

  background:rgba(4,4,10,0.97);

  backdrop-filter:blur(8px);

  z-index:9999;

  display:flex;

  align-items:center;

  justify-content:center;

  opacity:0;

  pointer-events:none;

  transition:opacity 0.3s ease;

}

.bbg-loading-overlay.active{opacity:1;pointer-events:all}

.bbg-loading-content{

  text-align:center;

  max-width:500px;

  padding:40px;

}

.bbg-loading-logo{

  font-size:36px;

  font-weight:800;

  letter-spacing:8px;

  color:#ff9500;

  margin-bottom:10px;

  text-shadow:0 0 20px rgba(255,149,0,0.5);

  animation:bbgPulse 2s ease-in-out infinite;

}

.bbg-loading-subtitle{

  font-size:11px;

  color:#666;

  letter-spacing:3px;

  text-transform:uppercase;

  margin-bottom:40px;

}

.bbg-loading-bar-container{

  width:100%;

  height:4px;

  background:#1a1a1a;

  border-radius:2px;

  overflow:hidden;

  margin-bottom:20px;

  position:relative;

}

.bbg-loading-bar{

  height:100%;

  background:linear-gradient(90deg,#ff9500,#ffb800,#ff9500);

  background-size:200% 100%;

  border-radius:2px;

  box-shadow:0 0 15px #ff9500;

  animation:bbgBarSlide 1.5s ease-in-out infinite;

  width:60%;

}

.bbg-loading-scanline{

  position:absolute;

  top:0;bottom:0;

  width:2px;

  background:linear-gradient(transparent,#ff9500,transparent);

  box-shadow:0 0 10px #ff9500;

  animation:bbgScan 2s linear infinite;

}

@keyframes bbgBarSlide{

  0%{background-position:0% 50%}

  50%{background-position:100% 50%}

  100%{background-position:0% 50%}

}

@keyframes bbgScan{

  0%{left:-2px}

  100%{left:100%}

}

@keyframes bbgPulse{

  0%,100%{opacity:1;transform:scale(1)}

  50%{opacity:0.85;transform:scale(1.02)}

}

.bbg-loading-stats{

  display:flex;

  justify-content:space-around;

  margin-top:30px;

  padding-top:20px;

  border-top:1px solid #333;

}

.bbg-loading-stat{

  text-align:center;

}

.bbg-loading-stat-value{

  font-size:24px;

  font-weight:700;

  color:#ff9500;

  font-variant-numeric:tabular-nums;

  margin-bottom:5px;

}

.bbg-loading-stat-label{

  font-size:9px;

  color:#444;

  text-transform:uppercase;

  letter-spacing:1px;

}

.bbg-loading-message{

  margin-top:20px;

  font-size:11px;

  color:#888;

  font-style:italic;

}

'''



def fmt_val(v, decimals=2):

    """Format a numeric value safely"""

    if v is None:

        return '-'

    if isinstance(v, float) and math.isnan(v):

        return '-'

    try:

        return f"{v:,.{decimals}f}".replace(",", " ")

    except Exception:
        return '-'



def gen_html(df: Any, screener: List[Dict[str, Any]], watchlist: List[str], update_history: bool = False) -> str:

    pos = df.to_dict('records')

    active = [p for p in pos if (p.get('qty') or 0) > 0]

    

    # Calculate totals safely

    tv = 0

    tc = 0

    for p in active:

        price = safe_float(p.get('price_eur')) or 0

        qty = safe_float(p.get('qty')) or 0

        cost = safe_float(p.get('avg_cost_eur')) or 0

        tv += price * qty

        tc += cost * qty

    

    pnl = tv - tc

    pnl_pct = (tv / tc - 1) * 100 if tc > 0 else 0

    opps = len([s for s in screener if s.get('signal') == 'ACHAT'])

    pnl_sign = '+' if pnl >= 0 else ''



    # Get realized PnL from position manager to include in NAV

    total_realized_pnl = 0.0

    try:

        price_data = {p.get('ticker', '').upper(): safe_float(p.get('price_eur')) or 0 for p in pos}

        name_data = {p.get('ticker', '').upper(): p.get('name', '') for p in pos}

        manager = get_position_manager()

        pnl_summary = manager.get_all_positions(price_data, name_data)

        total_realized_pnl = pnl_summary.total_realized_pnl

    except Exception as e:

        log.warning(f"Could not get realized PnL: {e}")



    # NAV = market value of positions + cumulative realized PnL (cash from sales)

    nav_total = tv + total_realized_pnl

    total_pnl = pnl + total_realized_pnl  # Total P&L = unrealized + realized

    total_pnl_pct = (total_pnl / tc * 100) if tc > 0 else 0



    # Update NAV history if requested (on refresh)

    if update_history and nav_total > 0:

        nav_history = update_nav_history(nav_total, tc, total_pnl, total_pnl_pct, total_realized_pnl)

    else:

        nav_history = load_nav_history()

    

    # Calculate portfolio performance stats

    if nav_history and len(nav_history) > 1:

        first_nav = nav_history[0]['nav']

        last_nav = nav_history[-1]['nav']

        total_perf = ((last_nav / first_nav) - 1) * 100 if first_nav > 0 else 0

        

        # Find high/low

        nav_high = max(h['nav'] for h in nav_history)

        nav_low = min(h['nav'] for h in nav_history)

        

        # 1 week perf

        if len(nav_history) >= 5:

            week_ago = nav_history[-5]['nav']

            perf_1w = ((last_nav / week_ago) - 1) * 100 if week_ago > 0 else 0

        else:

            perf_1w = 0

        

        # 1 month perf (approx 22 trading days)

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

    

    nav_history_json = json.dumps(nav_history)

    

    # Portfolio rows with proper alignment

    pf_rows = ""

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

        pc = 'pos' if pp >= 0 else 'neg'

        

        # Map signal to CSS class

        sig_lower = sig.lower()

        if sig_lower in ['buy', 'achat']:

            sc = 'sig-achat'

        elif sig_lower in ['sell', 'ecarter', 'ecarter']:

            sc = 'sig-ecarter'

        elif sig_lower in ['watch', 'surveillance']:

            sc = 'sig-surveillance'

        else:

            sc = 'sig-neutre'

        

        ps = '+' if pp >= 0 else ''



        # Format values

        price_str = fmt_val(price) if price > 0 else '-'

        val_str = fmt_val(val, 0) if val > 0 else '-'

        poids_str = f"{poids:.1f}%" if val > 0 else '-'

        chg_str = f"{ps}{pp:.1f}%" if price > 0 else '-'

        pe_str = fmt_val(pe, 1) if pe else '-'

        pcf_str = fmt_val(pcf, 1) if pcf else '-'

        roe_str = f"{roe*100:.0f}%" if roe else '-'



        # Color coding for PE (green if ≤10, yellow if ≤12, white otherwise)

        if pe:

            if pe <= 10:

                pe_color = '#00ff00'

                pe_weight = '700'

            elif pe <= 12:

                pe_color = '#ffff00'

                pe_weight = '600'

            else:

                pe_color = '#fff'

                pe_weight = '400'

        else:

            pe_color = '#666'

            pe_weight = '400'



        # Color coding for P/CF (green if ≤8, yellow if ≤12, red otherwise)
        if pcf:
            if pcf <= 8:
                pcf_color = '#00ff00'  # Excellent
                pcf_weight = '700'
            elif pcf <= 12:
                pcf_color = '#ffff00'  # Correct
                pcf_weight = '600'
            else:
                pcf_color = '#ff4444'  # Expensive
                pcf_weight = '400'
        else:
            pcf_color = '#666'
            pcf_weight = '400'

        # Color coding for ROE (green if ≥15%, yellow if ≥10%, white otherwise)

        if roe:

            roe_pct = roe * 100

            if roe_pct >= 15:

                roe_color = '#00ff00'

            elif roe_pct >= 10:

                roe_color = '#ffff00'

            else:

                roe_color = '#fff'

        else:

            roe_color = '#666'



        ticker = p['ticker']
        name = str(p.get('name', ''))[:16]
        # Escape for safe use in onclick handlers (XSS prevention)
        ticker_esc = html.escape(ticker, quote=True)
        name_esc = html.escape(name, quote=True)

        qty_str = f"{int(qty)}" if qty == int(qty) else f"{qty:.2f}"



        pf_rows += f'''<tr>

<td class="col-ticker"><a class="tk" href="/?detail={ticker}">{ticker}</a></td>

<td class="col-name nm">{name}</td>

<td class="col-qty r">{qty_str}</td>

<td class="col-last r">{price_str}</td>

<td class="col-mktval r">{val_str}</td>

<td class="col-weight r wgt">{poids_str}</td>

<td class="col-chg r {pc}">{chg_str}</td>

<td class="col-pe r" style="color:{pe_color};font-weight:{pe_weight}">{pe_str}</td>

<td class="col-pcf r" style="color:{pcf_color};font-weight:{pcf_weight}">{pcf_str}</td>

<td class="col-roe r" style="color:{roe_color}">{roe_str}</td>

<td class="col-signal c"><span class="sig {sc}">{sig}</span></td>

<td class="col-actions c"><button class="btn-buy" onclick="openTradeModal('{ticker_esc}', '{name_esc}', 'BUY')" title="Buy more">+</button><button class="btn-sell" onclick="openTradeModal('{ticker_esc}', '{name_esc}', 'SELL', {qty})" title="Sell">-</button><button class="btn-edit" onclick="editPosition('{ticker_esc}', '{name_esc}', {qty}, {cost})" title="Edit">✏️</button></td>

</tr>'''

    

    # Watchlist rows

    wl_rows = ""

    for w in watchlist:

        wl_rows += f'<tr><td><a class="tk" href="/?detail={w["ticker"]}">{w["ticker"]}</a></td><td class="nm">{w["name"]}</td><td>{w["country"]}</td><td>{w["sector"]}</td><td>{w["added"]}</td><td><button class="bb-btn bb-btn-r" onclick="rmW(\'{w["ticker"]}\')">DEL</button></td></tr>'

    if not watchlist:

        wl_rows = '<tr><td colspan="6" style="text-align:center;padding:40px;color:#666">No securities in watchlist</td></tr>'

    

    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Olyos Capital — Portfolio Terminal</title>

<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 32 32'><rect width='32' height='32' rx='6' fill='%2308081a'/><line x1='9' y1='8' x2='16' y2='16' stroke='%23c9a84c' stroke-width='.6' opacity='.35'/><line x1='16' y1='16' x2='25' y2='12' stroke='%23c9a84c' stroke-width='.6' opacity='.35'/><line x1='16' y1='16' x2='11' y2='25' stroke='%23c9a84c' stroke-width='.6' opacity='.35'/><circle cx='9' cy='8' r='3' fill='%23c9a84c' opacity='.8'/><circle cx='16' cy='16' r='4' fill='%23c9a84c'/><circle cx='25' cy='12' r='2.5' fill='%23c9a84c' opacity='.7'/><circle cx='11' cy='25' r='2' fill='%23c9a84c' opacity='.45'/></svg>">

<style>{BLOOMBERG_CSS}</style>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
</head><body>

<!-- ═══ BLOOMBERG LOADING OVERLAY ═══ -->

<div class="bbg-loading-overlay active" id="bbg-loader">

  <div class="bbg-loading-content">

    <div class="bbg-loading-logo" style="display:flex;align-items:center;justify-content:center;gap:12px;">

      <svg viewBox="0 0 38 38" width="48" height="48" xmlns="http://www.w3.org/2000/svg">

        <defs>

          <symbol id="s4-load" viewBox="0 0 20 20"><path d="M10,0 L12,7.5 L20,10 L12,12.5 L10,20 L8,12.5 L0,10 L8,7.5 Z"/></symbol>

          <symbol id="sp-load" viewBox="0 0 20 20"><path d="M10,0 L10.8,8.2 L20,10 L10.8,11.8 L10,20 L9.2,11.8 L0,10 L9.2,8.2 Z"/></symbol>

        </defs>

        <line x1="10" y1="10" x2="19" y2="19" stroke="#ff9500" stroke-width=".7" opacity=".4"/>

        <line x1="19" y1="19" x2="30" y2="14" stroke="#ff9500" stroke-width=".7" opacity=".4"/>

        <line x1="19" y1="19" x2="13" y2="30" stroke="#ff9500" stroke-width=".7" opacity=".4"/>

        <line x1="30" y1="14" x2="26" y2="28" stroke="#ff9500" stroke-width=".5" opacity=".3"/>

        <use href="#s4-load" x="5" y="5" width="10" height="10" fill="#ff9500" opacity=".8"/>

        <use href="#sp-load" x="12" y="12" width="14" height="14" fill="#ff9500"/>

        <use href="#s4-load" x="25" y="9" width="9" height="9" fill="#ff9500" opacity=".7"/>

        <use href="#sp-load" x="9.5" y="27" width="7" height="7" fill="#ff9500" opacity=".5"/>

      </svg>

      <span style="font-size:36px;font-weight:800;letter-spacing:8px;">OLYOS CAPITAL</span>

    </div>

    <div class="bbg-loading-subtitle">Portfolio Management System</div>



    <div class="bbg-loading-bar-container">

      <div class="bbg-loading-bar"></div>

      <div class="bbg-loading-scanline"></div>

    </div>



    <div class="bbg-loading-stats">

      <div class="bbg-loading-stat">

        <div class="bbg-loading-stat-value" id="bbg-load-positions">—</div>

        <div class="bbg-loading-stat-label">Positions</div>

      </div>

      <div class="bbg-loading-stat">

        <div class="bbg-loading-stat-value" id="bbg-load-nav">—</div>

        <div class="bbg-loading-stat-label">NAV</div>

      </div>

      <div class="bbg-loading-stat">

        <div class="bbg-loading-stat-value" id="bbg-load-time">—</div>

        <div class="bbg-loading-stat-label">Status</div>

      </div>

    </div>



    <div class="bbg-loading-message" id="bbg-load-msg">Loading portfolio data...</div>

  </div>

</div>

<div class="bb-top">

<div class="bb-logo"><svg viewBox="0 0 38 38" width="24" height="24" xmlns="http://www.w3.org/2000/svg">

  <defs>

    <symbol id="s4" viewBox="0 0 20 20"><path d="M10,0 L12,7.5 L20,10 L12,12.5 L10,20 L8,12.5 L0,10 L8,7.5 Z"/></symbol>

    <symbol id="sp" viewBox="0 0 20 20"><path d="M10,0 L10.8,8.2 L20,10 L10.8,11.8 L10,20 L9.2,11.8 L0,10 L9.2,8.2 Z"/></symbol>

  </defs>

  <line x1="10" y1="10" x2="19" y2="19" stroke="#ff9500" stroke-width=".7" opacity=".4"/>

  <line x1="19" y1="19" x2="30" y2="14" stroke="#ff9500" stroke-width=".7" opacity=".4"/>

  <line x1="19" y1="19" x2="13" y2="30" stroke="#ff9500" stroke-width=".7" opacity=".4"/>

  <line x1="30" y1="14" x2="26" y2="28" stroke="#ff9500" stroke-width=".5" opacity=".3"/>

  <use href="#s4" x="5" y="5" width="10" height="10" fill="#ff9500" opacity=".8"/>

  <use href="#sp" x="12" y="12" width="14" height="14" fill="#ff9500"/>

  <use href="#s4" x="25" y="9" width="9" height="9" fill="#ff9500" opacity=".7"/>

  <use href="#sp" x="9.5" y="27" width="7" height="7" fill="#ff9500" opacity=".5"/>

</svg><h1>OLYOS CAPITAL</h1><span>PORTFOLIO TERMINAL v4.0</span></div>

<input type="text" class="bb-cmd" placeholder="Enter ticker..." onkeydown="if(event.key==='Enter')location.href='/?detail='+this.value.toUpperCase()"/>

<div class="bb-time">{datetime.now().strftime('%H:%M:%S')} CET <span class="blink">●</span></div>

</div>

<div class="bb-fkeys">

<button class="fkey active" onclick="showTab(0)">F1 PORT</button>

<button class="fkey" onclick="showTab(1)">F2 SCRN</button>

<button class="fkey" onclick="showTab(2)">F3 WTCH</button>

<button class="fkey" onclick="showTab(3)">F4 BACK</button>

<button class="fkey" onclick="location.href='/?refresh=1'">F5 REFRESH</button>

<button class="fkey" onclick="if(confirm('Run full scan?'))location.href='/?screener=1'">F6 SCAN</button>

<button class="fkey" onclick="generateReport()" style="background:linear-gradient(135deg,#1a1a2e,#16213e);border-color:#ffd700;color:#ffd700;">F7 REPORT</button>

<button class="fkey" onclick="toggleInsiderPanel()" style="background:linear-gradient(135deg,#1a2e1a,#162e16);border-color:#22c55e;color:#22c55e;">F8 INSIDER</button>

<button class="fkey" onclick="toggleRebalancePanel()" style="background:linear-gradient(135deg,#2e1a1a,#3e1616);border-color:#f59e0b;color:#f59e0b;">F9 REBALANCE</button>

<button class="fkey" onclick="toggleHeatmapPanel()" style="background:linear-gradient(135deg,#1a1a2e,#2e1a2e);border-color:#a855f7;color:#a855f7;">F10 HEATMAP</button>

<button class="fkey" id="fkey-advisor" onclick="location.href='/advisor'" style="background:linear-gradient(135deg,#0f2533,#143042);border-color:#22d3ee;color:#22d3ee;" {'disabled' if not PORTFOLIO_ADVISOR_OK else ''}>F11 ADVISOR</button>

</div>

<div class="bb-tabs">

<div class="bb-tab active" onclick="showTab(0)">Portfolio<span class="bb-badge">{len(active)}</span></div>

<div class="bb-tab" onclick="location.href='/screener'">Screener<span class="bb-badge bb-badge-g">{opps}</span></div>

<div class="bb-tab" onclick="showTab(2)">Watchlist<span class="bb-badge">{len(watchlist)}</span></div>

<div class="bb-tab" onclick="showTab(3)">Backtest<span class="bb-badge" style="background:#9933ff">🔬</span></div>

</div>

<div id="t0" class="tc active">

<div class="bb-kpis">

<div class="bb-kpi"><span class="bb-kpi-label">NAV</span><span class="bb-kpi-val">{tv:,.0f} EUR</span></div>

<div class="bb-kpi"><span class="bb-kpi-label">P&L</span><span class="bb-kpi-val {'down' if pnl<0 else ''}">{pnl_sign}{abs(pnl):,.0f} EUR</span></div>

<div class="bb-kpi"><span class="bb-kpi-label">%CHG</span><span class="bb-kpi-chg {'up' if pnl>=0 else 'down'}">{pnl_sign}{pnl_pct:.2f}%</span></div>

<div class="bb-kpi"><span class="bb-kpi-label">POS</span><span style="color:#fff;font-size:14px;font-weight:600">{len(active)}</span></div>

<div class="bb-kpi"><span class="bb-kpi-label">UPD</span><span style="color:#888;font-size:11px">{datetime.now().strftime('%d-%b %H:%M').upper()}</span></div>

<div class="bb-kpi-divider"></div>

<div class="bb-kpi"><span class="bb-kpi-label">ALPHA</span><span class="bb-kpi-val" id="kpi-alpha" style="color:#888">--</span></div>

<div class="bb-kpi"><span class="bb-kpi-label">BETA</span><span style="color:#fff;font-size:14px;font-weight:600" id="kpi-beta">--</span></div>

<div class="bb-kpi"><span class="bb-kpi-label">SHARPE</span><span style="color:#fff;font-size:14px;font-weight:600" id="kpi-sharpe">--</span></div>

<div class="bb-kpi-divider"></div>

<div class="bb-kpi"><span class="bb-kpi-label">REALIZED</span><span style="color:#888;font-size:14px;font-weight:600" id="kpi-realized-pnl">--</span></div>

<div class="bb-kpi"><span class="bb-kpi-label">WIN RATE</span><span style="color:#fff;font-size:14px;font-weight:600" id="kpi-win-rate">--</span></div>

</div>

<style>
.bb-kpi-divider {{
  width: 1px;
  background: #333;
  margin: 0 8px;
}}
</style>

<!-- ALERTS PANEL -->
<div class="bb-alerts-panel" id="alerts-panel" style="display:none;">
<div class="bb-alerts-header">
<span class="bb-alerts-icon" id="alerts-icon">🔔</span>
<span class="bb-alerts-title">ALERTS</span>
<span class="bb-alerts-count" id="alerts-count">0</span>
<button class="bb-btn bb-btn-sm" onclick="checkAlerts()" style="margin-left:auto;font-size:10px;padding:4px 8px;">🔄 REFRESH</button>
</div>
<div class="bb-alerts-list" id="alerts-list">
<!-- Alerts will be loaded via JavaScript -->
</div>
</div>

<style>
.bb-alerts-panel {{
  background: linear-gradient(135deg, #1a1a1a 0%, #0d0d0d 100%);
  border: 1px solid #ff9500;
  border-radius: 4px;
  margin: 10px 0;
  overflow: hidden;
}}
.bb-alerts-header {{
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 15px;
  background: linear-gradient(90deg, rgba(255,149,0,0.2) 0%, transparent 100%);
  border-bottom: 1px solid #333;
}}
.bb-alerts-icon {{
  font-size: 18px;
  animation: alertPulse 2s ease-in-out infinite;
}}
.bb-alerts-icon.active {{
  animation: alertBlink 0.8s ease-in-out infinite;
}}
@keyframes alertPulse {{
  0%, 100% {{ opacity: 0.5; }}
  50% {{ opacity: 1; }}
}}
@keyframes alertBlink {{
  0%, 100% {{ opacity: 1; transform: scale(1); }}
  50% {{ opacity: 0.5; transform: scale(1.2); }}
}}
.bb-alerts-title {{
  font-size: 14px;
  font-weight: 700;
  color: #ff9500;
  letter-spacing: 2px;
}}
.bb-alerts-count {{
  background: #ff9500;
  color: #000;
  font-size: 11px;
  font-weight: 700;
  padding: 2px 8px;
  border-radius: 10px;
}}
.bb-alerts-list {{
  max-height: 200px;
  overflow-y: auto;
}}
.bb-alert-item {{
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 10px 15px;
  border-bottom: 1px solid #222;
  transition: background 0.2s;
}}
.bb-alert-item:hover {{
  background: rgba(255,149,0,0.1);
}}
.bb-alert-item.zone-achat {{
  border-left: 3px solid #00ff00;
}}
.bb-alert-item.pe-attractif {{
  border-left: 3px solid #ffff00;
}}
.bb-alert-item.roe-excellent {{
  border-left: 3px solid #00ffff;
}}
.bb-alert-item.prix-cible {{
  border-left: 3px solid #ff00ff;
}}
.bb-alert-item.momentum {{
  border-left: 3px solid #ff9500;
}}
.bb-alert-ticker {{
  color: #00ffff;
  font-weight: 600;
  font-size: 13px;
  min-width: 80px;
}}
.bb-alert-name {{
  color: #888;
  font-size: 11px;
  min-width: 100px;
}}
.bb-alert-message {{
  color: #fff;
  font-size: 12px;
  flex: 1;
}}
.bb-alert-actions {{
  display: flex;
  gap: 5px;
}}
.bb-alert-btn {{
  background: #333;
  border: 1px solid #555;
  color: #fff;
  font-size: 10px;
  padding: 4px 8px;
  cursor: pointer;
  border-radius: 3px;
  transition: all 0.2s;
}}
.bb-alert-btn:hover {{
  background: #ff9500;
  color: #000;
  border-color: #ff9500;
}}
.bb-alert-btn.dismiss {{
  color: #888;
}}
.bb-alert-btn.dismiss:hover {{
  background: #ff3333;
  border-color: #ff3333;
  color: #fff;
}}
.bb-no-alerts {{
  padding: 20px;
  text-align: center;
  color: #666;
  font-size: 12px;
}}
</style>

<div class="bb-portfolio-chart">

<div class="bb-portfolio-chart-header">

<span class="bb-portfolio-chart-title">📈 Portfolio Performance</span>

<div class="bb-chart-period">

<button onclick="setNavPeriod(7)" id="nav-1w">1W</button>

<button onclick="setNavPeriod(30)" id="nav-1m">1M</button>

<button onclick="setNavPeriod(90)" id="nav-3m">3M</button>

<button onclick="setNavPeriod(365)" id="nav-1y" class="active">ALL</button>

</div>

</div>

<div class="bb-portfolio-chart-canvas"><canvas id="navChart"></canvas></div>

<div class="bb-portfolio-stats">

<div class="bb-portfolio-stat"><span class="bb-portfolio-stat-label">1W Perf</span><span class="bb-portfolio-stat-value {'pos' if perf_1w >= 0 else 'neg'}">{'+' if perf_1w >= 0 else ''}{perf_1w:.2f}%</span></div>

<div class="bb-portfolio-stat"><span class="bb-portfolio-stat-label">1M Perf</span><span class="bb-portfolio-stat-value {'pos' if perf_1m >= 0 else 'neg'}">{'+' if perf_1m >= 0 else ''}{perf_1m:.2f}%</span></div>

<div class="bb-portfolio-stat"><span class="bb-portfolio-stat-label">Total Perf</span><span class="bb-portfolio-stat-value {'pos' if total_perf >= 0 else 'neg'}">{'+' if total_perf >= 0 else ''}{total_perf:.2f}%</span></div>

<div class="bb-portfolio-stat"><span class="bb-portfolio-stat-label">NAV High</span><span class="bb-portfolio-stat-value">{nav_high:,.0f}</span></div>

<div class="bb-portfolio-stat"><span class="bb-portfolio-stat-label">NAV Low</span><span class="bb-portfolio-stat-value">{nav_low:,.0f}</span></div>

<div class="bb-portfolio-stat"><span class="bb-portfolio-stat-label">Days Tracked</span><span class="bb-portfolio-stat-value">{len(nav_history)}</span></div>

</div>

</div>

<!-- BENCHMARK COMPARISON CHART -->
<div class="bb-benchmark-panel">
<div class="bb-benchmark-header">
<div class="bb-benchmark-title">
<span class="bb-benchmark-icon">📊</span>
<span>BENCHMARK COMPARISON</span>
</div>
<div class="bb-benchmark-controls">
<div class="bb-benchmark-select">
<button class="bb-bench-btn active" onclick="setBenchmark('CACMS')" id="bench-CACMS">CAC M&S</button>
<button class="bb-bench-btn" onclick="setBenchmark('CACS')" id="bench-CACS">CAC Small</button>
<button class="bb-bench-btn" onclick="setBenchmark('STOXX50E')" id="bench-STOXX50E">Euro Stoxx</button>
</div>
<div class="bb-benchmark-period">
<button onclick="setBenchPeriod('YTD')" id="bench-ytd">YTD</button>
<button onclick="setBenchPeriod('1Y')" id="bench-1y" class="active">1Y</button>
<button onclick="setBenchPeriod('3Y')" id="bench-3y">3Y</button>
<button onclick="setBenchPeriod('MAX')" id="bench-max">MAX</button>
</div>
</div>
</div>
<div class="bb-benchmark-alpha" id="benchmark-alpha">
<span class="bb-alpha-label">ALPHA (vs benchmark)</span>
<span class="bb-alpha-value" id="alpha-value">--</span>
</div>
<div class="bb-benchmark-chart">
<canvas id="benchmarkChart"></canvas>
</div>
<div class="bb-benchmark-metrics" id="benchmark-metrics">
<div class="bb-bench-metric"><span class="bb-bench-metric-label">Portfolio</span><span class="bb-bench-metric-value" id="metric-portfolio">--</span></div>
<div class="bb-bench-metric"><span class="bb-bench-metric-label">Benchmark</span><span class="bb-bench-metric-value" id="metric-benchmark">--</span></div>
<div class="bb-bench-metric"><span class="bb-bench-metric-label">Beta</span><span class="bb-bench-metric-value" id="metric-beta">--</span></div>
<div class="bb-bench-metric"><span class="bb-bench-metric-label">Sharpe</span><span class="bb-bench-metric-value" id="metric-sharpe">--</span></div>
<div class="bb-bench-metric"><span class="bb-bench-metric-label">Max DD</span><span class="bb-bench-metric-value" id="metric-maxdd">--</span></div>
<div class="bb-bench-metric"><span class="bb-bench-metric-label">Tracking Err</span><span class="bb-bench-metric-value" id="metric-tracking">--</span></div>
</div>
</div>

<style>
.bb-benchmark-panel {{
  background: #0a0a0a;
  border: 1px solid #333;
  margin: 8px;
  padding: 16px;
  border-radius: 4px;
}}
.bb-benchmark-header {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 10px;
}}
.bb-benchmark-title {{
  display: flex;
  align-items: center;
  gap: 8px;
  color: #ff9500;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1px;
}}
.bb-benchmark-icon {{
  font-size: 14px;
}}
.bb-benchmark-controls {{
  display: flex;
  gap: 15px;
  align-items: center;
}}
.bb-benchmark-select {{
  display: flex;
  gap: 4px;
}}
.bb-bench-btn {{
  background: #1a1a1a;
  border: 1px solid #333;
  color: #888;
  font-size: 10px;
  padding: 4px 10px;
  cursor: pointer;
  transition: all 0.2s;
}}
.bb-bench-btn:hover {{
  border-color: #ff9500;
  color: #fff;
}}
.bb-bench-btn.active {{
  background: #ff9500;
  color: #000;
  border-color: #ff9500;
  font-weight: 600;
}}
.bb-benchmark-period {{
  display: flex;
  gap: 2px;
}}
.bb-benchmark-period button {{
  background: #1a1a1a;
  border: 1px solid #333;
  color: #666;
  font-size: 10px;
  padding: 4px 8px;
  cursor: pointer;
}}
.bb-benchmark-period button:hover {{
  color: #fff;
}}
.bb-benchmark-period button.active {{
  background: #333;
  color: #fff;
}}
.bb-benchmark-alpha {{
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 15px;
  padding: 12px;
  background: linear-gradient(90deg, rgba(255,149,0,0.1) 0%, transparent 50%, rgba(255,149,0,0.1) 100%);
  margin-bottom: 12px;
  border-radius: 4px;
}}
.bb-alpha-label {{
  color: #888;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 1px;
}}
.bb-alpha-value {{
  font-size: 28px;
  font-weight: 700;
  color: #00ff00;
}}
.bb-alpha-value.negative {{
  color: #ff3333;
}}
.bb-benchmark-chart {{
  position: relative;
  height: 200px;
  border: 1px solid #1a1a1a;
  background: linear-gradient(180deg, #0d0d0d 0%, #050505 100%);
  margin-bottom: 12px;
}}
.bb-benchmark-chart canvas {{
  width: 100%;
  height: 100%;
}}
.bb-benchmark-metrics {{
  display: grid;
  grid-template-columns: repeat(6, 1fr);
  gap: 10px;
}}
.bb-bench-metric {{
  text-align: center;
  padding: 8px;
  background: #111;
  border-radius: 3px;
}}
.bb-bench-metric-label {{
  display: block;
  color: #666;
  font-size: 9px;
  text-transform: uppercase;
  letter-spacing: 0.5px;
  margin-bottom: 4px;
}}
.bb-bench-metric-value {{
  color: #fff;
  font-size: 14px;
  font-weight: 600;
}}
.bb-bench-metric-value.pos {{
  color: #00ff00;
}}
.bb-bench-metric-value.neg {{
  color: #ff3333;
}}
@media (max-width: 768px) {{
  .bb-benchmark-metrics {{
    grid-template-columns: repeat(3, 1fr);
  }}
}}
</style>

<!-- DIVIDENDS PANEL -->
<div class="bb-dividends-panel">
<div class="bb-dividends-header">
<div class="bb-dividends-title">
<span class="bb-dividends-icon">💰</span>
<span>DIVIDENDS CALENDAR</span>
</div>
<div class="bb-dividends-controls">
<button class="bb-div-period active" onclick="setDivPeriod(3)" id="div-3m">3M</button>
<button class="bb-div-period" onclick="setDivPeriod(6)" id="div-6m">6M</button>
<button class="bb-div-period" onclick="setDivPeriod(12)" id="div-12m">12M</button>
</div>
</div>
<div class="bb-dividends-summary" id="dividends-summary">
<div class="bb-div-total">
<span class="bb-div-total-label">Projected Annual Income</span>
<span class="bb-div-total-value" id="div-annual-income">--</span>
</div>
<div class="bb-div-stats">
<div class="bb-div-stat"><span class="bb-div-stat-label">Monthly Avg</span><span class="bb-div-stat-value" id="div-monthly">--</span></div>
<div class="bb-div-stat"><span class="bb-div-stat-label">Yield</span><span class="bb-div-stat-value" id="div-yield">--</span></div>
<div class="bb-div-stat"><span class="bb-div-stat-label">Payers</span><span class="bb-div-stat-value" id="div-payers">--</span></div>
</div>
</div>
<div class="bb-dividends-upcoming" id="dividends-upcoming">
<div class="bb-div-section-title">Upcoming Ex-Dates (Next 90 days)</div>
<div class="bb-div-list" id="div-upcoming-list">
<div class="bb-div-loading">Loading dividend data...</div>
</div>
</div>
<div class="bb-dividends-breakdown" id="dividends-breakdown">
<div class="bb-div-section-title">Top Dividend Contributors</div>
<div class="bb-div-breakdown-list" id="div-breakdown-list"></div>
</div>
</div>

<style>
.bb-dividends-panel {{
  background: #0a0a0a;
  border: 1px solid #333;
  margin: 8px;
  padding: 16px;
  border-radius: 4px;
}}
.bb-dividends-header {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 16px;
}}
.bb-dividends-title {{
  display: flex;
  align-items: center;
  gap: 8px;
  color: #00ff00;
  font-size: 11px;
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 1px;
}}
.bb-dividends-icon {{
  font-size: 14px;
}}
.bb-dividends-controls {{
  display: flex;
  gap: 4px;
}}
.bb-div-period {{
  background: #1a1a1a;
  border: 1px solid #333;
  color: #666;
  font-size: 10px;
  padding: 4px 10px;
  cursor: pointer;
  transition: all 0.2s;
}}
.bb-div-period:hover {{
  border-color: #00ff00;
  color: #fff;
}}
.bb-div-period.active {{
  background: #00ff00;
  color: #000;
  border-color: #00ff00;
  font-weight: 600;
}}
.bb-dividends-summary {{
  background: linear-gradient(90deg, rgba(0,255,0,0.08) 0%, transparent 50%, rgba(0,255,0,0.08) 100%);
  padding: 16px;
  border-radius: 4px;
  margin-bottom: 16px;
  display: flex;
  align-items: center;
  gap: 30px;
}}
.bb-div-total {{
  text-align: center;
  flex-shrink: 0;
}}
.bb-div-total-label {{
  display: block;
  color: #888;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 6px;
}}
.bb-div-total-value {{
  font-size: 32px;
  font-weight: 700;
  color: #00ff00;
}}
.bb-div-stats {{
  display: flex;
  gap: 20px;
  flex-grow: 1;
  justify-content: center;
}}
.bb-div-stat {{
  text-align: center;
  padding: 8px 15px;
  background: #111;
  border-radius: 3px;
}}
.bb-div-stat-label {{
  display: block;
  color: #666;
  font-size: 9px;
  text-transform: uppercase;
  margin-bottom: 4px;
}}
.bb-div-stat-value {{
  color: #fff;
  font-size: 14px;
  font-weight: 600;
}}
.bb-dividends-upcoming, .bb-dividends-breakdown {{
  margin-bottom: 12px;
}}
.bb-div-section-title {{
  color: #888;
  font-size: 10px;
  text-transform: uppercase;
  letter-spacing: 1px;
  margin-bottom: 10px;
  padding-bottom: 6px;
  border-bottom: 1px solid #222;
}}
.bb-div-list {{
  max-height: 180px;
  overflow-y: auto;
}}
.bb-div-item {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 10px;
  background: #111;
  margin-bottom: 4px;
  border-radius: 3px;
  border-left: 3px solid #333;
}}
.bb-div-item.upcoming {{
  border-left-color: #ff9500;
}}
.bb-div-item-info {{
  display: flex;
  flex-direction: column;
  gap: 2px;
}}
.bb-div-item-ticker {{
  color: #ff9500;
  font-size: 12px;
  font-weight: 600;
}}
.bb-div-item-name {{
  color: #666;
  font-size: 10px;
}}
.bb-div-item-details {{
  text-align: right;
}}
.bb-div-item-date {{
  color: #888;
  font-size: 10px;
}}
.bb-div-item-amount {{
  color: #00ff00;
  font-size: 13px;
  font-weight: 600;
}}
.bb-div-breakdown-list {{
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 8px;
}}
.bb-div-breakdown-item {{
  display: flex;
  justify-content: space-between;
  padding: 8px 10px;
  background: #111;
  border-radius: 3px;
}}
.bb-div-breakdown-ticker {{
  color: #ff9500;
  font-size: 11px;
  font-weight: 600;
}}
.bb-div-breakdown-income {{
  color: #00ff00;
  font-size: 12px;
  font-weight: 600;
}}
.bb-div-breakdown-yield {{
  color: #666;
  font-size: 10px;
}}
.bb-div-loading {{
  color: #666;
  font-size: 11px;
  text-align: center;
  padding: 20px;
}}
.bb-div-empty {{
  color: #555;
  font-size: 11px;
  text-align: center;
  padding: 15px;
  font-style: italic;
}}
</style>

<div class="bb-panel">

<div class="bb-panel-hdr"><span class="bb-panel-title">Holdings</span><span class="bb-panel-sub">Click column header to sort</span><div style="margin-left:auto;display:flex;gap:8px;"><button class="bb-btn bb-btn-trade" onclick="openTradeModal()" style="padding:4px 12px;font-size:11px;background:#ff9500;border-color:#ff9500;color:#000;font-weight:600;">⚡ TRADE</button><button class="bb-btn bb-btn-g" onclick="openAddModal()" style="padding:4px 12px;font-size:11px;">+ ADD</button></div></div>

<div class="bb-tbl"><table id="holdings-table">

<thead><tr>

<th class="col-ticker sortable" data-col="0" data-type="string">Ticker</th>

<th class="col-name sortable" data-col="1" data-type="string">Name</th>

<th class="col-qty sortable" style="text-align:right" data-col="2" data-type="number">Qty</th>

<th class="col-last sortable" style="text-align:right" data-col="3" data-type="number">Last</th>

<th class="col-mktval sortable" style="text-align:right" data-col="4" data-type="number">Mkt Val</th>

<th class="col-weight sortable" style="text-align:right" data-col="5" data-type="number">Weight</th>

<th class="col-chg sortable" style="text-align:right" data-col="6" data-type="number">%Chg</th>

<th class="col-pe sortable" style="text-align:right" data-col="7" data-type="number">P/E</th>

<th class="col-pcf sortable" style="text-align:right" data-col="8" data-type="number">P/CF</th>

<th class="col-roe sortable" style="text-align:right" data-col="9" data-type="number">ROE</th>

<th class="col-signal sortable" style="text-align:center" data-col="10" data-type="string">Signal</th>

<th class="col-actions" style="text-align:center;width:80px">Actions</th>

</tr></thead>

<tbody id="holdings-body">{pf_rows}</tbody>

</table></div>

</div>

<!-- Closed Positions Section (Collapsible) -->
<div class="bb-closed-positions" id="closed-positions-section">
<div class="bb-closed-header" onclick="toggleClosedPositions()">
<span class="bb-closed-icon">📊</span>
<span class="bb-closed-title">CLOSED POSITIONS</span>
<span class="bb-closed-count" id="closed-count">0</span>
<span class="bb-closed-pnl" id="closed-total-pnl">€0</span>
<span class="bb-closed-toggle" id="closed-toggle">▼</span>
</div>
<div class="bb-closed-content" id="closed-content" style="display:none;">
<div class="bb-tbl"><table id="closed-table">
<thead><tr>
<th>Ticker</th>
<th>Name</th>
<th style="text-align:right">Total Invested</th>
<th style="text-align:right">Total Sold</th>
<th style="text-align:right">Realized P&L</th>
<th style="text-align:right">P&L %</th>
<th style="text-align:right">Holding Days</th>
<th>Date Closed</th>
</tr></thead>
<tbody id="closed-body">
<tr><td colspan="8" style="text-align:center;padding:20px;color:#666;">Loading closed positions...</td></tr>
</tbody>
</table></div>
</div>
</div>

<style>
.bb-closed-positions {{
  margin: 8px;
  background: #0a0a0a;
  border: 1px solid #333;
  border-radius: 4px;
}}
.bb-closed-header {{
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 15px;
  cursor: pointer;
  background: linear-gradient(90deg, rgba(102,102,102,0.1) 0%, transparent 100%);
}}
.bb-closed-header:hover {{
  background: linear-gradient(90deg, rgba(102,102,102,0.2) 0%, transparent 100%);
}}
.bb-closed-icon {{
  font-size: 14px;
}}
.bb-closed-title {{
  font-size: 11px;
  font-weight: 600;
  color: #888;
  text-transform: uppercase;
  letter-spacing: 1px;
}}
.bb-closed-count {{
  background: #333;
  color: #888;
  padding: 2px 8px;
  border-radius: 10px;
  font-size: 10px;
}}
.bb-closed-pnl {{
  margin-left: auto;
  font-size: 14px;
  font-weight: 600;
}}
.bb-closed-pnl.positive {{
  color: #00ff00;
}}
.bb-closed-pnl.negative {{
  color: #ff3333;
}}
.bb-closed-toggle {{
  color: #666;
  transition: transform 0.2s;
}}
.bb-closed-toggle.open {{
  transform: rotate(180deg);
}}
.bb-closed-content {{
  border-top: 1px solid #222;
}}
#closed-table th {{
  color: #888;
  font-size: 10px;
  text-transform: uppercase;
  padding: 8px 10px;
  background: #111;
}}
#closed-table td {{
  padding: 8px 10px;
  font-size: 11px;
}}
</style>

<script>
function toggleClosedPositions() {{
    const content = document.getElementById('closed-content');
    const toggle = document.getElementById('closed-toggle');
    if (content.style.display === 'none') {{
        content.style.display = 'block';
        toggle.classList.add('open');
        loadClosedPositions();
    }} else {{
        content.style.display = 'none';
        toggle.classList.remove('open');
    }}
}}

function loadClosedPositions() {{
    fetch('/?action=get_closed_positions')
        .then(r => r.json())
        .then(data => {{
            if (!data.success) {{
                console.error('Error loading closed positions:', data.error);
                return;
            }}
            const positions = data.data || [];
            const tbody = document.getElementById('closed-body');
            const countEl = document.getElementById('closed-count');
            const pnlEl = document.getElementById('closed-total-pnl');

            countEl.textContent = positions.length;

            if (positions.length === 0) {{
                tbody.innerHTML = '<tr><td colspan="8" style="text-align:center;padding:20px;color:#666;">No closed positions yet</td></tr>';
                pnlEl.textContent = '€0';
                return;
            }}

            let totalPnl = 0;
            tbody.innerHTML = positions.map(p => {{
                totalPnl += p.realized_pnl || 0;
                const pnlClass = p.realized_pnl >= 0 ? 'pos' : 'neg';
                const pnlSign = p.realized_pnl >= 0 ? '+' : '';
                const pnlPct = p.total_invested > 0 ? (p.realized_pnl / p.total_invested * 100).toFixed(1) : 0;
                return `<tr>
                    <td><a class="tk" href="/?detail=${{p.ticker}}">${{p.ticker}}</a></td>
                    <td class="nm">${{p.name || ''}}</td>
                    <td style="text-align:right">€${{p.total_invested.toLocaleString('fr-FR', {{minimumFractionDigits: 0}})}}</td>
                    <td style="text-align:right">€${{(p.total_invested + p.realized_pnl).toLocaleString('fr-FR', {{minimumFractionDigits: 0}})}}</td>
                    <td style="text-align:right" class="${{pnlClass}}">${{pnlSign}}€${{Math.abs(p.realized_pnl).toFixed(2)}}</td>
                    <td style="text-align:right" class="${{pnlClass}}">${{pnlSign}}${{pnlPct}}%</td>
                    <td style="text-align:right">${{p.holding_days}}d</td>
                    <td>${{p.close_date || '-'}}</td>
                </tr>`;
            }}).join('');

            const totalSign = totalPnl >= 0 ? '+' : '';
            pnlEl.textContent = totalSign + '€' + Math.abs(totalPnl).toLocaleString('fr-FR', {{minimumFractionDigits: 2}});
            pnlEl.className = 'bb-closed-pnl ' + (totalPnl >= 0 ? 'positive' : 'negative');
        }})
        .catch(err => {{
            console.error('Error loading closed positions:', err);
        }});
}}

// Load P&L summary for KPIs
function loadPnLSummary() {{
    fetch('/?action=get_pnl_summary')
        .then(r => r.json())
        .then(data => {{
            if (!data.success) return;
            const summary = data.data;

            // Update KPIs if elements exist
            const realizedEl = document.getElementById('kpi-realized-pnl');
            const unrealizedEl = document.getElementById('kpi-unrealized-pnl');
            const winRateEl = document.getElementById('kpi-win-rate');

            if (realizedEl) {{
                const sign = summary.total_realized_pnl >= 0 ? '+' : '';
                realizedEl.textContent = sign + '€' + Math.abs(summary.total_realized_pnl).toFixed(0);
                realizedEl.style.color = summary.total_realized_pnl >= 0 ? '#00ff00' : '#ff3333';
            }}
            if (unrealizedEl) {{
                const sign = summary.total_unrealized_pnl >= 0 ? '+' : '';
                unrealizedEl.textContent = sign + '€' + Math.abs(summary.total_unrealized_pnl).toFixed(0);
                unrealizedEl.style.color = summary.total_unrealized_pnl >= 0 ? '#00ff00' : '#ff3333';
            }}
            if (winRateEl) {{
                winRateEl.textContent = summary.win_rate.toFixed(0) + '%';
            }}

            // Update closed positions count
            const closedCount = document.getElementById('closed-count');
            if (closedCount) {{
                closedCount.textContent = summary.closed_positions?.length || 0;
            }}
        }})
        .catch(err => console.error('Error loading P&L summary:', err));
}}

// Load P&L summary on page load
setTimeout(loadPnLSummary, 500);
</script>

</div>

<div id="t1" class="tc">

<div class="bb-scr-hdr">

<div class="bb-scr-stats">

<div class="bb-scr-stat"><span>Universe</span><b style="color:#fff">{len(screener)}</b></div>

<div class="bb-scr-stat"><span>Opportunities</span><b>{opps}</b></div>

<div class="bb-scr-stat"><span>Source</span><b style="color:#00bfff">{'EOD' if (EOD_OK or has_eod_cache()) else 'Yahoo'}</b></div>

</div>

<div class="bb-scr-actions">

<select id="screener-scope" class="bb-scope-select">

<option value="france">[FR] France</option>

<option value="europe">[EU] Europe</option>

<option value="legacy">🔍‹ Legacy (52)</option>

</select>

<select id="screener-mode" class="bb-scope-select">

<option value="standard">📊 Standard</option>

<option value="ai_optimal">🤖 AI Optimal (PE<=8, ROE>=12%, Top 18)</option>

</select>

<button class="bb-btn bb-btn-g" onclick="runScreenerScan()">RUN SCAN</button>

</div>

</div>

<div class="bb-ai-criteria" id="ai-criteria-banner" style="display:none">

<span>🤖 <b>AI OPTIMAL MODE</b></span>

<span class="bb-ai-crit">PE <= 8</span>

<span class="bb-ai-crit">ROE >= 12%</span>

<span class="bb-ai-crit">Debt/Equity <= 50%</span>

<span class="bb-ai-crit">Top 18 positions</span>

</div>

<div class="bb-filters"><div class="bb-filter"><label>Country</label><select id="fC" onchange="flt()"><option value="">ALL</option><option value="FR">France</option><option value="IT">Italie</option><option value="ES">Espagne</option><option value="DE">Allemagne</option><option value="UK">UK</option><option value="BE">Belgique</option><option value="NL">Netherlands</option><option value="GR">Grece</option></select></div><div class="bb-filter"><label>Max P/E</label><input type="number" id="fP" value="15" style="width:50px" onchange="flt()"></div><div class="bb-filter"><label>Signal</label><select id="fS" onchange="flt()"><option value="">ALL</option><option value="ACHAT">BUY</option><option value="AI BUY">AI BUY</option><option value="WATCH">WATCH</option></select></div></div>

<div class="bb-panel" style="margin-top:0;border-top:0"><div class="bb-tbl" style="max-height:480px"><table><thead><tr><th>#</th><th>Ticker</th><th>Name</th><th>Country</th><th>Sector</th><th style="text-align:right">P/E</th><th style="text-align:right">ROE</th><th style="text-align:right">Debt%</th><th style="text-align:right">Score</th><th style="text-align:center">Signal</th><th>Action</th></tr></thead><tbody id="stbl"></tbody></table></div></div>

</div>

<div id="t2" class="tc"><div class="bb-panel"><div class="bb-panel-hdr"><span class="bb-panel-title">Watchlist</span><span class="bb-panel-sub">{len(watchlist)} securities</span></div><div class="bb-tbl"><table><thead><tr><th>Ticker</th><th>Name</th><th>Country</th><th>Sector</th><th>Added</th><th>Remove</th></tr></thead><tbody>{wl_rows}</tbody></table></div></div></div>

<div id="t3" class="tc">

<div class="bb-backtest">

<div class="bb-backtest-header">

<div class="bb-backtest-title">

<h2>🔬 STRATEGY BACKTESTER</h2>

<p>Test your value investing strategy on historical data (powered by EOD Historical Data)</p>

</div>

<div class="bb-backtest-status">{'<span class="bb-api-ok">âœ“ EOD API Connected</span>' if EOD_OK else '<span class="bb-api-warn">âš¡ Offline Mode (using cached data)</span>'}</div>

</div>



<div class="bb-cache-panel">

<div class="bb-cache-info">

<span class="bb-cache-icon">💾</span>

<div class="bb-cache-stats" id="cache-stats">Loading cache stats...</div>

</div>

<div class="bb-cache-actions">

<button class="bb-btn" onclick="downloadAllData('france')" id="dl-france-btn">📥 Download France Data</button>

<button class="bb-btn" onclick="downloadAllData('europe')" id="dl-europe-btn">📥 Download Europe Data</button>

<button class="bb-btn bb-btn-r" onclick="clearCache()">Clear Cache</button>

</div>

</div>



<div class="bb-backtest-config">

<div class="bb-backtest-section">

<h3>🔍… Time Period</h3>

<div class="bb-backtest-row">

<div class="bb-backtest-field">

<label>Start Date</label>

<input type="date" id="bt-start" value="2014-01-01">

</div>

<div class="bb-backtest-field">

<label>End Date</label>

<input type="date" id="bt-end" value="{datetime.now().strftime('%Y-%m-%d')}">

</div>

<div class="bb-backtest-field">

<label>Rebalancing</label>

<select id="bt-rebalance">

<option value="monthly">Monthly</option>

<option value="quarterly" selected>Quarterly</option>

<option value="semi-annual">Semi-Annual</option>

<option value="yearly">Yearly</option>

</select>

</div>

</div>

</div>



<div class="bb-backtest-section">

<h3>📊 Strategy Parameters (Higgons-Style)</h3>

<div class="bb-backtest-row">

<div class="bb-backtest-field">

<label>Max P/E Ratio (BUY)</label>

<input type="number" id="bt-pe-max" value="12" min="1" max="50">

</div>

<div class="bb-backtest-field">

<label>Min ROE % (BUY)</label>

<input type="number" id="bt-roe-min" value="10" min="0" max="100">

</div>

<div class="bb-backtest-field">

<label>Max Debt/Equity %</label>

<input type="number" id="bt-debt-max" value="100" min="0" max="500">

</div>

<div class="bb-backtest-field">

<label>Max Positions</label>

<input type="number" id="bt-max-pos" value="20" min="1" max="50">

</div>

</div>

<div class="bb-backtest-row" style="margin-top:12px">

<div class="bb-backtest-field">

<label>PE Sell Threshold</label>

<input type="number" id="bt-pe-sell" value="17" min="10" max="50">

<span style="color:#666;font-size:9px">Sell if PE rises above this</span>

</div>

<div class="bb-backtest-field">

<label>Min ROE % (HOLD)</label>

<input type="number" id="bt-roe-hold" value="8" min="0" max="50">

<span style="color:#666;font-size:9px">Sell if ROE drops below this</span>

</div>

</div>

</div>



<div class="bb-backtest-section">

<h3>💰 Capital & Benchmark</h3>

<div class="bb-backtest-row">

<div class="bb-backtest-field">

<label>Initial Capital (â‚¬)</label>

<input type="number" id="bt-capital" value="100000" min="1000" step="1000">

</div>

<div class="bb-backtest-field">

<label>Benchmark</label>

<select id="bt-benchmark">

<option value="^FCHI">CAC 40</option>

<option value="^STOXX50E">Euro Stoxx 50</option>

<option value="^STOXX">Stoxx 600</option>

<option value="^GDAXI">DAX</option>

</select>

</div>

</div>

</div>



<div class="bb-backtest-section">

<h3>🌍 Universe Selection</h3>

<div class="bb-backtest-row">

<div class="bb-backtest-field">

<label>Market Scope</label>

<div class="bb-scope-toggle">

<button type="button" class="bb-scope-btn active" id="scope-france" onclick="setScope('france')">[FR] France</button>

<button type="button" class="bb-scope-btn" id="scope-europe" onclick="setScope('europe')">[EU] Europe</button>

<button type="button" class="bb-scope-btn" id="scope-custom" onclick="setScope('custom')">âœï¸ Custom</button>

</div>

<input type="hidden" id="bt-scope" value="france">

</div>

</div>

<div class="bb-backtest-field" style="width:100%;margin-top:12px" id="custom-universe-field" style="display:none">

<label>Custom tickers (comma separated) - Leave empty to scan entire market</label>

<textarea id="bt-universe" rows="2" placeholder="Leave empty to scan all stocks in selected market, or enter specific tickers: STF.PA, CARM.PA, GTT.PA..."></textarea>

</div>

<div class="bb-scope-info" id="scope-info">

<span style="color:#00ff00">[FR] France:</span> Will scan ~200 small/mid cap stocks on Euronext Paris

</div>

</div>



<div class="bb-backtest-actions">

<button class="bb-btn bb-btn-lg bb-btn-run" onclick="runBacktest()" id="bt-run-btn">

<span>â–¶ RUN BACKTEST</span>

</button>

<button class="bb-btn bb-btn-lg" onclick="resetBacktest()">â†º RESET</button>

<div class="bb-action-separator"></div>

<button class="bb-btn bb-btn-lg bb-btn-ai" onclick="runAIOptimize()" id="ai-opt-btn" {'disabled' if not ANTHROPIC_OK else ''}>

<span>🤖 AI OPTIMIZE</span>

</button>

<select id="ai-opt-goal" class="bb-opt-goal">

<option value="balanced">Balanced (Risk/Return)</option>

<option value="max_return">Max Return</option>

<option value="max_sharpe">Max Sharpe Ratio</option>

<option value="min_drawdown">Min Drawdown</option>

</select>

</div>

</div>



<div class="bb-ai-results" id="ai-results" style="display:none">

<div class="bb-ai-results-header">

<h3>🤖 AI OPTIMIZATION RESULTS</h3>

<span class="bb-ai-confidence" id="ai-confidence"></span>

</div>



<div class="bb-ai-optimal">

<h4>âœ¨ Optimal Parameters Found</h4>

<div class="bb-ai-params" id="ai-optimal-params"></div>

<div class="bb-ai-expected" id="ai-expected-metrics"></div>

</div>



<div class="bb-ai-analysis">

<h4>📊 AI Analysis</h4>

<div class="bb-ai-analysis-text" id="ai-analysis-text"></div>

</div>



<div class="bb-ai-explanation">

<h4>💡 Explanation</h4>

<div id="ai-explanation-text"></div>

</div>



<div class="bb-ai-warnings" id="ai-warnings-section">

<h4>âš ï¸ Warnings & Limitations</h4>

<ul id="ai-warnings-list"></ul>

</div>



<div class="bb-ai-grid-results">

<h4>🔍‹ Grid Search Results (14 tests)</h4>

<div class="bb-tbl" style="max-height:200px">

<table id="ai-grid-table">

<thead><tr><th>PE<=</th><th>ROE>=</th><th>Debt<=</th><th>Pos</th><th>Return</th><th>CAGR</th><th>Sharpe</th><th>MaxDD</th></tr></thead>

<tbody id="ai-grid-body"></tbody>

</table>

</div>

</div>



<button class="bb-btn bb-btn-lg bb-btn-run" onclick="applyOptimalParams()" style="margin-top:16px">

<span>âœ… APPLY OPTIMAL & RUN BACKTEST</span>

</button>

</div>



<div class="bb-backtest-results" id="bt-results" style="display:none">

<div class="bb-backtest-results-header">

<h3>📈 BACKTEST RESULTS</h3>

<div class="bb-backtest-period" id="bt-period-display"></div>

</div>



<div class="bb-backtest-metrics" id="bt-metrics">

<!-- Filled by JS -->

</div>



<div class="bb-backtest-chart-container">

<h4>📈 P&L Evolution (based on initial capital)</h4>

<div class="bb-backtest-chart"><canvas id="btChart"></canvas></div>

<div class="bb-backtest-legend">

<span class="bt-legend-item"><span class="bt-legend-color" style="background:#00ff00"></span> Strategy P&L</span>

<span class="bt-legend-item"><span class="bt-legend-color" style="background:#ff9500"></span> Benchmark P&L (if same capital)</span>

<span class="bt-legend-item"><span class="bt-legend-color" style="background:#333;height:1px;border-top:2px dashed #666"></span> Breakeven</span>

</div>

</div>



<div class="bb-backtest-yearly" id="bt-yearly">

<h4>📊 Yearly Returns</h4>

<div class="bb-yearly-chart"><canvas id="btYearlyChart"></canvas></div>

</div>



<div class="bb-backtest-trades" id="bt-trades">

<h4>🔍‹ Trade History</h4>

<div class="bb-tbl" style="max-height:300px"><table id="bt-trades-table">

<thead><tr><th>Date</th><th>Action</th><th>Ticker</th><th>Shares</th><th>Price</th><th>Value</th><th>P&L %</th></tr></thead>

<tbody id="bt-trades-body"></tbody>

</table></div>

</div>



<div class="bb-backtest-errors" id="bt-errors" style="display:none">

<h4>âš ï¸ Warnings & Errors</h4>

<ul id="bt-errors-list"></ul>

</div>



<div class="bb-backtest-history" id="bt-history">

<h4>

<span>🔍š Saved Backtests</span>

<button class="bb-btn" onclick="loadBacktestHistory()" style="padding:4px 8px;font-size:9px">â†» Refresh</button>

</h4>

<div class="bb-history-compare">

<label style="color:#888;font-size:10px">Select backtests to compare:</label>

<button class="bb-btn" onclick="compareSelected()" id="compare-btn" disabled>📊 Compare Selected</button>

</div>

<div class="bb-tbl" style="max-height:400px">

<table class="bb-history-table">

<thead>

<tr>

<th style="width:25px"><input type="checkbox" id="select-all-bt" onchange="toggleSelectAll()"></th>

<th>Name</th>

<th>Scope</th>

<th>Period</th>

<th>Rebal</th>

<th title="PE Max Buy / PE Sell">PE B/S</th>

<th title="ROE Min Buy / ROE Min Hold">ROE B/H</th>

<th>Pos</th>

<th>Return</th>

<th>CAGR</th>

<th>Sharpe</th>

<th>MaxDD</th>

<th>Win%</th>

<th style="width:60px">Actions</th>

</tr>

</thead>

<tbody id="bt-history-body">

<tr><td colspan="14" style="text-align:center;color:#666;padding:20px">Loading...</td></tr>

</tbody>

</table>

</div>

<div class="bb-compare-chart" id="compare-chart" style="display:none">

<h5>📊 Comparison Chart</h5>

<canvas id="compareChart" height="200"></canvas>

</div>

</div>

</div>

</div>

</div>

<div class="bb-status"><div class="bb-status-l">BLOOMBERG LP | EUR Small/Mid Cap Europe</div><div class="bb-status-r">Connected <span class="blink">●</span></div></div>

<script>

// ═══ BLOOMBERG LOADER ═══

let bbgLoadStartTime = 0;

let bbgLoadInterval = null;



function showBBGLoader(positions, nav, message) {{

  const loader = document.getElementById('bbg-loader');

  bbgLoadStartTime = Date.now();



  document.getElementById('bbg-load-positions').textContent = positions || '—';

  document.getElementById('bbg-load-nav').textContent = nav || '—';

  document.getElementById('bbg-load-time').textContent = 'LOADING';

  document.getElementById('bbg-load-msg').textContent = message || 'Loading portfolio data...';



  loader.classList.add('active');



  // Update timer

  bbgLoadInterval = setInterval(() => {{

    const elapsed = Math.round((Date.now() - bbgLoadStartTime) / 1000);

    document.getElementById('bbg-load-time').textContent = elapsed + 's';

  }}, 100);

}}



function updateBBGLoader(positions, nav, message) {{

  if (positions != null) document.getElementById('bbg-load-positions').textContent = positions;

  if (nav != null) document.getElementById('bbg-load-nav').textContent = nav;

  if (message) document.getElementById('bbg-load-msg').textContent = message;

}}



function hideBBGLoader() {{

  const loader = document.getElementById('bbg-loader');

  loader.classList.remove('active');

  if (bbgLoadInterval) {{

    clearInterval(bbgLoadInterval);

    bbgLoadInterval = null;

  }}

}}



// Show loader on page load, hide after content is ready

showBBGLoader({len(active)}, '{tv:,.0f} EUR', 'Loading portfolio data...');

setTimeout(() => {{

  updateBBGLoader({len(active)}, '{tv:,.0f} EUR', 'Portfolio loaded successfully!');

  setTimeout(() => hideBBGLoader(), 500);

}}, 800);



var scr={json.dumps(screener)};

var wl={json.dumps([w['ticker'] for w in watchlist])};

function showTab(n){{document.querySelectorAll('.bb-tab').forEach((t,i)=>t.classList.toggle('active',i===n));document.querySelectorAll('.fkey').forEach((f,i)=>{{if(i<3)f.classList.toggle('active',i===n)}});document.querySelectorAll('.tc').forEach((c,i)=>c.classList.toggle('active',i===n))}}

function render(d){{var tb=document.getElementById('stbl');tb.innerHTML='';d.sort((a,b)=>(b.score||0)-(a.score||0)).forEach((s,idx)=>{{var sig=s.signal||'';var cls=sig==='ACHAT'?'sig-buy':sig==='AI BUY'?'sig-ai':sig==='CHER'?'sig-sell':sig==='WATCH'?'sig-watch':'sig-hold';var inW=wl.includes(s.ticker);var rank=s.ai_rank||(idx+1);var debtPct=s.debt_equity?(s.debt_equity<5?(s.debt_equity*100).toFixed(0):s.debt_equity.toFixed(0))+'%':'-';var roePct=s.roe?(s.roe<1?(s.roe*100).toFixed(0):s.roe.toFixed(0))+'%':'-';tb.innerHTML+='<tr><td style="color:#666">'+rank+'</td><td><a class="tk" href="/?detail='+s.ticker+'">'+s.ticker+'</a></td><td class="nm">'+s.name+'</td><td>'+s.country+'</td><td>'+s.sector+'</td><td class="r">'+(s.pe?s.pe.toFixed(1):'-')+'</td><td class="r">'+roePct+'</td><td class="r">'+debtPct+'</td><td class="r">'+(s.score||'-')+'</td><td class="c"><span class="sig '+cls+'">'+sig+'</span></td><td><button class="bb-btn" onclick="addW(\\''+s.ticker+'\\',\\''+encodeURIComponent(s.name)+'\\',\\''+s.country+'\\',\\''+encodeURIComponent(s.sector)+'\\')\"'+(inW?' disabled style="opacity:0.3"':'')+'>'+(inW?'ADDED':'+ WATCH')+'</button></td></tr>'}})}}

render(scr);

function flt(){{var c=document.getElementById('fC').value,pe=parseFloat(document.getElementById('fP').value)||999,sig=document.getElementById('fS').value;render(scr.filter(s=>(!c||s.country===c)&&(!s.pe||s.pe<=pe)&&(!sig||s.signal===sig)))}}

function addW(t,n,c,s){{fetch('/?action=addwatch&ticker='+t+'&name='+n+'&country='+c+'&sector='+s).then(()=>location.reload())}}

function rmW(t){{fetch('/?action=rmwatch&ticker='+t).then(()=>location.reload())}}

function runScreenerScan(){{

    const scope = document.getElementById('screener-scope').value;

    const mode = document.getElementById('screener-mode').value;

    const modeText = mode === 'ai_optimal' ? 'AI Optimal (PE<=8, ROE>=12%, Top 18)' : 'Standard';

    if(confirm('Run ' + modeText + ' scan on ' + scope + ' universe? This may take a few minutes.')){{

        location.href='/?screener=1&scope=' + scope + '&mode=' + mode;

    }}

}}

document.getElementById('screener-mode')?.addEventListener('change', function(){{

    const banner = document.getElementById('ai-criteria-banner');

    if(this.value === 'ai_optimal'){{

        banner.style.display = 'flex';

    }} else {{

        banner.style.display = 'none';

    }}

}});

// Sort Holdings table

(function(){{

const table=document.getElementById('holdings-table');

if(!table)return;

const headers=table.querySelectorAll('th.sortable');

const tbody=document.getElementById('holdings-body');

let currentSort={{col:-1,asc:true}};

headers.forEach(th=>{{

th.addEventListener('click',function(){{

const col=parseInt(this.dataset.col);

const type=this.dataset.type;

const asc=currentSort.col===col?!currentSort.asc:true;

currentSort={{col,asc}};

headers.forEach(h=>h.classList.remove('asc','desc'));

this.classList.add(asc?'asc':'desc');

const rows=Array.from(tbody.querySelectorAll('tr'));

rows.sort((a,b)=>{{

let aVal=a.cells[col].textContent.trim();

let bVal=b.cells[col].textContent.trim();

if(type==='number'){{

aVal=parseFloat(aVal.replace(/[^0-9.-]/g,''))||0;

bVal=parseFloat(bVal.replace(/[^0-9.-]/g,''))||0;

return asc?aVal-bVal:bVal-aVal;

}}else{{

return asc?aVal.localeCompare(bVal):bVal.localeCompare(aVal);

}}

}});

rows.forEach(row=>tbody.appendChild(row));

}});

}});

}})();

// NAV Chart

const navData = {nav_history_json};

let navPeriod = 365;



function setNavPeriod(days) {{

    navPeriod = days;

    document.querySelectorAll('.bb-portfolio-chart .bb-chart-period button').forEach(b => b.classList.remove('active'));

    const btnId = days === 7 ? 'nav-1w' : days === 30 ? 'nav-1m' : days === 90 ? 'nav-3m' : 'nav-1y';

    document.getElementById(btnId).classList.add('active');

    drawNavChart();

}}



function drawNavChart() {{

    const canvas = document.getElementById('navChart');

    if (!canvas || !navData.length) return;

    

    const ctx = canvas.getContext('2d');

    const rect = canvas.parentElement.getBoundingClientRect();

    canvas.width = rect.width;

    canvas.height = rect.height;

    

    const data = navData.slice(-navPeriod);

    if (data.length < 2) {{

        ctx.fillStyle = '#666';

        ctx.font = '12px JetBrains Mono';

        ctx.textAlign = 'center';

        ctx.fillText('Not enough data yet. Refresh daily to track performance.', canvas.width/2, canvas.height/2);

        return;

    }}

    

    const navs = data.map(d => d.nav);

    const minNav = Math.min(...navs) * 0.99;

    const maxNav = Math.max(...navs) * 1.01;

    const navRange = maxNav - minNav || 1;

    

    const padding = {{ top: 15, right: 70, bottom: 25, left: 10 }};

    const chartWidth = canvas.width - padding.left - padding.right;

    const chartHeight = canvas.height - padding.top - padding.bottom;

    

    ctx.fillStyle = '#050505';

    ctx.fillRect(0, 0, canvas.width, canvas.height);

    

    // Grid

    ctx.strokeStyle = '#1a1a1a';

    ctx.lineWidth = 1;

    for (let i = 0; i <= 4; i++) {{

        const y = padding.top + (chartHeight / 4) * i;

        ctx.beginPath();

        ctx.moveTo(padding.left, y);

        ctx.lineTo(canvas.width - padding.right, y);

        ctx.stroke();

        

        const nav = maxNav - (navRange / 4) * i;

        ctx.fillStyle = '#666';

        ctx.font = '10px JetBrains Mono';

        ctx.textAlign = 'left';

        ctx.fillText(nav.toFixed(0), canvas.width - padding.right + 5, y + 4);

    }}

    

    // Cost basis line

    const avgCost = data[0].cost;

    if (avgCost > minNav && avgCost < maxNav) {{

        const costY = padding.top + ((maxNav - avgCost) / navRange) * chartHeight;

        ctx.strokeStyle = '#ff9500';

        ctx.setLineDash([3, 3]);

        ctx.beginPath();

        ctx.moveTo(padding.left, costY);

        ctx.lineTo(canvas.width - padding.right, costY);

        ctx.stroke();

        ctx.setLineDash([]);

        ctx.fillStyle = '#ff9500';

        ctx.font = '9px JetBrains Mono';

        ctx.fillText('COST', canvas.width - padding.right + 5, costY - 5);

    }}

    

    const isPositive = navs[navs.length - 1] >= navs[0];

    const lineColor = isPositive ? '#00ff00' : '#ff3b30';

    const fillColor = isPositive ? 'rgba(0, 255, 0, 0.15)' : 'rgba(255, 59, 48, 0.15)';

    

    // Area fill

    ctx.beginPath();

    ctx.moveTo(padding.left, padding.top + chartHeight);

    data.forEach((d, i) => {{

        const x = padding.left + (i / (data.length - 1)) * chartWidth;

        const y = padding.top + ((maxNav - d.nav) / navRange) * chartHeight;

        ctx.lineTo(x, y);

    }});

    ctx.lineTo(padding.left + chartWidth, padding.top + chartHeight);

    ctx.closePath();

    ctx.fillStyle = fillColor;

    ctx.fill();

    

    // Line

    ctx.beginPath();

    ctx.strokeStyle = lineColor;

    ctx.lineWidth = 2;

    data.forEach((d, i) => {{

        const x = padding.left + (i / (data.length - 1)) * chartWidth;

        const y = padding.top + ((maxNav - d.nav) / navRange) * chartHeight;

        if (i === 0) ctx.moveTo(x, y);

        else ctx.lineTo(x, y);

    }});

    ctx.stroke();

    

    // Current NAV

    const lastNav = navs[navs.length - 1];

    const lastY = padding.top + ((maxNav - lastNav) / navRange) * chartHeight;

    ctx.fillStyle = lineColor;

    ctx.font = 'bold 11px JetBrains Mono';

    ctx.fillText(lastNav.toFixed(0), canvas.width - padding.right + 5, lastY + 4);

    

    // Date labels

    ctx.fillStyle = '#666';

    ctx.font = '9px JetBrains Mono';

    ctx.textAlign = 'center';

    const labelCount = Math.min(5, data.length);

    for (let i = 0; i < labelCount; i++) {{

        const idx = Math.floor((i / (labelCount - 1)) * (data.length - 1));

        const x = padding.left + (idx / (data.length - 1)) * chartWidth;

        const date = new Date(data[idx].date);

        const label = date.toLocaleDateString('fr-FR', {{ month: 'short', day: 'numeric' }});

        ctx.fillText(label, x, canvas.height - 8);

    }}

}}



setTimeout(drawNavChart, 100);

window.addEventListener('resize', drawNavChart);



// ============= BACKTEST FUNCTIONS =============

let backtestResults = null;



// ============= CACHE FUNCTIONS =============

function loadCacheStats() {{

    fetch('/?action=cache_stats')

        .then(r => r.json())

        .then(stats => {{

            document.getElementById('cache-stats').innerHTML = 

                `<span>${{stats.fundamentals}}</span> fundamentals | ` +

                `<span>${{stats.prices}}</span> price series | ` +

                `<span>${{stats.total_size_mb}} MB</span> total`;

        }})

        .catch(() => {{

            document.getElementById('cache-stats').innerHTML = 'Unable to load cache stats';

        }});

}}



function downloadAllData(scope) {{

    const btn = document.getElementById('dl-' + scope + '-btn');

    const originalText = btn.innerHTML;

    btn.disabled = true;

    btn.innerHTML = 'â³ Downloading...';

    

    fetch('/?action=download_data&scope=' + scope, {{method: 'POST'}})

        .then(r => r.json())

        .then(result => {{

            btn.disabled = false;

            btn.innerHTML = originalText;

            

            if (result.error) {{

                alert('Error: ' + result.error);

            }} else {{

                alert(`Download complete!\\nâœ… Success: ${{result.success}}\\nâŒ Errors: ${{result.errors}}\\nTotal: ${{result.total}} tickers`);

                loadCacheStats();

            }}

        }})

        .catch(err => {{

            btn.disabled = false;

            btn.innerHTML = originalText;

            alert('Error: ' + err);

        }});

}}



function clearCache() {{

    if (!confirm('Are you sure you want to delete all cached data? You will need to re-download it.')) return;

    

    fetch('/?action=clear_cache', {{method: 'POST'}})

        .then(r => r.json())

        .then(result => {{

            alert(result.message || 'Cache cleared');

            loadCacheStats();

        }})

        .catch(err => alert('Error: ' + err));

}}



// Load cache stats on page load

setTimeout(loadCacheStats, 500);

// ============== ALERTS FUNCTIONS ==============

function loadAlerts() {{
    fetch('/?action=get_alerts')
        .then(r => r.json())
        .then(data => {{
            displayAlerts(data.alerts || []);
        }})
        .catch(err => {{
            console.error('Error loading alerts:', err);
        }});
}}

function checkAlerts() {{
    const btn = event.target;
    btn.disabled = true;
    btn.textContent = '⏳ Checking...';

    fetch('/?action=check_alerts')
        .then(r => r.json())
        .then(data => {{
            displayAlerts(data.alerts || []);
            btn.disabled = false;
            btn.textContent = '🔄 REFRESH';
        }})
        .catch(err => {{
            console.error('Error checking alerts:', err);
            btn.disabled = false;
            btn.textContent = '🔄 REFRESH';
        }});
}}

function displayAlerts(alerts) {{
    const panel = document.getElementById('alerts-panel');
    const list = document.getElementById('alerts-list');
    const count = document.getElementById('alerts-count');
    const icon = document.getElementById('alerts-icon');

    if (!alerts || alerts.length === 0) {{
        panel.style.display = 'none';
        return;
    }}

    panel.style.display = 'block';
    count.textContent = alerts.length;
    icon.classList.add('active');

    list.innerHTML = alerts.map(a => {{
        const typeClass = a.alert_type.toLowerCase().replace('_', '-');
        const alertId = `alert-${{a.ticker}}-${{a.alert_type}}`;
        return `
            <div class="bb-alert-item ${{typeClass}}" id="${{alertId}}">
                <span class="bb-alert-ticker">${{a.ticker}}</span>
                <span class="bb-alert-name">${{a.name}}</span>
                <span class="bb-alert-message">${{a.message}}</span>
                <div class="bb-alert-actions">
                    <button class="bb-alert-btn" onclick="window.location.href='/?detail=${{a.ticker}}'">DETAIL</button>
                    <button class="bb-alert-btn dismiss" onclick="dismissAlert('${{a.ticker}}', '${{a.alert_type}}', this)">✕</button>
                </div>
            </div>
        `;
    }}).join('');
}}

function dismissAlert(ticker, alertType, btn) {{
    // Immediately hide the alert for instant feedback
    const alertEl = document.getElementById(`alert-${{ticker}}-${{alertType}}`);
    if (alertEl) {{
        alertEl.style.opacity = '0.3';
        alertEl.style.pointerEvents = 'none';
    }}
    if (btn) btn.textContent = '...';

    fetch(`/?action=dismiss_alert&ticker=${{ticker}}&alert_type=${{alertType}}`)
        .then(r => r.json())
        .then(data => {{
            if (data.success) {{
                // Remove element from DOM
                if (alertEl) alertEl.remove();
                // Update alert count
                const remaining = document.querySelectorAll('.bb-alert-item').length;
                const count = document.getElementById('alerts-count');
                if (count) count.textContent = remaining;
                if (remaining === 0) {{
                    document.getElementById('alerts-panel').style.display = 'none';
                    document.getElementById('alerts-icon').classList.remove('active');
                }}
            }} else {{
                // Restore if failed
                if (alertEl) {{
                    alertEl.style.opacity = '1';
                    alertEl.style.pointerEvents = 'auto';
                }}
                if (btn) btn.textContent = '✕';
            }}
        }})
        .catch(err => {{
            console.error('Error dismissing alert:', err);
            // Restore on error
            if (alertEl) {{
                alertEl.style.opacity = '1';
                alertEl.style.pointerEvents = 'auto';
            }}
            if (btn) btn.textContent = '✕';
        }});
}}

// Load alerts on page load (delayed to not block initial render)
setTimeout(loadAlerts, 1000);

// ============== BENCHMARK COMPARISON ==============

let currentBenchmark = 'CACMS';
let currentBenchPeriod = '1Y';
let benchmarkChart = null;

function setBenchmark(benchmark) {{
    currentBenchmark = benchmark;
    document.querySelectorAll('.bb-bench-btn').forEach(b => b.classList.remove('active'));
    document.getElementById('bench-' + benchmark).classList.add('active');
    loadBenchmarkData();
}}

function setBenchPeriod(period) {{
    currentBenchPeriod = period;
    document.querySelectorAll('.bb-benchmark-period button').forEach(b => b.classList.remove('active'));
    document.getElementById('bench-' + period.toLowerCase()).classList.add('active');
    loadBenchmarkData();
}}

function loadBenchmarkData() {{
    fetch(`/?action=benchmark_compare&benchmark=${{currentBenchmark}}&period=${{currentBenchPeriod}}`)
        .then(r => r.json())
        .then(data => {{
            if (data.error) {{
                console.error('Benchmark error:', data.error);
                return;
            }}
            displayBenchmarkChart(data);
            displayBenchmarkMetrics(data.metrics);
        }})
        .catch(err => console.error('Error loading benchmark:', err));
}}

function displayBenchmarkChart(data) {{
    const ctx = document.getElementById('benchmarkChart');
    if (!ctx) return;

    const portfolio = data.portfolio || [];
    const benchmark = data.benchmark || [];

    if (portfolio.length === 0 && benchmark.length === 0) {{
        return;
    }}

    // Align data by date
    const portfolioMap = {{}};
    const benchmarkMap = {{}};
    portfolio.forEach(p => portfolioMap[p.date] = p.close);
    benchmark.forEach(b => benchmarkMap[b.date] = b.close);

    const allDates = [...new Set([...Object.keys(portfolioMap), ...Object.keys(benchmarkMap)])].sort();

    const labels = allDates;
    const portfolioData = allDates.map(d => portfolioMap[d] || null);
    const benchmarkData = allDates.map(d => benchmarkMap[d] || null);

    if (benchmarkChart) {{
        benchmarkChart.destroy();
    }}

    benchmarkChart = new Chart(ctx.getContext('2d'), {{
        type: 'line',
        data: {{
            labels: labels,
            datasets: [
                {{
                    label: 'Portfolio',
                    data: portfolioData,
                    borderColor: '#ff9500',
                    backgroundColor: 'rgba(255,149,0,0.1)',
                    borderWidth: 2,
                    pointRadius: 0,
                    fill: false,
                    tension: 0.1
                }},
                {{
                    label: data.benchmark_info?.name || 'Benchmark',
                    data: benchmarkData,
                    borderColor: '#666',
                    backgroundColor: 'rgba(102,102,102,0.1)',
                    borderWidth: 1.5,
                    pointRadius: 0,
                    fill: false,
                    tension: 0.1,
                    borderDash: [5, 5]
                }}
            ]
        }},
        options: {{
            responsive: true,
            maintainAspectRatio: false,
            interaction: {{
                intersect: false,
                mode: 'index'
            }},
            plugins: {{
                legend: {{
                    display: true,
                    position: 'top',
                    labels: {{
                        color: '#888',
                        font: {{ size: 10 }},
                        boxWidth: 15
                    }}
                }},
                tooltip: {{
                    backgroundColor: '#1a1a1a',
                    borderColor: '#333',
                    borderWidth: 1,
                    titleColor: '#ff9500',
                    bodyColor: '#fff',
                    callbacks: {{
                        label: function(ctx) {{
                            return ctx.dataset.label + ': ' + (ctx.raw ? ctx.raw.toFixed(1) : '--');
                        }}
                    }}
                }}
            }},
            scales: {{
                x: {{
                    display: true,
                    grid: {{ color: '#1a1a1a' }},
                    ticks: {{
                        color: '#666',
                        font: {{ size: 9 }},
                        maxTicksLimit: 8,
                        callback: function(val, i) {{
                            const label = this.getLabelForValue(val);
                            return label ? label.slice(5) : ''; // Show MM-DD
                        }}
                    }}
                }},
                y: {{
                    display: true,
                    grid: {{ color: '#1a1a1a' }},
                    ticks: {{
                        color: '#666',
                        font: {{ size: 9 }},
                        callback: v => v.toFixed(0)
                    }},
                    suggestedMin: 80,
                    suggestedMax: 120
                }}
            }}
        }}
    }});
}}

function displayBenchmarkMetrics(metrics) {{
    if (!metrics) return;

    // Alpha
    const alphaEl = document.getElementById('alpha-value');
    const alpha = metrics.alpha || 0;
    alphaEl.textContent = (alpha >= 0 ? '+' : '') + alpha.toFixed(1) + '%';
    alphaEl.className = 'bb-alpha-value ' + (alpha >= 0 ? '' : 'negative');

    // Portfolio return
    const portfolioEl = document.getElementById('metric-portfolio');
    const pRet = metrics.portfolio_return || 0;
    portfolioEl.textContent = (pRet >= 0 ? '+' : '') + pRet.toFixed(1) + '%';
    portfolioEl.className = 'bb-bench-metric-value ' + (pRet >= 0 ? 'pos' : 'neg');

    // Benchmark return
    const benchEl = document.getElementById('metric-benchmark');
    const bRet = metrics.benchmark_return || 0;
    benchEl.textContent = (bRet >= 0 ? '+' : '') + bRet.toFixed(1) + '%';
    benchEl.className = 'bb-bench-metric-value ' + (bRet >= 0 ? 'pos' : 'neg');

    // Beta
    document.getElementById('metric-beta').textContent = (metrics.beta || 0).toFixed(2);

    // Sharpe
    const sharpe = metrics.sharpe_ratio || 0;
    const sharpeEl = document.getElementById('metric-sharpe');
    sharpeEl.textContent = sharpe.toFixed(2);
    sharpeEl.className = 'bb-bench-metric-value ' + (sharpe >= 1 ? 'pos' : sharpe < 0 ? 'neg' : '');

    // Max Drawdown
    const maxDD = metrics.portfolio_max_dd || 0;
    const maxDDEl = document.getElementById('metric-maxdd');
    maxDDEl.textContent = '-' + Math.abs(maxDD).toFixed(1) + '%';
    maxDDEl.className = 'bb-bench-metric-value neg';

    // Tracking Error
    document.getElementById('metric-tracking').textContent = (metrics.tracking_error || 0).toFixed(1) + '%';

    // Update top KPIs bar
    const kpiAlpha = document.getElementById('kpi-alpha');
    if (kpiAlpha) {{
        kpiAlpha.textContent = (alpha >= 0 ? '+' : '') + alpha.toFixed(1) + '%';
        kpiAlpha.style.color = alpha >= 0 ? '#00ff00' : '#ff3333';
    }}

    const kpiBeta = document.getElementById('kpi-beta');
    if (kpiBeta) {{
        kpiBeta.textContent = (metrics.beta || 0).toFixed(2);
    }}

    const kpiSharpe = document.getElementById('kpi-sharpe');
    if (kpiSharpe) {{
        kpiSharpe.textContent = sharpe.toFixed(2);
        kpiSharpe.style.color = sharpe >= 1 ? '#00ff00' : sharpe < 0 ? '#ff3333' : '#fff';
    }}
}}

// Load benchmark data on page load
setTimeout(loadBenchmarkData, 1500);

// ============== DIVIDENDS CALENDAR ==============

let currentDivPeriod = 3;

function setDivPeriod(months) {{
    currentDivPeriod = months;
    document.querySelectorAll('.bb-div-period').forEach(b => b.classList.remove('active'));
    document.getElementById('div-' + months + 'm').classList.add('active');
    loadDividendData();
}}

function loadDividendData() {{
    // Load income projection
    fetch('/?action=dividends_income')
        .then(r => r.json())
        .then(data => {{
            if (data.error) {{
                console.error('Dividend income error:', data.error);
                return;
            }}
            displayDividendSummary(data);
            displayDividendBreakdown(data.breakdown || []);
        }})
        .catch(err => console.error('Error loading dividend income:', err));

    // Load calendar
    fetch(`/?action=dividends_calendar&months=${{currentDivPeriod}}`)
        .then(r => r.json())
        .then(data => {{
            if (data.error) {{
                console.error('Dividend calendar error:', data.error);
                return;
            }}
            displayUpcomingDividends(data.upcoming || []);
        }})
        .catch(err => console.error('Error loading dividend calendar:', err));
}}

function displayDividendSummary(data) {{
    const annualEl = document.getElementById('div-annual-income');
    const monthlyEl = document.getElementById('div-monthly');
    const yieldEl = document.getElementById('div-yield');
    const payersEl = document.getElementById('div-payers');

    if (annualEl) {{
        annualEl.textContent = '€' + (data.total_annual_income || 0).toLocaleString('fr-FR', {{minimumFractionDigits: 0}});
    }}
    if (monthlyEl) {{
        monthlyEl.textContent = '€' + (data.monthly_average || 0).toLocaleString('fr-FR', {{minimumFractionDigits: 0}});
    }}
    if (payersEl) {{
        payersEl.textContent = (data.positions_with_dividends || 0) + '/' + (data.total_positions || 0);
    }}

    // Calculate portfolio yield (needs total portfolio value)
    // For now just show number of payers
}}

function displayUpcomingDividends(upcoming) {{
    const listEl = document.getElementById('div-upcoming-list');
    if (!listEl) return;

    if (!upcoming || upcoming.length === 0) {{
        listEl.innerHTML = '<div class="bb-div-empty">No upcoming dividends in the next ' + currentDivPeriod + ' months</div>';
        return;
    }}

    listEl.innerHTML = upcoming.map(div => `
        <div class="bb-div-item upcoming">
            <div class="bb-div-item-info">
                <span class="bb-div-item-ticker">${{div.ticker}}</span>
                <span class="bb-div-item-name">${{div.name || ''}}</span>
            </div>
            <div class="bb-div-item-details">
                <span class="bb-div-item-date">${{formatDivDate(div.ex_date)}}</span>
                <span class="bb-div-item-amount">€${{div.expected_income.toFixed(2)}}</span>
            </div>
        </div>
    `).join('');
}}

function displayDividendBreakdown(breakdown) {{
    const listEl = document.getElementById('div-breakdown-list');
    if (!listEl) return;

    if (!breakdown || breakdown.length === 0) {{
        listEl.innerHTML = '<div class="bb-div-empty">No dividend data available</div>';
        return;
    }}

    // Show top 6 contributors
    const top = breakdown.slice(0, 6);
    listEl.innerHTML = top.map(item => `
        <div class="bb-div-breakdown-item">
            <div>
                <span class="bb-div-breakdown-ticker">${{item.ticker}}</span>
                <span class="bb-div-breakdown-yield">${{item.dividend_yield.toFixed(1)}}%</span>
            </div>
            <span class="bb-div-breakdown-income">€${{item.annual_income.toFixed(0)}}/yr</span>
        </div>
    `).join('');
}}

function formatDivDate(dateStr) {{
    if (!dateStr) return '';
    const d = new Date(dateStr);
    const now = new Date();
    const diffDays = Math.floor((d - now) / (1000 * 60 * 60 * 24));

    const formatted = d.toLocaleDateString('fr-FR', {{ day: '2-digit', month: 'short' }});

    if (diffDays <= 7) {{
        return formatted + ' (' + diffDays + 'j)';
    }}
    return formatted;
}}

// Load dividend data on page load
setTimeout(loadDividendData, 2000);

function setScope(scope) {{

    document.querySelectorAll('.bb-scope-btn').forEach(b => b.classList.remove('active'));

    document.getElementById('scope-' + scope).classList.add('active');

    document.getElementById('bt-scope').value = scope;

    

    const customField = document.getElementById('custom-universe-field');

    const infoDiv = document.getElementById('scope-info');

    

    if (scope === 'france') {{

        customField.style.display = 'none';

        infoDiv.innerHTML = '<span style="color:#00ff00">[FR] France:</span> Will scan ~200 small/mid cap stocks on Euronext Paris';

    }} else if (scope === 'europe') {{

        customField.style.display = 'none';

        infoDiv.innerHTML = '<span style="color:#00bfff">[EU] Europe:</span> Will scan ~500+ stocks across major European exchanges (PA, AS, BR, MI, MC, XETRA, LSE, SW)';

    }} else {{

        customField.style.display = 'block';

        infoDiv.innerHTML = '<span style="color:#ff9500">âœï¸ Custom:</span> Enter specific tickers to test';

    }}

}}



function runBacktest() {{

    const btn = document.getElementById('bt-run-btn');

    btn.disabled = true;

    btn.innerHTML = '<div class="spinner" style="width:16px;height:16px;border-width:2px;display:inline-block;vertical-align:middle;margin-right:8px"></div> Loading data & running simulation...';

    

    const scope = document.getElementById('bt-scope').value;

    const customUniverse = document.getElementById('bt-universe').value;

    

    const params = {{

        start_date: document.getElementById('bt-start').value,

        end_date: document.getElementById('bt-end').value,

        rebalance_freq: document.getElementById('bt-rebalance').value,

        pe_max: document.getElementById('bt-pe-max').value,

        roe_min: document.getElementById('bt-roe-min').value,

        pe_sell: document.getElementById('bt-pe-sell').value,

        roe_min_hold: document.getElementById('bt-roe-hold').value,

        debt_equity_max: document.getElementById('bt-debt-max').value,

        max_positions: document.getElementById('bt-max-pos').value,

        initial_capital: document.getElementById('bt-capital').value,

        benchmark: document.getElementById('bt-benchmark').value,

        universe_scope: scope,

        universe: scope === 'custom' ? customUniverse : ''

    }};

    

    fetch('/?action=run_backtest', {{

        method: 'POST',

        headers: {{'Content-Type': 'application/json'}},

        body: JSON.stringify(params)

    }})

    .then(r => r.json())

    .then(data => {{

        btn.disabled = false;

        btn.innerHTML = '<span>â–¶ RUN BACKTEST</span>';

        

        if (data.error) {{

            alert('Error: ' + data.error);

            return;

        }}

        

        backtestResults = data;

        displayBacktestResults(data);

    }})

    .catch(err => {{

        btn.disabled = false;

        btn.innerHTML = '<span>â–¶ RUN BACKTEST</span>';

        alert('Error: ' + err);

    }});

}}



function displayBacktestResults(data) {{

    document.getElementById('bt-results').style.display = 'block';

    

    const m = data.metrics || {{}};

    const params = data.params || {{}};

    

    // Period display

    document.getElementById('bt-period-display').innerHTML = 

        `${{params.start_date}} â†’ ${{params.end_date}} | ${{data.equity_curve?.length || 0}} rebalancing periods`;

    

    // Metrics

    const metricsHtml = `

        <div class="bb-metric-card highlight">

            <span class="bb-metric-card-label">Total Return</span>

            <span class="bb-metric-card-value ${{m.total_return >= 0 ? 'pos' : 'neg'}}">${{m.total_return?.toFixed(1) || 0}}%</span>

            <span class="bb-metric-card-sub">vs Benchmark: ${{m.benchmark_return?.toFixed(1) || 0}}%</span>

        </div>

        <div class="bb-metric-card">

            <span class="bb-metric-card-label">CAGR</span>

            <span class="bb-metric-card-value ${{m.cagr >= 0 ? 'pos' : 'neg'}}">${{m.cagr?.toFixed(2) || 0}}%</span>

            <span class="bb-metric-card-sub">Annualized</span>

        </div>

        <div class="bb-metric-card">

            <span class="bb-metric-card-label">Max Drawdown</span>

            <span class="bb-metric-card-value neg">-${{m.max_drawdown?.toFixed(1) || 0}}%</span>

        </div>

        <div class="bb-metric-card">

            <span class="bb-metric-card-label">Sharpe Ratio</span>

            <span class="bb-metric-card-value">${{m.sharpe?.toFixed(2) || 0}}</span>

        </div>

        <div class="bb-metric-card">

            <span class="bb-metric-card-label">Win Rate</span>

            <span class="bb-metric-card-value">${{m.win_rate?.toFixed(0) || 0}}%</span>

            <span class="bb-metric-card-sub">${{m.total_trades || 0}} trades</span>

        </div>

        <div class="bb-metric-card highlight">

            <span class="bb-metric-card-label">Alpha</span>

            <span class="bb-metric-card-value ${{m.alpha >= 0 ? 'pos' : 'neg'}}">${{m.alpha >= 0 ? '+' : ''}}${{m.alpha?.toFixed(1) || 0}}%</span>

            <span class="bb-metric-card-sub">vs Benchmark</span>

        </div>

    `;

    document.getElementById('bt-metrics').innerHTML = metricsHtml;

    

    // Draw equity curve

    setTimeout(() => drawEquityCurve(data), 100);

    

    // Draw yearly returns

    setTimeout(() => drawYearlyReturns(data.yearly_returns || []), 100);

    

    // Trades table

    const trades = data.trades || [];

    let tradesHtml = '';

    trades.slice(-50).reverse().forEach(t => {{

        const pnlClass = t.pnl_pct > 0 ? 'pos' : (t.pnl_pct < 0 ? 'neg' : '');

        const actionClass = t.action === 'BUY' ? 'sig-achat' : 'sig-ecarter';

        tradesHtml += `<tr>

            <td>${{t.date}}</td>

            <td><span class="sig ${{actionClass}}">${{t.action}}</span></td>

            <td>${{t.ticker}}</td>

            <td class="r">${{t.shares}}</td>

            <td class="r">${{t.price?.toFixed(2)}}</td>

            <td class="r">${{t.value?.toFixed(0)}}</td>

            <td class="r ${{pnlClass}}">${{t.pnl_pct ? (t.pnl_pct > 0 ? '+' : '') + t.pnl_pct.toFixed(1) + '%' : '-'}}</td>

        </tr>`;

    }});

    document.getElementById('bt-trades-body').innerHTML = tradesHtml || '<tr><td colspan="7" style="text-align:center;color:#666">No trades</td></tr>';

    

    // Errors

    if (data.errors && data.errors.length > 0) {{

        document.getElementById('bt-errors').style.display = 'block';

        document.getElementById('bt-errors-list').innerHTML = data.errors.map(e => `<li>${{e}}</li>`).join('');

    }} else {{

        document.getElementById('bt-errors').style.display = 'none';

    }}

}}



function drawEquityCurve(data) {{

    const canvas = document.getElementById('btChart');

    if (!canvas) return;

    

    const ctx = canvas.getContext('2d');

    const rect = canvas.parentElement.getBoundingClientRect();

    canvas.width = rect.width;

    canvas.height = rect.height;

    

    const equity = data.equity_curve || [];

    const benchmark = data.benchmark_curve || [];

    const initialCapital = data.params?.initial_capital || 100000;

    

    if (equity.length < 2) return;

    

    // Calculate P&L (portfolio value - initial capital)

    const pnlData = equity.map(e => ({{

        date: e.date, 

        value: e.value,

        pnl: e.value - initialCapital

    }}));

    

    // Normalize benchmark to same scale (P&L based on initial capital)

    let benchPnl = [];

    if (benchmark.length >= 2) {{

        const bStart = benchmark[0].price;

        benchPnl = benchmark.map(b => ({{

            date: b.date, 

            pnl: ((b.price / bStart) - 1) * initialCapital

        }}));

    }}

    

    // Find min/max P&L for scale

    const allPnl = [...pnlData.map(e => e.pnl), ...benchPnl.map(b => b.pnl)];

    const minPnl = Math.min(...allPnl, 0) * 1.1;  // Include 0 and add margin

    const maxPnl = Math.max(...allPnl) * 1.1;

    const range = maxPnl - minPnl || 1;

    

    const padding = {{top: 20, right: 80, bottom: 30, left: 10}};

    const w = canvas.width - padding.left - padding.right;

    const h = canvas.height - padding.top - padding.bottom;

    

    // Clear

    ctx.fillStyle = '#050505';

    ctx.fillRect(0, 0, canvas.width, canvas.height);

    

    // Zero line (breakeven)

    const zeroY = padding.top + ((maxPnl - 0) / range) * h;

    ctx.strokeStyle = '#333';

    ctx.lineWidth = 1;

    ctx.setLineDash([5, 3]);

    ctx.beginPath();

    ctx.moveTo(padding.left, zeroY);

    ctx.lineTo(canvas.width - padding.right, zeroY);

    ctx.stroke();

    ctx.setLineDash([]);

    ctx.fillStyle = '#666';

    ctx.font = '9px JetBrains Mono';

    ctx.textAlign = 'left';

    ctx.fillText('BREAKEVEN', padding.left + 5, zeroY - 5);

    

    // Grid and Y-axis labels (P&L in euros)

    ctx.strokeStyle = '#1a1a1a';

    ctx.lineWidth = 1;

    for (let i = 0; i <= 4; i++) {{

        const y = padding.top + (h / 4) * i;

        ctx.beginPath();

        ctx.moveTo(padding.left, y);

        ctx.lineTo(canvas.width - padding.right, y);

        ctx.stroke();

        

        const pnlVal = maxPnl - (range / 4) * i;

        const pnlStr = pnlVal >= 0 ? '+' + formatEur(pnlVal) : formatEur(pnlVal);

        ctx.fillStyle = pnlVal >= 0 ? '#00ff00' : '#ff3b30';

        ctx.font = '10px JetBrains Mono';

        ctx.textAlign = 'left';

        ctx.fillText(pnlStr, canvas.width - padding.right + 5, y + 4);

    }}

    

    // Benchmark P&L line (orange)

    if (benchPnl.length > 1) {{

        ctx.beginPath();

        ctx.strokeStyle = '#ff9500';

        ctx.lineWidth = 1.5;

        benchPnl.forEach((b, i) => {{

            const x = padding.left + (i / (benchPnl.length - 1)) * w;

            const y = padding.top + ((maxPnl - b.pnl) / range) * h;

            if (i === 0) ctx.moveTo(x, y);

            else ctx.lineTo(x, y);

        }});

        ctx.stroke();

    }}

    

    // Strategy P&L line (green/red based on final result)

    const finalPnl = pnlData[pnlData.length - 1].pnl;

    const strategyColor = finalPnl >= 0 ? '#00ff00' : '#ff3b30';

    

    // Fill area under curve

    ctx.beginPath();

    ctx.moveTo(padding.left, zeroY);

    pnlData.forEach((e, i) => {{

        const x = padding.left + (i / (pnlData.length - 1)) * w;

        const y = padding.top + ((maxPnl - e.pnl) / range) * h;

        ctx.lineTo(x, y);

    }});

    ctx.lineTo(padding.left + w, zeroY);

    ctx.closePath();

    ctx.fillStyle = finalPnl >= 0 ? 'rgba(0, 255, 0, 0.1)' : 'rgba(255, 59, 48, 0.1)';

    ctx.fill();

    

    // Strategy line

    ctx.beginPath();

    ctx.strokeStyle = strategyColor;

    ctx.lineWidth = 2;

    pnlData.forEach((e, i) => {{

        const x = padding.left + (i / (pnlData.length - 1)) * w;

        const y = padding.top + ((maxPnl - e.pnl) / range) * h;

        if (i === 0) ctx.moveTo(x, y);

        else ctx.lineTo(x, y);

    }});

    ctx.stroke();

    

    // Final P&L label

    const lastX = padding.left + w;

    const lastY = padding.top + ((maxPnl - finalPnl) / range) * h;

    ctx.fillStyle = strategyColor;

    ctx.font = 'bold 11px JetBrains Mono';

    ctx.textAlign = 'left';

    const finalStr = (finalPnl >= 0 ? '+' : '') + formatEur(finalPnl);

    ctx.fillText(finalStr, lastX + 5, lastY);

    

    // Date labels (X-axis)

    ctx.fillStyle = '#666';

    ctx.font = '9px JetBrains Mono';

    ctx.textAlign = 'center';

    const labelCount = Math.min(6, pnlData.length);

    for (let i = 0; i < labelCount; i++) {{

        const idx = Math.floor((i / (labelCount - 1)) * (pnlData.length - 1));

        const x = padding.left + (idx / (pnlData.length - 1)) * w;

        ctx.fillText(pnlData[idx].date.substring(0, 7), x, canvas.height - 8);

    }}

}}



function formatEur(val) {{

    if (Math.abs(val) >= 1000000) return (val / 1000000).toFixed(1) + 'Mâ‚¬';

    if (Math.abs(val) >= 1000) return (val / 1000).toFixed(0) + 'Kâ‚¬';

    return val.toFixed(0) + 'â‚¬';

}}



function drawYearlyReturns(yearly) {{

    const canvas = document.getElementById('btYearlyChart');

    if (!canvas || !yearly.length) return;

    

    const ctx = canvas.getContext('2d');

    const rect = canvas.parentElement.getBoundingClientRect();

    canvas.width = rect.width;

    canvas.height = rect.height;

    

    const padding = {{top: 20, right: 20, bottom: 30, left: 50}};

    const w = canvas.width - padding.left - padding.right;

    const h = canvas.height - padding.top - padding.bottom;

    

    const maxRet = Math.max(...yearly.map(y => Math.abs(y.return)), 10);

    

    ctx.fillStyle = '#050505';

    ctx.fillRect(0, 0, canvas.width, canvas.height);

    

    // Zero line

    const zeroY = padding.top + h / 2;

    ctx.strokeStyle = '#333';

    ctx.beginPath();

    ctx.moveTo(padding.left, zeroY);

    ctx.lineTo(canvas.width - padding.right, zeroY);

    ctx.stroke();

    

    const barWidth = w / yearly.length * 0.7;

    const gap = w / yearly.length * 0.3;

    

    yearly.forEach((y, i) => {{

        const x = padding.left + i * (barWidth + gap) + gap / 2;

        const barH = (y.return / maxRet) * (h / 2);

        const barY = y.return >= 0 ? zeroY - barH : zeroY;

        

        ctx.fillStyle = y.return >= 0 ? '#00ff00' : '#ff3b30';

        ctx.fillRect(x, y.return >= 0 ? barY : zeroY, barWidth, Math.abs(barH));

        

        // Year label

        ctx.fillStyle = '#888';

        ctx.font = '9px JetBrains Mono';

        ctx.textAlign = 'center';

        ctx.fillText(y.year, x + barWidth / 2, canvas.height - 8);

        

        // Value label

        ctx.fillStyle = y.return >= 0 ? '#00ff00' : '#ff3b30';

        ctx.fillText((y.return >= 0 ? '+' : '') + y.return.toFixed(0) + '%', 

            x + barWidth / 2, y.return >= 0 ? barY - 5 : zeroY + Math.abs(barH) + 12);

    }});

}}



function resetBacktest() {{

    document.getElementById('bt-results').style.display = 'none';

    document.getElementById('ai-results').style.display = 'none';

    document.getElementById('bt-start').value = '2014-01-01';

    document.getElementById('bt-end').value = new Date().toISOString().split('T')[0];

    document.getElementById('bt-pe-max').value = '12';

    document.getElementById('bt-roe-min').value = '10';

    document.getElementById('bt-debt-max').value = '100';

    document.getElementById('bt-max-pos').value = '20';

    document.getElementById('bt-capital').value = '100000';

}}



// ============= AI OPTIMIZER =============

let aiOptimalParams = null;



function runAIOptimize() {{

    const btn = document.getElementById('ai-opt-btn');

    const goal = document.getElementById('ai-opt-goal').value;

    const scope = document.getElementById('bt-scope').value;

    

    btn.disabled = true;

    btn.innerHTML = '<div class="spinner" style="width:14px;height:14px;border-width:2px;display:inline-block;vertical-align:middle;margin-right:8px"></div> Optimizing... (may take 2-5 min)';

    

    document.getElementById('ai-results').style.display = 'none';

    document.getElementById('bt-results').style.display = 'none';

    

    fetch('/?action=ai_optimize&scope=' + scope + '&goal=' + goal, {{

        method: 'POST'

    }})

    .then(r => r.json())

    .then(data => {{

        btn.disabled = false;

        btn.innerHTML = '<span>🤖 AI OPTIMIZE</span>';

        

        if (data.error) {{

            alert('Error: ' + data.error);

            return;

        }}

        

        displayAIResults(data);

    }})

    .catch(err => {{

        btn.disabled = false;

        btn.innerHTML = '<span>🤖 AI OPTIMIZE</span>';

        alert('Error: ' + err);

    }});

}}



function runPortfolioAdvisor() {{
    window.location.href = '/advisor';
}}


function displayAIResults(data) {{

    document.getElementById('ai-results').style.display = 'block';

    

    // Confidence badge

    const confidence = data.confidence || 'medium';

    const confEl = document.getElementById('ai-confidence');

    confEl.className = 'bb-ai-confidence ' + confidence;

    confEl.textContent = confidence.toUpperCase() + ' CONFIDENCE';

    

    // Optimal parameters

    const params = data.best_params || {{}};

    aiOptimalParams = params;

    

    document.getElementById('ai-optimal-params').innerHTML = `

        <div class="bb-ai-param">

            <span class="bb-ai-param-label">MAX P/E</span>

            <span class="bb-ai-param-value">${{params.pe_max || '?'}}</span>

        </div>

        <div class="bb-ai-param">

            <span class="bb-ai-param-label">MIN ROE %</span>

            <span class="bb-ai-param-value">${{params.roe_min || '?'}}</span>

        </div>

        <div class="bb-ai-param">

            <span class="bb-ai-param-label">SELL PE ></span>

            <span class="bb-ai-param-value">${{params.pe_sell || '?'}}</span>

        </div>

        <div class="bb-ai-param">

            <span class="bb-ai-param-label">MAX DEBT %</span>

            <span class="bb-ai-param-value">${{params.debt_equity_max || '?'}}</span>

        </div>

        <div class="bb-ai-param">

            <span class="bb-ai-param-label">POSITIONS</span>

            <span class="bb-ai-param-value">${{params.max_positions || '?'}}</span>

        </div>

    `;

    

    // Expected metrics

    const expected = data.expected_metrics || {{}};

    document.getElementById('ai-expected-metrics').innerHTML = `

        <div class="bb-ai-expected-item">Expected CAGR: <span>${{expected.cagr_estimate || '?'}}</span></div>

        <div class="bb-ai-expected-item">Expected Sharpe: <span>${{expected.sharpe_estimate || '?'}}</span></div>

        <div class="bb-ai-expected-item">Expected MaxDD: <span>${{expected.max_drawdown_estimate || '?'}}</span></div>

    `;

    

    // Actual best metrics if available

    if (data.best_metrics) {{

        const m = data.best_metrics;

        document.getElementById('ai-expected-metrics').innerHTML += `

            <div style="width:100%;margin-top:12px;padding-top:12px;border-top:1px solid #333">

                <span style="color:#00ff00;font-weight:600">ACTUAL RESULTS:</span>

                Return: <span style="color:#00ff00">${{(m.total_return||0).toFixed(1)}}%</span> |

                CAGR: <span style="color:#00ff00">${{(m.cagr||0).toFixed(2)}}%</span> |

                Sharpe: <span style="color:#00bfff">${{(m.sharpe||0).toFixed(2)}}</span> |

                MaxDD: <span style="color:#ff3b30">-${{(m.max_drawdown||0).toFixed(1)}}%</span>

            </div>

        `;

    }}

    

    // Analysis text

    document.getElementById('ai-analysis-text').textContent = data.ai_analysis || 'No analysis available';

    

    // Explanation

    document.getElementById('ai-explanation-text').textContent = data.explanation || 'No explanation available';

    

    // Warnings

    const warnings = data.warnings || [];

    if (warnings.length > 0) {{

        document.getElementById('ai-warnings-section').style.display = 'block';

        document.getElementById('ai-warnings-list').innerHTML = warnings.map(w => `<li>${{w}}</li>`).join('');

    }} else {{

        document.getElementById('ai-warnings-section').style.display = 'none';

    }}

    

    // Grid results table

    const iterations = data.iterations || [];

    let gridHtml = '';

    iterations.sort((a,b) => (b.metrics?.cagr||0) - (a.metrics?.cagr||0));

    iterations.forEach(it => {{

        const p = it.params;

        const m = it.metrics;

        const isOptimal = p.pe_max === params.pe_max && p.roe_min === params.roe_min;

        gridHtml += `<tr style="${{isOptimal ? 'background:#1a0033' : ''}}">

            <td>${{p.pe_max}}</td>

            <td>${{p.roe_min}}%</td>

            <td>${{p.debt_equity_max}}%</td>

            <td>${{p.max_positions}}</td>

            <td class="${{(m.total_return||0) >= 0 ? 'pos' : 'neg'}}">${{(m.total_return||0).toFixed(1)}}%</td>

            <td>${{(m.cagr||0).toFixed(2)}}%</td>

            <td>${{(m.sharpe||0).toFixed(2)}}</td>

            <td style="color:#ff3b30">-${{(m.max_drawdown||0).toFixed(1)}}%</td>

        </tr>`;

    }});

    document.getElementById('ai-grid-body').innerHTML = gridHtml || '<tr><td colspan="8">No data</td></tr>';

    

    // Scroll to results

    document.getElementById('ai-results').scrollIntoView({{behavior: 'smooth'}});

}}



function applyOptimalParams() {{

    if (!aiOptimalParams) {{

        alert('No optimal parameters available');

        return;

    }}

    

    // Apply parameters to form

    document.getElementById('bt-pe-max').value = aiOptimalParams.pe_max || 12;

    document.getElementById('bt-roe-min').value = aiOptimalParams.roe_min || 10;

    document.getElementById('bt-pe-sell').value = aiOptimalParams.pe_sell || 17;

    document.getElementById('bt-debt-max').value = aiOptimalParams.debt_equity_max || 100;

    document.getElementById('bt-max-pos').value = aiOptimalParams.max_positions || 20;

    

    // Run backtest with these params

    runBacktest();

}}



// ============= BACKTEST HISTORY =============

let backtestHistoryData = [];

let selectedBacktests = new Set();



function loadBacktestHistory() {{

    fetch('/?action=get_backtest_history')

        .then(r => r.json())

        .then(history => {{

            backtestHistoryData = history;

            renderBacktestHistory(history);

        }})

        .catch(err => {{

            document.getElementById('bt-history-body').innerHTML = 

                '<tr><td colspan="9" style="text-align:center;color:#ff3b30">Error loading history</td></tr>';

        }});

}}



function renderBacktestHistory(history) {{

    const tbody = document.getElementById('bt-history-body');

    

    if (!history || history.length === 0) {{

        tbody.innerHTML = '<tr><td colspan="14" style="text-align:center;color:#666;padding:20px">No saved backtests yet. Run a backtest and it will be saved automatically.</td></tr>';

        return;

    }}

    

    let html = '';

    history.forEach(bt => {{

        const m = bt.metrics || {{}};

        const p = bt.params || {{}};

        const retClass = (m.total_return || 0) >= 0 ? 'pos' : 'neg';

        const cagrClass = (m.cagr || 0) >= 0 ? 'pos' : 'neg';

        const checked = selectedBacktests.has(bt.id) ? 'checked' : '';

        

        // Format scope

        const scope = (p.universe_scope || 'custom').toUpperCase().substring(0, 3);

        const scopeColor = scope === 'FRA' ? '#00bfff' : scope === 'EUR' ? '#ff9500' : '#888';

        

        // Format rebalancing

        const rebalMap = {{'monthly': 'M', 'quarterly': 'Q', 'semi-annual': 'S', 'yearly': 'Y'}};

        const rebal = rebalMap[p.rebalance_freq] || p.rebalance_freq || '?';

        

        // Format period (shorter)

        const startY = (p.start_date || '').substring(0, 4);

        const endY = (p.end_date || '').substring(0, 4);

        

        html += `<tr>

            <td><input type="checkbox" class="bt-select" data-id="${{bt.id}}" ${{checked}} onchange="toggleBacktestSelect('${{bt.id}}')"></td>

            <td class="bb-history-name" onclick="showBacktestDetails('${{bt.id}}')" title="${{bt.name}}">${{bt.name.length > 20 ? bt.name.substring(0,20)+'...' : bt.name}}</td>

            <td style="color:${{scopeColor}};font-weight:600">${{scope}}</td>

            <td style="color:#888;font-size:10px">${{startY}}-${{endY}}</td>

            <td style="color:#888">${{rebal}}</td>

            <td style="color:#888">${{p.pe_max || '?'}}/${{p.pe_sell || '?'}}</td>

            <td style="color:#888">${{p.roe_min || '?'}}/${{p.roe_min_hold || '?'}}</td>

            <td style="color:#888">${{p.max_positions || '?'}}</td>

            <td class="bb-history-metric ${{retClass}}">${{(m.total_return || 0) >= 0 ? '+' : ''}}${{(m.total_return || 0).toFixed(1)}}%</td>

            <td class="bb-history-metric ${{cagrClass}}">${{(m.cagr || 0).toFixed(2)}}%</td>

            <td>${{(m.sharpe || 0).toFixed(2)}}</td>

            <td style="color:#ff3b30">-${{(m.max_drawdown || 0).toFixed(1)}}%</td>

            <td>${{(m.win_rate || 0).toFixed(0)}}%</td>

            <td class="bb-history-actions">

                <button onclick="renameBacktest('${{bt.id}}')" title="Rename">âœï¸</button>

                <button onclick="deleteBacktest('${{bt.id}}')" title="Delete"></button>

            </td>

        </tr>`;

    }});

    

    tbody.innerHTML = html;

}}



function toggleBacktestSelect(id) {{

    if (selectedBacktests.has(id)) {{

        selectedBacktests.delete(id);

    }} else {{

        selectedBacktests.add(id);

    }}

    document.getElementById('compare-btn').disabled = selectedBacktests.size < 2;

}}



function toggleSelectAll() {{

    const checked = document.getElementById('select-all-bt').checked;

    document.querySelectorAll('.bt-select').forEach(cb => {{

        cb.checked = checked;

        const id = cb.dataset.id;

        if (checked) selectedBacktests.add(id);

        else selectedBacktests.delete(id);

    }});

    document.getElementById('compare-btn').disabled = selectedBacktests.size < 2;

}}



function showBacktestDetails(id) {{

    const bt = backtestHistoryData.find(b => b.id === id);

    if (!bt) return;

    

    const m = bt.metrics || {{}};

    const p = bt.params || {{}};

    

    // Format rebalancing

    const rebalMap = {{'monthly': 'Monthly', 'quarterly': 'Quarterly', 'semi-annual': 'Semi-Annual', 'yearly': 'Yearly'}};

    const rebal = rebalMap[p.rebalance_freq] || p.rebalance_freq || '?';

    

    alert(`📊 ${{bt.name}}\\n` +

        `â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\\n\\n` +

        `🔍… PERIOD\\n` +

        `   ${{p.start_date}} â†’ ${{p.end_date}}\\n` +

        `   Rebalancing: ${{rebal}}\\n\\n` +

        `🌍 SCOPE\\n` +

        `   Universe: ${{(p.universe_scope || 'custom').toUpperCase()}}\\n` +

        `   Max Positions: ${{p.max_positions || '?'}}\\n\\n` +

        `📈 BUY CRITERIA\\n` +

        `   PE <= ${{p.pe_max || '?'}}\\n` +

        `   ROE >= ${{p.roe_min || '?'}}%\\n` +

        `   Debt/Equity <= ${{p.debt_equity_max || '?'}}%\\n\\n` +

        `🔍‰ SELL CRITERIA\\n` +

        `   PE > ${{p.pe_sell || '?'}}\\n` +

        `   ROE < ${{p.roe_min_hold || '?'}}%\\n\\n` +

        `â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”â”\\n` +

        `💰 RESULTS\\n\\n` +

        `   Total Return: ${{(m.total_return || 0) >= 0 ? '+' : ''}}${{(m.total_return || 0).toFixed(1)}}%\\n` +

        `   CAGR: ${{(m.cagr || 0).toFixed(2)}}%\\n` +

        `   Max Drawdown: -${{(m.max_drawdown || 0).toFixed(1)}}%\\n` +

        `   Volatility: ${{(m.volatility || 0).toFixed(1)}}%\\n` +

        `   Sharpe Ratio: ${{(m.sharpe || 0).toFixed(2)}}\\n\\n` +

        `   Win Rate: ${{(m.win_rate || 0).toFixed(0)}}%\\n` +

        `   Total Trades: ${{m.total_trades || 0}}\\n` +

        `   Avg Win: +${{(m.avg_win || 0).toFixed(1)}}%\\n` +

        `   Avg Loss: ${{(m.avg_loss || 0).toFixed(1)}}%\\n\\n` +

        `   Alpha vs Benchmark: ${{(m.alpha || 0) >= 0 ? '+' : ''}}${{(m.alpha || 0).toFixed(1)}}%\\n` +

        `   Benchmark Return: ${{(m.benchmark_return || 0).toFixed(1)}}%`);

}}



function renameBacktest(id) {{

    const bt = backtestHistoryData.find(b => b.id === id);

    if (!bt) return;

    

    const newName = prompt('Enter new name for this backtest:', bt.name);

    if (newName && newName.trim()) {{

        fetch('/?action=rename_backtest&id=' + id + '&name=' + encodeURIComponent(newName.trim()), {{method: 'POST'}})

            .then(() => loadBacktestHistory())

            .catch(err => alert('Error: ' + err));

    }}

}}



function deleteBacktest(id) {{

    if (!confirm('Delete this backtest?')) return;

    

    fetch('/?action=delete_backtest&id=' + id, {{method: 'POST'}})

        .then(() => {{

            selectedBacktests.delete(id);

            loadBacktestHistory();

        }})

        .catch(err => alert('Error: ' + err));

}}



function compareSelected() {{

    if (selectedBacktests.size < 2) {{

        alert('Select at least 2 backtests to compare');

        return;

    }}

    

    const selected = backtestHistoryData.filter(bt => selectedBacktests.has(bt.id));

    drawComparisonChart(selected);

}}



function drawComparisonChart(backtests) {{

    const container = document.getElementById('compare-chart');

    container.style.display = 'block';

    

    const canvas = document.getElementById('compareChart');

    const ctx = canvas.getContext('2d');

    const rect = canvas.parentElement.getBoundingClientRect();

    canvas.width = rect.width - 32;

    canvas.height = 200;

    

    // Clear

    ctx.fillStyle = '#050505';

    ctx.fillRect(0, 0, canvas.width, canvas.height);

    

    // Draw comparison bars

    const metrics = ['total_return', 'cagr', 'sharpe', 'max_drawdown'];

    const metricLabels = ['Total Return %', 'CAGR %', 'Sharpe', 'Max DD %'];

    const colors = ['#00ff00', '#00bfff', '#ff9500', '#9933ff', '#ff3b30', '#ffff00'];

    

    const barWidth = (canvas.width - 100) / metrics.length;

    const groupWidth = barWidth / (backtests.length + 1);

    

    // Find max values for scaling

    let maxVal = 0;

    metrics.forEach(m => {{

        backtests.forEach(bt => {{

            const val = Math.abs(bt.metrics?.[m] || 0);

            if (val > maxVal) maxVal = val;

        }});

    }});

    maxVal = maxVal * 1.2 || 100;

    

    const chartHeight = canvas.height - 60;

    const baseY = canvas.height - 40;

    

    // Draw bars

    metrics.forEach((metric, mi) => {{

        const x = 60 + mi * barWidth;

        

        backtests.forEach((bt, bi) => {{

            let val = bt.metrics?.[metric] || 0;

            if (metric === 'max_drawdown') val = -val;  // Make positive for display

            

            const barH = (Math.abs(val) / maxVal) * (chartHeight / 2);

            const barX = x + bi * groupWidth + 5;

            const barY = val >= 0 ? baseY - barH : baseY;

            

            ctx.fillStyle = colors[bi % colors.length];

            ctx.fillRect(barX, val >= 0 ? barY : baseY, groupWidth - 2, barH);

        }});

        

        // Label

        ctx.fillStyle = '#888';

        ctx.font = '9px JetBrains Mono';

        ctx.textAlign = 'center';

        ctx.fillText(metricLabels[mi], x + barWidth / 2, canvas.height - 5);

    }});

    

    // Zero line

    ctx.strokeStyle = '#333';

    ctx.beginPath();

    ctx.moveTo(50, baseY);

    ctx.lineTo(canvas.width - 10, baseY);

    ctx.stroke();

    

    // Legend

    ctx.textAlign = 'left';

    backtests.forEach((bt, i) => {{

        ctx.fillStyle = colors[i % colors.length];

        ctx.fillRect(10, 10 + i * 15, 10, 10);

        ctx.fillStyle = '#888';

        ctx.font = '9px JetBrains Mono';

        ctx.fillText(bt.name.substring(0, 25), 25, 18 + i * 15);

    }});

}}



// Load history on page load

setTimeout(loadBacktestHistory, 600);



setInterval(()=>{{var now=new Date();document.querySelector('.bb-time').innerHTML=('0'+now.getHours()).slice(-2)+':'+('0'+now.getMinutes()).slice(-2)+':'+('0'+now.getSeconds()).slice(-2)+' CET <span class="blink">●</span>'}},1000);


// Portfolio management functions
let editMode = false;
let editTicker = '';

function openAddModal() {{
    editMode = false;
    editTicker = '';
    document.getElementById('modal-title').textContent = 'Add Position';
    document.getElementById('pf-ticker').value = '';
    document.getElementById('pf-ticker').disabled = false;
    document.getElementById('pf-name').value = '';
    document.getElementById('pf-qty').value = '';
    document.getElementById('pf-cost').value = '';
    document.getElementById('pf-modal').style.display = 'flex';
}}

function editPosition(ticker, name, qty, cost) {{
    editMode = true;
    editTicker = ticker;
    document.getElementById('modal-title').textContent = 'Edit Position';
    document.getElementById('pf-ticker').value = ticker;
    document.getElementById('pf-ticker').disabled = true;
    document.getElementById('pf-name').value = name;
    document.getElementById('pf-name').disabled = true;
    document.getElementById('pf-qty').value = qty;
    document.getElementById('pf-cost').value = cost;
    document.getElementById('pf-modal').style.display = 'flex';
}}

function closeModal() {{
    document.getElementById('pf-modal').style.display = 'none';
    document.getElementById('pf-name').disabled = false;
}}

function savePosition() {{
    const ticker = document.getElementById('pf-ticker').value.trim().toUpperCase();
    const name = document.getElementById('pf-name').value.trim();
    const qty = parseFloat(document.getElementById('pf-qty').value) || 0;
    const cost = parseFloat(document.getElementById('pf-cost').value) || 0;

    if (!ticker) {{ alert('Ticker is required'); return; }}
    if (qty <= 0) {{ alert('Quantity must be > 0'); return; }}
    if (cost <= 0) {{ alert('Average cost must be > 0'); return; }}

    const action = editMode ? 'editportfolio' : 'addportfolio';
    const url = `/?action=${{action}}&ticker=${{ticker}}&name=${{encodeURIComponent(name)}}&qty=${{qty}}&avg_cost=${{cost}}`;

    fetch(url)
        .then(r => {{
            if (r.ok) {{
                closeModal();
                location.reload();
            }} else {{
                return r.text().then(t => {{ throw new Error(t); }});
            }}
        }})
        .catch(err => alert('Error: ' + err.message));
}}

function deletePosition(ticker) {{
    if (!confirm('Remove ' + ticker + ' from portfolio?')) return;

    fetch('/?action=rmportfolio&ticker=' + ticker)
        .then(r => {{
            if (r.ok) {{
                location.reload();
            }} else {{
                return r.text().then(t => {{ throw new Error(t); }});
            }}
        }})
        .catch(err => alert('Error: ' + err.message));
}}

</script>
<!-- Portfolio Modal -->
<div id="pf-modal" class="pf-modal-overlay" onclick="if(event.target===this)closeModal()">
<div class="pf-modal">
<h3 id="modal-title">Add Position</h3>
<div class="pf-modal-row"><label>Ticker</label><input type="text" id="pf-ticker" placeholder="e.g. AAPL.PA"></div>
<div class="pf-modal-row"><label>Name</label><input type="text" id="pf-name" placeholder="Company name"></div>
<div class="pf-modal-row"><label>Quantity</label><input type="number" id="pf-qty" placeholder="Number of shares" step="0.01"></div>
<div class="pf-modal-row"><label>Average Cost (EUR)</label><input type="number" id="pf-cost" placeholder="PRU / unit cost" step="0.01"></div>
<div class="pf-modal-btns">
<button class="btn-cancel" onclick="closeModal()">Cancel</button>
<button class="btn-save" onclick="savePosition()">Save</button>
</div>
</div>
</div>

<!-- Trade Modal -->
<div id="trade-modal" class="pf-modal-overlay" onclick="if(event.target===this)closeTradeModal()">
<div class="pf-modal trade-modal">
<h3 id="trade-modal-title">NEW TRADE</h3>
<div class="trade-type-toggle">
<button class="trade-type-btn buy active" id="trade-type-buy" onclick="setTradeType('BUY')">BUY</button>
<button class="trade-type-btn sell" id="trade-type-sell" onclick="setTradeType('SELL')">SELL</button>
</div>
<div class="pf-modal-row"><label>Ticker</label><input type="text" id="trade-ticker" placeholder="e.g. MC.PA" style="text-transform:uppercase;"></div>
<div class="pf-modal-row"><label>Quantity</label><input type="number" id="trade-qty" placeholder="Number of shares" step="0.01"><span class="trade-max-qty" id="trade-max-qty" style="display:none;" onclick="fillMaxQty()">MAX: <span id="max-qty-val">0</span></span></div>
<div class="pf-modal-row"><label>Price (EUR)</label><input type="number" id="trade-price" placeholder="Price per share" step="0.01"></div>
<div class="pf-modal-row"><label>Date</label><input type="date" id="trade-date"></div>
<div class="pf-modal-row"><label>Fees (EUR)</label><input type="number" id="trade-fees" placeholder="0.00" step="0.01" value="0"></div>
<div class="pf-modal-row"><label>Notes</label><input type="text" id="trade-notes" placeholder="Optional notes"></div>
<div class="trade-summary" id="trade-summary" style="display:none;">
<span id="trade-summary-text"></span>
</div>
<div class="pf-modal-btns">
<button class="btn-cancel" onclick="closeTradeModal()">Cancel</button>
<button class="btn-save trade-confirm" id="trade-confirm-btn" onclick="confirmTrade()">CONFIRM TRADE</button>
</div>
</div>
</div>

<style>
.btn-buy, .btn-sell {{
  border: none;
  padding: 2px 8px;
  font-size: 14px;
  font-weight: bold;
  cursor: pointer;
  border-radius: 2px;
  margin: 0 1px;
}}
.btn-buy {{
  background: #003300;
  color: #00ff00;
}}
.btn-buy:hover {{
  background: #004400;
}}
.btn-sell {{
  background: #330000;
  color: #ff3333;
}}
.btn-sell:hover {{
  background: #440000;
}}
.trade-modal {{
  max-width: 420px;
}}
.trade-type-toggle {{
  display: flex;
  gap: 0;
  margin-bottom: 15px;
}}
.trade-type-btn {{
  flex: 1;
  padding: 12px;
  border: 2px solid #333;
  background: #1a1a1a;
  color: #666;
  font-size: 14px;
  font-weight: 700;
  cursor: pointer;
  transition: all 0.2s;
}}
.trade-type-btn.buy {{
  border-radius: 4px 0 0 4px;
}}
.trade-type-btn.sell {{
  border-radius: 0 4px 4px 0;
}}
.trade-type-btn.buy.active {{
  background: #003300;
  border-color: #00ff00;
  color: #00ff00;
}}
.trade-type-btn.sell.active {{
  background: #330000;
  border-color: #ff3333;
  color: #ff3333;
}}
.trade-max-qty {{
  font-size: 10px;
  color: #ff9500;
  cursor: pointer;
  margin-left: 10px;
  padding: 2px 6px;
  background: #1a1a1a;
  border-radius: 3px;
}}
.trade-max-qty:hover {{
  background: #ff9500;
  color: #000;
}}
.trade-summary {{
  background: #1a1a1a;
  padding: 12px;
  border-radius: 4px;
  margin: 15px 0;
  font-size: 13px;
}}
.trade-summary.buy {{
  border-left: 3px solid #00ff00;
}}
.trade-summary.sell {{
  border-left: 3px solid #ff3333;
}}
.trade-confirm {{
  background: #ff9500 !important;
  color: #000 !important;
  font-weight: 700;
}}
.trade-confirm:hover {{
  background: #ffaa33 !important;
}}
.trade-confirm.sell-mode {{
  background: #ff3333 !important;
  color: #fff !important;
}}
</style>

<script>
// Trade Modal Functions
let currentTradeType = 'BUY';
let currentMaxQty = 0;

function openTradeModal(ticker='', name='', type='BUY', maxQty=0) {{
    currentTradeType = type;
    currentMaxQty = maxQty || 0;

    document.getElementById('trade-ticker').value = ticker;
    document.getElementById('trade-qty').value = '';
    document.getElementById('trade-price').value = '';
    document.getElementById('trade-date').value = new Date().toISOString().split('T')[0];
    document.getElementById('trade-fees').value = '0';
    document.getElementById('trade-notes').value = '';
    document.getElementById('trade-summary').style.display = 'none';

    setTradeType(type);

    // If selling, fetch current qty
    if (type === 'SELL' && ticker) {{
        fetchTickerQty(ticker);
    }}

    document.getElementById('trade-modal').style.display = 'flex';
    if (!ticker) {{
        document.getElementById('trade-ticker').focus();
    }} else {{
        document.getElementById('trade-qty').focus();
    }}
}}

function closeTradeModal() {{
    document.getElementById('trade-modal').style.display = 'none';
}}

function setTradeType(type) {{
    currentTradeType = type;
    const buyBtn = document.getElementById('trade-type-buy');
    const sellBtn = document.getElementById('trade-type-sell');
    const confirmBtn = document.getElementById('trade-confirm-btn');
    const maxQtyEl = document.getElementById('trade-max-qty');
    const summary = document.getElementById('trade-summary');

    if (type === 'BUY') {{
        buyBtn.classList.add('active');
        sellBtn.classList.remove('active');
        confirmBtn.classList.remove('sell-mode');
        confirmBtn.textContent = 'CONFIRM BUY';
        maxQtyEl.style.display = 'none';
        summary.classList.remove('sell');
        summary.classList.add('buy');
    }} else {{
        buyBtn.classList.remove('active');
        sellBtn.classList.add('active');
        confirmBtn.classList.add('sell-mode');
        confirmBtn.textContent = 'CONFIRM SELL';
        if (currentMaxQty > 0) {{
            document.getElementById('max-qty-val').textContent = currentMaxQty.toFixed(2);
            maxQtyEl.style.display = 'inline';
        }}
        summary.classList.remove('buy');
        summary.classList.add('sell');
    }}
    updateTradeSummary();
}}

function fetchTickerQty(ticker) {{
    fetch(`/?action=get_ticker_qty&ticker=${{ticker}}`)
        .then(r => r.json())
        .then(data => {{
            if (data.success && data.data) {{
                currentMaxQty = data.data.quantity || 0;
                document.getElementById('max-qty-val').textContent = currentMaxQty.toFixed(2);
                if (currentTradeType === 'SELL' && currentMaxQty > 0) {{
                    document.getElementById('trade-max-qty').style.display = 'inline';
                }}
            }}
        }})
        .catch(err => console.error('Error fetching qty:', err));
}}

function fillMaxQty() {{
    document.getElementById('trade-qty').value = currentMaxQty;
    updateTradeSummary();
}}

function updateTradeSummary() {{
    const qty = parseFloat(document.getElementById('trade-qty').value) || 0;
    const price = parseFloat(document.getElementById('trade-price').value) || 0;
    const fees = parseFloat(document.getElementById('trade-fees').value) || 0;
    const summary = document.getElementById('trade-summary');

    if (qty > 0 && price > 0) {{
        const total = qty * price;
        const netTotal = currentTradeType === 'BUY' ? total + fees : total - fees;
        const action = currentTradeType === 'BUY' ? 'Cost' : 'Proceeds';
        summary.innerHTML = `<span style="color:#888">${{currentTradeType}}</span> <span style="color:#fff">${{qty}}</span> shares @ <span style="color:#fff">€${{price.toFixed(2)}}</span> = <span style="color:${{currentTradeType === 'BUY' ? '#00ff00' : '#ff3333'}}">€${{netTotal.toFixed(2)}}</span> <span style="color:#666">(${{action}})</span>`;
        summary.style.display = 'block';
    }} else {{
        summary.style.display = 'none';
    }}
}}

// Update summary on input change
document.getElementById('trade-qty')?.addEventListener('input', updateTradeSummary);
document.getElementById('trade-price')?.addEventListener('input', updateTradeSummary);
document.getElementById('trade-fees')?.addEventListener('input', updateTradeSummary);

// Fetch qty when ticker changes (for sell)
document.getElementById('trade-ticker')?.addEventListener('change', function() {{
    if (currentTradeType === 'SELL' && this.value) {{
        fetchTickerQty(this.value);
    }}
}});

function confirmTrade() {{
    const ticker = document.getElementById('trade-ticker').value.trim().toUpperCase();
    const qty = parseFloat(document.getElementById('trade-qty').value) || 0;
    const price = parseFloat(document.getElementById('trade-price').value) || 0;
    const date = document.getElementById('trade-date').value;
    const fees = parseFloat(document.getElementById('trade-fees').value) || 0;
    const notes = document.getElementById('trade-notes').value;

    if (!ticker) {{ alert('Ticker is required'); return; }}
    if (qty <= 0) {{ alert('Quantity must be > 0'); return; }}
    if (price <= 0) {{ alert('Price must be > 0'); return; }}

    // Validate sell quantity
    if (currentTradeType === 'SELL' && qty > currentMaxQty) {{
        alert(`Cannot sell ${{qty}} shares. You only have ${{currentMaxQty.toFixed(2)}} shares.`);
        return;
    }}

    const confirmBtn = document.getElementById('trade-confirm-btn');
    confirmBtn.disabled = true;
    confirmBtn.textContent = 'Processing...';

    const url = `/?action=add_transaction&ticker=${{ticker}}&type=${{currentTradeType}}&date=${{date}}&quantity=${{qty}}&price=${{price}}&fees=${{fees}}&notes=${{encodeURIComponent(notes)}}`;

    fetch(url)
        .then(r => r.json())
        .then(data => {{
            if (data.success) {{
                closeTradeModal();
                alert(`${{currentTradeType}} order executed: ${{qty}} ${{ticker}} @ €${{price.toFixed(2)}}`);
                location.reload();
            }} else {{
                alert('Error: ' + (data.error || 'Unknown error'));
                confirmBtn.disabled = false;
                confirmBtn.textContent = currentTradeType === 'BUY' ? 'CONFIRM BUY' : 'CONFIRM SELL';
            }}
        }})
        .catch(err => {{
            alert('Error: ' + err.message);
            confirmBtn.disabled = false;
            confirmBtn.textContent = currentTradeType === 'BUY' ? 'CONFIRM BUY' : 'CONFIRM SELL';
        }});
}}

// ═══ PDF REPORT GENERATION ═══
function generateReport() {{
    const now = new Date();
    const month = now.getMonth() + 1;
    const year = now.getFullYear();

    // Show loading indicator
    const btn = event.target;
    const originalText = btn.textContent;
    btn.textContent = '⏳ GEN...';
    btn.disabled = true;

    // Generate and download report
    fetch(`/?action=generate_report&month=${{month}}&year=${{year}}`)
        .then(response => {{
            if (!response.ok) {{
                return response.json().then(data => {{
                    throw new Error(data.error || 'Failed to generate report');
                }});
            }}
            return response.blob();
        }})
        .then(blob => {{
            // Create download link
            const url = window.URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `report_${{year}}_${{String(month).padStart(2, '0')}}.pdf`;
            document.body.appendChild(a);
            a.click();
            window.URL.revokeObjectURL(url);
            a.remove();

            // Reset button
            btn.textContent = originalText;
            btn.disabled = false;
        }})
        .catch(err => {{
            alert('Error generating report: ' + err.message);
            btn.textContent = originalText;
            btn.disabled = false;
        }});
}}

// ═══ INSIDER TRADING PANEL ═══
let insiderPanelVisible = false;

function toggleInsiderPanel() {{
    const panel = document.getElementById('insiderPanel');
    if (!panel) {{
        createInsiderPanel();
        loadInsiderFeed();
    }} else {{
        insiderPanelVisible = !insiderPanelVisible;
        panel.style.display = insiderPanelVisible ? 'block' : 'none';
        if (insiderPanelVisible) loadInsiderFeed();
    }}
}}

function createInsiderPanel() {{
    const panel = document.createElement('div');
    panel.id = 'insiderPanel';
    panel.style.cssText = `
        position: fixed;
        top: 60px;
        right: 20px;
        width: 420px;
        max-height: 80vh;
        background: linear-gradient(180deg, #0d1117 0%, #161b22 100%);
        border: 1px solid #22c55e;
        border-radius: 8px;
        box-shadow: 0 8px 32px rgba(34, 197, 94, 0.2);
        z-index: 9999;
        overflow: hidden;
        font-family: 'Consolas', 'Monaco', monospace;
    `;

    panel.innerHTML = `
        <div style="padding:12px 16px;background:#0f1419;border-bottom:1px solid #22c55e;display:flex;justify-content:space-between;align-items:center;">
            <span style="color:#22c55e;font-weight:bold;font-size:14px;">📊 INSIDER ACTIVITY</span>
            <div>
                <select id="insiderScope" onchange="loadInsiderFeed()" style="background:#1a1f25;color:#9ca3af;border:1px solid #374151;border-radius:4px;padding:4px 8px;font-size:12px;margin-right:8px;">
                    <option value="portfolio">Portfolio</option>
                    <option value="watchlist">Watchlist</option>
                    <option value="all">All</option>
                </select>
                <button onclick="loadInsiderFeed()" style="background:none;border:none;color:#22c55e;cursor:pointer;font-size:14px;">🔄</button>
                <button onclick="toggleInsiderPanel()" style="background:none;border:none;color:#6b7280;cursor:pointer;font-size:18px;margin-left:8px;">×</button>
            </div>
        </div>
        <div id="insiderFeedContent" style="padding:12px;max-height:calc(80vh - 60px);overflow-y:auto;">
            <div style="color:#6b7280;text-align:center;padding:20px;">Loading...</div>
        </div>
    `;

    document.body.appendChild(panel);
    insiderPanelVisible = true;
}}

function loadInsiderFeed() {{
    const content = document.getElementById('insiderFeedContent');
    const scope = document.getElementById('insiderScope')?.value || 'portfolio';

    content.innerHTML = '<div style="color:#6b7280;text-align:center;padding:20px;">⏳ Loading insider data...</div>';

    fetch(`/?action=insider_feed&scope=${{scope}}&limit=30`)
        .then(r => r.json())
        .then(data => {{
            if (!data.success || !data.data.transactions.length) {{
                content.innerHTML = '<div style="color:#6b7280;text-align:center;padding:20px;">No insider transactions found</div>';
                return;
            }}

            let html = '';
            const transactions = data.data.transactions;

            // Group by date
            let currentDate = '';
            for (const t of transactions) {{
                if (t.date !== currentDate) {{
                    currentDate = t.date;
                    html += `<div style="color:#6b7280;font-size:10px;margin:12px 0 6px 0;text-transform:uppercase;border-bottom:1px solid #1f2937;padding-bottom:4px;">${{formatDate(t.date)}}</div>`;
                }}

                const isBuy = t.transaction_type === 'BUY';
                const color = isBuy ? '#22c55e' : '#ef4444';
                const icon = isBuy ? '📈' : '📉';
                const value = formatMoney(t.value);

                html += `
                    <div style="padding:8px;margin:4px 0;background:#1a1f25;border-radius:6px;border-left:3px solid ${{color}};">
                        <div style="display:flex;justify-content:space-between;align-items:flex-start;">
                            <div>
                                <span style="color:#ffd700;font-weight:bold;">${{t.ticker}}</span>
                                <span style="color:${{color}};font-size:12px;margin-left:6px;">${{icon}} ${{isBuy ? 'ACHAT' : 'VENTE'}}</span>
                            </div>
                            <span style="color:${{color}};font-weight:bold;">${{value}}</span>
                        </div>
                        <div style="color:#9ca3af;font-size:11px;margin-top:4px;">
                            ${{t.insider_name}} <span style="color:#6b7280;">(${{t.insider_title || 'Director'}})</span>
                        </div>
                        <div style="color:#6b7280;font-size:10px;margin-top:2px;">
                            ${{t.shares.toLocaleString()}} actions @ ${{t.price.toFixed(2)}}€
                        </div>
                    </div>
                `;
            }}

            content.innerHTML = html || '<div style="color:#6b7280;text-align:center;padding:20px;">No data</div>';
        }})
        .catch(err => {{
            content.innerHTML = `<div style="color:#ef4444;text-align:center;padding:20px;">Error: ${{err.message}}</div>`;
        }});
}}

function formatDate(dateStr) {{
    const d = new Date(dateStr);
    const options = {{ day: 'numeric', month: 'short', year: 'numeric' }};
    return d.toLocaleDateString('fr-FR', options);
}}

function formatMoney(val) {{
    if (val >= 1000000) return (val / 1000000).toFixed(1) + 'M€';
    if (val >= 1000) return (val / 1000).toFixed(0) + 'k€';
    return val.toFixed(0) + '€';
}}

// Keyboard shortcut for F8
document.addEventListener('keydown', function(e) {{
    if (e.key === 'F8') {{
        e.preventDefault();
        toggleInsiderPanel();
    }}
}});

// ═══ REBALANCING PANEL ═══
let rebalancePanelVisible = false;

function toggleRebalancePanel() {{
    const panel = document.getElementById('rebalancePanel');
    if (!panel) {{
        createRebalancePanel();
        loadRebalanceAnalysis();
    }} else {{
        rebalancePanelVisible = !rebalancePanelVisible;
        panel.style.display = rebalancePanelVisible ? 'block' : 'none';
        if (rebalancePanelVisible) loadRebalanceAnalysis();
    }}
}}

function createRebalancePanel() {{
    const panel = document.createElement('div');
    panel.id = 'rebalancePanel';
    panel.style.cssText = `
        position: fixed;
        top: 60px;
        right: 460px;
        width: 520px;
        max-height: 85vh;
        background: linear-gradient(180deg, #0d1117 0%, #161b22 100%);
        border: 1px solid #f59e0b;
        border-radius: 8px;
        box-shadow: 0 8px 32px rgba(245, 158, 11, 0.2);
        z-index: 9998;
        overflow: hidden;
        font-family: 'Consolas', 'Monaco', monospace;
    `;

    panel.innerHTML = `
        <div style="padding:12px 16px;background:#0f1419;border-bottom:1px solid #f59e0b;display:flex;justify-content:space-between;align-items:center;">
            <span style="color:#f59e0b;font-weight:bold;font-size:14px;">⚖️ REBALANCING</span>
            <div>
                <select id="rebalanceMethod" onchange="loadRebalanceAnalysis()" style="background:#1a1f25;color:#9ca3af;border:1px solid #374151;border-radius:4px;padding:4px 8px;font-size:12px;margin-right:8px;">
                    <option value="equal">Équipondéré</option>
                    <option value="score">Pondéré Score</option>
                    <option value="conviction">Conviction</option>
                </select>
                <button onclick="loadRebalanceAnalysis()" style="background:none;border:none;color:#f59e0b;cursor:pointer;font-size:14px;">🔄</button>
                <button onclick="toggleRebalancePanel()" style="background:none;border:none;color:#6b7280;cursor:pointer;font-size:18px;margin-left:8px;">×</button>
            </div>
        </div>
        <div id="rebalanceContent" style="padding:12px;max-height:calc(85vh - 60px);overflow-y:auto;">
            <div style="color:#6b7280;text-align:center;padding:20px;">Loading...</div>
        </div>
    `;

    document.body.appendChild(panel);
    rebalancePanelVisible = true;
}}

function loadRebalanceAnalysis() {{
    const content = document.getElementById('rebalanceContent');
    const method = document.getElementById('rebalanceMethod')?.value || 'equal';

    content.innerHTML = '<div style="color:#6b7280;text-align:center;padding:20px;">⏳ Analyzing portfolio...</div>';

    Promise.all([
        fetch('/?action=rebalance_analyze').then(r => r.json()),
        fetch(`/?action=rebalance_propose&method=${{method}}`).then(r => r.json())
    ])
    .then(([analysis, proposals]) => {{
        if (!analysis.success || !proposals.success) {{
            content.innerHTML = '<div style="color:#ef4444;text-align:center;padding:20px;">Error loading data</div>';
            return;
        }}

        const data = analysis.data;
        const propData = proposals.data;
        let html = '';

        // Summary stats
        html += `
            <div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:16px;">
                <div style="background:#1a1f25;padding:10px;border-radius:6px;text-align:center;">
                    <div style="color:#6b7280;font-size:10px;text-transform:uppercase;">Portfolio</div>
                    <div style="color:#ffd700;font-size:18px;font-weight:bold;">${{formatMoney(data.total_portfolio_value)}}</div>
                </div>
                <div style="background:#1a1f25;padding:10px;border-radius:6px;text-align:center;">
                    <div style="color:#6b7280;font-size:10px;text-transform:uppercase;">Positions</div>
                    <div style="color:#22d3ee;font-size:18px;font-weight:bold;">${{data.num_positions}}</div>
                </div>
                <div style="background:#1a1f25;padding:10px;border-radius:6px;text-align:center;">
                    <div style="color:#6b7280;font-size:10px;text-transform:uppercase;">Statut</div>
                    <div style="color:${{data.is_balanced ? '#22c55e' : '#f59e0b'}};font-size:18px;font-weight:bold;">
                        ${{data.is_balanced ? '✓ OK' : '⚠️ ' + data.imbalances.length}}
                    </div>
                </div>
            </div>
        `;

        // Imbalances section
        if (data.imbalances && data.imbalances.length > 0) {{
            html += `<div style="color:#f59e0b;font-size:12px;font-weight:bold;margin:12px 0 8px 0;text-transform:uppercase;">⚠️ Déséquilibres détectés</div>`;
            for (const imb of data.imbalances) {{
                const color = imb.severity === 'critical' ? '#ef4444' : '#f59e0b';
                const icon = imb.severity === 'critical' ? '🔴' : '🟡';
                html += `
                    <div style="padding:8px;margin:4px 0;background:#1a1f25;border-radius:6px;border-left:3px solid ${{color}};">
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <span style="color:#ffd700;font-weight:bold;">${{icon}} ${{imb.ticker}}</span>
                            <span style="color:${{color}};font-size:11px;padding:2px 6px;background:rgba(245,158,11,0.1);border-radius:4px;">${{imb.imbalance_type}}</span>
                        </div>
                        <div style="color:#9ca3af;font-size:11px;margin-top:4px;">${{imb.message}}</div>
                        <div style="color:#6b7280;font-size:10px;margin-top:2px;">
                            Action suggérée: <span style="color:#22d3ee;">${{imb.suggested_action}}</span>
                        </div>
                    </div>
                `;
            }}
        }}

        // Trade proposals section
        if (propData.proposals && propData.proposals.length > 0) {{
            html += `
                <div style="color:#22d3ee;font-size:12px;font-weight:bold;margin:16px 0 8px 0;text-transform:uppercase;">📋 Propositions de trades</div>
                <div style="display:flex;gap:12px;margin-bottom:12px;">
                    <div style="flex:1;background:#0f2818;padding:8px;border-radius:6px;text-align:center;border:1px solid #22c55e30;">
                        <div style="color:#6b7280;font-size:10px;">À acheter</div>
                        <div style="color:#22c55e;font-weight:bold;">${{formatMoney(propData.total_buy)}}</div>
                    </div>
                    <div style="flex:1;background:#280f0f;padding:8px;border-radius:6px;text-align:center;border:1px solid #ef444430;">
                        <div style="color:#6b7280;font-size:10px;">À vendre</div>
                        <div style="color:#ef4444;font-weight:bold;">${{formatMoney(propData.total_sell)}}</div>
                    </div>
                    <div style="flex:1;background:#1a1f25;padding:8px;border-radius:6px;text-align:center;">
                        <div style="color:#6b7280;font-size:10px;">Net</div>
                        <div style="color:#ffd700;font-weight:bold;">${{formatMoney(propData.net_flow)}}</div>
                    </div>
                </div>
            `;

            for (const trade of propData.proposals) {{
                const isBuy = trade.action === 'ADD';
                const color = isBuy ? '#22c55e' : (trade.action === 'SELL' ? '#ef4444' : '#f59e0b');
                const arrow = trade.deviation > 0 ? '↑' : '↓';

                html += `
                    <div style="padding:8px;margin:4px 0;background:#1a1f25;border-radius:6px;border-left:3px solid ${{color}};">
                        <div style="display:flex;justify-content:space-between;align-items:center;">
                            <div>
                                <span style="color:#ffd700;font-weight:bold;">${{trade.ticker}}</span>
                                <span style="color:${{color}};font-size:11px;margin-left:6px;">${{trade.action}}</span>
                            </div>
                            <span style="color:${{color}};font-weight:bold;">${{trade.trade_value > 0 ? '+' : ''}}${{formatMoney(Math.abs(trade.trade_value))}}</span>
                        </div>
                        <div style="color:#9ca3af;font-size:11px;margin-top:4px;">
                            ${{trade.current_weight.toFixed(1)}}% ${{arrow}} ${{trade.target_weight.toFixed(1)}}%
                            <span style="color:#6b7280;margin-left:8px;">(${{trade.deviation > 0 ? '+' : ''}}${{trade.deviation.toFixed(1)}}%)</span>
                        </div>
                        <div style="color:#6b7280;font-size:10px;margin-top:2px;">
                            ~${{Math.abs(trade.shares_to_trade).toFixed(0)}} actions @ ${{trade.current_price.toFixed(2)}}€
                        </div>
                    </div>
                `;
            }}
        }} else {{
            html += `<div style="color:#22c55e;text-align:center;padding:20px;background:#0f2818;border-radius:6px;margin-top:12px;">
                ✓ Portfolio équilibré - Aucune action requise
            </div>`;
        }}

        content.innerHTML = html;
    }})
    .catch(err => {{
        content.innerHTML = `<div style="color:#ef4444;text-align:center;padding:20px;">Error: ${{err.message}}</div>`;
    }});
}}

// Keyboard shortcut for F9
document.addEventListener('keydown', function(e) {{
    if (e.key === 'F9') {{
        e.preventDefault();
        toggleRebalancePanel();
    }}
}});

// ═══ HEATMAP TREEMAP PANEL ═══
let heatmapPanelVisible = false;
let heatmapMetric = 'pnl_pct';
let heatmapGrouping = 'sector';
let heatmapData = null;

function toggleHeatmapPanel() {{
    const panel = document.getElementById('heatmapPanel');
    if (!panel) {{
        createHeatmapPanel();
        loadHeatmapData();
    }} else {{
        heatmapPanelVisible = !heatmapPanelVisible;
        panel.style.display = heatmapPanelVisible ? 'block' : 'none';
        if (heatmapPanelVisible) loadHeatmapData();
    }}
}}

function createHeatmapPanel() {{
    const panel = document.createElement('div');
    panel.id = 'heatmapPanel';
    panel.style.cssText = `
        position: fixed;
        top: 50px;
        left: 50%;
        transform: translateX(-50%);
        width: 90vw;
        max-width: 1400px;
        height: 80vh;
        background: linear-gradient(180deg, #0d1117 0%, #161b22 100%);
        border: 1px solid #a855f7;
        border-radius: 8px;
        box-shadow: 0 8px 32px rgba(168, 85, 247, 0.3);
        z-index: 10000;
        overflow: hidden;
        font-family: 'Consolas', 'Monaco', monospace;
    `;

    panel.innerHTML = `
        <div style="padding:12px 16px;background:#0f1419;border-bottom:1px solid #a855f7;display:flex;justify-content:space-between;align-items:center;">
            <span style="color:#a855f7;font-weight:bold;font-size:14px;">📊 MARKET HEATMAP</span>
            <div style="display:flex;gap:12px;align-items:center;">
                <div>
                    <label style="color:#6b7280;font-size:11px;margin-right:4px;">Couleur:</label>
                    <select id="heatmapMetric" onchange="changeHeatmapMetric(this.value)" style="background:#1a1f25;color:#9ca3af;border:1px solid #374151;border-radius:4px;padding:4px 8px;font-size:11px;">
                        <option value="pnl_pct" selected>P&L Total</option>
                        <option value="change_pct">Perf Jour</option>
                        <option value="ytd_pct">Perf YTD</option>
                        <option value="score">Score Higgons</option>
                        <option value="pe">PE Ratio</option>
                        <option value="pcf">P/CF Ratio</option>
                    </select>
                </div>
                <div>
                    <label style="color:#6b7280;font-size:11px;margin-right:4px;">Grouper:</label>
                    <select id="heatmapGrouping" onchange="changeHeatmapGrouping(this.value)" style="background:#1a1f25;color:#9ca3af;border:1px solid #374151;border-radius:4px;padding:4px 8px;font-size:11px;">
                        <option value="sector">Secteur</option>
                        <option value="country">Pays</option>
                        <option value="flat">Aucun</option>
                    </select>
                </div>
                <button onclick="loadHeatmapData()" style="background:none;border:none;color:#a855f7;cursor:pointer;font-size:14px;">🔄</button>
                <button onclick="toggleHeatmapPanel()" style="background:none;border:none;color:#6b7280;cursor:pointer;font-size:18px;">×</button>
            </div>
        </div>
        <div id="heatmapContainer" style="width:100%;height:calc(100% - 50px);position:relative;">
            <div style="color:#6b7280;text-align:center;padding:40px;">Loading...</div>
        </div>
        <div id="heatmapTooltip" style="position:fixed;display:none;background:#1a1f25;border:1px solid #374151;border-radius:6px;padding:12px;box-shadow:0 4px 12px rgba(0,0,0,0.5);z-index:10001;pointer-events:none;min-width:200px;"></div>
    `;

    document.body.appendChild(panel);
    heatmapPanelVisible = true;
}}

function changeHeatmapMetric(metric) {{
    heatmapMetric = metric;
    renderHeatmap();
}}

function changeHeatmapGrouping(grouping) {{
    heatmapGrouping = grouping;
    loadHeatmapData();
}}

function loadHeatmapData() {{
    const container = document.getElementById('heatmapContainer');
    if (!container) return;

    container.innerHTML = '<div style="color:#6b7280;text-align:center;padding:40px;">⏳ Loading heatmap data...</div>';

    fetch(`/?action=heatmap_data&grouping=${{heatmapGrouping}}`)
        .then(r => r.json())
        .then(data => {{
            if (!data.success) {{
                container.innerHTML = '<div style="color:#ef4444;text-align:center;padding:40px;">Error loading data</div>';
                return;
            }}
            heatmapData = data.data;
            renderHeatmap();
        }})
        .catch(err => {{
            container.innerHTML = `<div style="color:#ef4444;text-align:center;padding:40px;">Error: ${{err.message}}</div>`;
        }});
}}

function getColorForValue(value, metric) {{
    // Returns color based on metric type and value
    if (value === null || value === undefined) return '#374151';

    if (metric === 'pe') {{
        // PE: < 10 green, 10-12 orange, > 12 red
        if (value < 10) {{
            return 'rgb(34, 197, 94)';  // Green
        }} else if (value <= 12) {{
            return 'rgb(251, 146, 60)'; // Orange
        }} else {{
            return 'rgb(239, 68, 68)';  // Red
        }}
    }} else if (metric === 'pcf') {{
        // P/CF: <= 8 green (excellent), 8-12 orange (correct), > 12 red (expensive)
        if (value <= 8) {{
            return 'rgb(34, 197, 94)';  // Green - excellent
        }} else if (value <= 12) {{
            return 'rgb(251, 146, 60)'; // Orange - correct
        }} else {{
            return 'rgb(239, 68, 68)';  // Red - expensive
        }}
    }} else if (metric === 'score') {{
        // Score: 0-4 red, 5-6 orange, 7-10 green
        if (value >= 7) {{
            const intensity = Math.min((value - 7) / 3, 1);
            return `rgb(${{34 - intensity * 10}}, ${{150 + intensity * 47}}, ${{70 + intensity * 24}})`;
        }} else if (value >= 5) {{
            return 'rgb(251, 146, 60)'; // Orange
        }} else {{
            const intensity = Math.min((5 - value) / 5, 1);
            return `rgb(${{180 + intensity * 59}}, ${{68 - intensity * 30}}, ${{68 - intensity * 30}})`;
        }}
    }} else {{
        // Performance metrics: positive = green, negative = red
        // Scale: -10% to +10%
        const normalized = Math.max(-1, Math.min(1, value / 10));
        if (normalized >= 0) {{
            const intensity = normalized;
            return `rgb(${{34 - intensity * 10}}, ${{100 + intensity * 97}}, ${{50 + intensity * 44}})`;
        }} else {{
            const intensity = -normalized;
            return `rgb(${{180 + intensity * 59}}, ${{68 - intensity * 30}}, ${{68 - intensity * 30}})`;
        }}
    }}
}}

function squarify(data, x, y, width, height) {{
    // Squarified treemap algorithm
    if (!data.length) return [];

    const totalValue = data.reduce((sum, d) => sum + d.value, 0);
    if (totalValue === 0) return [];

    const results = [];
    let remaining = [...data];
    let currentX = x, currentY = y, currentW = width, currentH = height;

    while (remaining.length > 0) {{
        const isHorizontal = currentW >= currentH;
        const side = isHorizontal ? currentH : currentW;

        let row = [];
        let rowValue = 0;
        let worstRatio = Infinity;

        for (let i = 0; i < remaining.length; i++) {{
            const testRow = [...row, remaining[i]];
            const testValue = rowValue + remaining[i].value;
            const testRatio = getWorstRatio(testRow, testValue, side, totalValue, currentW * currentH);

            if (testRatio <= worstRatio) {{
                row = testRow;
                rowValue = testValue;
                worstRatio = testRatio;
            }} else {{
                break;
            }}
        }}

        // Layout this row
        const rowArea = (rowValue / totalValue) * currentW * currentH;
        const rowLength = rowArea / side;

        let offset = 0;
        for (const item of row) {{
            const itemArea = (item.value / totalValue) * currentW * currentH;
            const itemLength = itemArea / rowLength;

            if (isHorizontal) {{
                results.push({{
                    ...item,
                    x: currentX,
                    y: currentY + offset,
                    width: rowLength,
                    height: itemLength
                }});
            }} else {{
                results.push({{
                    ...item,
                    x: currentX + offset,
                    y: currentY,
                    width: itemLength,
                    height: rowLength
                }});
            }}
            offset += itemLength;
        }}

        // Update remaining area
        remaining = remaining.slice(row.length);
        if (isHorizontal) {{
            currentX += rowLength;
            currentW -= rowLength;
        }} else {{
            currentY += rowLength;
            currentH -= rowLength;
        }}
    }}

    return results;
}}

function getWorstRatio(row, rowValue, side, totalValue, totalArea) {{
    if (!row.length) return Infinity;
    const rowArea = (rowValue / totalValue) * totalArea;
    const rowLength = rowArea / side;

    let worst = 0;
    for (const item of row) {{
        const itemArea = (item.value / totalValue) * totalArea;
        const itemLength = itemArea / rowLength;
        const ratio = Math.max(rowLength / itemLength, itemLength / rowLength);
        worst = Math.max(worst, ratio);
    }}
    return worst;
}}

function renderHeatmap() {{
    const container = document.getElementById('heatmapContainer');
    if (!container || !heatmapData) return;

    const rect = container.getBoundingClientRect();
    const width = rect.width;
    const height = rect.height;
    const padding = 4;
    const groupPadding = 20;

    container.innerHTML = '';

    const groups = heatmapData.groups;
    if (!groups || !groups.length) {{
        container.innerHTML = '<div style="color:#6b7280;text-align:center;padding:40px;">No data available</div>';
        return;
    }}

    // Calculate group rectangles
    const groupData = groups.map(g => ({{ name: g.name, value: g.value, positions: g.positions }}));
    const groupRects = squarify(groupData, padding, padding, width - padding * 2, height - padding * 2);

    for (const groupRect of groupRects) {{
        const group = groups.find(g => g.name === groupRect.name);
        if (!group) continue;

        // Create group container
        const groupDiv = document.createElement('div');
        groupDiv.style.cssText = `
            position: absolute;
            left: ${{groupRect.x}}px;
            top: ${{groupRect.y}}px;
            width: ${{groupRect.width}}px;
            height: ${{groupRect.height}}px;
            border: 1px solid #374151;
            box-sizing: border-box;
            overflow: hidden;
        `;

        // Group header
        if (heatmapGrouping !== 'flat') {{
            const header = document.createElement('div');
            header.style.cssText = `
                position: absolute;
                top: 0;
                left: 0;
                right: 0;
                background: rgba(15, 20, 25, 0.9);
                color: #9ca3af;
                font-size: 10px;
                padding: 2px 4px;
                text-transform: uppercase;
                z-index: 1;
                border-bottom: 1px solid #374151;
            `;
            header.textContent = `${{groupRect.name}} (${{(group.weight ?? 0).toFixed(1)}}%)`;
            groupDiv.appendChild(header);
        }}

        // Calculate position rectangles within group
        const innerX = 0;
        const innerY = heatmapGrouping !== 'flat' ? 18 : 0;
        const innerW = groupRect.width - 2;
        const innerH = groupRect.height - (heatmapGrouping !== 'flat' ? 20 : 2);

        const posData = group.positions.map(p => ({{ ...p }}));
        const posRects = squarify(posData, innerX, innerY, innerW, innerH);

        for (const posRect of posRects) {{
            const pos = group.positions.find(p => p.ticker === posRect.ticker);
            if (!pos) continue;

            const metricValue = pos[heatmapMetric];
            const bgColor = getColorForValue(metricValue, heatmapMetric);

            const posDiv = document.createElement('div');
            posDiv.className = 'heatmap-cell';
            posDiv.dataset.ticker = pos.ticker;
            posDiv.style.cssText = `
                position: absolute;
                left: ${{posRect.x + 1}}px;
                top: ${{posRect.y + 1}}px;
                width: ${{Math.max(posRect.width - 2, 0)}}px;
                height: ${{Math.max(posRect.height - 2, 0)}}px;
                background: ${{bgColor}};
                display: flex;
                flex-direction: column;
                justify-content: center;
                align-items: center;
                cursor: pointer;
                transition: transform 0.1s, box-shadow 0.1s;
                overflow: hidden;
            `;

            // Content based on cell size
            if (posRect.width > 60 && posRect.height > 40) {{
                const safeValue = metricValue ?? 0;
                const displayValue = heatmapMetric === 'pe' ? (metricValue !== null ? metricValue : '-') :
                                     heatmapMetric === 'score' ? `${{metricValue ?? 5}}/10` :
                                     `${{safeValue >= 0 ? '+' : ''}}${{safeValue.toFixed(1)}}%`;
                posDiv.innerHTML = `
                    <div style="color:#fff;font-weight:bold;font-size:${{posRect.width > 100 ? '13px' : '11px'}};text-shadow:0 1px 2px rgba(0,0,0,0.5);">${{pos.ticker}}</div>
                    <div style="color:rgba(255,255,255,0.9);font-size:${{posRect.width > 100 ? '12px' : '10px'}};">${{displayValue}}</div>
                    ${{posRect.height > 55 ? `<div style="color:rgba(255,255,255,0.6);font-size:9px;">${{(pos.weight ?? 0).toFixed(1)}}%</div>` : ''}}
                `;
            }} else if (posRect.width > 35 && posRect.height > 25) {{
                posDiv.innerHTML = `<div style="color:#fff;font-weight:bold;font-size:10px;text-shadow:0 1px 2px rgba(0,0,0,0.5);">${{pos.ticker}}</div>`;
            }}

            // Hover events
            posDiv.addEventListener('mouseenter', (e) => showHeatmapTooltip(e, pos));
            posDiv.addEventListener('mouseleave', hideHeatmapTooltip);
            posDiv.addEventListener('mousemove', (e) => moveHeatmapTooltip(e));

            // Click to navigate
            posDiv.addEventListener('click', () => {{
                window.location.href = `/?detail=${{pos.ticker}}`;
            }});

            groupDiv.appendChild(posDiv);
        }}

        container.appendChild(groupDiv);
    }}

    // Add hover style
    const style = document.createElement('style');
    style.textContent = `
        .heatmap-cell:hover {{
            transform: scale(1.02);
            box-shadow: 0 0 12px rgba(255,255,255,0.3);
            z-index: 10;
        }}
    `;
    container.appendChild(style);
}}

function showHeatmapTooltip(e, pos) {{
    const tooltip = document.getElementById('heatmapTooltip');
    if (!tooltip) return;

    const pe = pos.pe ?? null;
    const roe = pos.roe ?? null;
    const score = pos.score ?? 5;
    const pnl = pos.pnl_pct ?? 0;
    const change = pos.change_pct ?? 0;
    const weight = pos.weight ?? 0;

    const peColor = pe !== null ? (pe < 10 ? '#22c55e' : (pe < 17 ? '#ffd700' : '#ef4444')) : '#6b7280';
    const roeColor = roe !== null ? (roe > 15 ? '#22c55e' : (roe > 10 ? '#ffd700' : '#ef4444')) : '#6b7280';
    const scoreColor = score >= 7 ? '#22c55e' : (score >= 4 ? '#ffd700' : '#ef4444');
    const pnlColor = pnl >= 0 ? '#22c55e' : '#ef4444';

    tooltip.innerHTML = `
        <div style="font-weight:bold;color:#ffd700;margin-bottom:8px;">${{pos.ticker}} - ${{pos.name}}</div>
        <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px 16px;font-size:12px;">
            <div style="color:#6b7280;">Secteur:</div><div style="color:#9ca3af;">${{pos.sector}}</div>
            <div style="color:#6b7280;">Poids:</div><div style="color:#22d3ee;">${{weight.toFixed(1)}}%</div>
            <div style="color:#6b7280;">Valeur:</div><div style="color:#fff;">${{formatMoney(pos.value)}}</div>
            <div style="color:#6b7280;">P&L:</div><div style="color:${{pnlColor}};">${{pnl >= 0 ? '+' : ''}}${{pnl.toFixed(1)}}%</div>
            <div style="color:#6b7280;">Jour:</div><div style="color:${{change >= 0 ? '#22c55e' : '#ef4444'}};">${{change >= 0 ? '+' : ''}}${{change.toFixed(2)}}%</div>
            <div style="color:#6b7280;">PE:</div><div style="color:${{peColor}};">${{pe !== null ? pe : '-'}}</div>
            <div style="color:#6b7280;">ROE:</div><div style="color:${{roeColor}};">${{roe !== null ? roe.toFixed(1) + '%' : '-'}}</div>
            <div style="color:#6b7280;">Score:</div><div style="color:${{scoreColor}};">${{score}}/10</div>
        </div>
    `;

    tooltip.style.display = 'block';
    moveHeatmapTooltip(e);
}}

function moveHeatmapTooltip(e) {{
    const tooltip = document.getElementById('heatmapTooltip');
    if (!tooltip) return;

    let x = e.clientX + 15;
    let y = e.clientY + 15;

    // Keep tooltip on screen
    const rect = tooltip.getBoundingClientRect();
    if (x + rect.width > window.innerWidth - 10) {{
        x = e.clientX - rect.width - 15;
    }}
    if (y + rect.height > window.innerHeight - 10) {{
        y = e.clientY - rect.height - 15;
    }}

    tooltip.style.left = x + 'px';
    tooltip.style.top = y + 'px';
}}

function hideHeatmapTooltip() {{
    const tooltip = document.getElementById('heatmapTooltip');
    if (tooltip) tooltip.style.display = 'none';
}}

// Keyboard shortcut for F10
document.addEventListener('keydown', function(e) {{
    if (e.key === 'F10') {{
        e.preventDefault();
        toggleHeatmapPanel();
    }}
}});

// Keyboard shortcut for F11
document.addEventListener('keydown', function(e) {{
    if (e.key === 'F11') {{
        e.preventDefault();
        runPortfolioAdvisor();
    }}
}});
</script>

</body></html>'''



def gen_advisor_html() -> str:
    """Dedicated page for Portfolio Advisor."""

    advisor_ok = 'true' if PORTFOLIO_ADVISOR_OK else 'false'
    anthropic_ok = 'true' if ANTHROPIC_OK else 'false'

    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>Olyos Capital — Portfolio Advisor</title>
<style>{BLOOMBERG_CSS}
.bb-advisor-page{{padding:16px}}
.bb-advisor-card{{background:#0a0a0a;border:1px solid #333;padding:16px}}
.bb-advisor-title{{color:#22d3ee;font-size:16px;font-weight:700;margin:0 0 12px 0;letter-spacing:1px}}
.bb-advisor-controls{{display:flex;gap:12px;align-items:center;flex-wrap:wrap;margin-bottom:12px}}
.bb-advisor-check{{display:flex;align-items:center;gap:6px;color:#9ca3af;font-size:11px}}
.bb-advisor-run{{background:linear-gradient(135deg,#0f2533,#143042);border:1px solid #22d3ee;color:#22d3ee;padding:8px 14px;cursor:pointer;font-family:inherit;font-size:11px}}
.bb-advisor-run:disabled{{opacity:.5;cursor:not-allowed}}
.bb-advisor-status{{color:#888;font-size:11px;margin-bottom:10px}}
.bb-advisor-report{{white-space:pre-wrap;font-family:'JetBrains Mono',monospace;font-size:11px;line-height:1.6;color:#cfd8e3;background:#070b12;border:1px solid #1f2d3a;padding:14px;min-height:420px;max-height:70vh;overflow:auto}}
.bb-advisor-meta{{margin-top:10px;color:#6b7280;font-size:10px}}
</style></head><body>
<div class="bb-top">
<div class="bb-logo"><svg viewBox="0 0 24 24" fill="#22d3ee"><rect x="2" y="2" width="8" height="8"/><rect x="14" y="2" width="8" height="8"/><rect x="2" y="14" width="8" height="8"/><rect x="14" y="14" width="8" height="8"/></svg><h1>OLYOS CAPITAL</h1><span>PORTFOLIO ADVISOR</span></div>
<input type="text" class="bb-cmd" placeholder="Enter ticker..." onkeydown="if(event.key==='Enter')location.href='/?detail='+this.value.toUpperCase()"/>
<div class="bb-time">{datetime.now().strftime('%H:%M:%S')} CET <span class="blink">●</span></div>
</div>
<div class="bb-fkeys">
<button class="fkey" onclick="location.href='/'">F1 PORT</button>
<button class="fkey" onclick="location.href='/screener'">F2 SCRN</button>
<button class="fkey" onclick="location.href='/advisor'">F5 REFRESH</button>
<button class="fkey active" onclick="runAdvisorAnalysis()">F11 ADVISOR</button>
</div>
<div class="bb-advisor-page">
<div class="bb-advisor-card">
<h2 class="bb-advisor-title">Portfolio Advisor Analysis</h2>
<div class="bb-advisor-controls">
<button id="advisor-run-btn" class="bb-advisor-run" onclick="runAdvisorAnalysis()" {'disabled' if not PORTFOLIO_ADVISOR_OK else ''}>RUN ADVISOR</button>
<label class="bb-advisor-check"><input type="checkbox" id="advisor-use-llm" {'checked' if ANTHROPIC_OK else ''} {'disabled' if not ANTHROPIC_OK else ''}>Use Claude</label>
<label class="bb-advisor-check"><input type="checkbox" id="advisor-refresh-prices">Live prices (Yahoo)</label>
</div>
<div id="advisor-status" class="bb-advisor-status">{'Advisor module unavailable.' if not PORTFOLIO_ADVISOR_OK else 'Ready.'}</div>
<div id="advisor-report-text" class="bb-advisor-report">Click "RUN ADVISOR" to generate the portfolio analysis.</div>
<div id="advisor-meta" class="bb-advisor-meta"></div>
</div>
</div>
<script>
const advisorAvailable = {advisor_ok};
const anthropicAvailable = {anthropic_ok};

function runAdvisorAnalysis() {{
    if (!advisorAvailable) {{
        alert('Portfolio advisor module unavailable.');
        return;
    }}

    const btn = document.getElementById('advisor-run-btn');
    const status = document.getElementById('advisor-status');
    const reportBox = document.getElementById('advisor-report-text');
    const metaEl = document.getElementById('advisor-meta');
    const useLLM = document.getElementById('advisor-use-llm').checked && anthropicAvailable;
    const refreshPrices = document.getElementById('advisor-refresh-prices').checked;

    btn.disabled = true;
    btn.textContent = 'RUNNING...';
    status.textContent = 'Analyzing portfolio...';

    fetch('/?action=portfolio_advisor', {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{
            use_llm: useLLM,
            refresh_prices: refreshPrices,
            currency: 'EUR'
        }})
    }})
    .then(r => r.json())
    .then(data => {{
        if (!data.success) {{
            throw new Error(data.error || 'Advisor error');
        }}
        reportBox.textContent = data.report_markdown || 'No report generated';
        status.textContent = 'Analysis completed.';
        metaEl.textContent = 'LLM: ' + (data.llm_used ? 'ON' : 'OFF') + ' | Prices: ' + (data.refresh_prices ? 'LIVE' : 'LOCAL') + ' | Report: ' + (data.report_path || 'n/a');
    }})
    .catch(err => {{
        status.textContent = 'Error';
        reportBox.textContent = 'Portfolio advisor error: ' + err.message;
    }})
    .finally(() => {{
        btn.disabled = false;
        btn.textContent = 'RUN ADVISOR';
    }});
}}

document.addEventListener('keydown', function(e) {{
    if (e.key === 'F1') {{ e.preventDefault(); location.href = '/'; }}
    if (e.key === 'F2') {{ e.preventDefault(); location.href = '/screener'; }}
    if (e.key === 'F5') {{ e.preventDefault(); location.href = '/advisor'; }}
    if (e.key === 'F11') {{ e.preventDefault(); runAdvisorAnalysis(); }}
}});
</script>
</body></html>'''


def gen_detail_html(data: Dict[str, Any]) -> str:

    def fmt(v, pre='', suf='', dec=2):

        if v is None or (isinstance(v, float) and math.isnan(v)): return '-'

        if isinstance(v, (int, float)):

            if abs(v) >= 1e9: return f"{pre}{v/1e9:.1f}B{suf}"

            if abs(v) >= 1e6: return f"{pre}{v/1e6:.1f}M{suf}"

            return f"{pre}{v:,.{dec}f}{suf}".replace(",", " ")

        return f"{pre}{v}{suf}"

    def pct(v):

        if v is None or (isinstance(v, float) and math.isnan(v)): return '-'

        return f"{v*100:+.2f}%" if abs(v) < 1 else f"{v:+.2f}%"

    

    chg_cls = 'pos' if data['change'] >= 0 else 'neg'

    chg_sign = '+' if data['change'] >= 0 else ''

    price_cls = '' if data['change'] >= 0 else 'down'

    

    # Prepare chart data

    price_history = data.get('price_history', [])

    chart_data_json = json.dumps(price_history)

    

    # Calculate performance stats

    if price_history and len(price_history) > 1:

        first_price = price_history[0]['close']

        last_price = price_history[-1]['close']

        perf_1y = ((last_price / first_price) - 1) * 100 if first_price > 0 else 0

        high_1y = max(p['close'] for p in price_history)

        low_1y = min(p['close'] for p in price_history)

        

        # 1 month perf (approx 22 trading days)

        if len(price_history) > 22:

            perf_1m = ((last_price / price_history[-22]['close']) - 1) * 100

        else:

            perf_1m = perf_1y

        

        # 3 month perf (approx 66 trading days)

        if len(price_history) > 66:

            perf_3m = ((last_price / price_history[-66]['close']) - 1) * 100

        else:

            perf_3m = perf_1y

    else:

        perf_1y = perf_1m = perf_3m = 0

        high_1y = low_1y = data['price']

    

    # Memo section - display content inline if available

    if data['memo_content']:

        memo_html = f'''

<div class="bb-memo-header" style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px">

<span style="color:#ff9500;font-size:10px;text-transform:uppercase;letter-spacing:1px">🔍„ {os.path.basename(data['memo_file'])}</span>

<a href="/?download={urllib.parse.quote(data['memo_file'])}" class="bb-btn" style="padding:4px 8px;font-size:9px">

â†“ Download

</a>

</div>

<div class="bb-memo-content">

{data['memo_content']}

</div>'''

    elif data['memo_file']:

        memo_html = f'''<a href="/?download={urllib.parse.quote(data['memo_file'])}" class="bb-memo-btn"><svg viewBox="0 0 24 24" fill="currentColor"><path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8l-6-6zm4 18H6V4h7v5h5v11z"/><path d="M12 18l4-4h-3v-4h-2v4H8l4 4z"/></svg>Download: {os.path.basename(data['memo_file'])}</a>'''

    else:

        ai_button = f'''<button class="bb-create-memo-btn" style="background:linear-gradient(180deg,#1a0033,#0d001a);border-color:#9933ff;color:#9933ff" onclick="generateAIMemo()" id="aiGenBtn">

<svg viewBox="0 0 24 24" fill="currentColor" width="16" height="16"><path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm-1 17.93c-3.95-.49-7-3.85-7-7.93 0-.62.08-1.21.21-1.79L9 15v1c0 1.1.9 2 2 2v1.93zm6.9-2.54c-.26-.81-1-1.39-1.9-1.39h-1v-3c0-.55-.45-1-1-1H8v-2h2c.55 0 1-.45 1-1V7h2c1.1 0 2-.9 2-2v-.41c2.93 1.19 5 4.06 5 7.41 0 2.08-.8 3.97-2.1 5.39z"/></svg>

🤖 Generate with AI

</button>''' if ANTHROPIC_OK else '<div style="color:#666;font-size:10px;margin-top:8px">AI generation requires ANTHROPIC_API_KEY environment variable</div>'

        

        memo_html = f'''

<div class="bb-no-memo">No investment memo available for this security.</div>

{ai_button}

<button class="bb-create-memo-btn" onclick="toggleMemoForm()">

<svg viewBox="0 0 24 24" fill="currentColor" width="16" height="16"><path d="M19 13h-6v6h-2v-6H5v-2h6V5h2v6h6v2z"/></svg>

âœï¸ Create Manual Memo

</button>

<div class="bb-memo-form" id="memoForm">

<h4>🔍 New Investment Memo - {data['ticker']}</h4>

<form id="createMemoForm" action="/?action=create_memo" method="POST">

<input type="hidden" name="ticker" value="{data['ticker']}">

<input type="hidden" name="name" value="{data['name']}">

<input type="hidden" name="sector" value="{data['sector']}">

<input type="hidden" name="country" value="{data['country']}">



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

<input type="number" name="target_price" step="0.01" placeholder="Ex: 25.50" value="{data['target_price'] if data['target_price'] else ''}">

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

    

    return f'''<!DOCTYPE html><html><head><meta charset="UTF-8"><title>{data['ticker']} - Bloomberg</title>

<style>{BLOOMBERG_CSS}</style></head><body>

<div class="bb-top">

<div class="bb-logo"><svg viewBox="0 0 24 24" fill="#ff9500"><rect x="2" y="2" width="8" height="8"/><rect x="14" y="2" width="8" height="8"/><rect x="2" y="14" width="8" height="8"/><rect x="14" y="14" width="8" height="8"/></svg><h1>BLOOMBERG</h1><span>SECURITY DETAIL</span></div>

<input type="text" class="bb-cmd" placeholder="Enter ticker..." onkeydown="if(event.key==='Enter')location.href='/?detail='+this.value.toUpperCase()"/>

<div class="bb-time">{datetime.now().strftime('%H:%M:%S')} CET <span class="blink">●</span></div>

</div>

<div class="bb-fkeys">

<button class="fkey" onclick="location.href='/'">F1 PORT</button>

<button class="fkey">F2 SCRN</button>

<button class="fkey">F3 WTCH</button>

<button class="fkey" onclick="location.href='/?detail={data['ticker']}&refresh=1'">F5 REFRESH</button>

<button class="fkey active">F8 DETAIL</button>

</div>

<div class="bb-detail">

<a href="/" class="bb-back">â† Back to Portfolio</a>

<div class="bb-detail-header">

<div class="bb-detail-title">

<div><div class="bb-detail-name">{data['name'] or data['ticker']}</div><div class="bb-detail-ticker">{data['ticker']}</div><div class="bb-detail-sector">{data['sector']}{('  -  ' + data.get('industry','')) if data.get('industry') else ''}{('  -  ' + data['country']) if data['country'] else ''}</div></div>

<div style="display:flex;align-items:center;gap:16px;">
<div class="bb-detail-price"><div class="bb-detail-price-val {price_cls}">{fmt(data['price'])} EUR</div><div class="bb-detail-change {chg_cls}">{chg_sign}{fmt(data['change'])} ({chg_sign}{fmt(data['change_pct'])}%)</div></div>
<button class="bb-btn bb-btn-g" onclick="addToWatchlistDetail(this)" style="white-space:nowrap;padding:8px 16px;">+ WATCHLIST</button>
<button class="bb-btn" onclick="toggleAlertConfig()" style="white-space:nowrap;padding:8px 16px;">🔔 ALERTS</button>
<button id="btn-ai-analyze" class="btn-analyze" onclick="launchAnalysis('{data['ticker']}')" style="white-space:nowrap;"><span class="analyze-icon">◆</span><span class="analyze-text">Analyser</span><span class="analyze-badge">IA</span></button>
</div>

</div></div>

<!-- Alert Configuration Panel -->
<div id="alert-config-panel" class="bb-alert-config" style="display:none;">
<div class="bb-alert-config-header">
<span>🔔 Configure Alerts for {data['ticker']}</span>
<button onclick="toggleAlertConfig()" style="background:none;border:none;color:#888;cursor:pointer;font-size:16px;">✕</button>
</div>
<div class="bb-alert-config-body">
<div class="bb-alert-config-row">
<label>PE Threshold (alert when PE &lt; this)</label>
<input type="number" id="alert-pe" value="10" step="0.5" placeholder="e.g. 10">
</div>
<div class="bb-alert-config-row">
<label>ROE Threshold % (alert when ROE &gt; this)</label>
<input type="number" id="alert-roe" value="12" step="0.5" placeholder="e.g. 12">
</div>
<div class="bb-alert-config-row">
<label>Price Below (alert when price drops below)</label>
<input type="number" id="alert-price-below" step="0.01" placeholder="e.g. {fmt(data['price']*0.9) if data['price'] else ''}">
</div>
<div class="bb-alert-config-row">
<label>Price Above (alert when price rises above)</label>
<input type="number" id="alert-price-above" step="0.01" placeholder="e.g. {fmt(data['price']*1.1) if data['price'] else ''}">
</div>
<div class="bb-alert-config-actions">
<button class="bb-btn bb-btn-g" onclick="saveAlertConfig()">💾 SAVE ALERTS</button>
<button class="bb-btn" onclick="toggleAlertConfig()">CANCEL</button>
</div>
</div>
</div>

<style>
.bb-alert-config {{
  background: linear-gradient(135deg, #1a1a1a 0%, #0d0d0d 100%);
  border: 1px solid #ff9500;
  border-radius: 4px;
  margin: 15px 0;
  overflow: hidden;
}}
.bb-alert-config-header {{
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 12px 15px;
  background: linear-gradient(90deg, rgba(255,149,0,0.2) 0%, transparent 100%);
  border-bottom: 1px solid #333;
  color: #ff9500;
  font-weight: 600;
}}
.bb-alert-config-body {{
  padding: 15px;
}}
.bb-alert-config-row {{
  margin-bottom: 12px;
}}
.bb-alert-config-row label {{
  display: block;
  color: #888;
  font-size: 11px;
  margin-bottom: 4px;
  text-transform: uppercase;
  letter-spacing: 1px;
}}
.bb-alert-config-row input {{
  width: 100%;
  background: #1a1a1a;
  border: 1px solid #333;
  color: #fff;
  padding: 8px 12px;
  font-family: 'JetBrains Mono', monospace;
  font-size: 13px;
  border-radius: 3px;
}}
.bb-alert-config-row input:focus {{
  border-color: #ff9500;
  outline: none;
}}
.bb-alert-config-actions {{
  display: flex;
  gap: 10px;
  margin-top: 15px;
  padding-top: 15px;
  border-top: 1px solid #333;
}}
</style>

<style id="analysis-styles">
/* ========================================
   AI Equity Research — Button & Modal CSS
   ======================================== */

/* Analyze Button */
.btn-analyze {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 16px;
    background: linear-gradient(135deg, #1a2332 0%, #111822 100%);
    border: 1px solid #00ff88;
    border-radius: 4px;
    color: #00ff88;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s ease;
    letter-spacing: 0.5px;
}}
.btn-analyze:hover {{
    background: linear-gradient(135deg, #00ff88 0%, #00cc6a 100%);
    color: #0a0e14;
    box-shadow: 0 0 20px rgba(0, 255, 136, 0.3);
}}
.btn-analyze:active {{ transform: scale(0.98); }}
.btn-analyze .analyze-icon {{ font-size: 14px; }}
.btn-analyze .analyze-badge {{
    background: rgba(0, 255, 136, 0.15);
    padding: 1px 6px;
    border-radius: 2px;
    font-size: 9px;
    letter-spacing: 1px;
}}
.btn-analyze:hover .analyze-badge {{ background: rgba(10, 14, 20, 0.3); }}
.btn-analyze.loading {{
    pointer-events: none;
    opacity: 0.7;
    border-color: #ff9500;
    color: #ff9500;
}}
.btn-analyze.loading .analyze-badge {{
    background: rgba(255, 149, 0, 0.15);
    animation: analysePulse 1.5s infinite;
}}
@keyframes analysePulse {{
    0%, 100% {{ opacity: 1; }}
    50% {{ opacity: 0.4; }}
}}

/* Modal Fullscreen */
.analysis-modal {{
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: #0a0e14;
    z-index: 10000;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}}
.analysis-modal-header {{
    background: #111822;
    border-bottom: 1px solid #1e2d3d;
    padding: 8px 16px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-shrink: 0;
}}
.analysis-modal-logo {{
    color: #00ff88;
    font-weight: 700;
    font-size: 13px;
    letter-spacing: 2px;
}}
.analysis-modal-meta {{
    color: #484f58;
    font-size: 10px;
}}
.analysis-modal-meta span {{
    color: #ff9500;
}}
.analysis-cache-badge {{
    background: rgba(88,166,255,0.15);
    color: #58a6ff;
    padding: 1px 6px;
    border-radius: 2px;
    font-size: 8px;
    letter-spacing: 1px;
    margin-left: 8px;
    border: 1px solid rgba(88,166,255,0.3);
}}
.analysis-modal-actions {{
    display: flex;
    gap: 4px;
}}
.modal-btn {{
    background: transparent;
    border: 1px solid #1e2d3d;
    color: #8b949e;
    padding: 4px 10px;
    border-radius: 3px;
    cursor: pointer;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    transition: all 0.15s;
}}
.modal-btn:hover {{
    border-color: #00ff88;
    color: #00ff88;
}}
.modal-btn-close:hover {{
    border-color: #ff4444;
    color: #ff4444;
}}

/* Content area (scrollable) */
.analysis-content {{
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    max-width: 1400px;
    margin: 0 auto;
    width: 100%;
}}

/* Loading */
.analysis-loading {{
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 16px;
}}
.loading-spinner {{
    width: 40px;
    height: 40px;
    border: 3px solid #1e2d3d;
    border-top-color: #00ff88;
    border-radius: 50%;
    animation: analyseSpin 1s linear infinite;
}}
@keyframes analyseSpin {{
    to {{ transform: rotate(360deg); }}
}}
.loading-text {{
    color: #e6edf3;
    font-size: 14px;
    font-weight: 600;
}}
.loading-subtext {{
    color: #484f58;
    font-size: 11px;
}}
.loading-steps {{
    margin-top: 16px;
    display: flex;
    flex-direction: column;
    gap: 8px;
}}
.loading-step {{
    color: #484f58;
    font-size: 11px;
    transition: color 0.3s;
}}
.loading-step.active {{
    color: #00ff88;
}}
.loading-step.done {{
    color: #8b949e;
}}

/* Error */
.analysis-error {{
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
}}
.error-icon {{
    font-size: 32px;
    color: #ff4444;
}}
.error-text {{
    color: #ff4444;
    font-size: 12px;
}}

/* ========================================
   Equity Research Report Design System
   (Classes used by the Claude-generated HTML)
   ======================================== */

/* Ticker Header */
.analysis-content .ticker-header {{
    background: #111822;
    border: 1px solid #1e2d3d;
    border-radius: 4px;
    padding: 20px 24px;
    margin-bottom: 12px;
    display: grid;
    grid-template-columns: 1fr auto;
    gap: 24px;
    align-items: start;
}}
.analysis-content .ticker-info h1 {{
    font-size: 22px;
    font-weight: 700;
    color: #e6edf3;
    margin-bottom: 2px;
}}
.analysis-content .ticker-info h1 .ticker {{ color: #ff9500; }}
.analysis-content .ticker-info .subtitle {{ color: #8b949e; font-size: 11px; }}
.analysis-content .price-block {{ text-align: right; }}
.analysis-content .price-block .price {{
    font-size: 32px;
    font-weight: 700;
}}
.analysis-content .price-block .price-eur {{ color: #484f58; font-size: 14px; }}
.analysis-content .price-block .change {{ font-size: 12px; margin-top: 2px; }}
.analysis-content .price-block .asof {{ color: #484f58; font-size: 9px; margin-top: 4px; }}

/* Verdict Banner */
.analysis-content .verdict-banner {{
    background: linear-gradient(135deg, #1a2332 0%, #0f1922 100%);
    border: 1px solid #ff9500;
    border-left: 4px solid #ff9500;
    border-radius: 4px;
    padding: 16px 20px;
    margin-bottom: 12px;
}}
.analysis-content .verdict-banner .verdict-label {{
    color: #ff9500;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 2px;
    text-transform: uppercase;
    margin-bottom: 6px;
}}
.analysis-content .verdict-banner .verdict-text {{
    color: #e6edf3;
    font-size: 13px;
    font-weight: 500;
    line-height: 1.7;
}}

/* Grid Layouts */
.analysis-content .grid-2 {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 12px;
    margin-bottom: 12px;
}}
.analysis-content .grid-3 {{
    display: grid;
    grid-template-columns: 1fr 1fr 1fr;
    gap: 12px;
    margin-bottom: 12px;
}}
@media (max-width: 900px) {{
    .analysis-content .grid-2, .analysis-content .grid-3 {{ grid-template-columns: 1fr; }}
}}

/* Panel */
.analysis-content .panel {{
    background: #111822;
    border: 1px solid #1e2d3d;
    border-radius: 4px;
    overflow: hidden;
}}
.analysis-content .panel-title {{
    background: #1a2332;
    padding: 8px 14px;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    color: #00ff88;
    border-bottom: 1px solid #1e2d3d;
}}
.analysis-content .panel-body {{
    padding: 14px;
}}

/* Metrics */
.analysis-content .metric-row {{
    display: flex;
    justify-content: space-between;
    align-items: center;
    padding: 5px 0;
    border-bottom: 1px solid rgba(30,45,61,0.5);
}}
.analysis-content .metric-row:last-child {{ border-bottom: none; }}
.analysis-content .metric-label {{
    color: #8b949e;
    font-size: 11px;
}}
.analysis-content .metric-value {{
    font-weight: 600;
    font-size: 12px;
}}
.analysis-content .metric-value.good {{ color: #00ff88; }}
.analysis-content .metric-value.warning {{ color: #ff9500; }}
.analysis-content .metric-value.bad {{ color: #ff4444; }}
.analysis-content .metric-value.neutral {{ color: #e6edf3; }}

/* Higgons Score */
.analysis-content .higgons-grid {{
    display: grid;
    grid-template-columns: 1fr;
    gap: 8px;
}}
.analysis-content .higgons-criteria {{
    display: grid;
    grid-template-columns: auto 1fr auto auto;
    gap: 10px;
    align-items: center;
    padding: 8px 10px;
    background: #0a0e14;
    border-radius: 3px;
    border-left: 3px solid transparent;
}}
.analysis-content .higgons-criteria.pass {{ border-left-color: #00ff88; }}
.analysis-content .higgons-criteria.fail {{ border-left-color: #ff4444; }}
.analysis-content .higgons-criteria.partial {{ border-left-color: #ff9500; }}
.analysis-content .criteria-icon {{
    width: 18px;
    height: 18px;
    border-radius: 50%;
    display: flex;
    align-items: center;
    justify-content: center;
    font-size: 10px;
    font-weight: 700;
}}
.analysis-content .criteria-icon.pass {{ background: rgba(0,255,136,0.15); color: #00ff88; }}
.analysis-content .criteria-icon.fail {{ background: rgba(255,68,68,0.15); color: #ff4444; }}
.analysis-content .criteria-icon.partial {{ background: rgba(255,149,0,0.15); color: #ff9500; }}
.analysis-content .criteria-name {{ font-size: 11px; color: #e6edf3; }}
.analysis-content .criteria-target {{ font-size: 10px; color: #484f58; }}
.analysis-content .criteria-actual {{ font-size: 11px; font-weight: 600; }}

/* Score Badge */
.analysis-content .score-badge {{
    text-align: center;
    padding: 16px;
    margin-top: 10px;
    background: #0a0e14;
    border-radius: 4px;
}}
.analysis-content .score-badge .score-num {{
    font-size: 36px;
    font-weight: 700;
}}
.analysis-content .score-badge .score-label {{
    font-size: 10px;
    color: #484f58;
    letter-spacing: 1px;
    text-transform: uppercase;
    margin-top: 2px;
}}

/* Financial Table */
.analysis-content .fin-table {{
    width: 100%;
    border-collapse: collapse;
    font-size: 11px;
}}
.analysis-content .fin-table th {{
    text-align: right;
    padding: 6px 8px;
    color: #484f58;
    font-weight: 500;
    font-size: 10px;
    border-bottom: 1px solid #1e2d3d;
}}
.analysis-content .fin-table th:first-child {{ text-align: left; }}
.analysis-content .fin-table td {{
    text-align: right;
    padding: 5px 8px;
    border-bottom: 1px solid rgba(30,45,61,0.3);
}}
.analysis-content .fin-table td:first-child {{
    text-align: left;
    color: #8b949e;
}}
.analysis-content .fin-table tr:hover {{ background: rgba(0,255,136,0.02); }}

/* SWOT */
.analysis-content .swot-grid {{
    display: grid;
    grid-template-columns: 1fr 1fr;
    gap: 10px;
}}
.analysis-content .swot-box {{
    padding: 12px;
    border-radius: 3px;
    background: #0a0e14;
}}
.analysis-content .swot-box h4 {{
    font-size: 10px;
    letter-spacing: 1.5px;
    text-transform: uppercase;
    margin-bottom: 8px;
    padding-bottom: 4px;
    border-bottom: 1px solid #1e2d3d;
}}
.analysis-content .swot-box.strength h4 {{ color: #00ff88; }}
.analysis-content .swot-box.weakness h4 {{ color: #ff4444; }}
.analysis-content .swot-box.opportunity h4 {{ color: #58a6ff; }}
.analysis-content .swot-box.threat h4 {{ color: #ff9500; }}
.analysis-content .swot-box ul {{ list-style: none; padding: 0; }}
.analysis-content .swot-box li {{
    font-size: 10px;
    color: #8b949e;
    padding: 3px 0;
    padding-left: 12px;
    position: relative;
    line-height: 1.5;
}}
.analysis-content .swot-box li::before {{
    content: '›';
    position: absolute;
    left: 0;
    font-weight: 700;
}}
.analysis-content .swot-box.strength li::before {{ color: #00ff88; }}
.analysis-content .swot-box.weakness li::before {{ color: #ff4444; }}
.analysis-content .swot-box.opportunity li::before {{ color: #58a6ff; }}
.analysis-content .swot-box.threat li::before {{ color: #ff9500; }}

/* Tags */
.analysis-content .tag {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 2px;
    font-size: 9px;
    font-weight: 600;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}}
.analysis-content .tag.buy {{ background: rgba(0,255,136,0.12); color: #00ff88; border: 1px solid rgba(0,255,136,0.3); }}
.analysis-content .tag.hold {{ background: rgba(255,149,0,0.12); color: #ff9500; border: 1px solid rgba(255,149,0,0.3); }}
.analysis-content .tag.sell {{ background: rgba(255,68,68,0.12); color: #ff4444; border: 1px solid rgba(255,68,68,0.3); }}
.analysis-content .tag.info {{ background: rgba(88,166,255,0.12); color: #58a6ff; border: 1px solid rgba(88,166,255,0.3); }}

/* Progress Bar */
.analysis-content .progress-container {{
    display: flex;
    align-items: center;
    gap: 8px;
    margin: 4px 0;
}}
.analysis-content .progress-bar {{
    flex: 1;
    height: 4px;
    background: #0a0e14;
    border-radius: 2px;
    overflow: hidden;
}}
.analysis-content .progress-fill {{
    height: 100%;
    border-radius: 2px;
    transition: width 0.3s;
}}
.analysis-content .progress-label {{
    font-size: 10px;
    color: #484f58;
    min-width: 30px;
}}

/* Narrative */
.analysis-content .narrative {{
    padding: 14px;
    font-size: 11px;
    color: #8b949e;
    line-height: 1.8;
}}
.analysis-content .narrative p {{ margin-bottom: 10px; }}
.analysis-content .narrative strong {{ color: #e6edf3; }}
.analysis-content .narrative .highlight-green {{ color: #00ff88; }}
.analysis-content .narrative .highlight-red {{ color: #ff4444; }}
.analysis-content .narrative .highlight-orange {{ color: #ff9500; }}

/* Section Title */
.analysis-content .section-title {{
    color: #00ff88;
    font-size: 10px;
    font-weight: 600;
    letter-spacing: 2px;
    text-transform: uppercase;
    margin: 20px 0 12px;
    padding-bottom: 6px;
    border-bottom: 1px solid #1e2d3d;
}}

/* Separator */
.analysis-content .sep {{
    height: 1px;
    background: #1e2d3d;
    margin: 16px 0;
}}

/* Full width panel */
.analysis-content .full-width {{ margin-bottom: 12px; }}

/* Footer */
.analysis-content .footer {{
    margin-top: 24px;
    padding: 12px;
    text-align: center;
    color: #484f58;
    font-size: 9px;
    border-top: 1px solid #1e2d3d;
}}
.analysis-content .footer .disclaimer {{
    max-width: 800px;
    margin: 0 auto;
    line-height: 1.6;
}}

/* Live dot animation */
.analysis-content .live-dot {{
    display: inline-block;
    width: 6px;
    height: 6px;
    border-radius: 50%;
    background: #00ff88;
    animation: analyseBlink 1.5s infinite;
    margin-right: 4px;
}}
@keyframes analyseBlink {{
    0%, 50% {{ opacity: 1; }}
    51%, 100% {{ opacity: 0.3; }}
}}

@media (max-width: 900px) {{
    .analysis-content .swot-grid {{ grid-template-columns: 1fr; }}
    .analysis-content .ticker-header {{ grid-template-columns: 1fr; }}
}}
</style>

<div class="bb-chart-container">

<div class="bb-chart-header">

<span class="bb-chart-title">📈 Price History (1 Year)</span>

<div class="bb-chart-period">

<button onclick="setChartPeriod(30)" id="btn-1m">1M</button>

<button onclick="setChartPeriod(90)" id="btn-3m">3M</button>

<button onclick="setChartPeriod(180)" id="btn-6m">6M</button>

<button onclick="setChartPeriod(365)" id="btn-1y" class="active">1Y</button>

</div>

</div>

<div class="bb-chart"><canvas id="priceChart"></canvas></div>

<div class="bb-chart-stats">

<div class="bb-chart-stat"><span class="bb-chart-stat-label">1M Perf</span><span class="bb-chart-stat-value {'pos' if perf_1m >= 0 else 'neg'}">{'+' if perf_1m >= 0 else ''}{perf_1m:.1f}%</span></div>

<div class="bb-chart-stat"><span class="bb-chart-stat-label">3M Perf</span><span class="bb-chart-stat-value {'pos' if perf_3m >= 0 else 'neg'}">{'+' if perf_3m >= 0 else ''}{perf_3m:.1f}%</span></div>

<div class="bb-chart-stat"><span class="bb-chart-stat-label">1Y Perf</span><span class="bb-chart-stat-value {'pos' if perf_1y >= 0 else 'neg'}">{'+' if perf_1y >= 0 else ''}{perf_1y:.1f}%</span></div>

<div class="bb-chart-stat"><span class="bb-chart-stat-label">52W High</span><span class="bb-chart-stat-value">{fmt(high_1y)}</span></div>

<div class="bb-chart-stat"><span class="bb-chart-stat-label">52W Low</span><span class="bb-chart-stat-value">{fmt(low_1y)}</span></div>

</div>

</div>

<div class="bb-detail-grid">

<div class="bb-detail-card"><h3>Valuation</h3>

<div class="bb-metric"><span class="bb-metric-label">P/E (TTM)</span><span class="bb-metric-val">{fmt(data['pe'],dec=1)}</span></div>

<div class="bb-metric"><span class="bb-metric-label">P/E (FWD)</span><span class="bb-metric-val">{fmt(data.get('forward_pe'),dec=1)}</span></div>

<div class="bb-metric"><span class="bb-metric-label">EPS</span><span class="bb-metric-val">{fmt(data['eps'])}</span></div>

<div class="bb-metric"><span class="bb-metric-label">Book Value</span><span class="bb-metric-val">{fmt(data['book_value'])}</span></div>

<div class="bb-metric"><span class="bb-metric-label">Target Price</span><span class="bb-metric-val">{fmt(data['target_price'])}</span></div>

</div>

<div class="bb-detail-card"><h3>Returns</h3>

<div class="bb-metric"><span class="bb-metric-label">ROE</span><span class="bb-metric-val {'pos' if data['roe'] and data['roe']>0.10 else ''}">{pct(data['roe'])}</span></div>

<div class="bb-metric"><span class="bb-metric-label">Profit Margin</span><span class="bb-metric-val">{pct(data['profit_margin'])}</span></div>

<div class="bb-metric"><span class="bb-metric-label">Dividend Yield</span><span class="bb-metric-val">{pct(data['dividend_yield'])}</span></div>

<div class="bb-metric"><span class="bb-metric-label">Beta</span><span class="bb-metric-val">{fmt(data['beta'])}</span></div>

</div>

<div class="bb-detail-card"><h3>Trading Data</h3>

<div class="bb-metric"><span class="bb-metric-label">Market Cap</span><span class="bb-metric-val">{fmt(data['market_cap'])}</span></div>

<div class="bb-metric"><span class="bb-metric-label">52W High</span><span class="bb-metric-val">{fmt(data['high_52w'])}</span></div>

<div class="bb-metric"><span class="bb-metric-label">52W Low</span><span class="bb-metric-val">{fmt(data['low_52w'])}</span></div>

<div class="bb-metric"><span class="bb-metric-label">Volume</span><span class="bb-metric-val">{fmt(data['volume'],dec=0)}</span></div>

<div class="bb-metric"><span class="bb-metric-label">Avg Volume</span><span class="bb-metric-val">{fmt(data['avg_volume'],dec=0)}</span></div>

</div>

<div class="bb-detail-card"><h3>Financial Health</h3>

<div class="bb-metric"><span class="bb-metric-label">Revenue</span><span class="bb-metric-val">{fmt(data['revenue'])}</span></div>

<div class="bb-metric"><span class="bb-metric-label">Debt/Equity</span><span class="bb-metric-val {'neg' if data['debt_equity'] and data['debt_equity']>100 else ''}">{fmt(data['debt_equity'],dec=1)}</span></div>

<div class="bb-metric"><span class="bb-metric-label">Current Ratio</span><span class="bb-metric-val">{fmt(data['current_ratio'])}</span></div>

<div class="bb-metric"><span class="bb-metric-label">Employees</span><span class="bb-metric-val">{fmt(data.get('employees'),dec=0)}</span></div>

</div>

<div class="bb-detail-card bb-dividend-section" id="dividend-section">
<h3>💰 Dividends</h3>
<div id="dividend-loading" style="color:#666;font-size:11px;text-align:center;padding:20px;">Loading dividend data...</div>
<div id="dividend-content" style="display:none;">
<div class="bb-metric"><span class="bb-metric-label">Annual Dividend</span><span class="bb-metric-val" id="div-annual">-</span></div>
<div class="bb-metric"><span class="bb-metric-label">Dividend Yield</span><span class="bb-metric-val" id="div-yield-detail">-</span></div>
<div class="bb-metric"><span class="bb-metric-label">Frequency</span><span class="bb-metric-val" id="div-freq">-</span></div>
<div class="bb-metric"><span class="bb-metric-label">5Y Growth (CAGR)</span><span class="bb-metric-val" id="div-growth">-</span></div>
<div class="bb-metric"><span class="bb-metric-label">Next Ex-Date</span><span class="bb-metric-val" id="div-next">-</span></div>
<div id="div-history-mini" style="margin-top:10px;border-top:1px solid #333;padding-top:10px;">
<div style="color:#888;font-size:9px;text-transform:uppercase;letter-spacing:0.5px;margin-bottom:6px;">Recent Payments</div>
<div id="div-history-list" style="max-height:100px;overflow-y:auto;"></div>
</div>
</div>
<div id="dividend-empty" style="display:none;color:#666;font-size:11px;text-align:center;padding:15px;font-style:italic;">No dividend history available for this security.</div>
</div>

<div class="bb-detail-card bb-detail-desc"><h3>Business Description</h3>

<p>{(data['description'][:800]+'...') if len(data['description'])>800 else data['description'] or 'No description available.'}</p>

{f'<p style="margin-top:8px"><a href="{data.get("website","")}" target="_blank" style="color:#00bfff">{data.get("website","")}</a></p>' if data.get('website') else ''}

</div>

<div class="bb-detail-card bb-memo-section"><h3>Investment Memo</h3>{memo_html}</div>

</div></div>

<div class="bb-status"><div class="bb-status-l">BLOOMBERG LP | {data['ticker']} | {datetime.now().strftime('%d-%b-%Y %H:%M:%S').upper()}</div><div class="bb-status-r">Connected <span class="blink">●</span></div></div>

<script>

// Add to watchlist from detail page
function addToWatchlistDetail(btn) {{
    const ticker = '{data["ticker"]}';
    const name = '{data.get("name", data["ticker"])}';
    const country = '{data.get("country", "")}';
    const sector = '{data.get("sector", "")}';

    fetch(`/?action=addwatch&ticker=${{ticker}}&name=${{encodeURIComponent(name)}}&country=${{country}}&sector=${{encodeURIComponent(sector)}}`)
        .then(r => r.text())
        .then(() => {{
            alert('✓ ' + ticker + ' added to watchlist');
            btn.textContent = '✓ IN WATCHLIST';
            btn.disabled = true;
            btn.style.opacity = '0.6';
        }})
        .catch(err => {{
            alert('Error adding to watchlist: ' + err);
        }});
}}

// Alert configuration functions
function toggleAlertConfig() {{
    const panel = document.getElementById('alert-config-panel');
    panel.style.display = panel.style.display === 'none' ? 'block' : 'none';
}}

function saveAlertConfig() {{
    const ticker = '{data["ticker"]}';
    const pe = document.getElementById('alert-pe').value;
    const roe = document.getElementById('alert-roe').value;
    const priceBelow = document.getElementById('alert-price-below').value;
    const priceAbove = document.getElementById('alert-price-above').value;

    let url = `/?action=set_alert_config&ticker=${{ticker}}`;
    if (pe) url += `&pe_threshold=${{pe}}`;
    if (roe) url += `&roe_threshold=${{roe}}`;
    if (priceBelow) url += `&price_below=${{priceBelow}}`;
    if (priceAbove) url += `&price_above=${{priceAbove}}`;

    fetch(url)
        .then(r => r.json())
        .then(data => {{
            if (data.success) {{
                alert('✓ Alert configuration saved for ' + ticker);
                toggleAlertConfig();
            }} else {{
                alert('Error: ' + (data.error || 'Unknown error'));
            }}
        }})
        .catch(err => {{
            alert('Error saving alert config: ' + err);
        }});
}}

// Clock update

setInterval(()=>{{var now=new Date();document.querySelector('.bb-time').innerHTML=('0'+now.getHours()).slice(-2)+':'+('0'+now.getMinutes()).slice(-2)+':'+('0'+now.getSeconds()).slice(-2)+' CET <span class="blink">●</span>'}},1000);



// Chart data and rendering

const allData = {chart_data_json};

let currentPeriod = 365;



function setChartPeriod(days) {{

    currentPeriod = days;

    document.querySelectorAll('.bb-chart-period button').forEach(b => b.classList.remove('active'));

    document.getElementById('btn-' + (days === 30 ? '1m' : days === 90 ? '3m' : days === 180 ? '6m' : '1y')).classList.add('active');

    drawChart();

}}



function drawChart() {{

    const canvas = document.getElementById('priceChart');

    if (!canvas || !allData.length) return;

    

    const ctx = canvas.getContext('2d');

    const rect = canvas.parentElement.getBoundingClientRect();

    canvas.width = rect.width;

    canvas.height = rect.height;

    

    // Filter data by period

    const data = allData.slice(-currentPeriod);

    if (data.length < 2) return;

    

    const prices = data.map(d => d.close);

    const minPrice = Math.min(...prices);

    const maxPrice = Math.max(...prices);

    const priceRange = maxPrice - minPrice || 1;

    

    const padding = {{ top: 20, right: 60, bottom: 30, left: 10 }};

    const chartWidth = canvas.width - padding.left - padding.right;

    const chartHeight = canvas.height - padding.top - padding.bottom;

    

    // Clear canvas

    ctx.fillStyle = '#050505';

    ctx.fillRect(0, 0, canvas.width, canvas.height);

    

    // Draw grid lines

    ctx.strokeStyle = '#1a1a1a';

    ctx.lineWidth = 1;

    for (let i = 0; i <= 4; i++) {{

        const y = padding.top + (chartHeight / 4) * i;

        ctx.beginPath();

        ctx.moveTo(padding.left, y);

        ctx.lineTo(canvas.width - padding.right, y);

        ctx.stroke();

        

        // Price labels

        const price = maxPrice - (priceRange / 4) * i;

        ctx.fillStyle = '#666';

        ctx.font = '10px JetBrains Mono';

        ctx.textAlign = 'left';

        ctx.fillText(price.toFixed(2), canvas.width - padding.right + 5, y + 4);

    }}

    

    // Determine if positive or negative trend

    const isPositive = prices[prices.length - 1] >= prices[0];

    const lineColor = isPositive ? '#00ff00' : '#ff3b30';

    const fillColor = isPositive ? 'rgba(0, 255, 0, 0.1)' : 'rgba(255, 59, 48, 0.1)';

    

    // Draw area fill

    ctx.beginPath();

    ctx.moveTo(padding.left, padding.top + chartHeight);

    data.forEach((d, i) => {{

        const x = padding.left + (i / (data.length - 1)) * chartWidth;

        const y = padding.top + ((maxPrice - d.close) / priceRange) * chartHeight;

        ctx.lineTo(x, y);

    }});

    ctx.lineTo(padding.left + chartWidth, padding.top + chartHeight);

    ctx.closePath();

    ctx.fillStyle = fillColor;

    ctx.fill();

    

    // Draw price line

    ctx.beginPath();

    ctx.strokeStyle = lineColor;

    ctx.lineWidth = 2;

    data.forEach((d, i) => {{

        const x = padding.left + (i / (data.length - 1)) * chartWidth;

        const y = padding.top + ((maxPrice - d.close) / priceRange) * chartHeight;

        if (i === 0) ctx.moveTo(x, y);

        else ctx.lineTo(x, y);

    }});

    ctx.stroke();

    

    // Draw current price line

    const lastPrice = prices[prices.length - 1];

    const lastY = padding.top + ((maxPrice - lastPrice) / priceRange) * chartHeight;

    ctx.strokeStyle = lineColor;

    ctx.setLineDash([5, 3]);

    ctx.beginPath();

    ctx.moveTo(padding.left, lastY);

    ctx.lineTo(canvas.width - padding.right, lastY);

    ctx.stroke();

    ctx.setLineDash([]);

    

    // Draw current price label

    ctx.fillStyle = lineColor;

    ctx.font = 'bold 11px JetBrains Mono';

    ctx.fillText(lastPrice.toFixed(2), canvas.width - padding.right + 5, lastY + 4);

    

    // Draw date labels

    ctx.fillStyle = '#666';

    ctx.font = '9px JetBrains Mono';

    ctx.textAlign = 'center';

    const labelCount = Math.min(6, data.length);

    for (let i = 0; i < labelCount; i++) {{

        const idx = Math.floor((i / (labelCount - 1)) * (data.length - 1));

        const x = padding.left + (idx / (data.length - 1)) * chartWidth;

        const date = new Date(data[idx].date);

        const label = date.toLocaleDateString('fr-FR', {{ month: 'short', day: 'numeric' }});

        ctx.fillText(label, x, canvas.height - 10);

    }}

}}



// Initial draw

setTimeout(drawChart, 100);

window.addEventListener('resize', drawChart);



// Memo form toggle

function toggleMemoForm() {{

    const form = document.getElementById('memoForm');

    form.classList.toggle('active');

}}



// Generate memo with AI

function generateAIMemo() {{

    const btn = document.getElementById('aiGenBtn');

    if (!btn) return;

    const originalText = btn.innerHTML;

    btn.innerHTML = 'â³ Generating with AI...';

    btn.disabled = true;

    btn.style.opacity = '0.6';

    

    fetch('/?action=generate_ai_memo&ticker={data["ticker"]}', {{

        method: 'POST'

    }}).then(response => response.json())

    .then(result => {{

        if (result.success) {{

            alert('AI Memo generated successfully!');

            location.reload();

        }} else {{

            alert('Error generating memo: ' + result.error);

            btn.innerHTML = originalText;

            btn.disabled = false;

            btn.style.opacity = '1';

        }}

    }}).catch(err => {{

        alert('Error: ' + err);

        btn.innerHTML = originalText;

        btn.disabled = false;

        btn.style.opacity = '1';

    }});

}}



// Handle memo form submission

document.getElementById('createMemoForm')?.addEventListener('submit', function(e) {{

    e.preventDefault();

    const formData = new FormData(this);

    fetch('/?action=create_memo', {{

        method: 'POST',

        body: formData

    }}).then(response => response.json())

    .then(data => {{

        if (data.success) {{

            alert('Memo created successfully!');

            location.reload();

        }} else {{

            alert('Error creating memo: ' + data.error);

        }}

    }}).catch(err => {{

        alert('Error: ' + err);

    }});

}});

// Load dividend data for this ticker
function loadTickerDividends() {{
    const ticker = '{data["ticker"]}';
    fetch(`/?action=dividends_ticker&ticker=${{ticker}}&years=5`)
        .then(r => r.json())
        .then(data => {{
            const loading = document.getElementById('dividend-loading');
            const content = document.getElementById('dividend-content');
            const empty = document.getElementById('dividend-empty');

            if (data.error) {{
                loading.style.display = 'none';
                empty.style.display = 'block';
                return;
            }}

            // Check if there's dividend data
            if (!data.history || data.history.length === 0) {{
                loading.style.display = 'none';
                empty.style.display = 'block';
                return;
            }}

            // Populate dividend metrics
            document.getElementById('div-annual').textContent = data.annual_dividend > 0 ? '€' + data.annual_dividend.toFixed(2) : '-';
            document.getElementById('div-yield-detail').textContent = data.dividend_yield > 0 ? data.dividend_yield.toFixed(2) + '%' : '-';
            document.getElementById('div-freq').textContent = data.frequency ? data.frequency.charAt(0).toUpperCase() + data.frequency.slice(1) : '-';
            document.getElementById('div-growth').textContent = data.dividend_growth_5y !== null ? (data.dividend_growth_5y >= 0 ? '+' : '') + data.dividend_growth_5y.toFixed(1) + '%' : '-';
            document.getElementById('div-next').textContent = data.next_ex_date || '-';

            // Add growth color
            const growthEl = document.getElementById('div-growth');
            if (data.dividend_growth_5y !== null) {{
                growthEl.classList.add(data.dividend_growth_5y >= 0 ? 'pos' : 'neg');
            }}

            // Show recent payments
            const historyList = document.getElementById('div-history-list');
            const recent = data.history.slice(0, 5);
            historyList.innerHTML = recent.map(d => `
                <div style="display:flex;justify-content:space-between;padding:3px 0;font-size:10px;border-bottom:1px solid #1a1a1a;">
                    <span style="color:#888;">${{d.date}}</span>
                    <span style="color:#00ff00;">€${{d.amount.toFixed(4)}}</span>
                </div>
            `).join('');

            loading.style.display = 'none';
            content.style.display = 'block';
        }})
        .catch(err => {{
            console.error('Error loading dividend data:', err);
            document.getElementById('dividend-loading').style.display = 'none';
            document.getElementById('dividend-empty').style.display = 'block';
        }});
}}

// Load dividend data on page load
setTimeout(loadTickerDividends, 500);

// ========================================
// AI Equity Research Analysis
// ========================================

let currentAnalysisTicker = null;

function launchAnalysis(ticker) {{
    currentAnalysisTicker = ticker;

    // Open modal
    const modal = document.getElementById('analysis-modal');
    modal.style.display = 'flex';

    // Show loading
    document.getElementById('analysis-loading').style.display = 'flex';
    document.getElementById('analysis-content').style.display = 'none';
    document.getElementById('analysis-error').style.display = 'none';

    // Update header
    document.getElementById('analysis-ticker').textContent = ticker;
    document.getElementById('analysis-timestamp').textContent =
        new Date().toLocaleDateString('fr-FR', {{
            day: '2-digit', month: 'short', year: 'numeric',
            hour: '2-digit', minute: '2-digit'
        }});

    // Update button state
    const btn = document.getElementById('btn-ai-analyze');
    btn.classList.add('loading');
    btn.querySelector('.analyze-text').textContent = 'Analyse...';

    // Animate loading steps
    animateLoadingSteps();

    // API call
    fetch('/?action=analyze_stock&ticker=' + ticker, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{}}),
    }})
    .then(response => response.json())
    .then(data => {{
        if (data.success) {{
            document.getElementById('analysis-loading').style.display = 'none';
            const contentEl = document.getElementById('analysis-content');
            contentEl.innerHTML = data.html;
            contentEl.style.display = 'block';
            if (data.from_cache) {{
                document.getElementById('analysis-cache-badge').style.display = 'inline';
            }}
        }} else {{
            showAnalysisError(data.error || 'Erreur inconnue');
        }}
    }})
    .catch(error => {{
        showAnalysisError('Erreur de connexion : ' + error.message);
    }})
    .finally(() => {{
        const btn = document.getElementById('btn-ai-analyze');
        btn.classList.remove('loading');
        btn.querySelector('.analyze-text').textContent = 'Analyser';
        if (window._loadingInterval) clearInterval(window._loadingInterval);
    }});
}}

function animateLoadingSteps() {{
    const steps = ['step-data', 'step-analysis', 'step-report'];
    let current = 0;

    // Reset steps
    steps.forEach(s => {{
        const el = document.getElementById(s);
        if (el) {{
            el.classList.remove('active', 'done');
        }}
    }});
    document.getElementById(steps[0]).classList.add('active');

    const interval = setInterval(() => {{
        if (current > 0) {{
            const prev = document.getElementById(steps[current - 1]);
            if (prev) {{
                prev.classList.remove('active');
                prev.classList.add('done');
            }}
        }}
        current++;
        if (current < steps.length) {{
            document.getElementById(steps[current]).classList.add('active');
        }} else {{
            clearInterval(interval);
        }}
    }}, 3000);

    window._loadingInterval = interval;
}}

function showAnalysisError(message) {{
    document.getElementById('analysis-loading').style.display = 'none';
    document.getElementById('analysis-content').style.display = 'none';
    document.getElementById('analysis-error').style.display = 'flex';
    document.getElementById('error-message').textContent = message;
    if (window._loadingInterval) clearInterval(window._loadingInterval);
}}

function closeAnalysis() {{
    document.getElementById('analysis-modal').style.display = 'none';
    if (window._loadingInterval) clearInterval(window._loadingInterval);
}}

function retryAnalysis() {{
    if (currentAnalysisTicker) {{
        launchAnalysis(currentAnalysisTicker);
    }}
}}

function refreshAnalysis() {{
    if (!currentAnalysisTicker) return;

    // Force refresh (bypass cache)
    document.getElementById('analysis-loading').style.display = 'flex';
    document.getElementById('analysis-content').style.display = 'none';
    document.getElementById('analysis-error').style.display = 'none';
    document.getElementById('analysis-cache-badge').style.display = 'none';

    animateLoadingSteps();

    fetch('/?action=analyze_stock&ticker=' + currentAnalysisTicker, {{
        method: 'POST',
        headers: {{ 'Content-Type': 'application/json' }},
        body: JSON.stringify({{ force_refresh: true }}),
    }})
    .then(response => response.json())
    .then(data => {{
        if (data.success) {{
            document.getElementById('analysis-loading').style.display = 'none';
            const contentEl = document.getElementById('analysis-content');
            contentEl.innerHTML = data.html;
            contentEl.style.display = 'block';
        }} else {{
            showAnalysisError(data.error || 'Erreur inconnue');
        }}
    }})
    .catch(error => {{
        showAnalysisError('Erreur de connexion : ' + error.message);
    }})
    .finally(() => {{
        if (window._loadingInterval) clearInterval(window._loadingInterval);
    }});
}}

function printAnalysis() {{
    const content = document.getElementById('analysis-content').innerHTML;
    const printWindow = window.open('', '_blank');
    printWindow.document.write(`
        <html>
        <head>
            <title>Olyos Capital — Equity Research</title>
            <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&display=swap" rel="stylesheet">
            <style>
                :root {{
                    --bg-primary: #0a0e14; --bg-secondary: #111822; --bg-tertiary: #1a2332;
                    --border: #1e2d3d; --text-primary: #e6edf3; --text-secondary: #8b949e;
                    --text-muted: #484f58; --green: #00ff88; --red: #ff4444; --orange: #ff9500;
                    --yellow: #ffd700; --blue: #58a6ff; --cyan: #00d4ff;
                }}
                * {{ margin: 0; padding: 0; box-sizing: border-box; }}
                body {{ font-family: 'JetBrains Mono', monospace; background: var(--bg-primary); color: var(--text-primary); font-size: 12px; line-height: 1.6; padding: 16px; max-width: 1400px; margin: 0 auto; }}
                ${{document.getElementById('analysis-styles').textContent}}
            </style>
        </head>
        <body>${{content}}</body>
        </html>
    `);
    printWindow.document.close();
    printWindow.print();
}}

function downloadAnalysis() {{
    const content = document.getElementById('analysis-content').innerHTML;
    const ticker = currentAnalysisTicker;
    const date = new Date().toISOString().split('T')[0];

    const fullHtml = `<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Olyos Capital — ${{ticker}} — Equity Research</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {{
    --bg-primary: #0a0e14; --bg-secondary: #111822; --bg-tertiary: #1a2332;
    --border: #1e2d3d; --text-primary: #e6edf3; --text-secondary: #8b949e;
    --text-muted: #484f58; --green: #00ff88; --red: #ff4444; --orange: #ff9500;
    --yellow: #ffd700; --blue: #58a6ff; --cyan: #00d4ff;
}}
* {{ margin: 0; padding: 0; box-sizing: border-box; }}
body {{ font-family: 'JetBrains Mono', monospace; background: var(--bg-primary); color: var(--text-primary); font-size: 12px; line-height: 1.6; padding: 16px; max-width: 1400px; margin: 0 auto; }}
${{document.getElementById('analysis-styles').textContent}}
</style>
</head>
<body>${{content}}</body>
</html>`;

    const blob = new Blob([fullHtml], {{ type: 'text/html' }});
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${{ticker}}_equity_research_${{date}}.html`;
    a.click();
    URL.revokeObjectURL(url);
}}

// Close modal with Escape
document.addEventListener('keydown', (e) => {{
    if (e.key === 'Escape') closeAnalysis();
}});

</script>

<!-- Analysis Modal -->
<div id="analysis-modal" class="analysis-modal" style="display:none;">
    <div class="analysis-modal-header">
        <div class="analysis-modal-logo">◆ OLYOS CAPITAL</div>
        <div class="analysis-modal-meta">
            EQUITY RESEARCH │ <span id="analysis-ticker"></span> │
            <span id="analysis-timestamp"></span>
            <span id="analysis-cache-badge" class="analysis-cache-badge" style="display:none;">CACHE</span>
        </div>
        <div class="analysis-modal-actions">
            <button onclick="refreshAnalysis()" class="modal-btn" title="Rafraîchir (ignorer le cache)">↻</button>
            <button onclick="printAnalysis()" class="modal-btn" title="Imprimer">⎙</button>
            <button onclick="downloadAnalysis()" class="modal-btn" title="Télécharger HTML">↓</button>
            <button onclick="closeAnalysis()" class="modal-btn modal-btn-close" title="Fermer">✕</button>
        </div>
    </div>

    <div id="analysis-loading" class="analysis-loading" style="display:none;">
        <div class="loading-spinner"></div>
        <div class="loading-text">Analyse en cours...</div>
        <div class="loading-subtext">Claude génère le rapport d'equity research</div>
        <div class="loading-steps">
            <div class="loading-step active" id="step-data">▸ Collecte des données financières</div>
            <div class="loading-step" id="step-analysis">▸ Analyse méthode Higgons</div>
            <div class="loading-step" id="step-report">▸ Génération du rapport</div>
        </div>
    </div>

    <div id="analysis-content" class="analysis-content" style="display:none;"></div>

    <div id="analysis-error" class="analysis-error" style="display:none;">
        <div class="error-icon">⚠</div>
        <div class="error-text" id="error-message"></div>
        <button onclick="retryAnalysis()" class="btn-analyze" style="margin-top:12px;">◆ Réessayer</button>
    </div>
</div>

</body></html>'''



class Handler(SimpleHTTPRequestHandler):

    def do_POST(self):

        """Handle POST requests for memo creation"""

        content_length = int(self.headers['Content-Length'])

        post_data = self.rfile.read(content_length).decode('utf-8')

        

        # Parse form data

        params = urllib.parse.parse_qs(post_data)

        

        p = urllib.parse.urlparse(self.path)

        q = urllib.parse.parse_qs(p.query)

        

        if q.get('action') == ['create_memo']:

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

            

            self.send_response(200)

            self.send_header('Content-type', 'application/json')

            self.end_headers()

            

            if filepath:

                response = json.dumps({'success': True, 'filepath': filepath})

            else:

                response = json.dumps({'success': False, 'error': error})

            

            self.wfile.write(response.encode())

            return

        

        if q.get('action') == ['generate_ai_memo']:

            ticker = q.get('ticker', [''])[0]

            

            # Get security data

            security_data = get_security_data(ticker)

            

            # Generate memo with AI

            filepath, error = generate_memo_with_ai(security_data)

            

            self.send_response(200)

            self.send_header('Content-type', 'application/json')

            self.end_headers()

            

            if filepath:

                response = json.dumps({'success': True, 'filepath': filepath})

            else:

                response = json.dumps({'success': False, 'error': error or 'Unknown error'})

            

            self.wfile.write(response.encode())

            return



        if q.get('action') == ['analyze_stock']:

            ticker = q.get('ticker', [''])[0]

            if not ticker:
                # Try to get ticker from JSON body
                try:
                    body = json.loads(post_data)
                    ticker = body.get('ticker', '')
                    force_refresh = body.get('force_refresh', False)
                except Exception:
                    force_refresh = False

            else:
                try:
                    body = json.loads(post_data) if post_data else {}
                    force_refresh = body.get('force_refresh', False)
                except Exception:
                    force_refresh = False

            self.send_response(200)

            self.send_header('Content-type', 'application/json')

            self.end_headers()



            if not ticker:
                response = json.dumps({'success': False, 'error': 'Ticker manquant'})
            elif not ANTHROPIC_OK:
                response = json.dumps({'success': False, 'error': 'API Anthropic non configurée. Définir ANTHROPIC_API_KEY.'})
            else:
                result = run_ai_analysis(
                    ticker=ticker,
                    get_security_data_func=get_security_data,
                    yfinance_ok=YFINANCE_OK,
                    api_key=ANTHROPIC_API_KEY,
                    force_refresh=force_refresh
                )
                response = json.dumps(result, ensure_ascii=False)



            self.wfile.write(response.encode('utf-8'))

            return



        if q.get('action') == ['portfolio_advisor']:

            self.send_response(200)

            self.send_header('Content-type', 'application/json')

            self.end_headers()

            if not PORTFOLIO_ADVISOR_OK:
                response = json.dumps({
                    'success': False,
                    'error': 'Portfolio advisor indisponible (module ou dependances manquantes).'
                })
                self.wfile.write(response.encode('utf-8'))
                return

            temp_json_path = None

            try:
                body = json.loads(post_data) if post_data else {}
            except Exception:
                body = {}

            try:
                df, err = load_portfolio()
                if err or df is None:
                    raise Exception(err or "Could not load portfolio")

                use_llm = bool(body.get('use_llm', True)) and ANTHROPIC_OK
                refresh_prices = bool(body.get('refresh_prices', False))
                cash = safe_float(body.get('cash', 0.0)) or 0.0
                currency = str(body.get('currency', 'EUR') or 'EUR').upper()

                payload = build_advisor_portfolio_payload(df, cash=cash, currency=currency)
                if not payload.get('portfolio'):
                    raise Exception("No active positions found in portfolio")

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

                response = json.dumps({
                    'success': True,
                    'report_markdown': result.get('report_markdown', ''),
                    'report_path': result.get('report_path'),
                    'scratchpad_path': result.get('scratchpad_path'),
                    'llm_used': bool(result.get('llm_used', False)),
                    'refresh_prices': refresh_prices,
                }, ensure_ascii=False)
            except Exception as e:
                log.error(f"Portfolio advisor error: {e}")
                response = json.dumps({'success': False, 'error': str(e)}, ensure_ascii=False)
            finally:
                if temp_json_path and os.path.exists(temp_json_path):
                    try:
                        os.remove(temp_json_path)
                    except Exception:
                        pass

            self.wfile.write(response.encode('utf-8'))

            return


        if q.get('action') == ['run_backtest']:

            try:

                # Parse JSON body

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

                

                log_backtest.info("Starting with params:")

                log_backtest.info(f"Scope: {backtest_params['universe_scope']}")

                log_backtest.info(f"Period: {backtest_params['start_date']} to {backtest_params['end_date']}")

                log_backtest.info(f"BUY: PE <= {backtest_params['pe_max']}, ROE >= {backtest_params['roe_min']}%")

                log_backtest.info(f"SELL: PE > {backtest_params['pe_sell']} or ROE < {backtest_params['roe_min_hold']}%")

                

                results = run_backtest(backtest_params)

                

                # Auto-save backtest to history

                if results.get('metrics'):

                    bt_id = save_backtest_result(results)

                    results['saved_id'] = bt_id

                    log_backtest.info(f"Saved to history with ID: {bt_id}")

                

                self.send_response(200)

                self.send_header('Content-type', 'application/json')

                self.end_headers()

                self.wfile.write(json.dumps(results).encode())

                return

                

            except Exception as e:

                # Log error server-side only (don't expose details to client)
                log_backtest.error(f"Backtest error: {e}")

                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Backtest error occurred'}).encode())

                return

        

        if q.get('action') == ['download_data']:

            scope = q.get('scope', ['france'])[0]

            log_cache.info(f"Downloading all data for {scope}...")

            

            try:

                result = download_all_data(scope, start_date='2010-01-01')

                self.send_response(200)

                self.send_header('Content-type', 'application/json')

                self.end_headers()

                self.wfile.write(json.dumps(result).encode())

            except Exception as e:
                log_cache.error(f"Download error: {e}")
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Download error occurred'}).encode())

            return

        if q.get('action') == ['ai_optimize']:

            scope = q.get('scope', ['france'])[0]

            goal = q.get('goal', ['balanced'])[0]

            log_backtest.info(f"AI OPTIMIZER: Starting optimization for {scope} with goal: {goal}")

            

            try:

                result = run_ai_optimization(scope, goal)

                self.send_response(200)

                self.send_header('Content-type', 'application/json')

                self.end_headers()

                self.wfile.write(json.dumps(result).encode())

            except Exception as e:
                log_backtest.error(f"AI OPTIMIZE error: {e}")
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Optimization error occurred'}).encode())

            return

        if q.get('action') == ['clear_cache']:

            try:

                import shutil

                if os.path.exists(CACHE_DIR):

                    shutil.rmtree(CACHE_DIR)

                ensure_cache_dir()

                self.send_response(200)

                self.send_header('Content-type', 'application/json')

                self.end_headers()

                self.wfile.write(json.dumps({'message': 'Cache cleared successfully'}).encode())

            except Exception as e:
                log_cache.error(f"Clear cache error: {e}")
                self.send_response(200)
                self.send_header('Content-type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': 'Cache clear error occurred'}).encode())

            return

        if q.get('action') == ['rename_backtest']:

            bt_id = q.get('id', [''])[0]

            new_name = urllib.parse.unquote(q.get('name', [''])[0])

            rename_backtest(bt_id, new_name)

            self.send_response(200)

            self.send_header('Content-type', 'application/json')

            self.end_headers()

            self.wfile.write(json.dumps({'success': True}).encode())

            return

        

        if q.get('action') == ['delete_backtest']:

            bt_id = q.get('id', [''])[0]

            delete_backtest(bt_id)

            self.send_response(200)

            self.send_header('Content-type', 'application/json')

            self.end_headers()

            self.wfile.write(json.dumps({'success': True}).encode())

            return

        

        self.send_response(400)

        self.end_headers()

    

    def do_GET(self):

        p = urllib.parse.urlparse(self.path)

        q = urllib.parse.parse_qs(p.query)
        log.info(f"[DO_GET] path={p.path}, action={q.get('action')}")



        # Cache stats endpoint

        if q.get('action') == ['cache_stats']:

            self.send_response(200)

            self.send_header('Content-type', 'application/json')

            self.end_headers()

            stats = get_cache_stats()

            self.wfile.write(json.dumps(stats).encode())

            return

        

        # Backtest history endpoint

        if q.get('action') == ['get_backtest_history']:

            self.send_response(200)

            self.send_header('Content-type', 'application/json')

            self.end_headers()

            history = load_backtest_history()

            log_backtest.info(f"Loading backtest history: {len(history)} items from {CONFIG['backtest_history_file']}")

            self.wfile.write(json.dumps(history).encode())

            return

        

        if q.get('action') == ['addwatch']:

            add_to_watchlist(q.get('ticker',[''])[0], urllib.parse.unquote(q.get('name',[''])[0]), q.get('country',[''])[0], urllib.parse.unquote(q.get('sector',[''])[0]))

            self.send_response(200); self.end_headers(); return

        

        if q.get('action') == ['rmwatch']:

            remove_from_watchlist(q.get('ticker',[''])[0])

            self.send_response(200); self.end_headers(); return


        # Portfolio management actions
        if q.get('action') == ['addportfolio']:
            ticker = q.get('ticker',[''])[0]
            name = urllib.parse.unquote(q.get('name',[''])[0])
            qty = q.get('qty',['0'])[0]
            avg_cost = q.get('avg_cost',['0'])[0]
            success, err = add_portfolio_position(ticker, name, qty, avg_cost)
            if success:
                self.send_response(200)
            else:
                self.send_response(400)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write((err or 'OK').encode('utf-8'))
            return

        if q.get('action') == ['editportfolio']:
            ticker = q.get('ticker',[''])[0]
            qty = q.get('qty',['0'])[0]
            avg_cost = q.get('avg_cost',['0'])[0]
            success, err = edit_portfolio_position(ticker, qty, avg_cost)
            if success:
                self.send_response(200)
            else:
                self.send_response(400)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write((err or 'OK').encode('utf-8'))
            return

        if q.get('action') == ['rmportfolio']:
            ticker = q.get('ticker',[''])[0]
            success, err = remove_portfolio_position(ticker)
            if success:
                self.send_response(200)
            else:
                self.send_response(400)
            self.send_header('Content-Type', 'text/plain')
            self.end_headers()
            self.wfile.write((err or 'OK').encode('utf-8'))
            return

        # ============== ALERTS API ==============

        # GET /api/alerts - Get active alerts
        if q.get('action') == ['get_alerts']:
            try:
                service = get_alerts_service()
                alerts = service.check_alerts()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'alerts': [a.to_dict() for a in alerts],
                    'count': len(alerts)
                }).encode('utf-8'))
            except Exception as e:
                log.error(f"Error getting alerts: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))
            return

        # GET /api/alerts/check - Force check alerts
        if q.get('action') == ['check_alerts']:
            try:
                service = get_alerts_service()
                alerts = service.check_alerts()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'alerts': [a.to_dict() for a in alerts],
                    'count': len(alerts),
                    'checked_at': datetime.now().isoformat()
                }).encode('utf-8'))
            except Exception as e:
                log.error(f"Error checking alerts: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))
            return

        # GET /api/watchlist/status - Get watchlist with alert status
        if q.get('action') == ['watchlist_status']:
            try:
                service = get_alerts_service()
                items = service.get_watchlist_with_status()
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'watchlist': items,
                    'count': len(items)
                }).encode('utf-8'))
            except Exception as e:
                log.error(f"Error getting watchlist status: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))
            return

        # GET /api/alerts/dismiss - Dismiss an alert
        if q.get('action') == ['dismiss_alert']:
            try:
                ticker = q.get('ticker', [''])[0]
                alert_type = q.get('alert_type', [''])[0]
                service = get_alerts_service()
                success = service.dismiss_alert(ticker, alert_type)
                self.send_response(200 if success else 404)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': success}).encode('utf-8'))
            except Exception as e:
                log.error(f"Error dismissing alert: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))
            return

        # GET /api/alerts/config - Set alert config for a ticker
        if q.get('action') == ['set_alert_config']:
            try:
                ticker = q.get('ticker', [''])[0]
                pe_threshold = q.get('pe_threshold', [None])[0]
                roe_threshold = q.get('roe_threshold', [None])[0]
                price_below = q.get('price_below', [None])[0]
                price_above = q.get('price_above', [None])[0]

                config = AlertConfig(
                    pe_threshold=float(pe_threshold) if pe_threshold else None,
                    roe_threshold=float(roe_threshold) if roe_threshold else None,
                    price_below=float(price_below) if price_below else None,
                    price_above=float(price_above) if price_above else None
                )

                service = get_alerts_service()
                success = service.update_alert_config(ticker, config)

                self.send_response(200 if success else 404)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': success,
                    'ticker': ticker,
                    'config': config.to_dict()
                }).encode('utf-8'))
            except Exception as e:
                log.error(f"Error setting alert config: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))
            return

        # ============== BENCHMARK API ==============
        log.info(f"[DEBUG] Checking benchmark routes, action={q.get('action')}")

        # GET /api/benchmarks - Get list of available benchmarks
        if q.get('action') == ['get_benchmarks']:
            log.info("[DEBUG] Matched get_benchmarks!")
            try:
                benchmarks = [{'key': k, **v} for k, v in BENCHMARKS.items()]
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'benchmarks': benchmarks}).encode('utf-8'))
            except Exception as e:
                log.error(f"Error getting benchmarks: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))
            return

        # GET /api/benchmark/compare - Get comparison data (portfolio vs benchmark)
        if q.get('action') == ['benchmark_compare']:
            try:
                benchmark_key = q.get('benchmark', ['CACMS'])[0]
                period = q.get('period', ['1Y'])[0]

                service = get_benchmark_service()
                data = service.get_comparison_data(benchmark_key, period)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(data).encode('utf-8'))
            except Exception as e:
                log.error(f"Error getting benchmark comparison: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))
            return

        # GET /api/benchmark/metrics - Get performance metrics only
        if q.get('action') == ['benchmark_metrics']:
            try:
                benchmark_key = q.get('benchmark', ['CACMS'])[0]
                period = q.get('period', ['1Y'])[0]

                service = get_benchmark_service()
                metrics = service.calculate_metrics(benchmark_key, period)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(metrics.to_dict()).encode('utf-8'))
            except Exception as e:
                log.error(f"Error getting benchmark metrics: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))
            return

        # GET /api/benchmark/history - Get benchmark price history
        if q.get('action') == ['benchmark_history']:
            try:
                benchmark_key = q.get('benchmark', ['CACMS'])[0]
                period = q.get('period', ['1Y'])[0]

                # Calculate date range
                end_date = datetime.now()
                if period == 'YTD':
                    start_date = datetime(end_date.year, 1, 1)
                elif period == '1Y':
                    start_date = end_date - timedelta(days=365)
                elif period == '3Y':
                    start_date = end_date - timedelta(days=365 * 3)
                elif period == '5Y':
                    start_date = end_date - timedelta(days=365 * 5)
                else:
                    start_date = datetime(2010, 1, 1)

                service = get_benchmark_service()
                prices, err = service.get_benchmark_history(
                    benchmark_key,
                    start_date.strftime('%Y-%m-%d'),
                    end_date.strftime('%Y-%m-%d')
                )

                if err:
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': err}).encode('utf-8'))
                else:
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'benchmark': benchmark_key,
                        'prices': prices,
                        'period': period
                    }).encode('utf-8'))
            except Exception as e:
                log.error(f"Error getting benchmark history: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))
            return

        # ==================== DIVIDENDS API ====================

        # GET /api/dividends/calendar - Get dividend calendar for portfolio
        if q.get('action') == ['dividends_calendar']:
            try:
                months = int(q.get('months', ['3'])[0])
                df, err = load_portfolio()
                if err or df is None:
                    raise Exception(err or "Could not load portfolio")
                positions = []
                for _, row in df.iterrows():
                    positions.append({
                        'ticker': row.get('ticker', ''),
                        'name': row.get('name', row.get('ticker', '')),
                        'quantity': row.get('qty', row.get('quantity', 0)),
                        'price': row.get('price_eur', row.get('price', 0)),
                        'cost': row.get('avg_cost_eur', row.get('cost', 0))
                    })

                service = get_dividends_service()
                calendar = service.get_dividend_calendar(positions, months)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(calendar).encode('utf-8'))
            except Exception as e:
                log.error(f"Error getting dividend calendar: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))
            return

        # GET /api/dividends/income - Get projected annual income
        if q.get('action') == ['dividends_income']:
            try:
                df, err = load_portfolio()
                if err or df is None:
                    raise Exception(err or "Could not load portfolio")
                positions = []
                for _, row in df.iterrows():
                    positions.append({
                        'ticker': row.get('ticker', ''),
                        'name': row.get('name', row.get('ticker', '')),
                        'quantity': row.get('qty', row.get('quantity', 0)),
                        'price': row.get('price_eur', row.get('price', 0)),
                        'cost': row.get('avg_cost_eur', row.get('cost', 0))
                    })

                service = get_dividends_service()
                income = service.project_annual_income(positions)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(income).encode('utf-8'))
            except Exception as e:
                log.error(f"Error getting dividend income: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))
            return

        # GET /api/dividends/ticker - Get dividend history for a ticker
        if q.get('action') == ['dividends_ticker']:
            try:
                ticker = q.get('ticker', [''])[0]
                if not ticker:
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'error': 'Ticker required'}).encode('utf-8'))
                    return

                years = int(q.get('years', ['5'])[0])
                service = get_dividends_service()
                info = service.get_dividend_history(ticker, years)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps(info.to_dict()).encode('utf-8'))
            except Exception as e:
                log.error(f"Error getting dividend history for ticker: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))
            return

        # GET /api/dividends/upcoming - Get upcoming dividends for portfolio
        if q.get('action') == ['dividends_upcoming']:
            try:
                df, err = load_portfolio()
                if err or df is None:
                    raise Exception(err or "Could not load portfolio")
                positions = []
                for _, row in df.iterrows():
                    positions.append({
                        'ticker': row.get('ticker', ''),
                        'name': row.get('name', row.get('ticker', '')),
                        'quantity': row.get('qty', row.get('quantity', 0))
                    })

                service = get_dividends_service()
                upcoming = service.get_upcoming_dividends(positions)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'upcoming': upcoming}).encode('utf-8'))
            except Exception as e:
                log.error(f"Error getting upcoming dividends: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'error': str(e)}).encode('utf-8'))
            return

        # ==================== TRANSACTIONS & POSITIONS API ====================

        # GET /api/transactions - List all transactions with optional filters
        if q.get('action') == ['get_transactions']:
            try:
                ticker = q.get('ticker', [None])[0]
                txn_type = q.get('type', [None])[0]
                start_date = q.get('start_date', [None])[0]
                end_date = q.get('end_date', [None])[0]

                manager = get_position_manager()
                transactions = manager.get_transactions(ticker, txn_type, start_date, end_date)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'data': [t.to_dict() for t in transactions]
                }).encode('utf-8'))
            except Exception as e:
                log.error(f"Error getting transactions: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode('utf-8'))
            return

        # GET /api/positions - Get all open positions
        if q.get('action') == ['get_positions']:
            try:
                # Get price and name data from portfolio
                df, err = load_portfolio()
                price_data = {}
                name_data = {}
                if df is not None:
                    for _, row in df.iterrows():
                        ticker = row.get('ticker', '').upper()
                        if ticker:
                            price_data[ticker] = float(row.get('price_eur', 0))
                            name_data[ticker] = row.get('name', ticker)

                manager = get_position_manager()
                summary = manager.get_all_positions(price_data, name_data)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'data': [p.to_dict() for p in summary.open_positions]
                }).encode('utf-8'))
            except Exception as e:
                log.error(f"Error getting positions: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode('utf-8'))
            return

        # GET /api/positions/closed - Get all closed positions
        if q.get('action') == ['get_closed_positions']:
            try:
                df, err = load_portfolio()
                price_data = {}
                name_data = {}
                if df is not None:
                    for _, row in df.iterrows():
                        ticker = row.get('ticker', '').upper()
                        if ticker:
                            price_data[ticker] = float(row.get('price_eur', 0))
                            name_data[ticker] = row.get('name', ticker)

                manager = get_position_manager()
                summary = manager.get_all_positions(price_data, name_data)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'data': [p.to_dict() for p in summary.closed_positions]
                }).encode('utf-8'))
            except Exception as e:
                log.error(f"Error getting closed positions: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode('utf-8'))
            return

        # GET /api/positions/<ticker> - Get position detail with transactions
        if q.get('action') == ['get_position_detail']:
            try:
                ticker = q.get('ticker', [''])[0]
                if not ticker:
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': False, 'error': 'Ticker required'}).encode('utf-8'))
                    return

                # Get price from portfolio
                df, err = load_portfolio()
                price = 0
                name = ticker
                if df is not None:
                    ticker_upper = ticker.upper()
                    match = df[df['ticker'].str.upper() == ticker_upper]
                    if not match.empty:
                        price = float(match.iloc[0].get('price_eur', 0))
                        name = match.iloc[0].get('name', ticker)

                manager = get_position_manager()
                position = manager.get_position(ticker, price, name)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                result = position.to_dict()
                result['transactions'] = [t.to_dict() for t in position.transactions]
                self.wfile.write(json.dumps({'success': True, 'data': result}).encode('utf-8'))
            except Exception as e:
                log.error(f"Error getting position detail: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode('utf-8'))
            return

        # GET /api/pnl/summary - Get P&L summary
        if q.get('action') == ['get_pnl_summary']:
            try:
                df, err = load_portfolio()
                price_data = {}
                name_data = {}
                if df is not None:
                    for _, row in df.iterrows():
                        ticker = row.get('ticker', '').upper()
                        if ticker:
                            price_data[ticker] = float(row.get('price_eur', 0))
                            name_data[ticker] = row.get('name', ticker)

                manager = get_position_manager()
                summary = manager.get_all_positions(price_data, name_data)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'data': summary.to_dict()
                }).encode('utf-8'))
            except Exception as e:
                log.error(f"Error getting P&L summary: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode('utf-8'))
            return

        # GET /api/pnl/history - Get P&L history for chart
        if q.get('action') == ['get_pnl_history']:
            try:
                start_date = q.get('start_date', [None])[0]
                end_date = q.get('end_date', [None])[0]

                manager = get_position_manager()
                history = manager.get_pnl_history(start_date, end_date)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'data': history
                }).encode('utf-8'))
            except Exception as e:
                log.error(f"Error getting P&L history: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode('utf-8'))
            return

        # GET /api/transactions/add - Add transaction via GET (for simple forms)
        if q.get('action') == ['add_transaction']:
            try:
                ticker = q.get('ticker', [''])[0]
                txn_type = q.get('type', ['BUY'])[0]
                date_str = q.get('date', [datetime.now().strftime('%Y-%m-%d')])[0]
                quantity = float(q.get('quantity', [0])[0])
                price = float(q.get('price', [0])[0])
                fees = float(q.get('fees', [0])[0])
                notes = urllib.parse.unquote(q.get('notes', [''])[0])

                if not ticker:
                    raise ValueError("Ticker required")

                manager = get_position_manager()
                txn, err = manager.add_transaction(
                    ticker=ticker,
                    txn_type=txn_type,
                    date_str=date_str,
                    quantity=quantity,
                    price=price,
                    fees=fees,
                    notes=notes
                )

                if err:
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': False, 'error': err}).encode('utf-8'))
                else:
                    # Also update portfolio.xlsx to keep in sync
                    try:
                        df, load_err = load_portfolio()
                        if df is not None and not load_err:
                            mask = df['ticker'].str.upper() == ticker.upper()
                            if mask.any():
                                idx = df[mask].index[0]
                                current_qty = float(df.loc[idx, 'qty'] or 0)
                                current_cost = float(df.loc[idx, 'avg_cost_eur'] or 0)

                                if txn_type == 'SELL':
                                    # Reduce quantity
                                    new_qty = max(0, current_qty - quantity)
                                    df.loc[idx, 'qty'] = new_qty
                                    log.info(f"Portfolio updated: {ticker} qty {current_qty} -> {new_qty}")
                                elif txn_type == 'BUY':
                                    # Increase quantity and recalculate avg cost
                                    new_qty = current_qty + quantity
                                    # Weighted average cost
                                    total_old = current_qty * current_cost
                                    total_new = quantity * price
                                    new_avg_cost = (total_old + total_new) / new_qty if new_qty > 0 else price
                                    df.loc[idx, 'qty'] = new_qty
                                    df.loc[idx, 'avg_cost_eur'] = new_avg_cost
                                    log.info(f"Portfolio updated: {ticker} qty {current_qty} -> {new_qty}, cost {current_cost:.2f} -> {new_avg_cost:.2f}")

                                save_portfolio(df)
                    except Exception as sync_err:
                        log.warning(f"Could not sync portfolio.xlsx: {sync_err}")

                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({
                        'success': True,
                        'data': txn.to_dict()
                    }).encode('utf-8'))
            except Exception as e:
                log.error(f"Error adding transaction: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode('utf-8'))
            return

        # GET /api/transactions/delete - Delete transaction
        if q.get('action') == ['delete_transaction']:
            try:
                txn_id = q.get('id', [''])[0]
                if not txn_id:
                    raise ValueError("Transaction ID required")

                manager = get_position_manager()
                success, err = manager.delete_transaction(txn_id)

                if err:
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': False, 'error': err}).encode('utf-8'))
                else:
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': True}).encode('utf-8'))
            except Exception as e:
                log.error(f"Error deleting transaction: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode('utf-8'))
            return

        # GET /api/transactions/qty - Get current quantity for a ticker (for sell validation)
        if q.get('action') == ['get_ticker_qty']:
            try:
                ticker = q.get('ticker', [''])[0]
                if not ticker:
                    raise ValueError("Ticker required")

                manager = get_position_manager()
                qty = manager._get_current_qty(ticker)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'data': {'ticker': ticker.upper(), 'quantity': qty}
                }).encode('utf-8'))
            except Exception as e:
                log.error(f"Error getting ticker quantity: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode('utf-8'))
            return

        # ═══ PDF REPORT GENERATION ═══

        # GET /?action=generate_report - Generate PDF monthly report
        if q.get('action') == ['generate_report']:
            try:
                month = int(q.get('month', [datetime.now().month])[0])
                year = int(q.get('year', [datetime.now().year])[0])

                service = get_pdf_report_service()
                pdf_bytes, filename = service.generate_report(month, year)

                self.send_response(200)
                self.send_header('Content-Type', 'application/pdf')
                self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
                self.send_header('Content-Length', str(len(pdf_bytes)))
                self.end_headers()
                self.wfile.write(pdf_bytes)
            except Exception as e:
                log.error(f"Error generating report: {e}")
                import traceback
                traceback.print_exc()
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode('utf-8'))
            return

        # GET /?action=get_latest_report - Get the most recent report
        if q.get('action') == ['get_latest_report']:
            try:
                service = get_pdf_report_service()
                pdf_bytes, filename = service.get_latest_report()

                if pdf_bytes and filename:
                    self.send_response(200)
                    self.send_header('Content-Type', 'application/pdf')
                    self.send_header('Content-Disposition', f'attachment; filename="{filename}"')
                    self.send_header('Content-Length', str(len(pdf_bytes)))
                    self.end_headers()
                    self.wfile.write(pdf_bytes)
                else:
                    self.send_response(404)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': False, 'error': 'No reports found'}).encode('utf-8'))
            except Exception as e:
                log.error(f"Error getting latest report: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode('utf-8'))
            return

        # GET /?action=list_reports - List all available reports
        if q.get('action') == ['list_reports']:
            try:
                service = get_pdf_report_service()
                reports = service.list_reports()

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': True, 'data': reports}).encode('utf-8'))
            except Exception as e:
                log.error(f"Error listing reports: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode('utf-8'))
            return

        # ===================== INSIDER API ROUTES =====================

        # GET /?action=insider_transactions&ticker=MC - Get insider transactions for a ticker
        if q.get('action') == ['insider_transactions']:
            try:
                ticker = q.get('ticker', [''])[0]
                months = int(q.get('months', ['12'])[0])

                if not ticker:
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': False, 'error': 'Missing ticker parameter'}).encode('utf-8'))
                    return

                service = get_insider_service()
                transactions = service.get_insider_transactions(ticker, months)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'data': {
                        'ticker': ticker,
                        'transactions': [t.to_dict() for t in transactions]
                    }
                }).encode('utf-8'))
            except Exception as e:
                log.error(f"Error fetching insider transactions: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode('utf-8'))
            return

        # GET /?action=insider_sentiment&ticker=MC - Get insider sentiment for a ticker
        if q.get('action') == ['insider_sentiment']:
            try:
                ticker = q.get('ticker', [''])[0]
                months = int(q.get('months', ['12'])[0])

                if not ticker:
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': False, 'error': 'Missing ticker parameter'}).encode('utf-8'))
                    return

                service = get_insider_service()
                sentiment = service.calculate_insider_sentiment(ticker, months)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'data': sentiment.to_dict()
                }).encode('utf-8'))
            except Exception as e:
                log.error(f"Error calculating insider sentiment: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode('utf-8'))
            return

        # GET /?action=insider_feed&scope=portfolio - Get insider feed
        if q.get('action') == ['insider_feed']:
            try:
                scope = q.get('scope', ['portfolio'])[0]
                limit = int(q.get('limit', ['50'])[0])

                # Get tickers based on scope
                tickers = []
                if scope == 'portfolio':
                    df, _ = load_portfolio()
                    if df is not None and 'ticker' in df.columns:
                        tickers = df['ticker'].str.upper().tolist()
                elif scope == 'watchlist':
                    watchlist = load_watchlist()
                    tickers = [w.get('ticker', '').upper() for w in watchlist if w.get('ticker')]
                elif scope == 'all':
                    # Both portfolio and watchlist
                    df, _ = load_portfolio()
                    if df is not None and 'ticker' in df.columns:
                        tickers = df['ticker'].str.upper().tolist()
                    watchlist = load_watchlist()
                    tickers.extend([w.get('ticker', '').upper() for w in watchlist if w.get('ticker')])
                    tickers = list(set(tickers))

                service = get_insider_service()
                transactions = service.get_insider_feed(tickers, limit=limit)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'data': {
                        'scope': scope,
                        'count': len(transactions),
                        'transactions': [t.to_dict() for t in transactions]
                    }
                }).encode('utf-8'))
            except Exception as e:
                log.error(f"Error fetching insider feed: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode('utf-8'))
            return

        # GET /?action=insider_alerts - Get recent insider alerts
        if q.get('action') == ['insider_alerts']:
            try:
                # Get all tickers from portfolio and watchlist
                tickers = []
                ticker_names = {}

                df, _ = load_portfolio()
                if df is not None and 'ticker' in df.columns:
                    for _, row in df.iterrows():
                        t = row.get('ticker', '').upper()
                        if t:
                            tickers.append(t)
                            ticker_names[t] = row.get('name', t)

                watchlist = load_watchlist()
                for w in watchlist:
                    t = w.get('ticker', '').upper()
                    if t:
                        tickers.append(t)
                        if t not in ticker_names:
                            ticker_names[t] = w.get('name', t)

                tickers = list(set(tickers))

                service = get_insider_service()
                alerts = service.detect_alerts(tickers, ticker_names)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'data': {
                        'count': len(alerts),
                        'alerts': [a.to_dict() for a in alerts]
                    }
                }).encode('utf-8'))
            except Exception as e:
                log.error(f"Error detecting insider alerts: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode('utf-8'))
            return

        # GET /?action=insider_score&ticker=MC - Get insider score adjustment
        if q.get('action') == ['insider_score']:
            try:
                ticker = q.get('ticker', [''])[0]

                if not ticker:
                    self.send_response(400)
                    self.send_header('Content-Type', 'application/json')
                    self.end_headers()
                    self.wfile.write(json.dumps({'success': False, 'error': 'Missing ticker parameter'}).encode('utf-8'))
                    return

                service = get_insider_service()
                adjustment = service.get_insider_score_adjustment(ticker)
                sentiment = service.calculate_insider_sentiment(ticker, months=6)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'data': {
                        'ticker': ticker,
                        'score_adjustment': adjustment,
                        'recent_buy_days': sentiment.recent_buy_days,
                        'is_cluster_buying': sentiment.is_cluster_buying,
                        'sentiment_ratio': sentiment.sentiment_ratio
                    }
                }).encode('utf-8'))
            except Exception as e:
                log.error(f"Error calculating insider score: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode('utf-8'))
            return

        # ===================== END INSIDER API ROUTES =====================

        # ===================== REBALANCING API ROUTES =====================

        # GET /?action=rebalance_check - Check portfolio for imbalances
        if q.get('action') == ['rebalance_check']:
            try:
                service = get_rebalancing_service()

                # Load portfolio from Excel
                df, err = load_portfolio()
                if err or df is None:
                    raise Exception(f"Could not load portfolio: {err}")

                # Build positions list with metrics
                positions = []
                total_value = 0

                for _, row in df.iterrows():
                    qty = float(row.get('qty', 0) or 0)
                    if qty <= 0:
                        continue

                    price = float(row.get('price_eur', 0) or 0)
                    value = price * qty
                    total_value += value

                    # Get PE (try multiple columns)
                    pe = None
                    for col in ['pe', 'pe_ttm', 'trailing_pe']:
                        if col in df.columns:
                            val = row.get(col)
                            if val is not None and not (isinstance(val, float) and math.isnan(val)):
                                pe = float(val)
                                break

                    # Get ROE
                    roe = None
                    for col in ['roe', 'roe_ttm']:
                        if col in df.columns:
                            val = row.get(col)
                            if val is not None and not (isinstance(val, float) and math.isnan(val)):
                                roe = float(val)
                                if -1 < roe < 1:
                                    roe = roe * 100
                                break

                    pos_data = {
                        'ticker': str(row.get('ticker', '')),
                        'name': str(row.get('name', '')),
                        'value': value,
                        'price': price,
                        'sector': str(row.get('sector', 'Other') or 'Other'),
                        'pe': pe,
                        'roe': roe,
                        'higgons_score': int(row.get('score_higgons', row.get('higgons_score', 5)) or 5),
                        'verdict': str(row.get('verdict', '') or '')
                    }
                    positions.append(pos_data)

                # Add weights
                for pos in positions:
                    pos['weight'] = (pos['value'] / total_value * 100) if total_value > 0 else 0

                imbalances = service.check_portfolio_balance(positions, total_value)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'data': {
                        'total_value': round(total_value, 0),
                        'num_positions': len(positions),
                        'imbalances': [i.to_dict() for i in imbalances],
                        'is_balanced': len(imbalances) == 0
                    }
                }).encode('utf-8'))
            except Exception as e:
                log.error(f"Error checking rebalance: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode('utf-8'))
            return

        # GET /?action=rebalance_propose - Get trade proposals
        if q.get('action') == ['rebalance_propose']:
            try:
                method = q.get('method', ['equal'])[0]
                service = get_rebalancing_service()

                df, err = load_portfolio()
                if err or df is None:
                    raise Exception(f"Could not load portfolio: {err}")

                positions = []
                total_value = 0

                for _, row in df.iterrows():
                    qty = float(row.get('qty', 0) or 0)
                    if qty <= 0:
                        continue

                    price = float(row.get('price_eur', 0) or 0)
                    value = price * qty
                    total_value += value

                    pos_data = {
                        'ticker': str(row.get('ticker', '')),
                        'name': str(row.get('name', '')),
                        'value': value,
                        'price': price,
                        'sector': str(row.get('sector', 'Other') or 'Other'),
                        'higgons_score': int(row.get('score_higgons', row.get('higgons_score', 5)) or 5)
                    }
                    positions.append(pos_data)

                for pos in positions:
                    pos['weight'] = (pos['value'] / total_value * 100) if total_value > 0 else 0

                target_weights = service.calculate_target_weights(positions, method)
                proposals = service.propose_rebalancing(positions, target_weights, total_value)

                total_buy = sum(t.trade_value for t in proposals if t.trade_value > 0)
                total_sell = sum(abs(t.trade_value) for t in proposals if t.trade_value < 0)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'data': {
                        'method': method,
                        'total_value': round(total_value, 0),
                        'proposals': [p.to_dict() for p in proposals],
                        'total_buy': round(total_buy, 0),
                        'total_sell': round(total_sell, 0),
                        'net_flow': round(total_buy - total_sell, 0)
                    }
                }).encode('utf-8'))
            except Exception as e:
                log.error(f"Error proposing rebalance: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode('utf-8'))
            return

        # GET /?action=rebalance_analyze - Full portfolio analysis
        if q.get('action') == ['rebalance_analyze']:
            try:
                service = get_rebalancing_service()

                df, err = load_portfolio()
                if err or df is None:
                    raise Exception(f"Could not load portfolio: {err}")

                positions = []
                total_value = 0

                for _, row in df.iterrows():
                    qty = float(row.get('qty', 0) or 0)
                    if qty <= 0:
                        continue

                    price = float(row.get('price_eur', 0) or 0)
                    value = price * qty
                    total_value += value

                    pe = None
                    for col in ['pe', 'pe_ttm', 'trailing_pe']:
                        if col in df.columns:
                            val = row.get(col)
                            if val is not None and not (isinstance(val, float) and math.isnan(val)):
                                pe = float(val)
                                break

                    roe = None
                    for col in ['roe', 'roe_ttm']:
                        if col in df.columns:
                            val = row.get(col)
                            if val is not None and not (isinstance(val, float) and math.isnan(val)):
                                roe = float(val)
                                if -1 < roe < 1:
                                    roe = roe * 100
                                break

                    pos_data = {
                        'ticker': str(row.get('ticker', '')),
                        'name': str(row.get('name', '')),
                        'value': value,
                        'price': price,
                        'sector': str(row.get('sector', 'Other') or 'Other'),
                        'pe': pe,
                        'roe': roe,
                        'higgons_score': int(row.get('score_higgons', row.get('higgons_score', 5)) or 5),
                        'verdict': str(row.get('verdict', '') or '')
                    }
                    positions.append(pos_data)

                for pos in positions:
                    pos['weight'] = (pos['value'] / total_value * 100) if total_value > 0 else 0

                result = service.analyze_portfolio(positions, total_value)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'data': result.to_dict()
                }).encode('utf-8'))
            except Exception as e:
                log.error(f"Error analyzing portfolio: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode('utf-8'))
            return

        # GET /?action=rebalance_simulate - Simulate trade impact
        if q.get('action') == ['rebalance_simulate']:
            try:
                method = q.get('method', ['equal'])[0]
                service = get_rebalancing_service()

                df, err = load_portfolio()
                if err or df is None:
                    raise Exception(f"Could not load portfolio: {err}")

                positions = []
                total_value = 0

                for _, row in df.iterrows():
                    qty = float(row.get('qty', 0) or 0)
                    if qty <= 0:
                        continue

                    price = float(row.get('price_eur', 0) or 0)
                    value = price * qty
                    total_value += value

                    pos_data = {
                        'ticker': str(row.get('ticker', '')),
                        'name': str(row.get('name', '')),
                        'value': value,
                        'price': price,
                        'sector': str(row.get('sector', 'Other') or 'Other'),
                        'higgons_score': int(row.get('score_higgons', row.get('higgons_score', 5)) or 5)
                    }
                    positions.append(pos_data)

                for pos in positions:
                    pos['weight'] = (pos['value'] / total_value * 100) if total_value > 0 else 0

                target_weights = service.calculate_target_weights(positions, method)
                proposals = service.propose_rebalancing(positions, target_weights, total_value)
                simulation = service.simulate_trades(positions, proposals)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'data': simulation
                }).encode('utf-8'))
            except Exception as e:
                log.error(f"Error simulating rebalance: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode('utf-8'))
            return

        # ===================== END REBALANCING API ROUTES =====================

        # ===================== HEATMAP API ROUTES =====================

        # GET /?action=heatmap_data - Get portfolio data for treemap visualization
        if q.get('action') == ['heatmap_data']:
            try:
                metric = q.get('metric', ['perf_day'])[0]  # perf_day, perf_ytd, score, pe
                grouping = q.get('grouping', ['sector'])[0]  # sector, country, flat

                df, err = load_portfolio()
                if err or df is None:
                    raise Exception(f"Could not load portfolio: {err}")

                positions = []
                total_value = 0

                for _, row in df.iterrows():
                    qty = float(row.get('qty', 0) or 0)
                    if qty <= 0:
                        continue

                    price = float(row.get('price_eur', 0) or 0)
                    value = price * qty
                    total_value += value

                    # Get cost for P&L calculation
                    cost = float(row.get('avg_cost_eur', 0) or 0)
                    total_cost = cost * qty
                    pnl_pct = ((value / total_cost) - 1) * 100 if total_cost > 0 else 0

                    # Get daily change
                    change_pct = float(row.get('change_pct', row.get('pct_change', 0)) or 0)
                    # Convert from decimal if needed
                    if -1 < change_pct < 1 and change_pct != 0:
                        change_pct = change_pct * 100

                    # Get YTD change (use pnl_pct as proxy if not available)
                    ytd_pct = float(row.get('ytd_pct', row.get('perf_ytd', pnl_pct)) or pnl_pct)
                    if -1 < ytd_pct < 1 and ytd_pct != 0:
                        ytd_pct = ytd_pct * 100

                    # Get PE
                    pe = None
                    for col in ['pe', 'pe_ttm', 'trailing_pe']:
                        if col in df.columns:
                            val = row.get(col)
                            if val is not None and not (isinstance(val, float) and math.isnan(val)):
                                pe = float(val)
                                break

                    # Get ROE
                    roe = None
                    for col in ['roe', 'roe_ttm', 'returnOnEquity']:
                        if col in df.columns:
                            val = row.get(col)
                            if val is not None and not (isinstance(val, float) and math.isnan(val)):
                                roe = float(val)
                                if -1 < roe < 1:
                                    roe = roe * 100
                                break

                    # Get Gearing (debt/equity)
                    gearing = None
                    for col in ['gearing', 'debt_to_equity', 'debtToEquity']:
                        if col in df.columns:
                            val = row.get(col)
                            if val is not None and not (isinstance(val, float) and math.isnan(val)):
                                gearing = float(val)
                                # Convert from decimal to percentage if needed
                                if gearing < 5 and gearing > 0:
                                    gearing = gearing * 100
                                break

                    # Get P/CF (Price to Cash Flow)
                    pcf = None
                    for col in ['pcf', 'price_to_cashflow']:
                        if col in df.columns:
                            val = row.get(col)
                            if val is not None and not (isinstance(val, float) and math.isnan(val)):
                                pcf = float(val)
                                break

                    # Get Momentum (prefer 6M, fallback to 12M)
                    mom_6m = None
                    for col in ['mom_6m', 'momentum_6m', 'perf_6m', 'momentum_12m', 'mom_12m', 'perf_12m']:
                        if col in df.columns:
                            val = row.get(col)
                            if val is not None and not (isinstance(val, float) and math.isnan(val)):
                                mom_6m = float(val)
                                if -1 < mom_6m < 1:
                                    mom_6m = mom_6m * 100
                                break

                    # Calculate Higgons score dynamically (max 13 pts, scaled to 10)
                    score = 0
                    # P/E score (lower is better): < 8: 3pts, < 10: 2pts, < 12: 1pt
                    if pe is not None and pe > 0:
                        if pe < 8:
                            score += 3
                        elif pe < 10:
                            score += 2
                        elif pe < 12:
                            score += 1
                    # P/CF score (lower is better): <= 6: 3pts, <= 8: 2pts, <= 10: 1pt
                    if pcf is not None and pcf > 0:
                        if pcf <= 6:
                            score += 3
                        elif pcf <= 8:
                            score += 2
                        elif pcf <= 10:
                            score += 1
                    # ROE score (higher is better): > 15%: 3pts, > 12%: 2pts, > 10%: 1pt
                    if roe is not None:
                        if roe > 15:
                            score += 3
                        elif roe > 12:
                            score += 2
                        elif roe > 10:
                            score += 1
                    # Gearing score (lower is better): < 20%: 2pts, < 50%: 1pt
                    if gearing is not None:
                        if gearing < 20:
                            score += 2
                        elif gearing < 50:
                            score += 1
                    # Momentum score: > 20%: 2pts, > 0%: 1pt
                    if mom_6m is not None:
                        if mom_6m > 20:
                            score += 2
                        elif mom_6m > 0:
                            score += 1
                    # Scale to 10 (max is now 13)
                    score = min(round(score * 10 / 13), 10)

                    pos = {
                        'ticker': str(row.get('ticker', '')),
                        'name': str(row.get('name', '')),
                        'sector': str(row.get('sector', 'Other') or 'Other'),
                        'country': str(row.get('country', 'Unknown') or 'Unknown'),
                        'value': round(value, 0),
                        'price': round(price, 2),
                        'qty': qty,
                        'pnl_pct': round(pnl_pct, 2),
                        'change_pct': round(change_pct, 2),
                        'ytd_pct': round(ytd_pct, 2),
                        'pe': round(pe, 1) if pe else None,
                        'pcf': round(pcf, 1) if pcf else None,
                        'roe': round(roe, 1) if roe else None,
                        'score': score
                    }
                    positions.append(pos)

                # Calculate weights
                for pos in positions:
                    pos['weight'] = round((pos['value'] / total_value * 100), 2) if total_value > 0 else 0

                # Group positions
                grouped = {}
                if grouping == 'flat':
                    grouped = {'All': positions}
                else:
                    group_key = grouping  # 'sector' or 'country'
                    for pos in positions:
                        group = pos.get(group_key, 'Other')
                        if group not in grouped:
                            grouped[group] = []
                        grouped[group].append(pos)

                # Calculate group totals
                groups_data = []
                for group_name, group_positions in grouped.items():
                    group_value = sum(p['value'] for p in group_positions)
                    group_weight = (group_value / total_value * 100) if total_value > 0 else 0

                    # Calculate weighted average performance for group
                    if group_value > 0:
                        weighted_perf = sum(p['change_pct'] * p['value'] for p in group_positions) / group_value
                    else:
                        weighted_perf = 0

                    groups_data.append({
                        'name': group_name,
                        'value': round(group_value, 0),
                        'weight': round(group_weight, 2),
                        'perf': round(weighted_perf, 2),
                        'positions': sorted(group_positions, key=lambda x: x['value'], reverse=True)
                    })

                # Sort groups by value
                groups_data.sort(key=lambda x: x['value'], reverse=True)

                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({
                    'success': True,
                    'data': {
                        'total_value': round(total_value, 0),
                        'metric': metric,
                        'grouping': grouping,
                        'groups': groups_data
                    }
                }).encode('utf-8'))
            except Exception as e:
                log.error(f"Error getting heatmap data: {e}")
                self.send_response(500)
                self.send_header('Content-Type', 'application/json')
                self.end_headers()
                self.wfile.write(json.dumps({'success': False, 'error': str(e)}).encode('utf-8'))
            return

        # ===================== END HEATMAP API ROUTES =====================

        if 'download' in q:
            fp = urllib.parse.unquote(q['download'][0])
            # Security: Validate path is within allowed directory (prevent path traversal)
            fp = os.path.abspath(fp)
            safe_dir = os.path.abspath(CONFIG.get('memo_dir', '.'))
            if not fp.startswith(safe_dir):
                log.warning(f"Blocked path traversal attempt: {fp}")
                self.send_response(403); self.end_headers(); return

            if os.path.exists(fp):
                self.send_response(200)
                self.send_header('Content-Type', 'application/vnd.openxmlformats-officedocument.wordprocessingml.document')
                self.send_header('Content-Disposition', f'attachment; filename="{os.path.basename(fp)}"')
                self.end_headers()
                with open(fp, 'rb') as f: self.wfile.write(f.read())
                return

            self.send_response(404); self.end_headers(); return

        

        # ═══ REFRESH SCREENER DATA ═══

        if q.get('action') == ['refresh_screener_data']:

            scope = q.get('scope', ['france'])[0]



            # Check if already running

            if REFRESH_STATUS['running']:

                self.send_response(400)

                self.send_header('Content-type', 'application/json')

                self.end_headers()

                self.wfile.write(json.dumps({'error': 'Refresh already running'}).encode())

                return



            # Start background refresh in a separate thread

            threading.Thread(target=refresh_screener_data_background, args=(scope,), daemon=True).start()



            self.send_response(200)

            self.send_header('Content-type', 'application/json')

            self.end_headers()

            self.wfile.write(json.dumps({'status': 'started'}).encode())

            return



        # ═══ REFRESH STATUS ═══

        if q.get('action') == ['refresh_status']:

            self.send_response(200)

            self.send_header('Content-type', 'application/json')

            self.end_headers()

            self.wfile.write(json.dumps(REFRESH_STATUS).encode())

            return



        # ═══ SCREENER JSON API ═══

        # Sert les données du screener en JSON pour le frontend screener_v2

        # Utilise le cache existant — temps de réponse < 50ms

        if q.get('action') == ['screener_json']:

            scope = q.get('scope', ['france'])[0]

            mode = q.get('mode', ['standard'])[0]

            force = 'force' in q

            

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

            

            self.send_response(200)

            self.send_header('Content-type', 'application/json')

            self.send_header('Cache-Control', 'public, max-age=3600')

            self.send_header('Access-Control-Allow-Origin', '*')

            self.end_headers()

            self.wfile.write(json.dumps(response).encode())

            return

        

        # ═══ SERVE ADVISOR PAGE ═══

        if p.path in ('/advisor', '/advisor/'):
            self.send_response(200)
            self.send_header('Content-type', 'text/html; charset=utf-8')
            self.send_header('Cache-Control', 'no-cache')
            self.end_headers()
            self.wfile.write(gen_advisor_html().encode())
            return


        # ═══ SERVE SCREENER V2 PAGE ═══

        if p.path in ('/screener', '/screener/'):

            # Try multiple locations for screener_v2.html
            possible_paths = [
                os.path.join(os.path.dirname(__file__), 'templates', 'screener_v2.html'),
                os.path.join(os.path.dirname(os.path.dirname(__file__)), 'screener_v2.html'),
                'screener_v2.html',
            ]
            screener_html = None
            for path in possible_paths:
                if os.path.exists(path):
                    screener_html = path
                    break

            if screener_html:

                self.send_response(200)

                self.send_header('Content-type', 'text/html; charset=utf-8')

                self.send_header('Cache-Control', 'no-cache')

                self.end_headers()

                with open(screener_html, 'r', encoding='utf-8') as f:

                    self.wfile.write(f.read().encode())

                return

        

        # ═══ SERVE SCREENER CACHE FILE (fallback) ═══

        if p.path == '/screener_cache.json':

            cache_file = CONFIG['screener_cache_file']

            if os.path.exists(cache_file):

                self.send_response(200)

                self.send_header('Content-type', 'application/json')

                self.send_header('Cache-Control', 'public, max-age=1800')

                self.end_headers()

                with open(cache_file, 'rb') as f:

                    self.wfile.write(f.read())

                return

            self.send_response(404); self.end_headers(); return

        

        if 'detail' in q:

            ticker = q['detail'][0].upper()

            self.send_response(200)

            self.send_header('Content-type', 'text/html; charset=utf-8')

            self.end_headers()

            self.wfile.write(gen_detail_html(get_security_data(ticker)).encode())

            return

        

        self.send_response(200)

        self.send_header('Content-type', 'text/html; charset=utf-8')

        self.end_headers()

        

        df, err = load_portfolio()

        if err:

            self.wfile.write(f"<h1>Erreur: {err}</h1>".encode())

            return

        

        do_refresh = 'refresh' in q and YFINANCE_OK

        if do_refresh:

            log_portfolio.info("Refreshing portfolio data...")

            df = update_portfolio(df)

        

        # Screener with scope and mode support

        screener_scope = q.get('scope', ['france'])[0] if 'screener' in q else 'france'

        screener_mode = q.get('mode', ['standard'])[0] if 'screener' in q else 'standard'

        screener_data = run_screener(force='screener' in q, scope=screener_scope, mode=screener_mode)

        

        df = calc_scores(df)

        self.wfile.write(gen_html(df, screener_data, load_watchlist(), update_history=do_refresh).encode())

    

    def log_message(self, *args): pass



if __name__ == "__main__":

    log.info("="*50)

    log.info("   BLOOMBERG PORTFOLIO TERMINAL v3.1")

    log.info("="*50)

    if not os.path.exists(CONFIG['portfolio_file']):

        log.error(f"Erreur: {CONFIG['portfolio_file']} non trouve")

        sys.exit(1)

    log.info(f"http://localhost:{CONFIG['port']}")

    threading.Timer(1, lambda: webbrowser.open(f"http://localhost:{CONFIG['port']}")).start()

    log.info("Ctrl+C pour arreter")

    log.info("-"*50)

    try:

        HTTPServer(('localhost', CONFIG['port']), Handler).serve_forever()

    except KeyboardInterrupt:

        log.info("Bye")

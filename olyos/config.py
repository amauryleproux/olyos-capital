#!/usr/bin/env python3
"""
OLYOS CAPITAL - Configuration Module
=====================================
Centralized configuration for Portfolio Terminal v4.0

All hardcoded values extracted from app.py for easy modification.
"""

from dataclasses import dataclass, field
from typing import Dict, List, Optional
from datetime import datetime


# =============================================================================
# APPLICATION INFO
# =============================================================================

APP_NAME: str = "OLYOS CAPITAL"
APP_TITLE: str = "PORTFOLIO TERMINAL"
APP_VERSION: str = "4.0"
APP_SUBTITLE: str = "Bloomberg Style with Backtesting"


# =============================================================================
# FILE PATHS & DIRECTORIES
# =============================================================================

@dataclass
class FileConfig:
    """File and directory paths configuration."""
    portfolio_file: str = 'portfolio.xlsx'
    watchlist_file: str = 'watchlist.json'
    screener_cache_file: str = 'screener_cache.json'
    nav_history_file: str = 'nav_history.json'
    backtest_cache_dir: str = 'backtest_cache'
    backtest_history_file: str = 'backtest_history.json'
    memo_dir: str = '.'


FILES = FileConfig()

# Legacy CONFIG dict for backward compatibility
CONFIG: Dict[str, any] = {
    'portfolio_file': FILES.portfolio_file,
    'watchlist_file': FILES.watchlist_file,
    'screener_cache_file': FILES.screener_cache_file,
    'nav_history_file': FILES.nav_history_file,
    'backtest_cache_dir': FILES.backtest_cache_dir,
    'backtest_history_file': FILES.backtest_history_file,
    'memo_dir': FILES.memo_dir,
    'port': 8080,
    'cache_days': 30
}


# =============================================================================
# SERVER CONFIGURATION
# =============================================================================

@dataclass
class ServerConfig:
    """HTTP server configuration."""
    port: int = 8080
    host: str = '0.0.0.0'


SERVER = ServerConfig()


# =============================================================================
# CACHE CONFIGURATION
# =============================================================================

@dataclass
class CacheConfig:
    """Cache duration settings in days."""
    cache_dir: str = 'backtest_cache'
    fundamentals_days: int = 30  # Refresh fundamentals monthly
    prices_days: int = 1  # Refresh prices daily (only if online)
    universe_days: int = 30  # Refresh universe monthly
    general_days: int = 30  # General cache validity


CACHE = CacheConfig()


# =============================================================================
# API CONFIGURATION
# =============================================================================

@dataclass
class APIConfig:
    """API endpoints and settings."""
    # EOD Historical Data API
    eod_base_url: str = "https://eodhd.com/api"
    eod_exchange_list_endpoint: str = "/exchange-symbol-list/{exchange}"
    eod_fundamentals_endpoint: str = "/fundamentals/{ticker}"
    eod_prices_endpoint: str = "/eod/{ticker}"

    # Timeouts in seconds
    timeout_universe: int = 60
    timeout_fundamentals: int = 30
    timeout_prices: int = 30

    # Anthropic Claude AI
    claude_model: str = "claude-sonnet-4-20250514"


API = APIConfig()


# =============================================================================
# HIGGONS SCORING THRESHOLDS
# =============================================================================

@dataclass
class HiggonsConfig:
    """Higgons-style value investing criteria and scoring thresholds."""

    # === BUY CRITERIA (Default) ===
    pe_max_buy: float = 12.0  # Maximum P/E for buying
    roe_min_buy: float = 10.0  # Minimum ROE % for buying
    debt_equity_max: float = 100.0  # Maximum Debt/Equity % for buying

    # === SELL CRITERIA (Default) ===
    pe_sell_threshold: float = 17.0  # Sell if P/E exceeds this
    roe_min_hold: float = 8.0  # Sell if ROE drops below this %

    # === AI OPTIMAL CRITERIA ===
    # Results from AI optimization backtesting
    ai_pe_max: float = 8.0
    ai_roe_min: float = 12.0  # percentage
    ai_debt_equity_max: float = 50.0  # percentage
    ai_max_positions: int = 18

    # === PE SCORING THRESHOLDS ===
    # Points awarded based on P/E ratio (max 30 points)
    pe_score_excellent: float = 8.0  # <= 8 gets 30 points
    pe_score_very_good: float = 10.0  # <= 10 gets 25 points
    pe_score_good: float = 12.0  # <= 12 gets 20 points
    pe_score_fair: float = 15.0  # <= 15 gets 15 points
    pe_score_acceptable: float = 20.0  # <= 20 gets 10 points

    # === ROE SCORING THRESHOLDS ===
    # Points awarded based on ROE (max 30 points)
    roe_score_excellent: float = 20.0  # >= 20% gets 30 points
    roe_score_very_good: float = 15.0  # >= 15% gets 25 points
    roe_score_good: float = 12.0  # >= 12% gets 20 points
    roe_score_fair: float = 10.0  # >= 10% gets 15 points
    roe_score_acceptable: float = 8.0  # >= 8% gets 10 points

    # === DEBT/EQUITY SCORING THRESHOLDS ===
    # Points awarded based on D/E ratio (max 20 points)
    de_score_excellent: float = 0.0  # <= 0 (net cash) gets 20 points
    de_score_very_good: float = 0.3  # <= 30% gets 15 points
    de_score_good: float = 0.5  # <= 50% gets 10 points
    de_score_fair: float = 1.0  # <= 100% gets 5 points

    # === NET DEBT/EBITDA SCORING THRESHOLDS ===
    # Points for leverage (max 20 points)
    nd_ebitda_excellent: float = 0.0  # <= 0 (net cash) gets 20 points
    nd_ebitda_very_good: float = 1.0  # <= 1x gets 15 points
    nd_ebitda_good: float = 2.0  # <= 2x gets 10 points
    nd_ebitda_fair: float = 3.0  # <= 3x gets 5 points

    # === PROFIT MARGIN SCORING THRESHOLDS ===
    # Points based on profit margin (max 20 points)
    margin_excellent: float = 0.15  # >= 15% gets 20 points
    margin_very_good: float = 0.10  # >= 10% gets 15 points
    margin_good: float = 0.07  # >= 7% gets 10 points
    margin_fair: float = 0.05  # >= 5% gets 5 points

    # === HIGGONS GATE THRESHOLDS ===
    # Gates that must be passed for consideration
    gate_pe_max: float = 25.0  # PE must be <= 25
    gate_roe_min: float = 0.05  # ROE must be >= 5%
    gate_equity_ratio_min: float = 0.30  # Equity ratio >= 30%
    gate_leverage_max: float = 3.0  # Net Debt/EBITDA <= 3


HIGGONS = HiggonsConfig()

# AI Optimal Criteria dict for backward compatibility
AI_OPTIMAL_CRITERIA: Dict[str, any] = {
    'pe_max': HIGGONS.ai_pe_max,
    'roe_min': HIGGONS.ai_roe_min,
    'debt_equity_max': HIGGONS.ai_debt_equity_max,
    'max_positions': HIGGONS.ai_max_positions
}


# =============================================================================
# BACKTEST CONFIGURATION
# =============================================================================

@dataclass
class BacktestConfig:
    """Backtesting default parameters."""
    # Default date range
    default_start_date: str = '2014-01-01'
    default_start_date_alt: str = '2015-01-01'

    # Portfolio settings
    initial_capital: float = 100000.0
    max_positions: int = 20
    default_benchmark: str = '^FCHI'  # CAC 40

    # Rebalancing
    default_rebalance_freq: str = 'quarterly'  # 'monthly', 'quarterly', 'yearly'

    # Universe limits
    max_universe_tickers: int = 200  # Limit to avoid API overload
    max_backtest_history: int = 50  # Keep last N backtests

    # Default parameter grid for optimization
    pe_variations: List[int] = field(default_factory=lambda: [8, 10, 12, 15])
    roe_variations: List[int] = field(default_factory=lambda: [8, 10, 12, 15])
    debt_variations: List[int] = field(default_factory=lambda: [50, 100, 150])
    position_variations: List[int] = field(default_factory=lambda: [10, 15, 20, 25, 30])


BACKTEST = BacktestConfig()

# Default backtest parameter grid
BACKTEST_PARAM_GRID: List[Dict[str, any]] = [
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


# =============================================================================
# EXCHANGE CONFIGURATION
# =============================================================================

@dataclass
class ExchangeConfig:
    """Stock exchange settings."""
    # Default exchange for French stocks
    default_exchange: str = 'PA'  # Euronext Paris

    # European exchanges for universe scanning
    europe_exchanges: List[str] = field(default_factory=lambda: [
        'PA',      # Euronext Paris (France)
        'AS',      # Euronext Amsterdam (Netherlands)
        'BR',      # Euronext Brussels (Belgium)
        'MI',      # Borsa Italiana (Italy)
        'MC',      # Bolsa de Madrid (Spain)
        'XETRA',   # Deutsche Borse (Germany)
        'SW',      # SIX Swiss Exchange (Switzerland)
        'LSE',     # London Stock Exchange (UK)
    ])

    # Market cap filters for universe (in currency)
    max_market_cap: float = 10e9  # 10 billion
    min_market_cap: float = 50e6  # 50 million


EXCHANGES = ExchangeConfig()


# =============================================================================
# TICKER MAPPING
# =============================================================================

# Mapping of ticker symbols to Yahoo Finance format
TICKER_MAP: Dict[str, str] = {
    # Belgian stocks
    'SIP': 'SIP.BR',
    'BEKB': 'BEKB.BR',

    # Danish stocks
    'PNDORA': 'PNDORA.CO',

    # German stocks
    'NEAG': 'NEAG.DE',
    'HBH': 'HBH.DE',
    'WAC': 'WAC.DE',
    'NDA': 'NDA.DE',
    'SZG': 'SZG.DE',

    # Swiss stocks
    'ZURN': 'ZURN.SW',
    'IMPN': 'IMPN.SW',

    # US stocks
    'FCX': 'FCX',

    # Dutch stocks
    'BAMNB': 'BAMNB.AS',
    'HEIJM': 'HEIJM.AS',

    # Italian stocks
    'WBD': 'WBD.MI',
    'DAN': 'DAN.MI',
    'MAIRE': 'MAIRE.MI',
    'BZU': 'BZU.MI',
    'CEM': 'CEM.MI',

    # Spanish stocks
    'CAF': 'CAF.MC',
    'TRE': 'TRE.MC',
    'IDR': 'IDR.MC',
    'CIE': 'CIE.MC',
    'SCYR': 'SCYR.MC',

    # Greek stocks
    'METLEN': 'METLEN.AT',
    'MOH': 'MOH.AT',
    'BELA': 'BELA.AT',

    # Portuguese stocks
    'EGL': 'EGL.LS',

    # Austrian stocks
    'POS': 'POS.VI',

    # UK stocks
    'KLR': 'KLR.L',
    'MGNS': 'MGNS.L',
    'IMB': 'IMB.L',
    'RIO': 'RIO.L',
    'BA': 'BA.L',

    # French stocks (explicit mapping)
    'MC': 'MC.PA',
    'VIE': 'VIE.PA',
    'GFC': 'GFC.PA',
    'ALVAP': 'ALVAP.PA',
    'ALWEC': 'ALWEC.PA',
    'NXI': 'NXI.PA',
    'SK': 'SK.PA',
    'ALCAT': 'ALCAT.PA',
    'CATG': 'ALCAT.PA',  # Old ticker
}


# =============================================================================
# MEMO FILE PATTERNS
# =============================================================================

# Patterns for finding investment memo files by ticker
MEMO_PATTERNS: Dict[str, List[str]] = {
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


# =============================================================================
# EUROPE DATABASE (Legacy Stock List)
# =============================================================================

EUROPE_DB: List[Dict[str, str]] = [
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


# =============================================================================
# UI COLOR SCHEME (Bloomberg-style)
# =============================================================================

@dataclass
class ColorScheme:
    """Color codes used in the Bloomberg-style UI."""
    # Primary colors
    background: str = '#000'
    background_secondary: str = '#0a0a0a'
    background_tertiary: str = '#0d0d0d'
    background_panel: str = '#1a1a1a'
    background_hover: str = '#111'

    # Brand color (Orange - Bloomberg style)
    primary: str = '#ff9500'
    primary_light: str = '#ffaa33'

    # Text colors
    text_primary: str = '#fff'
    text_secondary: str = '#ccc'
    text_muted: str = '#888'
    text_dark: str = '#666'

    # Accent colors
    accent_blue: str = '#00bfff'  # Tickers, links
    accent_green: str = '#00ff00'  # Positive values, time
    accent_red: str = '#ff3b30'  # Negative values
    accent_purple: str = '#9933ff'  # Backtest badge

    # Signal colors
    signal_buy: str = '#00ff00'
    signal_sell: str = '#ff3b30'
    signal_hold: str = '#ff9500'
    signal_watch: str = '#00bfff'

    # Border colors
    border_primary: str = '#ff9500'
    border_secondary: str = '#333'
    border_light: str = '#222'
    border_dark: str = '#1a1a1a'

    # Gradient backgrounds
    gradient_header: str = 'linear-gradient(180deg,#1a1a1a,#0d0d0d)'
    gradient_panel: str = 'linear-gradient(180deg,#1a1a1a,#111)'
    gradient_chart: str = 'linear-gradient(180deg,#0d0d0d 0%,#050505 100%)'


COLORS = ColorScheme()


# =============================================================================
# UI TEXT & LABELS
# =============================================================================

@dataclass
class UILabels:
    """UI text strings and labels."""
    # Navigation tabs
    tab_portfolio: str = "Portfolio"
    tab_screener: str = "Screener"
    tab_watchlist: str = "Watchlist"
    tab_backtest: str = "Backtest"

    # Function keys
    fkey_portfolio: str = "F1 PORT"
    fkey_screener: str = "F2 SCRN"
    fkey_watchlist: str = "F3 WTCH"
    fkey_backtest: str = "F4 BACK"
    fkey_refresh: str = "F5 REFRESH"
    fkey_scan: str = "F6 SCAN"

    # KPI labels
    kpi_nav: str = "NAV"
    kpi_pnl: str = "P&L"
    kpi_change: str = "%CHG"
    kpi_positions: str = "POS"
    kpi_updated: str = "UPD"

    # Table headers
    col_ticker: str = "Ticker"
    col_name: str = "Name"
    col_qty: str = "Qty"
    col_last: str = "Last"
    col_mkt_val: str = "Mkt Val"
    col_weight: str = "Weight"
    col_change: str = "%Chg"
    col_pe: str = "P/E"
    col_roe: str = "ROE"
    col_signal: str = "Signal"
    col_actions: str = "Actions"

    # Buttons
    btn_add_position: str = "+ ADD POSITION"
    btn_run_scan: str = "RUN SCAN"
    btn_save: str = "SAVE"
    btn_cancel: str = "CANCEL"

    # Performance labels
    perf_1w: str = "1W Perf"
    perf_1m: str = "1M Perf"
    perf_total: str = "Total Perf"
    nav_high: str = "NAV High"
    nav_low: str = "NAV Low"
    days_tracked: str = "Days Tracked"

    # Screener labels
    screener_universe: str = "Universe"
    screener_opportunities: str = "Opportunities"
    screener_source: str = "Source"

    # Screener scope options
    scope_france: str = "[FR] France"
    scope_europe: str = "[EU] Europe"
    scope_legacy: str = "Legacy (52)"

    # Screener mode options
    mode_standard: str = "Standard"
    mode_ai_optimal: str = "AI Optimal (PE<=8, ROE>=12%, Top 18)"

    # Chart period buttons
    period_1w: str = "1W"
    period_1m: str = "1M"
    period_3m: str = "3M"
    period_all: str = "ALL"

    # Holdings panel
    panel_holdings: str = "Holdings"
    panel_subtitle: str = "Click column header to sort"

    # Input placeholders
    placeholder_ticker: str = "Enter ticker..."

    # Status messages
    status_initializing: str = "Initializing..."
    status_refresh_complete: str = "Refresh complete! Running screener..."
    status_done: str = "Done!"


LABELS = UILabels()


# =============================================================================
# SIGNAL KEYWORDS
# =============================================================================

# Signal keyword mappings (used in memo parsing)
SIGNAL_KEYWORDS: Dict[str, str] = {
    'ACHAT': 'buy',
    'BUY': 'buy',
    'STRONG BUY': 'buy',
    'VENTE': 'sell',
    'SELL': 'sell',
    'ECARTER': 'sell',
    'SURVEILLANCE': 'watch',
    'WATCH': 'watch',
    'HOLD': 'hold',
    'NEUTRE': 'hold',
    'NEUTRAL': 'hold',
}


# =============================================================================
# MEMO SECTION KEYWORDS
# =============================================================================

# Keywords for detecting section headers in investment memos
MEMO_SECTION_KEYWORDS: List[str] = [
    'SIGNAL', 'RESUME', 'SUMMARY', 'THESIS', 'RISQUES', 'RISK',
    'VALORISATION', 'VALUATION', 'FINANCIER', 'FINANCIAL',
    'CONCLUSION', 'PROFIL', 'PROFILE', 'ACTIONNARIAT', 'SHAREHOLDERS',
    'GEOGRAPHIE', 'GEOGRAPHY', 'CATALYSTS', 'CATALYSEURS',
    'POINTS FORTS', 'STRENGTHS', 'POINTS FAIBLES', 'WEAKNESSES',
    'RECOMMENDATION', 'RECOMMANDATION', 'OVERVIEW', 'APERCU',
    'DESCRIPTION', 'STRUCTURE', 'STRATEGIE', 'STRATEGY',
    'HISTORIQUE', 'HISTORY', 'ACQUISITION'
]


# =============================================================================
# FILTER KEYWORDS (For Universe Filtering)
# =============================================================================

@dataclass
class FilterKeywords:
    """Keywords used to filter out unwanted securities from universe."""
    # Name patterns to exclude (ADRs, GDRs, etc.)
    exclude_name_patterns: List[str] = field(default_factory=lambda: [
        'ADR', 'GDR', 'DEPOSITARY', 'RECEIPT', 'SPONSORED'
    ])

    # Types to exclude (ETFs, funds, etc.)
    exclude_types: List[str] = field(default_factory=lambda: [
        'ETF', 'FUND', 'WARRANT', 'TRACKER', 'CERTIFICATE', 'REIT', 'TRUST'
    ])

    # Special characters to exclude in ticker codes
    exclude_ticker_chars: List[str] = field(default_factory=lambda: [
        '$', '#', '&', ' ', '='
    ])

    # Minimum ticker length
    min_ticker_length: int = 2


FILTERS = FilterKeywords()


# =============================================================================
# REFRESH STATUS TEMPLATE
# =============================================================================

# Template for refresh status tracking
REFRESH_STATUS_TEMPLATE: Dict[str, any] = {
    'running': False,
    'progress': 0,
    'total': 0,
    'current_ticker': '',
    'message': ''
}


# =============================================================================
# UTILITY FUNCTIONS
# =============================================================================

def get_current_date() -> str:
    """Get current date in YYYY-MM-DD format."""
    return datetime.now().strftime('%Y-%m-%d')


def get_default_end_date() -> str:
    """Get default end date for backtests (current date)."""
    return get_current_date()


def get_default_start_date() -> str:
    """Get default start date for backtests."""
    return BACKTEST.default_start_date

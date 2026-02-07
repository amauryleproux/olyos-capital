"""
OLYOS CAPITAL - PDF Report Service (Bloomberg Dark Theme)
==========================================================
Generate professional 3-page monthly factsheet reports.

Pages:
1. Dashboard - KPIs, Performance Chart, Monthly Heatmap, Risk Metrics
2. Portfolio Composition - Higgons Metrics Table
3. Allocations & Methodology - Sector/Geographic charts, Top/Bottom performers
"""

import io
import os
import json
import math
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

# Matplotlib configuration (must be before pyplot import)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import matplotlib.patches as mpatches
from matplotlib.patches import FancyBboxPatch
import numpy as np

from olyos.logger import get_logger

# ReportLab imports
try:
    from reportlab.lib import colors
    from reportlab.lib.pagesizes import A4
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import mm, cm, inch
    from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT, TA_JUSTIFY
    from reportlab.platypus import (
        SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
        PageBreak, Image, KeepTogether, Flowable
    )
    from reportlab.graphics.shapes import Drawing, Rect, String, Line
    from reportlab.graphics import renderPDF
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    REPORTLAB_AVAILABLE = True
except ImportError:
    REPORTLAB_AVAILABLE = False

# SVG support
try:
    from svglib.svglib import svg2rlg
    SVGLIB_AVAILABLE = True
except ImportError:
    SVGLIB_AVAILABLE = False

log = get_logger('pdf_report')


# ============================================================================
# BLOOMBERG DARK THEME COLORS
# ============================================================================

class Colors:
    """Bloomberg-style dark theme color palette"""
    BG_DARK = '#0A0E17'         # Main background
    BG_CARD = '#111827'          # Card background
    BG_CARD_ALT = '#0F1623'      # Alternating row background
    BG_HEADER = '#0D1320'        # Table header background
    BORDER = '#1E293B'           # Borders
    GOLD = '#D4A843'             # Primary accent (titles, tickers)
    GOLD_DIM = '#8B7635'         # Dimmed gold (labels)
    GREEN = '#22C55E'            # Positive values
    RED = '#EF4444'              # Negative values
    ORANGE = '#F59E0B'           # Warning/attention
    BLUE = '#3B82F6'             # Secondary accent
    TEXT_PRIMARY = '#F1F5F9'     # Primary text
    TEXT_SECONDARY = '#94A3B8'   # Secondary text
    TEXT_DIM = '#64748B'         # Dim labels
    TEXT_MUTED = '#475569'       # Very muted text

    @staticmethod
    def hex_to_rgb(hex_color: str) -> Tuple[float, float, float]:
        """Convert hex color to RGB tuple (0-1 range)"""
        hex_color = hex_color.lstrip('#')
        return tuple(int(hex_color[i:i+2], 16) / 255 for i in (0, 2, 4))

    @staticmethod
    def to_reportlab(hex_color: str) -> colors.Color:
        """Convert hex to ReportLab color"""
        r, g, b = Colors.hex_to_rgb(hex_color)
        return colors.Color(r, g, b)


# Chart colors for sectors
SECTOR_COLORS = [
    '#D4A843', '#22C55E', '#3B82F6', '#EF4444', '#F59E0B',
    '#8B5CF6', '#EC4899', '#14B8A6', '#6366F1', '#84CC16'
]

MONTH_NAMES = ['Jan', 'Fév', 'Mar', 'Avr', 'Mai', 'Jun',
               'Jul', 'Aoû', 'Sep', 'Oct', 'Nov', 'Déc']

MONTH_NAMES_FR = [
    'Janvier', 'Février', 'Mars', 'Avril', 'Mai', 'Juin',
    'Juillet', 'Août', 'Septembre', 'Octobre', 'Novembre', 'Décembre'
]


# ============================================================================
# DATA CLASSES
# ============================================================================

@dataclass
class ReportData:
    """Container for all report data"""
    month: int
    year: int
    generation_date: str

    # Performance KPIs
    nav_current: float = 0.0
    nav_mtd_pct: float = 0.0
    nav_ytd_pct: float = 0.0
    nav_inception_pct: float = 0.0
    inception_date: str = "2025-02-06"

    # Benchmark
    benchmark_name: str = "CAC Mid & Small"
    benchmark_ytd_pct: float = 0.0
    alpha_ytd: float = 0.0

    # Risk metrics
    sharpe_ratio: float = 0.0
    sortino_ratio: float = 0.0
    max_drawdown: float = 0.0
    volatility: float = 0.0
    beta: float = 1.0
    win_rate: float = 0.0
    var_95: float = 0.0
    information_ratio: float = 0.0

    # Portfolio
    num_positions: int = 0
    total_value: float = 0.0
    total_cost: float = 0.0
    realized_pnl: float = 0.0

    # Positions with Higgons metrics
    positions: List[Dict] = field(default_factory=list)

    # Allocations
    sector_allocation: List[Dict] = field(default_factory=list)
    geo_allocation: List[Dict] = field(default_factory=list)

    # Performance history for charts
    nav_history: List[Dict] = field(default_factory=list)
    benchmark_history: List[Dict] = field(default_factory=list)
    monthly_returns: Dict[int, Dict[int, float]] = field(default_factory=dict)


# ============================================================================
# CHART GENERATORS (Matplotlib with Dark Theme)
# ============================================================================

def configure_dark_style():
    """Configure matplotlib for dark theme"""
    plt.style.use('dark_background')
    plt.rcParams.update({
        'figure.facecolor': Colors.BG_DARK,
        'axes.facecolor': Colors.BG_CARD,
        'axes.edgecolor': Colors.BORDER,
        'axes.labelcolor': Colors.TEXT_SECONDARY,
        'text.color': Colors.TEXT_PRIMARY,
        'xtick.color': Colors.TEXT_DIM,
        'ytick.color': Colors.TEXT_DIM,
        'grid.color': Colors.BORDER,
        'grid.alpha': 0.3,
        'legend.facecolor': Colors.BG_CARD,
        'legend.edgecolor': Colors.BORDER,
        'font.family': 'sans-serif',
        'font.size': 8,
    })


def create_performance_chart(nav_history: List[Dict], benchmark_history: List[Dict],
                             width: float = 6, height: float = 2.5) -> io.BytesIO:
    """Create cumulative performance chart (base 100)"""
    configure_dark_style()

    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_facecolor(Colors.BG_DARK)
    ax.set_facecolor(Colors.BG_CARD)

    if nav_history:
        # Normalize to base 100
        dates = [datetime.strptime(n['date'], '%Y-%m-%d') for n in nav_history]
        first_nav = nav_history[0].get('nav', 1)
        values = [(n.get('nav', first_nav) / first_nav) * 100 for n in nav_history]

        # Portfolio line with fill
        ax.fill_between(dates, 100, values, alpha=0.2, color=Colors.GOLD)
        ax.plot(dates, values, color=Colors.GOLD, linewidth=2, label='Portfolio')

        # Final return annotation
        final_return = values[-1] - 100
        ax.annotate(f'{final_return:+.1f}%',
                   xy=(dates[-1], values[-1]),
                   xytext=(10, 0), textcoords='offset points',
                   color=Colors.GOLD, fontsize=10, fontweight='bold')

    if benchmark_history:
        bench_dates = [datetime.strptime(b['date'], '%Y-%m-%d') for b in benchmark_history]
        first_bench = benchmark_history[0].get('close', 100)
        bench_values = [(b.get('close', first_bench) / first_bench) * 100 for b in benchmark_history]

        ax.plot(bench_dates, bench_values, color=Colors.TEXT_DIM, linewidth=1.5,
                linestyle='--', label='CAC Mid & Small', alpha=0.7)

    # Styling
    ax.axhline(y=100, color=Colors.BORDER, linewidth=0.5, linestyle='-')
    ax.set_ylabel('Base 100', color=Colors.TEXT_DIM, fontsize=8)
    ax.legend(loc='upper left', fontsize=8, framealpha=0.8)
    ax.grid(True, alpha=0.2)

    # Format x-axis
    ax.tick_params(axis='both', which='major', labelsize=7)
    fig.autofmt_xdate(rotation=0)

    plt.tight_layout()

    # Save to buffer
    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, facecolor=Colors.BG_DARK,
                edgecolor='none', bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf


def create_monthly_heatmap(monthly_returns: Dict[int, Dict[int, float]],
                           width: float = 6, height: float = 1.8) -> io.BytesIO:
    """Create monthly returns heatmap"""
    configure_dark_style()

    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_facecolor(Colors.BG_DARK)
    ax.set_facecolor(Colors.BG_DARK)

    if not monthly_returns:
        ax.text(0.5, 0.5, 'Données insuffisantes', ha='center', va='center',
                color=Colors.TEXT_DIM, fontsize=10)
        ax.axis('off')
    else:
        years = sorted(monthly_returns.keys(), reverse=True)[:3]  # Last 3 years
        n_years = len(years)

        # Create data matrix
        for row_idx, year in enumerate(years):
            ytd = 0
            for month in range(1, 13):
                val = monthly_returns.get(year, {}).get(month)
                x = month - 1
                y = n_years - 1 - row_idx

                if val is not None:
                    ytd += val
                    # Color based on value
                    if val > 0:
                        intensity = min(abs(val) / 10, 1)
                        color = (*Colors.hex_to_rgb(Colors.GREEN), 0.3 + 0.5 * intensity)
                    elif val < 0:
                        intensity = min(abs(val) / 10, 1)
                        color = (*Colors.hex_to_rgb(Colors.RED), 0.3 + 0.5 * intensity)
                    else:
                        color = (*Colors.hex_to_rgb(Colors.TEXT_DIM), 0.3)

                    rect = plt.Rectangle((x, y), 0.9, 0.8, facecolor=color,
                                         edgecolor=Colors.BORDER, linewidth=0.5)
                    ax.add_patch(rect)
                    ax.text(x + 0.45, y + 0.4, f'{val:+.1f}%', ha='center', va='center',
                           fontsize=6, color=Colors.TEXT_PRIMARY if abs(val) > 2 else Colors.TEXT_DIM)
                else:
                    rect = plt.Rectangle((x, y), 0.9, 0.8, facecolor=Colors.BG_CARD,
                                         edgecolor=Colors.BORDER, linewidth=0.5)
                    ax.add_patch(rect)
                    ax.text(x + 0.45, y + 0.4, '-', ha='center', va='center',
                           fontsize=6, color=Colors.TEXT_MUTED)

            # YTD column
            rect = plt.Rectangle((12, y), 0.9, 0.8, facecolor=Colors.BG_HEADER,
                                 edgecolor=Colors.GOLD, linewidth=1)
            ax.add_patch(rect)
            ytd_color = Colors.GREEN if ytd > 0 else Colors.RED if ytd < 0 else Colors.TEXT_DIM
            ax.text(12.45, y + 0.4, f'{ytd:+.1f}%', ha='center', va='center',
                   fontsize=6, color=ytd_color, fontweight='bold')

            # Year label
            ax.text(-0.5, y + 0.4, str(year), ha='right', va='center',
                   fontsize=7, color=Colors.GOLD)

        # Month labels
        for i, month in enumerate(MONTH_NAMES + ['YTD']):
            ax.text(i + 0.45, n_years + 0.1, month, ha='center', va='bottom',
                   fontsize=6, color=Colors.TEXT_DIM)

        ax.set_xlim(-1, 13.5)
        ax.set_ylim(-0.2, n_years + 0.5)
        ax.axis('off')

    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, facecolor=Colors.BG_DARK,
                edgecolor='none', bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf


def create_sector_donut(sector_data: List[Dict], width: float = 3, height: float = 2.5) -> io.BytesIO:
    """Create sector allocation donut chart"""
    configure_dark_style()

    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_facecolor(Colors.BG_DARK)

    # Filter out invalid data (NaN, 0, None)
    valid_data = []
    for s in (sector_data or []):
        weight = s.get('weight', 0)
        if weight and not np.isnan(weight) and weight > 0:
            valid_data.append(s)

    if not valid_data:
        ax.text(0.5, 0.5, 'N/A', ha='center', va='center', color=Colors.TEXT_DIM, fontsize=12)
        ax.axis('off')
    else:
        sizes = [s.get('weight', 0) for s in valid_data]
        labels = [s.get('name', '')[:15] for s in valid_data]
        chart_colors = SECTOR_COLORS[:len(sizes)]

        wedges, texts, autotexts = ax.pie(
            sizes, labels=None, autopct='%1.0f%%',
            colors=chart_colors, startangle=90,
            wedgeprops=dict(width=0.6, edgecolor=Colors.BG_DARK),
            pctdistance=0.75
        )

        for autotext in autotexts:
            autotext.set_color(Colors.TEXT_PRIMARY)
            autotext.set_fontsize(7)

        # Legend
        ax.legend(wedges, labels, loc='center left', bbox_to_anchor=(1, 0.5),
                 fontsize=6, frameon=False)

    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, facecolor=Colors.BG_DARK,
                edgecolor='none', bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf


def create_geo_bars(geo_data: List[Dict], width: float = 3, height: float = 2) -> io.BytesIO:
    """Create geographic allocation horizontal bar chart"""
    configure_dark_style()

    fig, ax = plt.subplots(figsize=(width, height))
    fig.patch.set_facecolor(Colors.BG_DARK)
    ax.set_facecolor(Colors.BG_DARK)

    # Filter out invalid data
    valid_data = []
    for g in (geo_data or []):
        weight = g.get('weight', 0)
        if weight and not np.isnan(weight) and weight > 0:
            valid_data.append(g)

    if not valid_data:
        ax.text(0.5, 0.5, 'N/A', ha='center', va='center', color=Colors.TEXT_DIM, fontsize=12)
        ax.axis('off')
    else:
        labels = [g.get('name', '') for g in valid_data]
        values = [float(g.get('weight', 0)) for g in valid_data]
        bar_colors = [Colors.GOLD, Colors.BLUE, Colors.TEXT_DIM][:len(values)]

        y_pos = range(len(labels))
        bars = ax.barh(y_pos, values, color=bar_colors, height=0.6,
                      edgecolor=Colors.BORDER)

        ax.set_yticks(list(y_pos))
        ax.set_yticklabels(labels, fontsize=8, color=Colors.TEXT_PRIMARY)
        ax.set_xlim(0, 100)
        ax.set_xlabel('%', fontsize=8, color=Colors.TEXT_DIM)

        # Add value labels
        for bar, val in zip(bars, values):
            ax.text(bar.get_width() + 2, bar.get_y() + bar.get_height()/2,
                   f'{val:.0f}%', va='center', fontsize=8, color=Colors.TEXT_PRIMARY)

        ax.spines['top'].set_visible(False)
        ax.spines['right'].set_visible(False)
        ax.spines['bottom'].set_color(Colors.BORDER)
        ax.spines['left'].set_color(Colors.BORDER)

    plt.tight_layout()

    buf = io.BytesIO()
    fig.savefig(buf, format='png', dpi=150, facecolor=Colors.BG_DARK,
                edgecolor='none', bbox_inches='tight')
    plt.close(fig)
    buf.seek(0)
    return buf


# ============================================================================
# HIGGONS SCORING FUNCTIONS
# ============================================================================

def calculate_higgons_score(pe: float, roe: float, gearing: float,
                           mom_6m: float, mom_12m: float, pcf: float = None) -> int:
    """
    Calculate Higgons score out of 15 (scaled to 10).

    Scoring:
    - P/E < 8: 3pts, < 10: 2pts, < 12: 1pt (max 3)
    - P/CF <= 6: 3pts, <= 8: 2pts, <= 10: 1pt (max 3) - NEW
    - ROE > 15%: 3pts, > 12%: 2pts, > 10%: 1pt (max 3)
    - Gearing < 20%: 2pts, < 50%: 1pt (max 2)
    - Mom 6M > 20%: 2pts, > 0%: 1pt (max 2)

    Total max = 13 points, scaled to 10
    """
    score = 0

    # P/E score (lower is better)
    if pe is not None and pe > 0:
        if pe < 8:
            score += 3
        elif pe < 10:
            score += 2
        elif pe < 12:
            score += 1

    # P/CF score (lower is better) - Price to Cash Flow
    if pcf is not None and pcf > 0:
        if pcf <= 6:
            score += 3
        elif pcf <= 8:
            score += 2
        elif pcf <= 10:
            score += 1

    # ROE score (higher is better)
    if roe is not None:
        if roe > 15:
            score += 3
        elif roe > 12:
            score += 2
        elif roe > 10:
            score += 1

    # Gearing score (lower is better)
    if gearing is not None:
        if gearing < 20:
            score += 2
        elif gearing < 50:
            score += 1

    # Momentum score
    if mom_6m is not None:
        if mom_6m > 20:
            score += 2
        elif mom_6m > 0:
            score += 1

    # Scale to 10 (max is now 13)
    return min(round(score * 10 / 13), 10)


def get_metric_color(metric_type: str, value: float) -> str:
    """Get color for Higgons metric based on thresholds"""
    if value is None:
        return Colors.TEXT_DIM

    if metric_type == 'pe':
        if value < 8:
            return Colors.GREEN
        elif value < 12:
            return Colors.GOLD
        else:
            return Colors.RED
    elif metric_type == 'roe':
        if value > 15:
            return Colors.GREEN
        elif value > 12:
            return Colors.GOLD
        else:
            return Colors.ORANGE
    elif metric_type == 'gearing':
        if value < 30:
            return Colors.GREEN
        elif value < 50:
            return Colors.GOLD
        else:
            return Colors.RED
    elif metric_type == 'momentum':
        return Colors.GREEN if value > 0 else Colors.RED

    return Colors.TEXT_PRIMARY


# ============================================================================
# PDF REPORT SERVICE
# ============================================================================

class PDFReportService:
    """Service for generating Bloomberg-style PDF reports"""

    def __init__(
        self,
        reports_dir: str,
        nav_history_file: str,
        portfolio_func=None,
        benchmark_service=None,
        position_manager=None
    ):
        if not REPORTLAB_AVAILABLE:
            raise ImportError("ReportLab is not installed. Run: pip install reportlab")

        self.reports_dir = reports_dir
        self.nav_history_file = nav_history_file
        self.get_portfolio = portfolio_func
        self.benchmark_service = benchmark_service
        self.position_manager = position_manager

        os.makedirs(reports_dir, exist_ok=True)

    def _load_nav_history(self) -> List[Dict]:
        """Load NAV history from file"""
        if not os.path.exists(self.nav_history_file):
            return []
        try:
            with open(self.nav_history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log.error(f"Error loading NAV history: {e}")
            return []

    def _calculate_monthly_returns(self, nav_history: List[Dict]) -> Dict[int, Dict[int, float]]:
        """Calculate monthly returns from NAV history"""
        monthly = {}
        month_navs = {}

        for n in nav_history:
            date_str = n.get('date', '')
            if not date_str:
                continue
            try:
                dt = datetime.strptime(date_str, '%Y-%m-%d')
                key = (dt.year, dt.month)
                if key not in month_navs:
                    month_navs[key] = {'first': None, 'last': None}
                if month_navs[key]['first'] is None:
                    month_navs[key]['first'] = n.get('nav', 0)
                month_navs[key]['last'] = n.get('nav', 0)
            except ValueError:
                continue

        for (year, month), navs in month_navs.items():
            if navs['first'] and navs['first'] > 0:
                ret = ((navs['last'] / navs['first']) - 1) * 100
                if year not in monthly:
                    monthly[year] = {}
                monthly[year][month] = round(ret, 1)

        return monthly

    def _calculate_risk_metrics(self, nav_history: List[Dict]) -> Dict:
        """Calculate risk metrics from NAV history"""
        metrics = {
            'sharpe': 0.0, 'sortino': 0.0, 'max_dd': 0.0,
            'volatility': 0.0, 'win_rate': 0.0, 'var_95': 0.0
        }

        if len(nav_history) < 2:
            return metrics

        # Calculate daily returns
        navs = [n.get('nav', 0) for n in nav_history if n.get('nav', 0) > 0]
        returns = []
        for i in range(1, len(navs)):
            returns.append((navs[i] / navs[i-1]) - 1)

        if not returns:
            return metrics

        returns = np.array(returns)

        # Volatility (annualized)
        metrics['volatility'] = float(np.std(returns) * np.sqrt(252) * 100)

        # Sharpe Ratio (assuming 3.5% risk-free rate)
        rf_daily = 0.035 / 252
        avg_return = np.mean(returns)
        if metrics['volatility'] > 0:
            metrics['sharpe'] = float((avg_return - rf_daily) * np.sqrt(252) / np.std(returns))

        # Sortino Ratio
        downside_returns = returns[returns < 0]
        if len(downside_returns) > 0:
            downside_std = np.std(downside_returns) * np.sqrt(252)
            if downside_std > 0:
                metrics['sortino'] = float((avg_return - rf_daily) * np.sqrt(252) / downside_std)

        # Max Drawdown
        peak = navs[0]
        max_dd = 0
        for nav in navs:
            if nav > peak:
                peak = nav
            dd = (peak - nav) / peak
            if dd > max_dd:
                max_dd = dd
        metrics['max_dd'] = float(max_dd * 100)

        # Win Rate (% of positive days)
        metrics['win_rate'] = float(np.sum(returns > 0) / len(returns) * 100)

        # VaR 95%
        metrics['var_95'] = float(np.percentile(returns, 5) * 100)

        return metrics

    def _gather_report_data(self, month: int, year: int) -> ReportData:
        """Gather all data needed for the report"""
        data = ReportData(
            month=month,
            year=year,
            generation_date=datetime.now().strftime('%d/%m/%Y %H:%M')
        )

        # Load NAV history
        nav_history = self._load_nav_history()
        if nav_history:
            data.nav_history = nav_history
            data.nav_current = nav_history[-1].get('nav', 0)

            # Find inception date and value
            data.inception_date = nav_history[0].get('date', '2025-02-06')
            nav_inception = nav_history[0].get('nav', nav_history[0].get('cost', 1))

            # Calculate YTD
            year_start = f"{year}-01-01"
            nav_start_year = nav_inception
            for n in nav_history:
                if n.get('date', '') >= year_start:
                    nav_start_year = n.get('nav', nav_inception)
                    break

            # Calculate MTD
            month_start = f"{year}-{month:02d}-01"
            nav_start_month = data.nav_current
            for n in nav_history:
                if n.get('date', '') >= month_start:
                    nav_start_month = n.get('nav', data.nav_current)
                    break

            # Calculate returns
            if nav_start_month > 0:
                data.nav_mtd_pct = ((data.nav_current / nav_start_month) - 1) * 100
            if nav_start_year > 0:
                data.nav_ytd_pct = ((data.nav_current / nav_start_year) - 1) * 100
            if nav_inception > 0:
                data.nav_inception_pct = ((data.nav_current / nav_inception) - 1) * 100

            # Monthly returns for heatmap
            data.monthly_returns = self._calculate_monthly_returns(nav_history)

            # Risk metrics
            risk_metrics = self._calculate_risk_metrics(nav_history)
            data.sharpe_ratio = risk_metrics['sharpe']
            data.sortino_ratio = risk_metrics['sortino']
            data.max_drawdown = risk_metrics['max_dd']
            data.volatility = risk_metrics['volatility']
            data.win_rate = risk_metrics['win_rate']
            data.var_95 = risk_metrics['var_95']

        # Get benchmark data
        if self.benchmark_service:
            try:
                metrics = self.benchmark_service.calculate_metrics('CACMS', 'YTD')
                data.benchmark_name = metrics.benchmark_name
                data.benchmark_ytd_pct = metrics.benchmark_return
                data.alpha_ytd = data.nav_ytd_pct - data.benchmark_ytd_pct
                data.beta = metrics.beta
                if metrics.tracking_error > 0:
                    data.information_ratio = data.alpha_ytd / metrics.tracking_error

                # Benchmark history for chart
                start_date = f"{year}-01-01"
                end_date = datetime.now().strftime('%Y-%m-%d')
                benchmark_data, _ = self.benchmark_service.get_benchmark_history(
                    'CACMS', start_date, end_date, normalize=False
                )
                data.benchmark_history = benchmark_data
            except Exception as e:
                log.error(f"Error getting benchmark data: {e}")

        # Get portfolio data
        if self.get_portfolio:
            try:
                df, err = self.get_portfolio()
                if df is not None and not df.empty:
                    data.num_positions = len(df)

                    # Calculate value from qty * price
                    if 'qty' in df.columns and 'price_eur' in df.columns:
                        df['_value'] = df['qty'].fillna(0) * df['price_eur'].fillna(0)
                    else:
                        df['_value'] = 0

                    if 'qty' in df.columns and 'avg_cost_eur' in df.columns:
                        df['_cost'] = df['qty'].fillna(0) * df['avg_cost_eur'].fillna(0)
                    else:
                        df['_cost'] = 0

                    data.total_value = float(df['_value'].sum())
                    data.total_cost = float(df['_cost'].sum())

                    # Build positions list with Higgons metrics
                    positions = []
                    for _, row in df.iterrows():
                        value = float(row.get('_value', 0) or 0)
                        cost = float(row.get('_cost', 0) or 0)
                        weight = (value / data.total_value * 100) if data.total_value > 0 else 0
                        pnl_pct = ((value / cost) - 1) * 100 if cost > 0 else 0

                        sector = row.get('sector', '')
                        if not sector or (isinstance(sector, float) and np.isnan(sector)):
                            sector = 'Autres'

                        # Get PE - try multiple column names
                        pe = None
                        for col in ['pe', 'pe_ttm', 'trailing_pe', 'trailingPE']:
                            if col in df.columns:
                                val = row.get(col)
                                if val is not None and not (isinstance(val, float) and np.isnan(val)):
                                    pe = float(val)
                                    break

                        # Get ROE - try multiple column names (convert from decimal to %)
                        roe = None
                        for col in ['roe', 'roe_ttm', 'returnOnEquity']:
                            if col in df.columns:
                                val = row.get(col)
                                if val is not None and not (isinstance(val, float) and np.isnan(val)):
                                    roe = float(val)
                                    # Convert from decimal to percentage if needed
                                    if -1 < roe < 1:
                                        roe = roe * 100
                                    break

                        # Calculate gearing from debt/equity if not available
                        gearing = None
                        if 'gearing' in df.columns:
                            val = row.get('gearing')
                            if val is not None and not (isinstance(val, float) and np.isnan(val)):
                                gearing = float(val)
                        elif 'debt_to_equity' in df.columns:
                            val = row.get('debt_to_equity')
                            if val is not None and not (isinstance(val, float) and np.isnan(val)):
                                gearing = float(val) * 100
                        elif 'total_debt' in df.columns and 'total_equity' in df.columns:
                            debt = row.get('total_debt', 0) or 0
                            equity = row.get('total_equity', 0) or 0
                            if equity > 0:
                                gearing = (debt / equity) * 100

                        # Get momentum (convert from decimal to %)
                        mom_6m = None
                        for col in ['mom_6m', 'momentum_6m', 'perf_6m']:
                            if col in df.columns:
                                val = row.get(col)
                                if val is not None and not (isinstance(val, float) and np.isnan(val)):
                                    mom_6m = float(val)
                                    if -1 < mom_6m < 1:
                                        mom_6m = mom_6m * 100
                                    break

                        mom_12m = None
                        for col in ['mom_12m', 'momentum_12m', 'perf_12m']:
                            if col in df.columns:
                                val = row.get(col)
                                if val is not None and not (isinstance(val, float) and np.isnan(val)):
                                    mom_12m = float(val)
                                    if -1 < mom_12m < 1:
                                        mom_12m = mom_12m * 100
                                    break

                        # Use mom_12m as fallback for mom_6m if not available
                        mom_for_score = mom_6m if mom_6m is not None else mom_12m

                        pos = {
                            'ticker': str(row.get('ticker', '')),
                            'name': str(row.get('name', ''))[:25],
                            'sector': sector,
                            'weight': round(weight, 1),
                            'pnl_pct': round(pnl_pct, 1),
                            'value': round(value, 0),
                            'pe': pe,
                            'roe': roe,
                            'gearing': gearing,
                            'mom_6m': mom_for_score,  # Display the available momentum
                            'mom_12m': mom_12m,
                        }
                        pos['higgons_score'] = calculate_higgons_score(
                            pos['pe'], pos['roe'], pos['gearing'], mom_for_score, pos['mom_12m']
                        )
                        positions.append(pos)

                    # Sort by weight
                    positions.sort(key=lambda x: x['weight'], reverse=True)
                    data.positions = positions

                    # Sector allocation
                    sectors = {}
                    for pos in positions:
                        sector = pos.get('sector', 'Autres')
                        if not sector:
                            sector = 'Autres'
                        if sector not in sectors:
                            sectors[sector] = 0
                        sectors[sector] += pos['weight']

                    # Filter out empty sectors and ensure valid data
                    data.sector_allocation = [
                        {'name': k if k else 'Autres', 'weight': round(v, 1)}
                        for k, v in sorted(sectors.items(), key=lambda x: x[1], reverse=True)
                        if v > 0
                    ]

                    # If no sectors, provide default
                    if not data.sector_allocation:
                        data.sector_allocation = [{'name': 'Portefeuille', 'weight': 100}]

                    # Geographic allocation from country data
                    countries = {}
                    for _, row in df.iterrows():
                        country = row.get('country', 'France')
                        if not country or (isinstance(country, float) and np.isnan(country)):
                            country = 'France'
                        value = float(row.get('_value', 0) or 0)
                        weight = (value / data.total_value * 100) if data.total_value > 0 else 0
                        if country not in countries:
                            countries[country] = 0
                        countries[country] += weight

                    if countries:
                        data.geo_allocation = [
                            {'name': k, 'weight': round(v, 1)}
                            for k, v in sorted(countries.items(), key=lambda x: x[1], reverse=True)
                            if v > 0
                        ]
                    else:
                        data.geo_allocation = [
                            {'name': 'France', 'weight': 100}
                        ]

            except Exception as e:
                log.error(f"Error loading portfolio: {e}")
                import traceback
                traceback.print_exc()

        # Get realized P&L from position manager
        if self.position_manager:
            try:
                summary = self.position_manager.get_all_positions()
                if summary.closed_positions:
                    data.realized_pnl = sum(p.realized_pnl for p in summary.closed_positions)
            except Exception as e:
                log.error(f"Error getting position manager data: {e}")

        return data

    def _add_header(self, c, doc, page_num: int, total_pages: int, title: str = None):
        """Add header to each page"""
        width, height = A4
        c.saveState()

        # Background
        c.setFillColor(Colors.to_reportlab(Colors.BG_DARK))
        c.rect(0, height - 50, width, 50, fill=True, stroke=False)

        # Logo - try to load SVG from static/logos/
        logo_drawn = False
        if SVGLIB_AVAILABLE:
            # Try to find logo file relative to this module
            module_dir = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
            logo_path = os.path.join(module_dir, 'static', 'logos', 'olyos-icon-dark.svg')

            if os.path.exists(logo_path):
                try:
                    drawing = svg2rlg(logo_path)
                    if drawing:
                        # Scale logo to fit header (35x35 pixels)
                        scale = 35 / max(drawing.width, drawing.height)
                        drawing.width *= scale
                        drawing.height *= scale
                        drawing.scale(scale, scale)

                        # Draw at position
                        renderPDF.draw(drawing, c, 15, height - 45)
                        logo_drawn = True
                except Exception as e:
                    log.warning(f"Could not load SVG logo: {e}")

        # Fallback: draw simple constellation if SVG failed
        if not logo_drawn:
            base_x, base_y = 32, height - 25
            c.setFillColor(Colors.to_reportlab(Colors.GOLD))
            c.circle(base_x, base_y, 4, fill=True, stroke=False)
            for dx, dy in [(-8, 6), (8, 8), (12, -2), (6, -10), (-6, -8), (-10, 0)]:
                c.circle(base_x + dx, base_y + dy, 2.5, fill=True, stroke=False)

        # Title
        c.setFillColor(Colors.to_reportlab(Colors.GOLD))
        c.setFont('Helvetica-Bold', 14)
        c.drawString(55, height - 30, 'OLYOS CAPITAL')

        if title:
            c.setFillColor(Colors.to_reportlab(Colors.TEXT_SECONDARY))
            c.setFont('Helvetica', 10)
            c.drawString(55, height - 42, title)

        # Date
        c.setFillColor(Colors.to_reportlab(Colors.TEXT_DIM))
        c.setFont('Helvetica', 9)
        date_str = datetime.now().strftime('%d %B %Y')
        c.drawRightString(width - 20, height - 30, date_str)

        # Separator line
        c.setStrokeColor(Colors.to_reportlab(Colors.GOLD))
        c.setLineWidth(1)
        c.line(20, height - 52, width - 20, height - 52)

        c.restoreState()

    def _add_footer(self, canvas, doc, page_num: int, total_pages: int):
        """Add footer to each page"""
        width, height = A4
        canvas.saveState()

        # Background
        canvas.setFillColor(Colors.to_reportlab(Colors.BG_DARK))
        canvas.rect(0, 0, width, 30, fill=True, stroke=False)

        # Separator line
        canvas.setStrokeColor(Colors.to_reportlab(Colors.BORDER))
        canvas.line(20, 32, width - 20, 32)

        # Contact info
        canvas.setFillColor(Colors.to_reportlab(Colors.TEXT_DIM))
        canvas.setFont('Helvetica', 7)
        canvas.drawString(20, 12, 'OLYOS CAPITAL | contact@olyos.capital')

        # Page number
        canvas.drawRightString(width - 20, 12, f'{page_num} / {total_pages}')

        canvas.restoreState()

    def generate_report(self, month: int = None, year: int = None) -> Tuple[bytes, str]:
        """Generate 3-page PDF monthly report"""
        now = datetime.now()
        if month is None:
            month = now.month
        if year is None:
            year = now.year

        log.info(f"Generating Bloomberg-style report for {MONTH_NAMES_FR[month-1]} {year}")

        # Gather data
        data = self._gather_report_data(month, year)

        # Create PDF buffer
        buffer = io.BytesIO()

        # Build PDF manually for more control
        # Note: Each _draw_page* method draws its own background first
        c = canvas.Canvas(buffer, pagesize=A4)
        width, height = A4

        # ==================== PAGE 1: DASHBOARD ====================
        self._draw_page1(c, data, width, height)
        c.showPage()

        # ==================== PAGE 2: PORTFOLIO COMPOSITION ====================
        self._draw_page2(c, data, width, height)
        c.showPage()

        # ==================== PAGE 3: ALLOCATIONS & METHODOLOGY ====================
        self._draw_page3(c, data, width, height)

        c.save()

        # Get PDF bytes
        pdf_bytes = buffer.getvalue()
        buffer.close()

        # Save to file
        filename = f"report_{year}_{month:02d}.pdf"
        filepath = os.path.join(self.reports_dir, filename)
        with open(filepath, 'wb') as f:
            f.write(pdf_bytes)

        log.info(f"Report saved to {filepath} ({len(pdf_bytes)} bytes)")

        return pdf_bytes, filename

    def _draw_page1(self, c, data: ReportData, width: float, height: float):
        """Draw Page 1: Dashboard"""
        # Background
        c.setFillColor(Colors.to_reportlab(Colors.BG_DARK))
        c.rect(0, 0, width, height, fill=True, stroke=False)

        # Header
        self._add_header(c, None, 1, 3, f"Rapport Mensuel — {MONTH_NAMES_FR[data.month-1]} {data.year}")

        y = height - 80

        # ── KPI CARDS ──
        kpi_data = [
            ('NAV', f"€{data.nav_current:,.0f}", f"{data.nav_mtd_pct:+.1f}% MTD", Colors.GOLD),
            ('YTD', f"{data.nav_ytd_pct:+.1f}%", f"vs {data.benchmark_ytd_pct:+.1f}% bench", Colors.GREEN if data.nav_ytd_pct > 0 else Colors.RED),
            ('Depuis Création', f"{data.nav_inception_pct:+.1f}%", f"Depuis {data.inception_date[:4]}", Colors.GREEN if data.nav_inception_pct > 0 else Colors.RED),
            ('Alpha YTD', f"{data.alpha_ytd:+.1f}%", f"{data.num_positions} positions", Colors.GREEN if data.alpha_ytd > 0 else Colors.RED),
        ]

        card_width = (width - 60) / 4
        card_height = 60

        for i, (label, value, sub, color) in enumerate(kpi_data):
            x = 20 + i * (card_width + 10)

            # Card background
            c.setFillColor(Colors.to_reportlab(Colors.BG_CARD))
            c.setStrokeColor(Colors.to_reportlab(Colors.BORDER))
            c.roundRect(x, y - card_height, card_width, card_height, 5, fill=True, stroke=True)

            # Label
            c.setFillColor(Colors.to_reportlab(Colors.TEXT_DIM))
            c.setFont('Helvetica', 8)
            c.drawString(x + 10, y - 15, label)

            # Value
            c.setFillColor(Colors.to_reportlab(color))
            c.setFont('Helvetica-Bold', 18)
            c.drawString(x + 10, y - 38, value)

            # Sub-label
            c.setFillColor(Colors.to_reportlab(Colors.TEXT_MUTED))
            c.setFont('Helvetica', 7)
            c.drawString(x + 10, y - 52, sub)

        y -= card_height + 25

        # ── PERFORMANCE CHART ──
        c.setFillColor(Colors.to_reportlab(Colors.GOLD))
        c.setFont('Helvetica-Bold', 10)
        c.drawString(20, y, 'PERFORMANCE CUMULÉE')
        y -= 10

        try:
            chart_buf = create_performance_chart(data.nav_history, data.benchmark_history)
            from reportlab.lib.utils import ImageReader
            img = ImageReader(chart_buf)
            c.drawImage(img, 20, y - 160, width=width - 40, height=150, mask='auto')
            y -= 170
        except Exception as e:
            log.error(f"Error creating performance chart: {e}")
            y -= 20

        # ── MONTHLY HEATMAP ──
        c.setFillColor(Colors.to_reportlab(Colors.GOLD))
        c.setFont('Helvetica-Bold', 10)
        c.drawString(20, y, 'RENDEMENTS MENSUELS')
        y -= 10

        try:
            heatmap_buf = create_monthly_heatmap(data.monthly_returns)
            from reportlab.lib.utils import ImageReader
            img = ImageReader(heatmap_buf)
            c.drawImage(img, 20, y - 120, width=width - 40, height=110, mask='auto')
            y -= 130
        except Exception as e:
            log.error(f"Error creating heatmap: {e}")
            y -= 20

        # ── RISK METRICS BAR ──
        c.setFillColor(Colors.to_reportlab(Colors.GOLD))
        c.setFont('Helvetica-Bold', 10)
        c.drawString(20, y, 'MÉTRIQUES DE RISQUE')
        y -= 15

        risk_metrics = [
            ('Sharpe', f"{data.sharpe_ratio:.2f}"),
            ('Sortino', f"{data.sortino_ratio:.2f}"),
            ('Max DD', f"{data.max_drawdown:.1f}%"),
            ('Volatilité', f"{data.volatility:.1f}%"),
            ('Beta', f"{data.beta:.2f}"),
            ('Win Rate', f"{data.win_rate:.0f}%"),
            ('VaR 95%', f"{data.var_95:.1f}%"),
            ('Info Ratio', f"{data.information_ratio:.2f}"),
        ]

        metric_width = (width - 60) / 8
        for i, (label, value) in enumerate(risk_metrics):
            x = 20 + i * metric_width

            # Background
            c.setFillColor(Colors.to_reportlab(Colors.BG_CARD))
            c.setStrokeColor(Colors.to_reportlab(Colors.BORDER))
            c.roundRect(x, y - 45, metric_width - 5, 45, 3, fill=True, stroke=True)

            # Label
            c.setFillColor(Colors.to_reportlab(Colors.TEXT_DIM))
            c.setFont('Helvetica', 6)
            c.drawCentredString(x + metric_width/2 - 2, y - 12, label)

            # Value
            c.setFillColor(Colors.to_reportlab(Colors.TEXT_PRIMARY))
            c.setFont('Helvetica-Bold', 11)
            c.drawCentredString(x + metric_width/2 - 2, y - 32, value)

        # Footer
        self._add_footer(c, None, 1, 3)

    def _draw_page2(self, c, data: ReportData, width: float, height: float):
        """Draw Page 2: Portfolio Composition with Higgons Metrics"""
        # Background
        c.setFillColor(Colors.to_reportlab(Colors.BG_DARK))
        c.rect(0, 0, width, height, fill=True, stroke=False)

        # Header
        self._add_header(c, None, 2, 3, "Composition du Portefeuille")

        y = height - 80

        # ── POSITIONS TABLE ──
        c.setFillColor(Colors.to_reportlab(Colors.GOLD))
        c.setFont('Helvetica-Bold', 10)
        c.drawString(20, y, 'POSITIONS & MÉTRIQUES HIGGONS')
        y -= 20

        # Table headers
        headers = ['Ticker', 'Nom', 'Poids', 'P&L', 'Valeur', 'P/E', 'ROE', 'Gear.', 'Mom6M', 'Score']
        col_widths = [50, 100, 40, 45, 60, 35, 35, 35, 45, 35]
        col_x = [20]
        for w in col_widths[:-1]:
            col_x.append(col_x[-1] + w)

        # Header row
        c.setFillColor(Colors.to_reportlab(Colors.BG_HEADER))
        c.rect(20, y - 18, width - 40, 18, fill=True, stroke=False)

        c.setFillColor(Colors.to_reportlab(Colors.GOLD))
        c.setFont('Helvetica-Bold', 7)
        for i, header in enumerate(headers):
            c.drawString(col_x[i] + 3, y - 13, header)

        y -= 20

        # Position rows
        row_height = 16
        if not data.positions:
            c.setFillColor(Colors.to_reportlab(Colors.TEXT_DIM))
            c.setFont('Helvetica', 9)
            c.drawString(20, y - 20, "Aucune position dans le portefeuille")

        for idx, pos in enumerate(data.positions[:15]):  # Max 15 positions
            # Alternating background
            bg_color = Colors.BG_CARD if idx % 2 == 0 else Colors.BG_CARD_ALT
            c.setFillColor(Colors.to_reportlab(bg_color))
            c.rect(20, y - row_height + 2, width - 40, row_height, fill=True, stroke=False)

            c.setFont('Helvetica', 7)

            # Ticker (gold)
            c.setFillColor(Colors.to_reportlab(Colors.GOLD))
            c.drawString(col_x[0] + 3, y - 10, pos['ticker'][:8])

            # Name
            c.setFillColor(Colors.to_reportlab(Colors.TEXT_PRIMARY))
            c.drawString(col_x[1] + 3, y - 10, pos['name'][:18])

            # Weight
            c.drawString(col_x[2] + 3, y - 10, f"{pos['weight']:.1f}%")

            # P&L
            pnl_color = Colors.GREEN if pos['pnl_pct'] >= 0 else Colors.RED
            c.setFillColor(Colors.to_reportlab(pnl_color))
            c.drawString(col_x[3] + 3, y - 10, f"{pos['pnl_pct']:+.1f}%")

            # Value
            c.setFillColor(Colors.to_reportlab(Colors.TEXT_PRIMARY))
            c.drawString(col_x[4] + 3, y - 10, f"€{pos['value']:,.0f}")

            # P/E (color coded)
            pe = pos.get('pe')
            if pe is not None:
                c.setFillColor(Colors.to_reportlab(get_metric_color('pe', pe)))
                c.drawString(col_x[5] + 3, y - 10, f"{pe:.1f}")
            else:
                c.setFillColor(Colors.to_reportlab(Colors.TEXT_DIM))
                c.drawString(col_x[5] + 3, y - 10, "N/A")

            # ROE (color coded)
            roe = pos.get('roe')
            if roe is not None:
                c.setFillColor(Colors.to_reportlab(get_metric_color('roe', roe)))
                c.drawString(col_x[6] + 3, y - 10, f"{roe:.0f}%")
            else:
                c.setFillColor(Colors.to_reportlab(Colors.TEXT_DIM))
                c.drawString(col_x[6] + 3, y - 10, "N/A")

            # Gearing (color coded)
            gearing = pos.get('gearing')
            if gearing is not None:
                c.setFillColor(Colors.to_reportlab(get_metric_color('gearing', gearing)))
                c.drawString(col_x[7] + 3, y - 10, f"{gearing:.0f}%")
            else:
                c.setFillColor(Colors.to_reportlab(Colors.TEXT_DIM))
                c.drawString(col_x[7] + 3, y - 10, "N/A")

            # Momentum 6M (color coded)
            mom = pos.get('mom_6m')
            if mom is not None:
                c.setFillColor(Colors.to_reportlab(get_metric_color('momentum', mom)))
                c.drawString(col_x[8] + 3, y - 10, f"{mom:+.1f}%")
            else:
                c.setFillColor(Colors.to_reportlab(Colors.TEXT_DIM))
                c.drawString(col_x[8] + 3, y - 10, "N/A")

            # Higgons Score
            score = pos.get('higgons_score', 0)
            score_color = Colors.GREEN if score >= 7 else Colors.GOLD if score >= 4 else Colors.RED
            c.setFillColor(Colors.to_reportlab(score_color))
            c.setFont('Helvetica-Bold', 8)
            c.drawString(col_x[9] + 3, y - 10, f"{score}/10")

            y -= row_height

        y -= 20

        # ── LEGEND ──
        c.setFillColor(Colors.to_reportlab(Colors.TEXT_SECONDARY))
        c.setFont('Helvetica', 7)
        c.drawString(20, y, "Barème Higgons: P/E < 8 → 3pts | ROE > 15% → 3pts | Gearing < 20% → 2pts | Mom 6M > 20% → 2pts")
        y -= 12
        c.drawString(20, y, "Couleurs: Vert = Excellent | Or = Bon | Rouge = Attention")

        # Footer
        self._add_footer(c, None, 2, 3)

    def _draw_page3(self, c, data: ReportData, width: float, height: float):
        """Draw Page 3: Allocations & Methodology"""
        # Background
        c.setFillColor(Colors.to_reportlab(Colors.BG_DARK))
        c.rect(0, 0, width, height, fill=True, stroke=False)

        # Header
        self._add_header(c, None, 3, 3, "Allocations & Méthodologie")

        y = height - 80

        # ── ALLOCATION CHARTS ──
        c.setFillColor(Colors.to_reportlab(Colors.GOLD))
        c.setFont('Helvetica-Bold', 10)
        c.drawString(20, y, 'ALLOCATION SECTORIELLE')
        c.drawString(width/2 + 10, y, 'ALLOCATION GÉOGRAPHIQUE')
        y -= 10

        try:
            # Sector donut
            sector_buf = create_sector_donut(data.sector_allocation)
            from reportlab.lib.utils import ImageReader
            img = ImageReader(sector_buf)
            c.drawImage(img, 20, y - 160, width=width/2 - 30, height=150, mask='auto')

            # Geographic bars
            geo_buf = create_geo_bars(data.geo_allocation)
            img = ImageReader(geo_buf)
            c.drawImage(img, width/2 + 10, y - 140, width=width/2 - 30, height=120, mask='auto')
        except Exception as e:
            log.error(f"Error creating allocation charts: {e}")

        y -= 180

        # ── TOP/BOTTOM PERFORMERS ──
        c.setFillColor(Colors.to_reportlab(Colors.GOLD))
        c.setFont('Helvetica-Bold', 10)
        c.drawString(20, y, 'TOP 5 PERFORMERS')
        c.drawString(width/2 + 10, y, 'BOTTOM 5 PERFORMERS')
        y -= 15

        if data.positions:
            # Sort positions by P&L
            sorted_pos = sorted(data.positions, key=lambda x: x.get('pnl_pct', 0), reverse=True)
            top5 = sorted_pos[:5]
            bottom5 = sorted_pos[-5:][::-1] if len(sorted_pos) >= 5 else sorted_pos[::-1]

            c.setFont('Helvetica', 8)
            for i, pos in enumerate(top5):
                c.setFillColor(Colors.to_reportlab(Colors.GREEN))
                c.drawString(25, y - i*14, f"{pos['ticker']}")
                c.setFillColor(Colors.to_reportlab(Colors.TEXT_PRIMARY))
                c.drawString(80, y - i*14, f"{pos['name'][:15]}")
                c.setFillColor(Colors.to_reportlab(Colors.GREEN))
                c.drawString(180, y - i*14, f"{pos['pnl_pct']:+.1f}%")

            for i, pos in enumerate(bottom5):
                c.setFillColor(Colors.to_reportlab(Colors.RED))
                c.drawString(width/2 + 15, y - i*14, f"{pos['ticker']}")
                c.setFillColor(Colors.to_reportlab(Colors.TEXT_PRIMARY))
                c.drawString(width/2 + 70, y - i*14, f"{pos['name'][:15]}")
                c.setFillColor(Colors.to_reportlab(Colors.RED))
                c.drawString(width/2 + 170, y - i*14, f"{pos['pnl_pct']:+.1f}%")
        else:
            c.setFont('Helvetica', 8)
            c.setFillColor(Colors.to_reportlab(Colors.TEXT_DIM))
            c.drawString(25, y, "Aucune position")

        y -= 90

        # ── METHODOLOGY ──
        c.setFillColor(Colors.to_reportlab(Colors.GOLD))
        c.setFont('Helvetica-Bold', 10)
        c.drawString(20, y, 'MÉTHODOLOGIE WILLIAM HIGGONS')
        y -= 20

        criteria = [
            ("P/E < 8", "Valorisation attractive — acheter des entreprises sous-évaluées"),
            ("ROE > 12%", "Rentabilité élevée — qualité du modèle économique"),
            ("Croiss. BPA > 5%", "Dynamique bénéficiaire — entreprise en croissance"),
            ("Gearing < 50%", "Dette maîtrisée — solidité financière"),
            ("Momentum haussier", "Tendance positive — timing de marché"),
        ]

        c.setFont('Helvetica', 8)
        for criterion, description in criteria:
            c.setFillColor(Colors.to_reportlab(Colors.GOLD))
            c.drawString(25, y, "•")
            c.setFont('Helvetica-Bold', 8)
            c.drawString(35, y, criterion)
            c.setFillColor(Colors.to_reportlab(Colors.TEXT_SECONDARY))
            c.setFont('Helvetica', 8)
            c.drawString(130, y, description)
            y -= 14

        y -= 20

        # ── DISCLAIMER ──
        c.setFillColor(Colors.to_reportlab('#0D1117'))
        c.rect(15, 40, width - 30, y - 40, fill=True, stroke=False)

        c.setFillColor(Colors.to_reportlab(Colors.TEXT_MUTED))
        c.setFont('Helvetica', 6)

        disclaimer_lines = [
            "AVERTISSEMENT : Ce document est fourni à titre informatif uniquement et ne constitue pas un conseil en investissement.",
            "Les performances passées ne préjugent pas des performances futures. Tout investissement comporte des risques de perte en capital.",
            "Avant toute décision d'investissement, consultez un conseiller financier professionnel.",
            f"Document généré automatiquement le {data.generation_date}. © Olyos Capital {data.year}."
        ]

        for i, line in enumerate(disclaimer_lines):
            c.drawString(25, y - 10 - i*10, line)

        # Footer
        self._add_footer(c, None, 3, 3)

    def get_latest_report(self) -> Tuple[Optional[bytes], Optional[str]]:
        """Get the most recently generated report"""
        if not os.path.exists(self.reports_dir):
            return None, None

        pdfs = [f for f in os.listdir(self.reports_dir) if f.endswith('.pdf') and f.startswith('report_')]
        if not pdfs:
            return None, None

        pdfs.sort(reverse=True)
        latest = pdfs[0]

        filepath = os.path.join(self.reports_dir, latest)
        with open(filepath, 'rb') as f:
            return f.read(), latest

    def list_reports(self) -> List[Dict]:
        """List all available reports"""
        if not os.path.exists(self.reports_dir):
            return []

        reports = []
        for f in os.listdir(self.reports_dir):
            if f.endswith('.pdf') and f.startswith('report_'):
                filepath = os.path.join(self.reports_dir, f)
                stat = os.stat(filepath)

                parts = f.replace('.pdf', '').split('_')
                if len(parts) >= 3:
                    year = int(parts[1])
                    month = int(parts[2])
                    month_name = MONTH_NAMES_FR[month - 1]
                else:
                    year, month = 0, 0
                    month_name = 'Unknown'

                reports.append({
                    'filename': f,
                    'year': year,
                    'month': month,
                    'month_name': month_name,
                    'size': stat.st_size,
                    'created': datetime.fromtimestamp(stat.st_mtime).isoformat()
                })

        reports.sort(key=lambda x: (x['year'], x['month']), reverse=True)
        return reports


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

def create_pdf_report_service(
    reports_dir: str,
    nav_history_file: str,
    portfolio_func=None,
    benchmark_service=None,
    position_manager=None
) -> PDFReportService:
    """Factory function to create PDF report service"""
    return PDFReportService(
        reports_dir=reports_dir,
        nav_history_file=nav_history_file,
        portfolio_func=portfolio_func,
        benchmark_service=benchmark_service,
        position_manager=position_manager
    )

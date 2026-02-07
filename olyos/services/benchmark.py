"""
OLYOS CAPITAL - Benchmark Service
==================================
Performance comparison against market indices.

Supported Benchmarks:
- CAC 40: CAC.INDX
- CAC Mid & Small: CACMS.INDX
- CAC Small: CACS.INDX
- Euro Stoxx 50: STOXX50E.INDX
- MSCI Europe Small Cap: MSCIESM.INDX
"""

import json
import os
import math
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

from olyos.logger import get_logger

log = get_logger('benchmark')


# Benchmark definitions
BENCHMARKS = {
    'CAC40': {
        'ticker': 'CAC.INDX',
        'name': 'CAC 40',
        'color': '#0066cc',
        'yahoo': '^FCHI'
    },
    'CACMS': {
        'ticker': 'CACMS.INDX',
        'name': 'CAC Mid & Small',
        'color': '#9933ff',
        'yahoo': '^CACMS'
    },
    'CACS': {
        'ticker': 'CACS.INDX',
        'name': 'CAC Small',
        'color': '#00cc66',
        'yahoo': None
    },
    'STOXX50E': {
        'ticker': 'STOXX50E.INDX',
        'name': 'Euro Stoxx 50',
        'color': '#cc6600',
        'yahoo': '^STOXX50E'
    },
    'MSCIESM': {
        'ticker': 'MSCIESM.INDX',
        'name': 'MSCI Europe Small',
        'color': '#cc0066',
        'yahoo': None
    }
}

# Risk-free rate (EUR, as of 2024)
RISK_FREE_RATE = 0.035  # 3.5%


@dataclass
class PerformanceMetrics:
    """Portfolio performance metrics vs benchmark"""
    # Returns
    portfolio_return: float = 0.0
    benchmark_return: float = 0.0
    alpha: float = 0.0

    # Risk metrics
    beta: float = 0.0
    sharpe_ratio: float = 0.0
    tracking_error: float = 0.0
    information_ratio: float = 0.0

    # Drawdown
    portfolio_max_dd: float = 0.0
    benchmark_max_dd: float = 0.0

    # Volatility
    portfolio_volatility: float = 0.0
    benchmark_volatility: float = 0.0

    # Period info
    period: str = ""
    start_date: str = ""
    end_date: str = ""
    benchmark_name: str = ""

    def to_dict(self) -> Dict:
        return {
            'portfolio_return': round(self.portfolio_return, 2),
            'benchmark_return': round(self.benchmark_return, 2),
            'alpha': round(self.alpha, 2),
            'beta': round(self.beta, 2),
            'sharpe_ratio': round(self.sharpe_ratio, 2),
            'tracking_error': round(self.tracking_error, 2),
            'information_ratio': round(self.information_ratio, 2),
            'portfolio_max_dd': round(self.portfolio_max_dd, 2),
            'benchmark_max_dd': round(self.benchmark_max_dd, 2),
            'portfolio_volatility': round(self.portfolio_volatility, 2),
            'benchmark_volatility': round(self.benchmark_volatility, 2),
            'period': self.period,
            'start_date': self.start_date,
            'end_date': self.end_date,
            'benchmark_name': self.benchmark_name
        }


class BenchmarkService:
    """Service for benchmark comparison and performance analytics"""

    def __init__(self, cache_dir: str, nav_history_file: str, get_prices_func=None):
        """
        Initialize benchmark service.

        Args:
            cache_dir: Directory for benchmark cache files
            nav_history_file: Path to portfolio NAV history JSON
            get_prices_func: Function to fetch prices (eod_get_historical_prices)
        """
        self.cache_dir = cache_dir
        self.nav_history_file = nav_history_file
        self.get_prices = get_prices_func

        # Ensure cache directory exists
        os.makedirs(cache_dir, exist_ok=True)

    def get_benchmark_history(
        self,
        benchmark_key: str,
        start_date: str,
        end_date: str,
        normalize: bool = True
    ) -> Tuple[List[Dict], Optional[str]]:
        """
        Get benchmark price history.

        Args:
            benchmark_key: Key from BENCHMARKS dict (e.g., 'CACMS')
            start_date: Start date YYYY-MM-DD
            end_date: End date YYYY-MM-DD
            normalize: If True, normalize to base 100

        Returns:
            Tuple of (price_list, error_message)
        """
        if benchmark_key not in BENCHMARKS:
            return [], f"Unknown benchmark: {benchmark_key}"

        benchmark = BENCHMARKS[benchmark_key]
        ticker = benchmark['ticker']

        # Check cache first
        cache_file = os.path.join(
            self.cache_dir,
            f"benchmark_{benchmark_key}_{start_date}_{end_date}.json"
        )

        if os.path.exists(cache_file):
            try:
                with open(cache_file, 'r', encoding='utf-8') as f:
                    cache_data = json.load(f)

                # Check if cache is fresh (< 1 day old)
                cache_date = datetime.strptime(
                    cache_data.get('_cache_date', '2000-01-01'),
                    '%Y-%m-%d'
                )
                if (datetime.now() - cache_date).days < 1:
                    log.info(f"Using cached benchmark data for {benchmark_key}")
                    prices = cache_data.get('prices', [])
                    if normalize:
                        prices = self._normalize_series(prices)
                    return prices, None
            except Exception as e:
                log.warning(f"Cache read error: {e}")

        # Fetch from API
        if not self.get_prices:
            return [], "No price fetch function configured"

        log.info(f"Fetching benchmark {benchmark_key} from API...")
        prices, err = self.get_prices(ticker, start_date, end_date, use_cache=True)

        if err or not prices:
            log.error(f"Error fetching benchmark {benchmark_key}: {err}")
            return [], err or "No data returned"

        # Save to cache
        try:
            cache_data = {
                '_cache_date': datetime.now().strftime('%Y-%m-%d'),
                'benchmark': benchmark_key,
                'ticker': ticker,
                'prices': prices
            }
            with open(cache_file, 'w', encoding='utf-8') as f:
                json.dump(cache_data, f)
            log.info(f"Cached benchmark data for {benchmark_key}")
        except Exception as e:
            log.warning(f"Cache write error: {e}")

        if normalize:
            prices = self._normalize_series(prices)

        return prices, None

    def _normalize_series(self, prices: List[Dict], base: float = 100.0) -> List[Dict]:
        """Normalize price series to base 100 at start"""
        if not prices:
            return []

        # Find first valid close price
        first_close = None
        for p in prices:
            if p.get('close'):
                first_close = float(p['close'])
                break

        if not first_close:
            return prices

        normalized = []
        for p in prices:
            close = p.get('close')
            if close:
                normalized.append({
                    'date': p.get('date'),
                    'close': round((float(close) / first_close) * base, 2),
                    'original_close': float(close)
                })

        return normalized

    def load_nav_history(self) -> List[Dict]:
        """Load portfolio NAV history"""
        if not os.path.exists(self.nav_history_file):
            return []

        try:
            with open(self.nav_history_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            log.error(f"Error loading NAV history: {e}")
            return []

    def get_nav_normalized(self, start_date: str = None, end_date: str = None) -> List[Dict]:
        """Get normalized NAV history (base 100)"""
        nav_history = self.load_nav_history()
        if not nav_history:
            return []

        # Filter by date range
        if start_date:
            nav_history = [n for n in nav_history if n.get('date', '') >= start_date]
        if end_date:
            nav_history = [n for n in nav_history if n.get('date', '') <= end_date]

        if not nav_history:
            return []

        # Normalize
        first_nav = nav_history[0].get('nav', 1)
        return [
            {
                'date': n.get('date'),
                'close': round((n.get('nav', first_nav) / first_nav) * 100, 2),
                'original_nav': n.get('nav')
            }
            for n in nav_history
        ]

    def calculate_metrics(
        self,
        benchmark_key: str,
        period: str = '1Y'
    ) -> PerformanceMetrics:
        """
        Calculate performance metrics vs benchmark.

        Args:
            benchmark_key: Benchmark to compare against
            period: Time period ('YTD', '1Y', '3Y', '5Y', 'MAX')

        Returns:
            PerformanceMetrics object
        """
        metrics = PerformanceMetrics()
        metrics.benchmark_name = BENCHMARKS.get(benchmark_key, {}).get('name', benchmark_key)
        metrics.period = period

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
        else:  # MAX
            start_date = datetime(2010, 1, 1)

        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')
        metrics.start_date = start_str
        metrics.end_date = end_str

        # Get portfolio NAV
        nav_data = self.get_nav_normalized(start_str, end_str)
        if len(nav_data) < 2:
            log.warning("Not enough NAV data for metrics calculation")
            return metrics

        # Get benchmark data
        benchmark_data, err = self.get_benchmark_history(benchmark_key, start_str, end_str)
        if err or len(benchmark_data) < 2:
            log.warning(f"Not enough benchmark data: {err}")
            return metrics

        # Align dates (use benchmark dates as reference)
        portfolio_by_date = {n['date']: n['close'] for n in nav_data}
        benchmark_by_date = {b['date']: b['close'] for b in benchmark_data}

        # Find common dates
        common_dates = sorted(set(portfolio_by_date.keys()) & set(benchmark_by_date.keys()))
        if len(common_dates) < 10:
            log.warning("Not enough common dates for metrics")
            return metrics

        # Build aligned series
        portfolio_series = [portfolio_by_date[d] for d in common_dates]
        benchmark_series = [benchmark_by_date[d] for d in common_dates]

        # Calculate returns
        metrics.portfolio_return = (portfolio_series[-1] / portfolio_series[0] - 1) * 100
        metrics.benchmark_return = (benchmark_series[-1] / benchmark_series[0] - 1) * 100
        metrics.alpha = metrics.portfolio_return - metrics.benchmark_return

        # Calculate daily returns for risk metrics
        portfolio_returns = self._calculate_returns(portfolio_series)
        benchmark_returns = self._calculate_returns(benchmark_series)

        if len(portfolio_returns) < 10:
            return metrics

        # Volatility (annualized)
        metrics.portfolio_volatility = self._std(portfolio_returns) * math.sqrt(252) * 100
        metrics.benchmark_volatility = self._std(benchmark_returns) * math.sqrt(252) * 100

        # Beta
        covariance = self._covariance(portfolio_returns, benchmark_returns)
        benchmark_variance = self._variance(benchmark_returns)
        if benchmark_variance > 0:
            metrics.beta = covariance / benchmark_variance

        # Sharpe Ratio
        avg_portfolio_return = self._mean(portfolio_returns) * 252  # Annualized
        if metrics.portfolio_volatility > 0:
            metrics.sharpe_ratio = (avg_portfolio_return - RISK_FREE_RATE) / (metrics.portfolio_volatility / 100)

        # Tracking Error and Information Ratio
        excess_returns = [p - b for p, b in zip(portfolio_returns, benchmark_returns)]
        metrics.tracking_error = self._std(excess_returns) * math.sqrt(252) * 100
        if metrics.tracking_error > 0:
            metrics.information_ratio = (metrics.alpha / 100) / (metrics.tracking_error / 100)

        # Max Drawdown
        metrics.portfolio_max_dd = self._max_drawdown(portfolio_series) * 100
        metrics.benchmark_max_dd = self._max_drawdown(benchmark_series) * 100

        log.info(f"Metrics calculated: Alpha={metrics.alpha:.2f}%, Beta={metrics.beta:.2f}, Sharpe={metrics.sharpe_ratio:.2f}")
        return metrics

    def _calculate_returns(self, prices: List[float]) -> List[float]:
        """Calculate daily returns from price series"""
        returns = []
        for i in range(1, len(prices)):
            if prices[i-1] > 0:
                returns.append((prices[i] / prices[i-1]) - 1)
        return returns

    def _mean(self, values: List[float]) -> float:
        """Calculate mean"""
        if not values:
            return 0
        return sum(values) / len(values)

    def _std(self, values: List[float]) -> float:
        """Calculate standard deviation"""
        if len(values) < 2:
            return 0
        mean = self._mean(values)
        variance = sum((x - mean) ** 2 for x in values) / (len(values) - 1)
        return math.sqrt(variance)

    def _variance(self, values: List[float]) -> float:
        """Calculate variance"""
        if len(values) < 2:
            return 0
        mean = self._mean(values)
        return sum((x - mean) ** 2 for x in values) / (len(values) - 1)

    def _covariance(self, x: List[float], y: List[float]) -> float:
        """Calculate covariance between two series"""
        if len(x) != len(y) or len(x) < 2:
            return 0
        mean_x = self._mean(x)
        mean_y = self._mean(y)
        return sum((xi - mean_x) * (yi - mean_y) for xi, yi in zip(x, y)) / (len(x) - 1)

    def _max_drawdown(self, prices: List[float]) -> float:
        """Calculate maximum drawdown"""
        if not prices:
            return 0

        peak = prices[0]
        max_dd = 0

        for price in prices:
            if price > peak:
                peak = price
            dd = (peak - price) / peak
            if dd > max_dd:
                max_dd = dd

        return max_dd

    def get_comparison_data(
        self,
        benchmark_key: str,
        period: str = '1Y'
    ) -> Dict[str, Any]:
        """
        Get complete comparison data for charting.

        Returns dict with:
        - portfolio: normalized NAV series
        - benchmark: normalized benchmark series
        - metrics: performance metrics
        - benchmark_info: name, color, etc.
        """
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

        start_str = start_date.strftime('%Y-%m-%d')
        end_str = end_date.strftime('%Y-%m-%d')

        # Get data
        portfolio_data = self.get_nav_normalized(start_str, end_str)
        benchmark_data, _ = self.get_benchmark_history(benchmark_key, start_str, end_str)
        metrics = self.calculate_metrics(benchmark_key, period)

        return {
            'portfolio': portfolio_data,
            'benchmark': benchmark_data,
            'metrics': metrics.to_dict(),
            'benchmark_info': BENCHMARKS.get(benchmark_key, {}),
            'period': period,
            'start_date': start_str,
            'end_date': end_str
        }

    @staticmethod
    def get_available_benchmarks() -> List[Dict]:
        """Get list of available benchmarks"""
        return [
            {'key': k, **v}
            for k, v in BENCHMARKS.items()
        ]


def create_benchmark_service(cache_dir: str, nav_history_file: str, get_prices_func=None) -> BenchmarkService:
    """Factory function to create benchmark service"""
    return BenchmarkService(cache_dir, nav_history_file, get_prices_func)

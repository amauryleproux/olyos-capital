"""
OLYOS CAPITAL - Dividends Service
==================================
Track dividend history, upcoming ex-dates, yields, and projected income.

Data Sources:
- EOD API: /api/div/{ticker}
- Yahoo Finance fallback
"""

import json
import os
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field

from olyos.logger import get_logger

log = get_logger('dividends')

# Cache validity in days
CACHE_VALIDITY_DAYS = 7


@dataclass
class Dividend:
    """Single dividend payment"""
    date: str  # Ex-dividend date YYYY-MM-DD
    amount: float
    currency: str = "EUR"
    payment_date: Optional[str] = None
    record_date: Optional[str] = None

    def to_dict(self) -> Dict:
        return {
            'date': self.date,
            'amount': self.amount,
            'currency': self.currency,
            'payment_date': self.payment_date,
            'record_date': self.record_date
        }


@dataclass
class DividendInfo:
    """Complete dividend information for a ticker"""
    ticker: str
    name: str = ""
    history: List[Dividend] = field(default_factory=list)
    annual_dividend: float = 0.0
    dividend_yield: float = 0.0
    payout_ratio: Optional[float] = None
    dividend_growth_5y: Optional[float] = None  # CAGR
    next_ex_date: Optional[str] = None
    next_amount: Optional[float] = None
    frequency: str = "annual"  # annual, semi-annual, quarterly
    last_updated: str = field(default_factory=lambda: datetime.now().isoformat())

    def to_dict(self) -> Dict:
        return {
            'ticker': self.ticker,
            'name': self.name,
            'history': [d.to_dict() for d in self.history],
            'annual_dividend': round(self.annual_dividend, 4),
            'dividend_yield': round(self.dividend_yield, 2),
            'payout_ratio': round(self.payout_ratio, 2) if self.payout_ratio else None,
            'dividend_growth_5y': round(self.dividend_growth_5y, 2) if self.dividend_growth_5y else None,
            'next_ex_date': self.next_ex_date,
            'next_amount': round(self.next_amount, 4) if self.next_amount else None,
            'frequency': self.frequency,
            'last_updated': self.last_updated
        }


class DividendsService:
    """Service for dividend tracking and projections"""

    def __init__(self, cache_file: str, get_dividends_func=None, get_fundamentals_func=None):
        """
        Initialize dividends service.

        Args:
            cache_file: Path to dividend cache JSON
            get_dividends_func: Function to fetch dividends from EOD API
            get_fundamentals_func: Function to fetch fundamentals (for payout ratio)
        """
        self.cache_file = cache_file
        self.get_dividends_api = get_dividends_func
        self.get_fundamentals = get_fundamentals_func
        self._cache: Dict[str, DividendInfo] = {}
        self._load_cache()

    def _load_cache(self):
        """Load dividend cache from file"""
        if not os.path.exists(self.cache_file):
            return

        try:
            with open(self.cache_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            for ticker, info in data.items():
                # Check if cache is still valid
                last_updated = datetime.fromisoformat(info.get('last_updated', '2000-01-01'))
                if (datetime.now() - last_updated).days < CACHE_VALIDITY_DAYS:
                    history = [Dividend(**d) for d in info.get('history', [])]
                    self._cache[ticker] = DividendInfo(
                        ticker=ticker,
                        name=info.get('name', ''),
                        history=history,
                        annual_dividend=info.get('annual_dividend', 0),
                        dividend_yield=info.get('dividend_yield', 0),
                        payout_ratio=info.get('payout_ratio'),
                        dividend_growth_5y=info.get('dividend_growth_5y'),
                        next_ex_date=info.get('next_ex_date'),
                        next_amount=info.get('next_amount'),
                        frequency=info.get('frequency', 'annual'),
                        last_updated=info.get('last_updated')
                    )

            log.info(f"Loaded {len(self._cache)} tickers from dividend cache")
        except Exception as e:
            log.error(f"Error loading dividend cache: {e}")

    def _save_cache(self):
        """Save dividend cache to file"""
        try:
            data = {ticker: info.to_dict() for ticker, info in self._cache.items()}
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            log.info(f"Saved {len(self._cache)} tickers to dividend cache")
        except Exception as e:
            log.error(f"Error saving dividend cache: {e}")

    def get_dividend_history(self, ticker: str, years: int = 5) -> DividendInfo:
        """
        Get dividend history for a ticker.

        Args:
            ticker: Stock ticker (e.g., 'TTE.PA')
            years: Number of years of history

        Returns:
            DividendInfo object
        """
        # Check cache first
        if ticker in self._cache:
            cached = self._cache[ticker]
            last_updated = datetime.fromisoformat(cached.last_updated)
            if (datetime.now() - last_updated).days < CACHE_VALIDITY_DAYS:
                log.info(f"Using cached dividend data for {ticker}")
                return cached

        # Fetch from API
        info = self._fetch_dividend_data(ticker, years)
        if info:
            self._cache[ticker] = info
            self._save_cache()
            return info

        # Return empty info if fetch failed
        return DividendInfo(ticker=ticker)

    def _fetch_dividend_data(self, ticker: str, years: int = 5) -> Optional[DividendInfo]:
        """Fetch dividend data from API"""
        if not self.get_dividends_api:
            log.warning("No dividend API function configured")
            return None

        try:
            end_date = datetime.now()
            start_date = end_date - timedelta(days=years * 365)

            # Fetch from EOD API
            dividends, err = self.get_dividends_api(
                ticker,
                start_date.strftime('%Y-%m-%d'),
                end_date.strftime('%Y-%m-%d')
            )

            if err:
                log.error(f"Error fetching dividends for {ticker}: {err}")
                return None

            if not dividends:
                log.info(f"No dividends found for {ticker}")
                return DividendInfo(ticker=ticker)

            # Convert to Dividend objects
            history = []
            for d in dividends:
                history.append(Dividend(
                    date=d.get('date', d.get('ex_date', '')),
                    amount=float(d.get('value', d.get('amount', 0))),
                    currency=d.get('currency', 'EUR'),
                    payment_date=d.get('paymentDate', d.get('payment_date')),
                    record_date=d.get('recordDate', d.get('record_date'))
                ))

            # Sort by date (most recent first)
            history.sort(key=lambda x: x.date, reverse=True)

            # Calculate metrics
            info = DividendInfo(ticker=ticker, history=history)
            self._calculate_metrics(info)

            return info

        except Exception as e:
            log.error(f"Error fetching dividend data for {ticker}: {e}")
            return None

    def _calculate_metrics(self, info: DividendInfo):
        """Calculate dividend metrics from history"""
        if not info.history:
            return

        # Determine frequency and annual dividend
        today = datetime.now()
        one_year_ago = today - timedelta(days=365)

        # Count dividends in last year
        recent_divs = [d for d in info.history if d.date >= one_year_ago.strftime('%Y-%m-%d')]
        num_divs_year = len(recent_divs)

        if num_divs_year >= 4:
            info.frequency = 'quarterly'
        elif num_divs_year >= 2:
            info.frequency = 'semi-annual'
        else:
            info.frequency = 'annual'

        # Calculate trailing 12-month dividend
        info.annual_dividend = sum(d.amount for d in recent_divs)

        # Estimate next ex-date based on history
        if len(info.history) >= 2:
            # Calculate average gap between dividends
            dates = [datetime.strptime(d.date, '%Y-%m-%d') for d in info.history[:5]]
            if len(dates) >= 2:
                gaps = [(dates[i] - dates[i+1]).days for i in range(len(dates)-1)]
                avg_gap = sum(gaps) / len(gaps)

                # Estimate next ex-date
                last_date = dates[0]
                next_date = last_date + timedelta(days=avg_gap)

                # If next date is in the past, project forward
                while next_date < today:
                    next_date += timedelta(days=avg_gap)

                info.next_ex_date = next_date.strftime('%Y-%m-%d')
                info.next_amount = info.history[0].amount  # Assume same as last

        # Calculate 5-year CAGR if enough data
        five_years_ago = (today - timedelta(days=5*365)).strftime('%Y-%m-%d')
        old_divs = [d for d in info.history if d.date <= five_years_ago]

        if old_divs and recent_divs:
            # Compare oldest year's dividend to most recent year's
            old_annual = sum(d.amount for d in old_divs[:4]) if len(old_divs) >= 4 else old_divs[0].amount
            new_annual = info.annual_dividend

            if old_annual > 0 and new_annual > 0:
                # CAGR formula: (end/start)^(1/years) - 1
                info.dividend_growth_5y = ((new_annual / old_annual) ** (1/5) - 1) * 100

    def get_upcoming_dividends(self, portfolio: List[Dict]) -> List[Dict]:
        """
        Get upcoming ex-dividend dates for portfolio positions.

        Args:
            portfolio: List of positions with 'ticker' and 'quantity'

        Returns:
            List of upcoming dividends sorted by date
        """
        upcoming = []
        today = datetime.now().strftime('%Y-%m-%d')
        three_months = (datetime.now() + timedelta(days=90)).strftime('%Y-%m-%d')

        for pos in portfolio:
            ticker = pos.get('ticker', '')
            qty = float(pos.get('quantity', pos.get('qty', 0)))
            name = pos.get('name', ticker)

            if not ticker or qty <= 0:
                continue

            info = self.get_dividend_history(ticker)

            if info.next_ex_date and info.next_ex_date >= today and info.next_ex_date <= three_months:
                expected_income = (info.next_amount or 0) * qty
                upcoming.append({
                    'ticker': ticker,
                    'name': name,
                    'ex_date': info.next_ex_date,
                    'amount_per_share': info.next_amount or 0,
                    'quantity': qty,
                    'expected_income': round(expected_income, 2),
                    'yield': info.dividend_yield,
                    'frequency': info.frequency
                })

        # Sort by ex_date
        upcoming.sort(key=lambda x: x['ex_date'])
        return upcoming

    def calculate_dividend_yield(self, ticker: str, current_price: float) -> float:
        """
        Calculate current dividend yield.

        Args:
            ticker: Stock ticker
            current_price: Current stock price

        Returns:
            Dividend yield as percentage
        """
        if current_price <= 0:
            return 0

        info = self.get_dividend_history(ticker)
        if info.annual_dividend <= 0:
            return 0

        yield_pct = (info.annual_dividend / current_price) * 100
        info.dividend_yield = yield_pct
        return yield_pct

    def project_annual_income(self, portfolio: List[Dict]) -> Dict:
        """
        Project annual dividend income from portfolio.

        Args:
            portfolio: List of positions with 'ticker', 'quantity', and optionally 'price'

        Returns:
            Dict with total income and breakdown by ticker
        """
        total_income = 0
        breakdown = []

        for pos in portfolio:
            ticker = pos.get('ticker', '')
            qty = float(pos.get('quantity', pos.get('qty', 0)))
            price = float(pos.get('price', pos.get('current_price', 0)))
            name = pos.get('name', ticker)
            cost = float(pos.get('cost', pos.get('avg_cost', 0))) * qty

            if not ticker or qty <= 0:
                continue

            info = self.get_dividend_history(ticker)

            # Update yield if we have current price
            if price > 0:
                info.dividend_yield = (info.annual_dividend / price) * 100

            annual_income = info.annual_dividend * qty
            total_income += annual_income

            # Calculate yield on cost
            yoc = (annual_income / cost * 100) if cost > 0 else 0

            breakdown.append({
                'ticker': ticker,
                'name': name,
                'quantity': qty,
                'annual_dividend': info.annual_dividend,
                'annual_income': round(annual_income, 2),
                'dividend_yield': round(info.dividend_yield, 2),
                'yield_on_cost': round(yoc, 2),
                'frequency': info.frequency,
                'next_ex_date': info.next_ex_date,
                'dividend_growth_5y': info.dividend_growth_5y
            })

        # Sort by annual income (highest first)
        breakdown.sort(key=lambda x: x['annual_income'], reverse=True)

        return {
            'total_annual_income': round(total_income, 2),
            'monthly_average': round(total_income / 12, 2),
            'positions_with_dividends': len([b for b in breakdown if b['annual_income'] > 0]),
            'total_positions': len(breakdown),
            'breakdown': breakdown
        }

    def get_dividend_calendar(self, portfolio: List[Dict], months: int = 3) -> Dict:
        """
        Generate dividend calendar for the next N months.

        Args:
            portfolio: List of positions
            months: Number of months to project

        Returns:
            Calendar data with monthly breakdown
        """
        today = datetime.now()
        calendar = {}

        # Initialize months
        for i in range(months):
            month_date = today + timedelta(days=i * 30)
            month_key = month_date.strftime('%Y-%m')
            calendar[month_key] = {
                'month': month_date.strftime('%B %Y'),
                'events': [],
                'total_expected': 0
            }

        # Get upcoming dividends
        upcoming = self.get_upcoming_dividends(portfolio)

        for div in upcoming:
            ex_date = div['ex_date']
            month_key = ex_date[:7]  # YYYY-MM

            if month_key in calendar:
                calendar[month_key]['events'].append({
                    'date': ex_date,
                    'ticker': div['ticker'],
                    'name': div['name'],
                    'amount': div['expected_income']
                })
                calendar[month_key]['total_expected'] += div['expected_income']

        # Round totals
        for month in calendar.values():
            month['total_expected'] = round(month['total_expected'], 2)

        return {
            'months': list(calendar.values()),
            'upcoming': upcoming
        }


def create_dividends_service(cache_file: str, get_dividends_func=None, get_fundamentals_func=None) -> DividendsService:
    """Factory function to create dividends service"""
    return DividendsService(cache_file, get_dividends_func, get_fundamentals_func)

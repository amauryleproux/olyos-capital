"""
OLYOS CAPITAL - Insider Trading Tracker Service
================================================
Track insider (directors, executives) transactions on portfolio and watchlist stocks.
Insider buying on small caps is a strong signal in value investing.

Data Sources:
- EOD API: /api/insider-transactions endpoint
- AMF (France): BDIF register (fallback scraping)
"""

import os
import json
import requests
from datetime import datetime, timedelta
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum

from olyos.logger import get_logger

log = get_logger('insider')


# ============================================================================
# DATA CLASSES
# ============================================================================

class TransactionType(str, Enum):
    """Insider transaction types"""
    BUY = "BUY"
    SELL = "SELL"
    GIFT = "GIFT"
    EXERCISE = "EXERCISE"
    OTHER = "OTHER"


@dataclass
class InsiderTransaction:
    """Single insider transaction"""
    ticker: str
    date: str  # YYYY-MM-DD
    insider_name: str
    insider_title: str  # CEO, CFO, Director, etc.
    transaction_type: TransactionType
    shares: float
    price: float
    value: float  # shares * price
    shares_owned_after: float = 0
    percent_change: float = 0  # % change in holdings
    filing_date: str = ""
    source: str = "EOD"  # EOD, AMF, FCA

    def to_dict(self) -> Dict:
        """Convert to dictionary"""
        d = asdict(self)
        d['transaction_type'] = self.transaction_type.value
        return d

    @classmethod
    def from_dict(cls, data: Dict) -> 'InsiderTransaction':
        """Create from dictionary"""
        data = data.copy()
        if 'transaction_type' in data:
            data['transaction_type'] = TransactionType(data['transaction_type'])
        return cls(**data)


@dataclass
class InsiderSentiment:
    """Insider sentiment for a ticker"""
    ticker: str
    period_months: int = 12
    total_buys: int = 0
    total_sells: int = 0
    buy_value: float = 0
    sell_value: float = 0
    net_value: float = 0  # buy_value - sell_value
    sentiment_ratio: float = 0  # buys / (buys + sells), 0.5 = neutral
    unique_buyers: int = 0
    unique_sellers: int = 0
    last_transaction_date: str = ""
    is_cluster_buying: bool = False  # 3+ insiders bought in < 30 days
    recent_buy_days: int = 0  # Days since last buy (0 = no recent buy)

    def to_dict(self) -> Dict:
        return asdict(self)


@dataclass
class InsiderAlert:
    """Alert for significant insider activity"""
    ticker: str
    ticker_name: str
    alert_type: str  # INSIDER_BUY, INSIDER_SELL, CLUSTER_BUY
    date: str
    insider_name: str
    insider_title: str
    value: float
    message: str

    def to_dict(self) -> Dict:
        return asdict(self)


# ============================================================================
# INSIDER SERVICE
# ============================================================================

class InsiderService:
    """Service for tracking insider transactions"""

    def __init__(
        self,
        eod_api_key: str,
        cache_file: str = "data/insider_cache.json",
        cache_days: int = 3
    ):
        self.eod_api_key = eod_api_key
        self.cache_file = cache_file
        self.cache_days = cache_days
        self._cache: Dict = {}
        self._load_cache()

    def _load_cache(self):
        """Load cache from file"""
        if os.path.exists(self.cache_file):
            try:
                with open(self.cache_file, 'r', encoding='utf-8') as f:
                    self._cache = json.load(f)
            except Exception as e:
                log.error(f"Error loading insider cache: {e}")
                self._cache = {}

    def _save_cache(self):
        """Save cache to file"""
        try:
            os.makedirs(os.path.dirname(self.cache_file), exist_ok=True)
            with open(self.cache_file, 'w', encoding='utf-8') as f:
                json.dump(self._cache, f, indent=2, default=str)
        except Exception as e:
            log.error(f"Error saving insider cache: {e}")

    def _is_cache_valid(self, ticker: str) -> bool:
        """Check if cached data is still valid"""
        if ticker not in self._cache:
            return False
        cached = self._cache[ticker]
        cached_date = datetime.fromisoformat(cached.get('cached_at', '2000-01-01'))
        return datetime.now() - cached_date < timedelta(days=self.cache_days)

    def _get_eod_ticker(self, ticker: str) -> str:
        """Convert ticker to EOD format"""
        ticker = ticker.upper().strip()
        # Handle already formatted tickers
        if '.' in ticker:
            return ticker
        # French tickers
        if ticker.startswith('AL') or len(ticker) <= 5:
            return f"{ticker}.PA"
        return ticker

    def get_insider_transactions(
        self,
        ticker: str,
        months: int = 12,
        force_refresh: bool = False
    ) -> List[InsiderTransaction]:
        """
        Get insider transactions for a ticker.

        Args:
            ticker: Stock ticker
            months: Number of months to look back
            force_refresh: Force API call even if cached

        Returns:
            List of InsiderTransaction objects
        """
        # Check cache
        if not force_refresh and self._is_cache_valid(ticker):
            cached = self._cache[ticker]
            transactions = [InsiderTransaction.from_dict(t) for t in cached.get('transactions', [])]
            log.debug(f"Using cached insider data for {ticker}")
            return transactions

        # Fetch from EOD API
        transactions = self._fetch_from_eod(ticker, months)

        # Cache results
        self._cache[ticker] = {
            'cached_at': datetime.now().isoformat(),
            'transactions': [t.to_dict() for t in transactions]
        }
        self._save_cache()

        return transactions

    def _fetch_from_eod(self, ticker: str, months: int) -> List[InsiderTransaction]:
        """Fetch insider transactions from EOD API"""
        if not self.eod_api_key:
            log.warning("No EOD API key configured for insider data")
            return []

        eod_ticker = self._get_eod_ticker(ticker)
        from_date = (datetime.now() - timedelta(days=months * 30)).strftime('%Y-%m-%d')

        url = f"https://eodhd.com/api/insider-transactions"
        params = {
            'code': eod_ticker,
            'from': from_date,
            'api_token': self.eod_api_key,
            'fmt': 'json'
        }

        try:
            log.info(f"Fetching insider transactions for {eod_ticker}")
            response = requests.get(url, params=params, timeout=15)

            if response.status_code == 404:
                log.debug(f"No insider data available for {ticker}")
                return []

            response.raise_for_status()
            data = response.json()

            if not data or not isinstance(data, list):
                return []

            transactions = []
            for item in data:
                try:
                    # Parse transaction type
                    trans_type_str = item.get('transactionType', '').upper()
                    if 'BUY' in trans_type_str or 'PURCHASE' in trans_type_str or 'ACQUISITION' in trans_type_str:
                        trans_type = TransactionType.BUY
                    elif 'SELL' in trans_type_str or 'SALE' in trans_type_str or 'DISPOSAL' in trans_type_str:
                        trans_type = TransactionType.SELL
                    elif 'GIFT' in trans_type_str:
                        trans_type = TransactionType.GIFT
                    elif 'EXERCISE' in trans_type_str or 'OPTION' in trans_type_str:
                        trans_type = TransactionType.EXERCISE
                    else:
                        trans_type = TransactionType.OTHER

                    shares = float(item.get('transactionShares', 0) or 0)
                    price = float(item.get('transactionPrice', 0) or 0)
                    value = float(item.get('transactionValue', shares * price) or 0)

                    transaction = InsiderTransaction(
                        ticker=ticker.upper(),
                        date=item.get('date', ''),
                        insider_name=item.get('reporterName', item.get('ownerName', 'Unknown')),
                        insider_title=item.get('reporterTitle', item.get('ownerTitle', '')),
                        transaction_type=trans_type,
                        shares=abs(shares),
                        price=price,
                        value=abs(value),
                        shares_owned_after=float(item.get('postTransactionShares', 0) or 0),
                        filing_date=item.get('filingDate', item.get('date', '')),
                        source='EOD'
                    )
                    transactions.append(transaction)
                except Exception as e:
                    log.warning(f"Error parsing insider transaction: {e}")
                    continue

            log.info(f"Found {len(transactions)} insider transactions for {ticker}")
            return sorted(transactions, key=lambda t: t.date, reverse=True)

        except requests.exceptions.RequestException as e:
            log.error(f"Error fetching insider data for {ticker}: {e}")
            return []

    def get_recent_buys(
        self,
        tickers: List[str],
        days: int = 90
    ) -> List[InsiderTransaction]:
        """
        Get recent insider buys across multiple tickers.

        Args:
            tickers: List of tickers to check
            days: Number of days to look back

        Returns:
            List of buy transactions sorted by date
        """
        cutoff_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
        all_buys = []

        for ticker in tickers:
            try:
                transactions = self.get_insider_transactions(ticker, months=int(days / 30) + 1)
                for t in transactions:
                    if t.transaction_type == TransactionType.BUY and t.date >= cutoff_date:
                        all_buys.append(t)
            except Exception as e:
                log.warning(f"Error getting insider buys for {ticker}: {e}")

        return sorted(all_buys, key=lambda t: t.date, reverse=True)

    def calculate_insider_sentiment(
        self,
        ticker: str,
        months: int = 12
    ) -> InsiderSentiment:
        """
        Calculate insider sentiment for a ticker.

        Returns:
            InsiderSentiment object with buy/sell ratio and cluster detection
        """
        transactions = self.get_insider_transactions(ticker, months)

        sentiment = InsiderSentiment(ticker=ticker, period_months=months)

        if not transactions:
            return sentiment

        # Calculate metrics
        buyers = set()
        sellers = set()
        recent_buy_dates = []
        cutoff_30d = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')
        cutoff_90d = (datetime.now() - timedelta(days=90)).strftime('%Y-%m-%d')

        for t in transactions:
            if t.transaction_type == TransactionType.BUY:
                sentiment.total_buys += 1
                sentiment.buy_value += t.value
                buyers.add(t.insider_name)
                if t.date >= cutoff_30d:
                    recent_buy_dates.append(t.date)
            elif t.transaction_type == TransactionType.SELL:
                sentiment.total_sells += 1
                sentiment.sell_value += t.value
                sellers.add(t.insider_name)

        sentiment.unique_buyers = len(buyers)
        sentiment.unique_sellers = len(sellers)
        sentiment.net_value = sentiment.buy_value - sentiment.sell_value

        # Sentiment ratio (0 to 1, 0.5 = neutral)
        total = sentiment.total_buys + sentiment.total_sells
        if total > 0:
            sentiment.sentiment_ratio = sentiment.total_buys / total

        # Last transaction date
        if transactions:
            sentiment.last_transaction_date = transactions[0].date

        # Detect cluster buying (3+ unique buyers in last 30 days)
        if len(set(recent_buy_dates)) >= 3 or len(buyers) >= 3:
            # Check if 3+ unique insiders bought recently
            recent_buyers = set()
            for t in transactions:
                if t.transaction_type == TransactionType.BUY and t.date >= cutoff_30d:
                    recent_buyers.add(t.insider_name)
            sentiment.is_cluster_buying = len(recent_buyers) >= 3

        # Days since last buy
        for t in transactions:
            if t.transaction_type == TransactionType.BUY and t.date >= cutoff_90d:
                try:
                    buy_date = datetime.strptime(t.date, '%Y-%m-%d')
                    sentiment.recent_buy_days = (datetime.now() - buy_date).days
                    break
                except ValueError:
                    pass

        return sentiment

    def get_insider_score_adjustment(
        self,
        ticker: str,
        base_bonus: int = 5,
        base_malus: int = -5
    ) -> int:
        """
        Get score adjustment based on insider activity.

        Args:
            ticker: Stock ticker
            base_bonus: Points to add for recent insider buying
            base_malus: Points to subtract for heavy selling

        Returns:
            Score adjustment (-5 to +5)
        """
        sentiment = self.calculate_insider_sentiment(ticker, months=6)

        adjustment = 0

        # Bonus for recent buying
        if sentiment.recent_buy_days > 0 and sentiment.recent_buy_days <= 90:
            adjustment += base_bonus
            # Extra bonus for cluster buying
            if sentiment.is_cluster_buying:
                adjustment += 2

        # Malus for heavy selling
        if sentiment.sentiment_ratio < 0.3 and sentiment.sell_value > 100000:
            adjustment += base_malus

        # Cap adjustment
        return max(-5, min(7, adjustment))

    def get_insider_feed(
        self,
        tickers: List[str],
        limit: int = 50,
        transaction_types: List[TransactionType] = None
    ) -> List[InsiderTransaction]:
        """
        Get a feed of recent insider transactions.

        Args:
            tickers: List of tickers to include
            limit: Maximum number of transactions
            transaction_types: Filter by transaction types

        Returns:
            List of transactions sorted by date
        """
        all_transactions = []

        for ticker in tickers:
            try:
                transactions = self.get_insider_transactions(ticker, months=6)
                if transaction_types:
                    transactions = [t for t in transactions if t.transaction_type in transaction_types]
                all_transactions.extend(transactions)
            except Exception as e:
                log.warning(f"Error getting insider feed for {ticker}: {e}")

        # Sort by date and limit
        all_transactions.sort(key=lambda t: t.date, reverse=True)
        return all_transactions[:limit]

    def detect_alerts(
        self,
        tickers: List[str],
        ticker_names: Dict[str, str] = None,
        min_value: float = 10000
    ) -> List[InsiderAlert]:
        """
        Detect significant insider activity that should trigger alerts.

        Args:
            tickers: List of tickers to check
            ticker_names: Dict mapping ticker -> company name
            min_value: Minimum transaction value to alert on

        Returns:
            List of InsiderAlert objects
        """
        ticker_names = ticker_names or {}
        alerts = []
        cutoff = (datetime.now() - timedelta(days=7)).strftime('%Y-%m-%d')

        for ticker in tickers:
            try:
                transactions = self.get_insider_transactions(ticker, months=1)
                sentiment = self.calculate_insider_sentiment(ticker, months=1)

                for t in transactions:
                    if t.date < cutoff:
                        continue
                    if t.value < min_value:
                        continue

                    if t.transaction_type == TransactionType.BUY:
                        alert_type = "CLUSTER_BUY" if sentiment.is_cluster_buying else "INSIDER_BUY"
                        message = f"{t.insider_name} ({t.insider_title}) a acheté {t.shares:,.0f} actions pour {t.value:,.0f}€"
                        if sentiment.is_cluster_buying:
                            message += " [CLUSTER BUYING]"

                        alerts.append(InsiderAlert(
                            ticker=ticker,
                            ticker_name=ticker_names.get(ticker, ticker),
                            alert_type=alert_type,
                            date=t.date,
                            insider_name=t.insider_name,
                            insider_title=t.insider_title,
                            value=t.value,
                            message=message
                        ))

                    elif t.transaction_type == TransactionType.SELL and t.value >= min_value * 5:
                        alerts.append(InsiderAlert(
                            ticker=ticker,
                            ticker_name=ticker_names.get(ticker, ticker),
                            alert_type="INSIDER_SELL",
                            date=t.date,
                            insider_name=t.insider_name,
                            insider_title=t.insider_title,
                            value=t.value,
                            message=f"{t.insider_name} ({t.insider_title}) a vendu {t.shares:,.0f} actions pour {t.value:,.0f}€"
                        ))

            except Exception as e:
                log.warning(f"Error detecting insider alerts for {ticker}: {e}")

        return sorted(alerts, key=lambda a: a.date, reverse=True)

    def refresh_cache(self, tickers: List[str]):
        """Force refresh cache for specific tickers"""
        for ticker in tickers:
            self.get_insider_transactions(ticker, months=12, force_refresh=True)


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

def create_insider_service(
    eod_api_key: str,
    cache_file: str = "data/insider_cache.json"
) -> InsiderService:
    """Factory function to create InsiderService"""
    return InsiderService(
        eod_api_key=eod_api_key,
        cache_file=cache_file
    )

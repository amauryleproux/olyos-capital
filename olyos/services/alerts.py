"""
OLYOS CAPITAL - Alerts Service
==============================
Intelligent watchlist alerts based on Higgons criteria.

Alert Types:
- ZONE_ACHAT: PE < threshold AND ROE > threshold (highest priority)
- PE_ATTRACTIF: PE dropped below threshold
- ROE_EXCELLENT: ROE above threshold
- PRIX_CIBLE: Price reached target
- MOMENTUM_RETOURNE: Technical momentum turned positive
"""

import json
import os
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum

from olyos.logger import get_logger

log = get_logger('alerts')


class AlertType(Enum):
    """Alert priority levels (lower = higher priority)"""
    INSIDER_BUY = 0      # Insider bought shares - highest priority
    ZONE_ACHAT = 1       # Buy zone - PE low AND ROE high
    PE_ATTRACTIF = 2     # PE dropped below threshold
    ROE_EXCELLENT = 3    # ROE above threshold
    PRIX_CIBLE = 4       # Price target reached
    MOMENTUM_RETOURNE = 5  # Momentum turned positive
    INSIDER_SELL = 6     # Insider sold shares (warning)
    REBALANCE_NEEDED = 7 # Portfolio needs rebalancing


@dataclass
class AlertConfig:
    """Alert thresholds configuration for a watchlist item"""
    pe_threshold: Optional[float] = 10.0      # Alert when PE < this
    roe_threshold: Optional[float] = 12.0     # Alert when ROE > this
    price_below: Optional[float] = None       # Alert when price < this
    price_above: Optional[float] = None       # Alert when price > this
    momentum_positive: bool = False           # Alert on positive momentum

    def to_dict(self) -> Dict:
        return {
            'pe_threshold': self.pe_threshold,
            'roe_threshold': self.roe_threshold,
            'price_below': self.price_below,
            'price_above': self.price_above,
            'momentum_positive': self.momentum_positive
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'AlertConfig':
        return cls(
            pe_threshold=data.get('pe_threshold', 10.0),
            roe_threshold=data.get('roe_threshold', 12.0),
            price_below=data.get('price_below'),
            price_above=data.get('price_above'),
            momentum_positive=data.get('momentum_positive', False)
        )


@dataclass
class Alert:
    """Represents a triggered alert"""
    ticker: str
    name: str
    alert_type: AlertType
    message: str
    current_value: float
    threshold_value: float
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    dismissed: bool = False

    def to_dict(self) -> Dict:
        return {
            'ticker': self.ticker,
            'name': self.name,
            'alert_type': self.alert_type.name,
            'priority': self.alert_type.value,
            'message': self.message,
            'current_value': self.current_value,
            'threshold_value': self.threshold_value,
            'timestamp': self.timestamp,
            'dismissed': self.dismissed
        }


@dataclass
class WatchlistItem:
    """Enhanced watchlist item with alert capabilities"""
    ticker: str
    name: str
    country: str = ""
    sector: str = ""
    added: str = field(default_factory=lambda: datetime.now().strftime('%Y-%m-%d'))
    alerts: AlertConfig = field(default_factory=AlertConfig)
    last_check: Optional[str] = None
    last_pe: Optional[float] = None
    last_roe: Optional[float] = None
    last_price: Optional[float] = None
    last_momentum: Optional[str] = None  # 'positive', 'negative', 'neutral'
    alert_triggered: bool = False
    alert_history: List[Dict] = field(default_factory=list)
    dismissed_types: List[str] = field(default_factory=list)  # e.g., ["ZONE_ACHAT_2026-02-06"]

    def to_dict(self) -> Dict:
        return {
            'ticker': self.ticker,
            'name': self.name,
            'country': self.country,
            'sector': self.sector,
            'added': self.added,
            'alerts': self.alerts.to_dict(),
            'last_check': self.last_check,
            'last_pe': self.last_pe,
            'last_roe': self.last_roe,
            'last_price': self.last_price,
            'last_momentum': self.last_momentum,
            'alert_triggered': self.alert_triggered,
            'alert_history': self.alert_history,
            'dismissed_types': self.dismissed_types
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'WatchlistItem':
        # Handle legacy format (without alerts field)
        alerts_data = data.get('alerts', {})
        if isinstance(alerts_data, dict):
            alerts = AlertConfig.from_dict(alerts_data)
        else:
            alerts = AlertConfig()

        return cls(
            ticker=data.get('ticker', ''),
            name=data.get('name', ''),
            country=data.get('country', ''),
            sector=data.get('sector', ''),
            added=data.get('added', datetime.now().strftime('%Y-%m-%d')),
            alerts=alerts,
            last_check=data.get('last_check'),
            last_pe=data.get('last_pe'),
            last_roe=data.get('last_roe'),
            last_price=data.get('last_price'),
            last_momentum=data.get('last_momentum'),
            alert_triggered=data.get('alert_triggered', False),
            alert_history=data.get('alert_history', []),
            dismissed_types=data.get('dismissed_types', [])
        )


class AlertsService:
    """Service for managing watchlist alerts"""

    def __init__(self, watchlist_file: str, get_fundamentals_func=None, get_prices_func=None):
        """
        Initialize alerts service.

        Args:
            watchlist_file: Path to watchlist.json
            get_fundamentals_func: Function to fetch fundamentals (eod_get_fundamentals)
            get_prices_func: Function to fetch prices (eod_get_historical_prices)
        """
        self.watchlist_file = watchlist_file
        self.get_fundamentals = get_fundamentals_func
        self.get_prices = get_prices_func
        self._watchlist: List[WatchlistItem] = []
        self._active_alerts: List[Alert] = []

    def load_watchlist(self) -> List[WatchlistItem]:
        """Load watchlist from JSON file"""
        if not os.path.exists(self.watchlist_file):
            return []

        try:
            with open(self.watchlist_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self._watchlist = [WatchlistItem.from_dict(item) for item in data]
            log.info(f"Loaded {len(self._watchlist)} items from watchlist")
            return self._watchlist
        except Exception as e:
            log.error(f"Error loading watchlist: {e}")
            return []

    def save_watchlist(self) -> bool:
        """Save watchlist to JSON file"""
        try:
            data = [item.to_dict() for item in self._watchlist]
            with open(self.watchlist_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            log.info(f"Saved {len(self._watchlist)} items to watchlist")
            return True
        except Exception as e:
            log.error(f"Error saving watchlist: {e}")
            return False

    def get_item(self, ticker: str) -> Optional[WatchlistItem]:
        """Get a watchlist item by ticker"""
        for item in self._watchlist:
            if item.ticker == ticker:
                return item
        return None

    def update_alert_config(self, ticker: str, config: AlertConfig) -> bool:
        """Update alert configuration for a ticker"""
        item = self.get_item(ticker)
        if item:
            item.alerts = config
            self.save_watchlist()
            log.info(f"Updated alert config for {ticker}")
            return True
        return False

    def check_alerts(self) -> List[Alert]:
        """
        Check all watchlist items for alerts.
        Returns list of triggered alerts sorted by priority.
        """
        self.load_watchlist()
        alerts = []

        for item in self._watchlist:
            item_alerts = self._check_item_alerts(item)
            alerts.extend(item_alerts)

            # Update item status
            item.alert_triggered = len(item_alerts) > 0
            item.last_check = datetime.now().isoformat()

            # Add to history if new alerts
            for alert in item_alerts:
                history_entry = alert.to_dict()
                history_entry['checked_at'] = datetime.now().isoformat()
                item.alert_history.append(history_entry)
                # Keep only last 50 alerts in history
                item.alert_history = item.alert_history[-50:]

        self.save_watchlist()

        # Sort by priority (lower = higher priority)
        alerts.sort(key=lambda a: a.alert_type.value)
        self._active_alerts = alerts

        log.info(f"Alert check complete: {len(alerts)} alerts triggered")
        return alerts

    def _check_item_alerts(self, item: WatchlistItem) -> List[Alert]:
        """Check alerts for a single watchlist item"""
        alerts = []

        # Fetch current data
        pe, roe, price, momentum = self._fetch_current_data(item.ticker)

        # Update item with latest values
        item.last_pe = pe
        item.last_roe = roe
        item.last_price = price
        item.last_momentum = momentum

        config = item.alerts

        # Check ZONE_ACHAT (highest priority) - PE low AND ROE high
        if pe is not None and roe is not None:
            pe_ok = config.pe_threshold and pe < config.pe_threshold
            roe_ok = config.roe_threshold and roe > config.roe_threshold

            if pe_ok and roe_ok:
                alerts.append(Alert(
                    ticker=item.ticker,
                    name=item.name,
                    alert_type=AlertType.ZONE_ACHAT,
                    message=f"ZONE D'ACHAT: PE={pe:.1f} < {config.pe_threshold} ET ROE={roe:.1f}% > {config.roe_threshold}%",
                    current_value=pe,
                    threshold_value=config.pe_threshold
                ))
            elif pe_ok:
                # Only PE attractive
                alerts.append(Alert(
                    ticker=item.ticker,
                    name=item.name,
                    alert_type=AlertType.PE_ATTRACTIF,
                    message=f"PE attractif: {pe:.1f} < {config.pe_threshold}",
                    current_value=pe,
                    threshold_value=config.pe_threshold
                ))
            elif roe_ok:
                # Only ROE excellent
                alerts.append(Alert(
                    ticker=item.ticker,
                    name=item.name,
                    alert_type=AlertType.ROE_EXCELLENT,
                    message=f"ROE excellent: {roe:.1f}% > {config.roe_threshold}%",
                    current_value=roe,
                    threshold_value=config.roe_threshold
                ))

        # Check price targets
        if price is not None:
            if config.price_below and price < config.price_below:
                alerts.append(Alert(
                    ticker=item.ticker,
                    name=item.name,
                    alert_type=AlertType.PRIX_CIBLE,
                    message=f"Prix cible atteint: {price:.2f} < {config.price_below:.2f}",
                    current_value=price,
                    threshold_value=config.price_below
                ))
            if config.price_above and price > config.price_above:
                alerts.append(Alert(
                    ticker=item.ticker,
                    name=item.name,
                    alert_type=AlertType.PRIX_CIBLE,
                    message=f"Prix cible atteint: {price:.2f} > {config.price_above:.2f}",
                    current_value=price,
                    threshold_value=config.price_above
                ))

        # Check momentum
        if config.momentum_positive and momentum == 'positive':
            alerts.append(Alert(
                ticker=item.ticker,
                name=item.name,
                alert_type=AlertType.MOMENTUM_RETOURNE,
                message=f"Momentum redevenu positif",
                current_value=1.0,
                threshold_value=0.0
            ))

        # Filter out dismissed alerts (dismissed today)
        today = datetime.now().strftime('%Y-%m-%d')
        filtered_alerts = []
        for alert in alerts:
            dismissed_key = f"{alert.alert_type.name}_{today}"
            if dismissed_key not in item.dismissed_types:
                filtered_alerts.append(alert)
            else:
                log.info(f"Skipping dismissed alert {alert.alert_type.name} for {item.ticker}")

        return filtered_alerts

    def _fetch_current_data(self, ticker: str) -> Tuple[Optional[float], Optional[float], Optional[float], Optional[str]]:
        """
        Fetch current PE, ROE, price and momentum for a ticker.
        Returns (pe, roe, price, momentum)
        """
        pe = None
        roe = None
        price = None
        momentum = None

        try:
            # Fetch fundamentals
            if self.get_fundamentals:
                fund_data, err = self.get_fundamentals(ticker, use_cache=True)
                if fund_data and not err:
                    # Extract PE
                    highlights = fund_data.get('Highlights', {})
                    pe = highlights.get('PERatio')
                    if pe is not None:
                        try:
                            pe = float(pe)
                        except (ValueError, TypeError):
                            pe = None

                    # Extract ROE
                    roe = highlights.get('ReturnOnEquityTTM')
                    if roe is not None:
                        try:
                            roe = float(roe) * 100  # Convert to percentage
                        except (ValueError, TypeError):
                            roe = None

                    # Extract price
                    price = fund_data.get('General', {}).get('LastClose')
                    if price is None:
                        price = highlights.get('MarketCapitalization')
                        shares = fund_data.get('SharesStats', {}).get('SharesOutstanding')
                        if price and shares:
                            try:
                                price = float(price) / float(shares)
                            except:
                                price = None

            # Fetch prices for momentum calculation
            if self.get_prices:
                from datetime import datetime, timedelta
                end_date = datetime.now().strftime('%Y-%m-%d')
                start_date = (datetime.now() - timedelta(days=30)).strftime('%Y-%m-%d')

                prices_data, err = self.get_prices(ticker, start_date, end_date, use_cache=True)
                if prices_data and len(prices_data) > 5:
                    # Simple momentum: compare last price to 20-day average
                    recent_prices = [p.get('close', 0) for p in prices_data[-20:] if p.get('close')]
                    if recent_prices:
                        avg_price = sum(recent_prices) / len(recent_prices)
                        last_price = recent_prices[-1]
                        price = last_price  # Update price with latest

                        if last_price > avg_price * 1.02:
                            momentum = 'positive'
                        elif last_price < avg_price * 0.98:
                            momentum = 'negative'
                        else:
                            momentum = 'neutral'

        except Exception as e:
            log.error(f"Error fetching data for {ticker}: {e}")

        return pe, roe, price, momentum

    def get_active_alerts(self) -> List[Dict]:
        """Get list of active (non-dismissed) alerts as dicts"""
        return [a.to_dict() for a in self._active_alerts if not a.dismissed]

    def dismiss_alert(self, ticker: str, alert_type: str) -> bool:
        """Dismiss an alert - persists to watchlist file"""
        # Mark in active alerts
        for alert in self._active_alerts:
            if alert.ticker == ticker and alert.alert_type.name == alert_type:
                alert.dismissed = True

        # Persist to watchlist file
        self.load_watchlist()
        item = self.get_item(ticker)
        if item:
            # Mark the last alert of this type as dismissed in history
            for hist in reversed(item.alert_history):
                if hist.get('alert_type') == alert_type and not hist.get('dismissed', False):
                    hist['dismissed'] = True
                    hist['dismissed_at'] = datetime.now().isoformat()
                    break

            # Also store in a dismissed_types list for quick lookup
            if not hasattr(item, 'dismissed_types'):
                item.dismissed_types = []

            # Add to dismissed (will be checked before creating new alerts)
            dismissed_key = f"{alert_type}_{datetime.now().strftime('%Y-%m-%d')}"
            if dismissed_key not in getattr(item, 'dismissed_types', []):
                if not hasattr(item, 'dismissed_types'):
                    item.dismissed_types = []
                item.dismissed_types.append(dismissed_key)

            self.save_watchlist()
            log.info(f"Dismissed alert {alert_type} for {ticker}")
            return True
        return False

    def get_watchlist_with_status(self) -> List[Dict]:
        """Get watchlist items with their current alert status"""
        self.load_watchlist()
        return [item.to_dict() for item in self._watchlist]


# Convenience function to create service
def create_alerts_service(watchlist_file: str, get_fundamentals_func=None, get_prices_func=None) -> AlertsService:
    """Create and initialize an alerts service"""
    service = AlertsService(watchlist_file, get_fundamentals_func, get_prices_func)
    service.load_watchlist()
    return service

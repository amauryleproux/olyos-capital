"""
OLYOS CAPITAL - Position Manager Service
=========================================
Manages transactions, calculates positions from transaction history,
and computes realized/unrealized P&L using weighted average cost method.

Transaction Types:
- BUY: Purchase shares (increases position, updates avg cost)
- SELL: Sell shares (decreases position, generates realized P&L)

P&L Calculation:
- Unrealized P&L = (current_price - avg_cost) * quantity
- Realized P&L = (sell_price - avg_cost_at_sale) * sold_quantity
"""

import json
import os
from datetime import datetime, date
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum
import uuid

from olyos.logger import get_logger

log = get_logger('positions')


class TransactionType(Enum):
    BUY = "BUY"
    SELL = "SELL"


@dataclass
class Transaction:
    """Represents a single buy or sell transaction"""
    id: str
    ticker: str
    type: str  # "BUY" or "SELL"
    date: str  # YYYY-MM-DD
    quantity: float
    price_per_share: float
    currency: str = "EUR"
    fees: float = 0.0
    notes: str = ""
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    # Computed at time of transaction for sells
    avg_cost_at_sale: Optional[float] = None
    realized_pnl: Optional[float] = None

    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'ticker': self.ticker,
            'type': self.type,
            'date': self.date,
            'quantity': self.quantity,
            'price_per_share': self.price_per_share,
            'currency': self.currency,
            'fees': self.fees,
            'notes': self.notes,
            'created_at': self.created_at,
            'avg_cost_at_sale': self.avg_cost_at_sale,
            'realized_pnl': self.realized_pnl
        }

    @classmethod
    def from_dict(cls, data: Dict) -> 'Transaction':
        return cls(
            id=data.get('id', ''),
            ticker=data.get('ticker', ''),
            type=data.get('type', 'BUY'),
            date=data.get('date', ''),
            quantity=float(data.get('quantity', 0)),
            price_per_share=float(data.get('price_per_share', 0)),
            currency=data.get('currency', 'EUR'),
            fees=float(data.get('fees', 0)),
            notes=data.get('notes', ''),
            created_at=data.get('created_at', datetime.now().isoformat()),
            avg_cost_at_sale=data.get('avg_cost_at_sale'),
            realized_pnl=data.get('realized_pnl')
        )

    @property
    def total_value(self) -> float:
        """Total value of transaction (price * qty + fees for buys, price * qty - fees for sells)"""
        base = self.price_per_share * self.quantity
        if self.type == "BUY":
            return base + self.fees
        else:
            return base - self.fees


@dataclass
class Position:
    """Represents a current or closed position"""
    ticker: str
    name: str = ""
    status: str = "OPEN"  # OPEN or CLOSED
    total_qty: float = 0.0
    avg_cost: float = 0.0
    total_invested: float = 0.0
    current_price: float = 0.0
    current_value: float = 0.0
    unrealized_pnl: float = 0.0
    unrealized_pnl_pct: float = 0.0
    realized_pnl: float = 0.0
    total_fees: float = 0.0
    first_buy_date: Optional[str] = None
    last_transaction_date: Optional[str] = None
    close_date: Optional[str] = None
    holding_days: int = 0
    transactions: List[Transaction] = field(default_factory=list)

    def to_dict(self) -> Dict:
        return {
            'ticker': self.ticker,
            'name': self.name,
            'status': self.status,
            'total_qty': round(self.total_qty, 4),
            'avg_cost': round(self.avg_cost, 4),
            'total_invested': round(self.total_invested, 2),
            'current_price': round(self.current_price, 2),
            'current_value': round(self.current_value, 2),
            'unrealized_pnl': round(self.unrealized_pnl, 2),
            'unrealized_pnl_pct': round(self.unrealized_pnl_pct, 2),
            'realized_pnl': round(self.realized_pnl, 2),
            'total_fees': round(self.total_fees, 2),
            'first_buy_date': self.first_buy_date,
            'last_transaction_date': self.last_transaction_date,
            'close_date': self.close_date,
            'holding_days': self.holding_days,
            'transaction_count': len(self.transactions)
        }


@dataclass
class PortfolioSummary:
    """Summary of entire portfolio"""
    open_positions: List[Position]
    closed_positions: List[Position]
    total_realized_pnl: float = 0.0
    total_unrealized_pnl: float = 0.0
    total_pnl: float = 0.0
    total_fees: float = 0.0
    total_invested: float = 0.0
    total_current_value: float = 0.0
    win_rate: float = 0.0  # % of winning closed positions
    avg_holding_days: float = 0.0
    total_transactions: int = 0

    def to_dict(self) -> Dict:
        return {
            'open_positions': [p.to_dict() for p in self.open_positions],
            'closed_positions': [p.to_dict() for p in self.closed_positions],
            'total_realized_pnl': round(self.total_realized_pnl, 2),
            'total_unrealized_pnl': round(self.total_unrealized_pnl, 2),
            'total_pnl': round(self.total_pnl, 2),
            'total_fees': round(self.total_fees, 2),
            'total_invested': round(self.total_invested, 2),
            'total_current_value': round(self.total_current_value, 2),
            'win_rate': round(self.win_rate, 2),
            'avg_holding_days': round(self.avg_holding_days, 1),
            'total_transactions': self.total_transactions
        }


class PositionManager:
    """
    Manages portfolio positions and transactions.

    Uses weighted average cost method:
    - On BUY: avg_cost = (old_qty * old_avg + new_qty * new_price) / (old_qty + new_qty)
    - On SELL: avg_cost stays the same, realized P&L = (sell_price - avg_cost) * qty
    """

    def __init__(self, transactions_file: str, get_price_func=None):
        """
        Initialize position manager.

        Args:
            transactions_file: Path to transactions.json
            get_price_func: Function to get current price for a ticker
        """
        self.transactions_file = transactions_file
        self.get_price = get_price_func
        self._transactions: List[Transaction] = []
        self._load_transactions()

    def _load_transactions(self):
        """Load transactions from JSON file"""
        if not os.path.exists(self.transactions_file):
            self._transactions = []
            return

        try:
            with open(self.transactions_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            self._transactions = [Transaction.from_dict(t) for t in data]
            log.info(f"Loaded {len(self._transactions)} transactions")
        except Exception as e:
            log.error(f"Error loading transactions: {e}")
            self._transactions = []

    def _save_transactions(self):
        """Save transactions to JSON file"""
        try:
            os.makedirs(os.path.dirname(self.transactions_file), exist_ok=True)
            data = [t.to_dict() for t in self._transactions]
            with open(self.transactions_file, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
            log.info(f"Saved {len(self._transactions)} transactions")
        except Exception as e:
            log.error(f"Error saving transactions: {e}")

    def _generate_transaction_id(self) -> str:
        """Generate unique transaction ID: TXN-YYYYMMDD-XXX"""
        today = datetime.now().strftime('%Y%m%d')

        # Count today's transactions
        today_count = sum(1 for t in self._transactions if t.id.startswith(f'TXN-{today}'))

        return f"TXN-{today}-{today_count + 1:03d}"

    def add_transaction(self, ticker: str, txn_type: str, date_str: str,
                       quantity: float, price: float, fees: float = 0.0,
                       notes: str = "", currency: str = "EUR") -> Tuple[Optional[Transaction], Optional[str]]:
        """
        Add a new transaction.

        Args:
            ticker: Stock ticker
            txn_type: "BUY" or "SELL"
            date_str: Transaction date (YYYY-MM-DD)
            quantity: Number of shares
            price: Price per share
            fees: Transaction fees
            notes: Optional notes
            currency: Currency (default EUR)

        Returns:
            (Transaction, None) on success, (None, error_message) on failure
        """
        ticker = ticker.upper().strip()
        txn_type = txn_type.upper().strip()

        # Validation
        if txn_type not in ["BUY", "SELL"]:
            return None, f"Invalid transaction type: {txn_type}"

        if quantity <= 0:
            return None, "Quantity must be positive"

        if price <= 0:
            return None, "Price must be positive"

        # For SELL, check we have enough shares
        if txn_type == "SELL":
            current_qty = self._get_current_qty(ticker)
            if quantity > current_qty + 0.0001:  # Small tolerance for float comparison
                return None, f"Cannot sell {quantity} shares, only {current_qty} available"

        # Calculate avg_cost at sale and realized P&L for SELL
        avg_cost_at_sale = None
        realized_pnl = None

        if txn_type == "SELL":
            avg_cost_at_sale = self._get_current_avg_cost(ticker)
            if avg_cost_at_sale > 0:
                realized_pnl = (price - avg_cost_at_sale) * quantity - fees
            else:
                realized_pnl = -fees

        # Create transaction
        txn = Transaction(
            id=self._generate_transaction_id(),
            ticker=ticker,
            type=txn_type,
            date=date_str,
            quantity=quantity,
            price_per_share=price,
            currency=currency,
            fees=fees,
            notes=notes,
            avg_cost_at_sale=avg_cost_at_sale,
            realized_pnl=realized_pnl
        )

        self._transactions.append(txn)
        self._save_transactions()

        log.info(f"Added transaction: {txn.id} - {txn_type} {quantity} {ticker} @ {price}")
        return txn, None

    def update_transaction(self, txn_id: str, **kwargs) -> Tuple[Optional[Transaction], Optional[str]]:
        """Update an existing transaction"""
        for i, txn in enumerate(self._transactions):
            if txn.id == txn_id:
                # Update allowed fields
                for key in ['date', 'quantity', 'price_per_share', 'fees', 'notes']:
                    if key in kwargs:
                        setattr(txn, key, kwargs[key])

                # Recalculate realized P&L if it was a SELL
                if txn.type == "SELL":
                    # Need to recalculate based on historical avg_cost
                    # For simplicity, we keep the original avg_cost_at_sale
                    if txn.avg_cost_at_sale:
                        txn.realized_pnl = (txn.price_per_share - txn.avg_cost_at_sale) * txn.quantity - txn.fees

                self._save_transactions()
                return txn, None

        return None, f"Transaction {txn_id} not found"

    def delete_transaction(self, txn_id: str) -> Tuple[bool, Optional[str]]:
        """Delete a transaction"""
        for i, txn in enumerate(self._transactions):
            if txn.id == txn_id:
                del self._transactions[i]
                self._save_transactions()
                log.info(f"Deleted transaction: {txn_id}")
                return True, None

        return False, f"Transaction {txn_id} not found"

    def get_transactions(self, ticker: str = None, txn_type: str = None,
                        start_date: str = None, end_date: str = None) -> List[Transaction]:
        """Get transactions with optional filters"""
        result = self._transactions.copy()

        if ticker:
            ticker = ticker.upper()
            result = [t for t in result if t.ticker == ticker]

        if txn_type:
            txn_type = txn_type.upper()
            result = [t for t in result if t.type == txn_type]

        if start_date:
            result = [t for t in result if t.date >= start_date]

        if end_date:
            result = [t for t in result if t.date <= end_date]

        # Sort by date descending (most recent first)
        result.sort(key=lambda t: (t.date, t.created_at), reverse=True)

        return result

    def _get_current_qty(self, ticker: str) -> float:
        """Get current quantity held for a ticker"""
        ticker = ticker.upper()
        total = 0.0
        for txn in self._transactions:
            if txn.ticker == ticker:
                if txn.type == "BUY":
                    total += txn.quantity
                else:
                    total -= txn.quantity
        return max(0, total)

    def _get_current_avg_cost(self, ticker: str) -> float:
        """
        Calculate current weighted average cost for a ticker.
        Uses weighted average method - avg cost updates on buys, stays same on sells.
        """
        ticker = ticker.upper()
        total_qty = 0.0
        total_cost = 0.0

        # Sort transactions by date to process chronologically
        sorted_txns = sorted(
            [t for t in self._transactions if t.ticker == ticker],
            key=lambda t: (t.date, t.created_at)
        )

        for txn in sorted_txns:
            if txn.type == "BUY":
                # Weighted average: new_avg = (old_qty * old_avg + new_qty * new_price) / (old_qty + new_qty)
                total_cost = total_qty * (total_cost / total_qty if total_qty > 0 else 0) + txn.quantity * txn.price_per_share
                total_qty += txn.quantity
            else:  # SELL
                total_qty -= txn.quantity
                # avg cost stays the same, just reduce quantity

        if total_qty <= 0:
            return 0.0

        return total_cost / total_qty

    def get_position(self, ticker: str, current_price: float = None, name: str = "") -> Position:
        """
        Calculate position for a single ticker from transaction history.

        Args:
            ticker: Stock ticker
            current_price: Current market price (optional, for P&L calculation)
            name: Company name (optional)
        """
        ticker = ticker.upper()

        # Get all transactions for this ticker, sorted chronologically
        txns = sorted(
            [t for t in self._transactions if t.ticker == ticker],
            key=lambda t: (t.date, t.created_at)
        )

        if not txns:
            return Position(ticker=ticker, name=name, status="NONE")

        # Calculate position using weighted average
        total_qty = 0.0
        weighted_cost = 0.0
        total_realized_pnl = 0.0
        total_fees = 0.0
        first_buy_date = None
        last_txn_date = None
        close_date = None

        for txn in txns:
            total_fees += txn.fees
            last_txn_date = txn.date

            if txn.type == "BUY":
                if first_buy_date is None:
                    first_buy_date = txn.date

                # Update weighted average cost
                new_total_qty = total_qty + txn.quantity
                if new_total_qty > 0:
                    weighted_cost = (total_qty * weighted_cost + txn.quantity * txn.price_per_share) / new_total_qty
                total_qty = new_total_qty

            else:  # SELL
                # Realized P&L = (sell_price - avg_cost) * qty
                if txn.realized_pnl is not None:
                    total_realized_pnl += txn.realized_pnl
                else:
                    total_realized_pnl += (txn.price_per_share - weighted_cost) * txn.quantity - txn.fees

                total_qty -= txn.quantity

                # Check if position is closed
                if total_qty <= 0.0001:
                    total_qty = 0
                    close_date = txn.date

        # Determine status
        status = "CLOSED" if total_qty <= 0 else "OPEN"

        # Calculate current value and unrealized P&L
        if current_price is None and self.get_price:
            current_price = self.get_price(ticker) or 0

        current_price = current_price or 0
        total_invested = weighted_cost * total_qty
        current_value = current_price * total_qty
        unrealized_pnl = current_value - total_invested if total_qty > 0 else 0
        unrealized_pnl_pct = (unrealized_pnl / total_invested * 100) if total_invested > 0 else 0

        # Calculate holding days
        holding_days = 0
        if first_buy_date:
            end_date = close_date or datetime.now().strftime('%Y-%m-%d')
            try:
                start = datetime.strptime(first_buy_date, '%Y-%m-%d')
                end = datetime.strptime(end_date, '%Y-%m-%d')
                holding_days = (end - start).days
            except:
                pass

        return Position(
            ticker=ticker,
            name=name,
            status=status,
            total_qty=total_qty,
            avg_cost=weighted_cost,
            total_invested=total_invested,
            current_price=current_price,
            current_value=current_value,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_pct=unrealized_pnl_pct,
            realized_pnl=total_realized_pnl,
            total_fees=total_fees,
            first_buy_date=first_buy_date,
            last_transaction_date=last_txn_date,
            close_date=close_date,
            holding_days=holding_days,
            transactions=txns
        )

    def get_all_positions(self, price_data: Dict[str, float] = None,
                         name_data: Dict[str, str] = None) -> PortfolioSummary:
        """
        Calculate all positions from transaction history.

        Args:
            price_data: Dict mapping ticker to current price
            name_data: Dict mapping ticker to company name
        """
        price_data = price_data or {}
        name_data = name_data or {}

        # Get unique tickers
        tickers = set(t.ticker for t in self._transactions)

        open_positions = []
        closed_positions = []
        total_realized = 0.0
        total_unrealized = 0.0
        total_fees = 0.0
        total_invested = 0.0
        total_value = 0.0
        total_holding_days = 0
        winning_closed = 0

        for ticker in tickers:
            price = price_data.get(ticker, 0)
            name = name_data.get(ticker, ticker)
            pos = self.get_position(ticker, price, name)

            if pos.status == "OPEN":
                open_positions.append(pos)
                total_unrealized += pos.unrealized_pnl
                total_invested += pos.total_invested
                total_value += pos.current_value
            else:
                closed_positions.append(pos)
                if pos.realized_pnl > 0:
                    winning_closed += 1

            total_realized += pos.realized_pnl
            total_fees += pos.total_fees
            total_holding_days += pos.holding_days

        # Sort positions
        open_positions.sort(key=lambda p: p.current_value, reverse=True)
        closed_positions.sort(key=lambda p: p.close_date or '', reverse=True)

        # Calculate metrics
        win_rate = (winning_closed / len(closed_positions) * 100) if closed_positions else 0
        avg_holding = total_holding_days / len(tickers) if tickers else 0

        return PortfolioSummary(
            open_positions=open_positions,
            closed_positions=closed_positions,
            total_realized_pnl=total_realized,
            total_unrealized_pnl=total_unrealized,
            total_pnl=total_realized + total_unrealized,
            total_fees=total_fees,
            total_invested=total_invested,
            total_current_value=total_value,
            win_rate=win_rate,
            avg_holding_days=avg_holding,
            total_transactions=len(self._transactions)
        )

    def get_pnl_history(self, start_date: str = None, end_date: str = None) -> List[Dict]:
        """
        Get P&L history day by day for charting.
        Shows cumulative realized P&L over time.
        """
        if not self._transactions:
            return []

        # Get all sell transactions sorted by date
        sells = sorted(
            [t for t in self._transactions if t.type == "SELL"],
            key=lambda t: t.date
        )

        if not sells:
            return []

        # Build cumulative P&L
        history = []
        cumulative_pnl = 0.0

        for txn in sells:
            if start_date and txn.date < start_date:
                continue
            if end_date and txn.date > end_date:
                continue

            pnl = txn.realized_pnl or 0
            cumulative_pnl += pnl

            history.append({
                'date': txn.date,
                'ticker': txn.ticker,
                'realized_pnl': round(pnl, 2),
                'cumulative_pnl': round(cumulative_pnl, 2)
            })

        return history


def create_position_manager(transactions_file: str, get_price_func=None) -> PositionManager:
    """Factory function to create position manager"""
    return PositionManager(transactions_file, get_price_func)

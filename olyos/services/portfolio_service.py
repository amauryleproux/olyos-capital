"""
Portfolio Service - Centralizes portfolio loading and position data extraction.
Eliminates the duplicated load_portfolio + iterate pattern found ~8 times in app.py.
"""

import math
from typing import Dict, List, Optional, Tuple, Any

from olyos.logger import get_logger

log = get_logger('portfolio_service')


class PortfolioService:
    """Centralized portfolio data access."""

    def __init__(self, load_portfolio_func, save_portfolio_func, load_watchlist_func):
        self._load_portfolio = load_portfolio_func
        self._save_portfolio = save_portfolio_func
        self._load_watchlist = load_watchlist_func

    def load_dataframe(self):
        """Load raw portfolio DataFrame. Returns (df, error)."""
        return self._load_portfolio()

    def load_dataframe_or_raise(self):
        """Load portfolio DataFrame, raise on error."""
        df, err = self._load_portfolio()
        if err or df is None:
            raise Exception(err or "Could not load portfolio")
        return df

    def save_dataframe(self, df):
        """Save portfolio DataFrame back to file."""
        self._save_portfolio(df)

    def load_watchlist(self) -> List[Dict]:
        """Load watchlist."""
        return self._load_watchlist()

    def get_price_name_data(self) -> Tuple[Dict[str, float], Dict[str, str]]:
        """Extract price_data and name_data dicts from portfolio.
        This pattern was duplicated ~8 times in the original code."""
        df, err = self._load_portfolio()
        price_data = {}
        name_data = {}
        if df is not None:
            for _, row in df.iterrows():
                ticker = row.get('ticker', '').upper()
                if ticker:
                    price_data[ticker] = float(row.get('price_eur', 0) or 0)
                    name_data[ticker] = row.get('name', ticker)
        return price_data, name_data

    def get_positions_list(self, include_metrics: bool = False) -> Tuple[List[Dict], float]:
        """Build positions list with optional metrics (PE, ROE).
        Returns (positions, total_value).
        This pattern was duplicated in rebalancing and heatmap endpoints."""
        df = self.load_dataframe_or_raise()
        positions = []
        total_value = 0.0

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
                'higgons_score': int(row.get('score_higgons', row.get('higgons_score', 5)) or 5),
            }

            if include_metrics:
                # PE
                pe = None
                for col in ['pe', 'pe_ttm', 'trailing_pe']:
                    if col in df.columns:
                        val = row.get(col)
                        if val is not None and not (isinstance(val, float) and math.isnan(val)):
                            pe = float(val)
                            break
                pos_data['pe'] = pe

                # ROE
                roe = None
                for col in ['roe', 'roe_ttm']:
                    if col in df.columns:
                        val = row.get(col)
                        if val is not None and not (isinstance(val, float) and math.isnan(val)):
                            roe = float(val)
                            if -1 < roe < 1:
                                roe = roe * 100
                            break
                pos_data['roe'] = roe
                pos_data['verdict'] = str(row.get('verdict', '') or '')

            positions.append(pos_data)

        # Add weights
        for pos in positions:
            pos['weight'] = (pos['value'] / total_value * 100) if total_value > 0 else 0

        return positions, total_value

    def get_dividend_positions(self, include_price: bool = True) -> List[Dict]:
        """Build positions list for dividends service."""
        df = self.load_dataframe_or_raise()
        positions = []
        for _, row in df.iterrows():
            pos = {
                'ticker': row.get('ticker', ''),
                'name': row.get('name', row.get('ticker', '')),
                'quantity': row.get('qty', row.get('quantity', 0)),
            }
            if include_price:
                pos['price'] = row.get('price_eur', row.get('price', 0))
                pos['cost'] = row.get('avg_cost_eur', row.get('cost', 0))
            positions.append(pos)
        return positions

    def get_all_tickers(self, include_watchlist: bool = False) -> Tuple[List[str], Dict[str, str]]:
        """Get all tickers from portfolio (and optionally watchlist).
        Returns (tickers, ticker_names_dict)."""
        tickers = []
        ticker_names = {}

        df, _ = self._load_portfolio()
        if df is not None and 'ticker' in df.columns:
            for _, row in df.iterrows():
                t = row.get('ticker', '').upper()
                if t:
                    tickers.append(t)
                    ticker_names[t] = row.get('name', t)

        if include_watchlist:
            watchlist = self._load_watchlist()
            for w in watchlist:
                t = w.get('ticker', '').upper()
                if t:
                    tickers.append(t)
                    if t not in ticker_names:
                        ticker_names[t] = w.get('name', t)
            tickers = list(set(tickers))

        return tickers, ticker_names

    def get_heatmap_positions(self) -> Tuple[List[Dict], float]:
        """Build positions list with full metrics for heatmap visualization."""
        df = self.load_dataframe_or_raise()
        positions = []
        total_value = 0.0

        for _, row in df.iterrows():
            qty = float(row.get('qty', 0) or 0)
            if qty <= 0:
                continue

            price = float(row.get('price_eur', 0) or 0)
            value = price * qty
            total_value += value

            cost = float(row.get('avg_cost_eur', 0) or 0)
            total_cost = cost * qty
            pnl_pct = ((value / total_cost) - 1) * 100 if total_cost > 0 else 0

            change_pct = float(row.get('change_pct', row.get('pct_change', 0)) or 0)
            if -1 < change_pct < 1 and change_pct != 0:
                change_pct = change_pct * 100

            ytd_pct = float(row.get('ytd_pct', row.get('perf_ytd', pnl_pct)) or pnl_pct)
            if -1 < ytd_pct < 1 and ytd_pct != 0:
                ytd_pct = ytd_pct * 100

            pe = None
            for col in ['pe', 'pe_ttm', 'trailing_pe']:
                if col in df.columns:
                    val = row.get(col)
                    if val is not None and not (isinstance(val, float) and math.isnan(val)):
                        pe = float(val)
                        break

            pos_data = {
                'ticker': str(row.get('ticker', '')),
                'name': str(row.get('name', '')),
                'value': value,
                'price': price,
                'cost': cost,
                'sector': str(row.get('sector', 'Other') or 'Other'),
                'country': str(row.get('country', '') or ''),
                'change_pct': change_pct,
                'ytd_pct': ytd_pct,
                'pnl_pct': pnl_pct,
                'pe': pe,
                'higgons_score': int(row.get('score_higgons', row.get('higgons_score', 5)) or 5),
            }
            positions.append(pos_data)

        for pos in positions:
            pos['weight'] = (pos['value'] / total_value * 100) if total_value > 0 else 0

        return positions, total_value

    def sync_transaction_to_portfolio(self, ticker: str, txn_type: str, quantity: float, price: float):
        """Sync a transaction to portfolio.xlsx (update qty and avg cost)."""
        try:
            df, load_err = self._load_portfolio()
            if df is None or load_err:
                return

            mask = df['ticker'].str.upper() == ticker.upper()
            if not mask.any():
                return

            idx = df[mask].index[0]
            current_qty = float(df.loc[idx, 'qty'] or 0)
            current_cost = float(df.loc[idx, 'avg_cost_eur'] or 0)

            if txn_type == 'SELL':
                new_qty = max(0, current_qty - quantity)
                df.loc[idx, 'qty'] = new_qty
                log.info(f"Portfolio synced: {ticker} qty {current_qty} -> {new_qty}")
            elif txn_type == 'BUY':
                new_qty = current_qty + quantity
                total_old = current_qty * current_cost
                total_new = quantity * price
                new_avg_cost = (total_old + total_new) / new_qty if new_qty > 0 else price
                df.loc[idx, 'qty'] = new_qty
                df.loc[idx, 'avg_cost_eur'] = new_avg_cost
                log.info(f"Portfolio synced: {ticker} qty {current_qty} -> {new_qty}, cost {current_cost:.2f} -> {new_avg_cost:.2f}")

            self._save_portfolio(df)
        except Exception as e:
            log.warning(f"Could not sync portfolio.xlsx: {e}")

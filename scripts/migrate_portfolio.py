#!/usr/bin/env python3
"""
Migration Script: Portfolio to Transactions
============================================
Converts existing portfolio.xlsx positions to transactions.json

This script reads the current portfolio state and creates initial BUY transactions
for each position, using the current avg_cost as the purchase price.

Usage:
    python scripts/migrate_portfolio.py

The script will:
1. Read data/portfolio.xlsx
2. For each position with qty > 0, create a BUY transaction
3. Write results to data/transactions.json
4. Create a backup of any existing transactions.json
"""

import os
import sys
import json
import shutil
from datetime import datetime

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

try:
    import pandas as pd
except ImportError:
    print("ERROR: pandas is required. Install with: pip install pandas openpyxl")
    sys.exit(1)


def migrate_portfolio():
    """Convert portfolio.xlsx to transactions.json"""

    # Paths
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    portfolio_file = os.path.join(base_dir, 'data', 'portfolio.xlsx')
    transactions_file = os.path.join(base_dir, 'data', 'transactions.json')

    # Check if portfolio exists
    if not os.path.exists(portfolio_file):
        print(f"ERROR: Portfolio file not found: {portfolio_file}")
        return False

    # Backup existing transactions if any
    if os.path.exists(transactions_file):
        backup_file = transactions_file.replace('.json', f'_backup_{datetime.now().strftime("%Y%m%d_%H%M%S")}.json')
        shutil.copy(transactions_file, backup_file)
        print(f"Backed up existing transactions to: {backup_file}")

    # Read portfolio
    print(f"Reading portfolio from: {portfolio_file}")
    df = pd.read_excel(portfolio_file)

    # Normalize column names
    df.columns = [c.lower().strip().replace(' ', '_') for c in df.columns]

    print(f"Found {len(df)} rows in portfolio")
    print(f"Columns: {df.columns.tolist()}")

    # Create transactions
    transactions = []
    today = datetime.now().strftime('%Y-%m-%d')
    created_at = datetime.now().isoformat()

    for idx, row in df.iterrows():
        ticker = str(row.get('ticker', '')).strip()
        name = str(row.get('name', ticker)).strip()
        qty = float(row.get('qty', row.get('quantity', 0)))
        avg_cost = float(row.get('avg_cost_eur', row.get('avg_cost', row.get('pru', 0))))

        if not ticker or qty <= 0:
            print(f"  Skipping row {idx}: ticker={ticker}, qty={qty}")
            continue

        # Create transaction ID
        txn_id = f"TXN-MIGRATE-{idx + 1:03d}"

        transaction = {
            "id": txn_id,
            "ticker": ticker.upper(),
            "type": "BUY",
            "date": today,
            "quantity": qty,
            "price_per_share": avg_cost,
            "currency": "EUR",
            "fees": 0.0,
            "notes": f"Migration from portfolio.xlsx - {name}",
            "created_at": created_at,
            "avg_cost_at_sale": None,
            "realized_pnl": None
        }

        transactions.append(transaction)
        total_value = qty * avg_cost
        print(f"  Created: {txn_id} - BUY {qty:.2f} {ticker} @ {avg_cost:.2f} EUR = {total_value:.2f} EUR")

    # Save transactions
    print(f"\nSaving {len(transactions)} transactions to: {transactions_file}")

    with open(transactions_file, 'w', encoding='utf-8') as f:
        json.dump(transactions, f, indent=2, ensure_ascii=False)

    print("\nMigration complete!")
    print(f"Total transactions created: {len(transactions)}")

    # Summary
    total_invested = sum(t['quantity'] * t['price_per_share'] for t in transactions)
    print(f"Total invested value: {total_invested:,.2f} EUR")

    return True


if __name__ == '__main__':
    print("=" * 60)
    print("OLYOS CAPITAL - Portfolio Migration Script")
    print("=" * 60)
    print()

    success = migrate_portfolio()

    if success:
        print("\n[SUCCESS] Migration completed successfully!")
        print("\nNext steps:")
        print("1. Verify transactions.json looks correct")
        print("2. The portfolio.xlsx is no longer the source of truth")
        print("3. All new trades should be added via the Transaction API")
    else:
        print("\n[FAILED] Migration failed!")
        sys.exit(1)

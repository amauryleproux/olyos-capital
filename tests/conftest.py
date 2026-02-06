"""
Pytest configuration and shared fixtures for Olyos Capital tests.
"""

import json
import math
import os
import tempfile
from datetime import datetime, timedelta
from typing import Any, Dict

import pytest


# =============================================================================
# TEMPORARY DIRECTORY FIXTURES
# =============================================================================

@pytest.fixture
def temp_dir():
    """Create a temporary directory for test files."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield tmpdir


@pytest.fixture
def temp_json_file(temp_dir):
    """Create a temporary JSON file path."""
    return os.path.join(temp_dir, "test_data.json")


@pytest.fixture
def temp_cache_file(temp_dir):
    """Create a temporary cache file path."""
    return os.path.join(temp_dir, "test_cache.json")


# =============================================================================
# SAMPLE DATA FIXTURES
# =============================================================================

@pytest.fixture
def sample_json_data():
    """Sample JSON data for testing."""
    return {
        "name": "Test Portfolio",
        "positions": [
            {"ticker": "AAPL.PA", "qty": 100, "price": 150.50},
            {"ticker": "MSFT.PA", "qty": 50, "price": 300.25}
        ],
        "metadata": {
            "created": "2024-01-15",
            "updated": "2024-01-20"
        }
    }


@pytest.fixture
def sample_cache_data():
    """Sample cache data with timestamp."""
    return {
        "_cache_date": datetime.now().strftime('%Y-%m-%d'),
        "data": [1, 2, 3, 4, 5],
        "ticker": "TEST.PA"
    }


@pytest.fixture
def expired_cache_data():
    """Cache data that has expired (30+ days old)."""
    old_date = (datetime.now() - timedelta(days=60)).strftime('%Y-%m-%d')
    return {
        "_cache_date": old_date,
        "data": [1, 2, 3],
        "ticker": "OLD.PA"
    }


@pytest.fixture
def sample_prices_dict():
    """Sample price data dictionary for testing."""
    return {
        "2024-01-15": {"open": 100.0, "high": 105.0, "low": 99.0, "close": 102.0},
        "2024-01-14": {"open": 98.0, "high": 101.0, "low": 97.0, "close": 100.0},
        "2024-01-12": {"open": 97.0, "high": 99.0, "low": 96.0, "close": 98.0},
        "2024-01-10": {"open": 95.0, "high": 98.0, "low": 94.0, "close": 97.0}
    }


# =============================================================================
# HELPER FIXTURES
# =============================================================================

@pytest.fixture
def create_json_file(temp_dir):
    """Factory fixture to create JSON files with custom data."""
    def _create(filename: str, data: Dict[str, Any]) -> str:
        filepath = os.path.join(temp_dir, filename)
        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f)
        return filepath
    return _create


@pytest.fixture
def create_invalid_json_file(temp_dir):
    """Create an invalid JSON file for error handling tests."""
    filepath = os.path.join(temp_dir, "invalid.json")
    with open(filepath, 'w', encoding='utf-8') as f:
        f.write("{not valid json")
    return filepath


# =============================================================================
# NaN VALUE FIXTURES
# =============================================================================

@pytest.fixture
def nan_value():
    """Return a NaN float value."""
    return float('nan')


@pytest.fixture
def inf_value():
    """Return an infinity float value."""
    return float('inf')


# =============================================================================
# DATE FIXTURES
# =============================================================================

@pytest.fixture
def test_datetime():
    """Return a fixed datetime for testing."""
    return datetime(2024, 1, 15, 10, 30, 0)


@pytest.fixture
def weekday_datetime():
    """Return a weekday datetime (Wednesday)."""
    return datetime(2024, 1, 17, 10, 0, 0)  # Wednesday


@pytest.fixture
def weekend_datetime():
    """Return a weekend datetime (Saturday)."""
    return datetime(2024, 1, 20, 10, 0, 0)  # Saturday


# =============================================================================
# STOCK DATA FIXTURES
# =============================================================================

@pytest.fixture
def sample_stock_fundamentals():
    """Sample stock fundamental data."""
    return {
        "ticker": "TEST.PA",
        "name": "Test Company",
        "pe": 12.5,
        "roe": 0.15,
        "debt_equity": 0.45,
        "market_cap": 5000000000,
        "sector": "Technology"
    }


@pytest.fixture
def sample_portfolio():
    """Sample portfolio data."""
    return [
        {"ticker": "AAPL.PA", "name": "Apple", "qty": 100, "price": 150.0, "value": 15000.0},
        {"ticker": "MSFT.PA", "name": "Microsoft", "qty": 50, "price": 300.0, "value": 15000.0},
        {"ticker": "GOOG.PA", "name": "Alphabet", "qty": 20, "price": 500.0, "value": 10000.0}
    ]


# =============================================================================
# SIGNAL TEST DATA
# =============================================================================

@pytest.fixture
def achat_signal_data():
    """Data that should produce ACHAT signal."""
    return {"pe": 10, "roe": 0.15, "score": 60}


@pytest.fixture
def watch_signal_data():
    """Data that should produce WATCH signal."""
    return {"pe": 14, "roe": 0.09, "score": 45}


@pytest.fixture
def cher_signal_data():
    """Data that should produce CHER signal."""
    return {"pe": 25, "roe": 0.04, "score": 30}


@pytest.fixture
def neutre_signal_data():
    """Data that should produce NEUTRE signal."""
    return {"pe": 18, "roe": 0.06, "score": 40}

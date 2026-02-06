"""
Utility functions for the Olyos Capital portfolio management application.

This module provides common utility functions for:
- Safe type conversions
- JSON file operations
- Value formatting
- Date/time utilities
- Cache management
- Exchange/country mappings
"""

import json
import math
import os
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional, TypeVar, Union

T = TypeVar('T')


# =============================================================================
# TYPE CONVERSION UTILITIES
# =============================================================================

def safe_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    """
    Safely convert a value to float.

    Handles None, NaN values, and conversion errors gracefully.

    Args:
        value: The value to convert to float.
        default: The default value to return if conversion fails.

    Returns:
        The float value, or the default if conversion is not possible.

    Examples:
        >>> safe_float("123.45")
        123.45
        >>> safe_float(None, 0.0)
        0.0
        >>> safe_float("invalid", -1.0)
        -1.0
    """
    if value is None:
        return default

    # Handle NaN values (common in pandas/numpy)
    if isinstance(value, float) and math.isnan(value):
        return default

    try:
        return float(value)
    except (ValueError, TypeError):
        return default


def safe_int(value: Any, default: Optional[int] = None) -> Optional[int]:
    """
    Safely convert a value to int.

    Args:
        value: The value to convert to int.
        default: The default value to return if conversion fails.

    Returns:
        The int value, or the default if conversion is not possible.

    Examples:
        >>> safe_int("123")
        123
        >>> safe_int(None, 0)
        0
    """
    if value is None:
        return default

    if isinstance(value, float) and math.isnan(value):
        return default

    try:
        return int(value)
    except (ValueError, TypeError):
        return default


def safe_str(value: Any, default: str = "") -> str:
    """
    Safely convert a value to string.

    Args:
        value: The value to convert to string.
        default: The default value to return if value is None.

    Returns:
        The string representation of the value.
    """
    if value is None:
        return default
    return str(value)


# =============================================================================
# JSON FILE OPERATIONS
# =============================================================================

def load_json(filepath: str, default: T) -> T:
    """
    Load JSON data from a file with error handling.

    Args:
        filepath: Path to the JSON file.
        default: Default value to return if file doesn't exist or is invalid.

    Returns:
        The parsed JSON data, or the default value on error.

    Examples:
        >>> load_json("config.json", {})
        {'key': 'value'}
        >>> load_json("missing.json", [])
        []
    """
    try:
        if os.path.exists(filepath):
            with open(filepath, 'r', encoding='utf-8') as f:
                return json.load(f)
        return default
    except (json.JSONDecodeError, IOError, OSError):
        return default


def save_json(filepath: str, data: Any, indent: int = 2) -> bool:
    """
    Save data to a JSON file.

    Args:
        filepath: Path to the JSON file.
        data: Data to serialize and save.
        indent: JSON indentation level (default: 2).

    Returns:
        True if save was successful, False otherwise.

    Examples:
        >>> save_json("output.json", {"key": "value"})
        True
    """
    try:
        # Ensure directory exists
        directory = os.path.dirname(filepath)
        if directory:
            os.makedirs(directory, exist_ok=True)

        with open(filepath, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=indent, ensure_ascii=False)
        return True
    except (IOError, OSError, TypeError) as e:
        print(f"Error saving JSON to {filepath}: {e}")
        return False


# =============================================================================
# VALUE FORMATTING
# =============================================================================

def fmt_val(value: Any, decimals: int = 2, placeholder: str = '-') -> str:
    """
    Format a numeric value safely for display.

    Handles None values and NaN gracefully, using French-style
    space as thousands separator.

    Args:
        value: The value to format.
        decimals: Number of decimal places (default: 2).
        placeholder: String to return for invalid values (default: '-').

    Returns:
        Formatted string representation of the value.

    Examples:
        >>> fmt_val(1234567.89)
        '1 234 567.89'
        >>> fmt_val(None)
        '-'
        >>> fmt_val(42.5, decimals=0)
        '43'
    """
    if value is None:
        return placeholder

    if isinstance(value, float) and math.isnan(value):
        return placeholder

    try:
        formatted = f"{value:,.{decimals}f}"
        # Replace comma with space for French-style formatting
        return formatted.replace(",", " ")
    except (ValueError, TypeError):
        return placeholder


def fmt_pct(value: Any, decimals: int = 2, placeholder: str = '-') -> str:
    """
    Format a value as a percentage.

    Args:
        value: The value to format (as decimal, e.g., 0.15 for 15%).
        decimals: Number of decimal places (default: 2).
        placeholder: String to return for invalid values (default: '-').

    Returns:
        Formatted percentage string with % symbol.

    Examples:
        >>> fmt_pct(0.1567)
        '15.67%'
        >>> fmt_pct(None)
        '-'
    """
    if value is None:
        return placeholder

    if isinstance(value, float) and math.isnan(value):
        return placeholder

    try:
        pct_value = float(value) * 100
        return f"{pct_value:.{decimals}f}%"
    except (ValueError, TypeError):
        return placeholder


def fmt_currency(
    value: Any,
    currency: str = "EUR",
    decimals: int = 2,
    placeholder: str = '-'
) -> str:
    """
    Format a value as currency.

    Args:
        value: The value to format.
        currency: Currency symbol or code (default: 'EUR').
        decimals: Number of decimal places (default: 2).
        placeholder: String to return for invalid values (default: '-').

    Returns:
        Formatted currency string.

    Examples:
        >>> fmt_currency(1234.56)
        '1 234.56 EUR'
        >>> fmt_currency(1234.56, currency='$')
        '1 234.56 $'
    """
    formatted = fmt_val(value, decimals, placeholder)
    if formatted == placeholder:
        return placeholder
    return f"{formatted} {currency}"


def fmt_large_number(value: Any, placeholder: str = '-') -> str:
    """
    Format large numbers with K/M/B suffixes.

    Args:
        value: The value to format.
        placeholder: String to return for invalid values (default: '-').

    Returns:
        Formatted string with appropriate suffix.

    Examples:
        >>> fmt_large_number(1500000)
        '1.50M'
        >>> fmt_large_number(2500000000)
        '2.50B'
        >>> fmt_large_number(1500)
        '1.50K'
    """
    if value is None:
        return placeholder

    try:
        num = float(value)
        if math.isnan(num):
            return placeholder

        if abs(num) >= 1e9:
            return f"{num / 1e9:.2f}B"
        elif abs(num) >= 1e6:
            return f"{num / 1e6:.2f}M"
        elif abs(num) >= 1e3:
            return f"{num / 1e3:.2f}K"
        else:
            return f"{num:.2f}"
    except (ValueError, TypeError):
        return placeholder


# =============================================================================
# DATE/TIME UTILITIES
# =============================================================================

def parse_date(
    date_str: str,
    formats: Optional[List[str]] = None
) -> Optional[datetime]:
    """
    Parse a date string using multiple possible formats.

    Args:
        date_str: The date string to parse.
        formats: List of date formats to try (default: common formats).

    Returns:
        Parsed datetime object, or None if parsing fails.

    Examples:
        >>> parse_date("2024-01-15")
        datetime.datetime(2024, 1, 15, 0, 0)
        >>> parse_date("15/01/2024")
        datetime.datetime(2024, 1, 15, 0, 0)
    """
    if not date_str:
        return None

    if formats is None:
        formats = [
            '%Y-%m-%d',
            '%d/%m/%Y',
            '%d-%m-%Y',
            '%Y/%m/%d',
            '%d.%m.%Y',
            '%Y-%m-%dT%H:%M:%S',
            '%Y-%m-%d %H:%M:%S',
        ]

    for fmt in formats:
        try:
            return datetime.strptime(date_str, fmt)
        except ValueError:
            continue

    return None


def format_date(
    dt: Optional[datetime],
    fmt: str = '%Y-%m-%d'
) -> str:
    """
    Format a datetime object to string.

    Args:
        dt: The datetime object to format.
        fmt: Output format string (default: '%Y-%m-%d').

    Returns:
        Formatted date string, or empty string if dt is None.

    Examples:
        >>> format_date(datetime(2024, 1, 15))
        '2024-01-15'
    """
    if dt is None:
        return ''
    return dt.strftime(fmt)


def get_date_range(
    days_back: int,
    end_date: Optional[datetime] = None
) -> tuple[str, str]:
    """
    Get a date range as (start_date, end_date) strings.

    Args:
        days_back: Number of days to go back from end_date.
        end_date: End date (default: today).

    Returns:
        Tuple of (start_date, end_date) in 'YYYY-MM-DD' format.

    Examples:
        >>> get_date_range(30)
        ('2024-01-01', '2024-01-31')  # Example output
    """
    if end_date is None:
        end_date = datetime.now()

    start_date = end_date - timedelta(days=days_back)

    return (
        start_date.strftime('%Y-%m-%d'),
        end_date.strftime('%Y-%m-%d')
    )


def is_market_open(
    dt: Optional[datetime] = None,
    market_open_hour: int = 9,
    market_close_hour: int = 17,
    weekend_closed: bool = True
) -> bool:
    """
    Check if the market is likely open at a given time.

    Args:
        dt: Datetime to check (default: now).
        market_open_hour: Hour when market opens (default: 9).
        market_close_hour: Hour when market closes (default: 17).
        weekend_closed: Whether market is closed on weekends (default: True).

    Returns:
        True if market is likely open, False otherwise.
    """
    if dt is None:
        dt = datetime.now()

    # Check weekend
    if weekend_closed and dt.weekday() >= 5:
        return False

    # Check hours
    return market_open_hour <= dt.hour < market_close_hour


# =============================================================================
# CACHE UTILITIES
# =============================================================================

def is_cache_valid(
    cache_file: str,
    max_days: int,
    date_key: str = '_cache_date'
) -> bool:
    """
    Check if a cache file exists and is not too old.

    Args:
        cache_file: Path to the cache file.
        max_days: Maximum age in days for the cache to be valid.
        date_key: Key in the JSON data storing the cache date.

    Returns:
        True if cache exists and is valid, False otherwise.

    Examples:
        >>> is_cache_valid("data_cache.json", max_days=7)
        True
    """
    if not os.path.exists(cache_file):
        return False

    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            data = json.load(f)

        cache_date_str = data.get(date_key, '2000-01-01')
        cache_date = datetime.strptime(cache_date_str, '%Y-%m-%d')

        return (datetime.now() - cache_date).days < max_days
    except (json.JSONDecodeError, IOError, ValueError, KeyError):
        return False


def load_from_cache(cache_file: str) -> Optional[Dict[str, Any]]:
    """
    Load data from a cache file.

    Args:
        cache_file: Path to the cache file.

    Returns:
        Cached data as dictionary, or None if loading fails.
    """
    try:
        with open(cache_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    except (json.JSONDecodeError, IOError, OSError):
        return None


def save_to_cache(
    cache_file: str,
    data: Dict[str, Any],
    date_key: str = '_cache_date'
) -> bool:
    """
    Save data to a cache file with a timestamp.

    Args:
        cache_file: Path to the cache file.
        data: Data to cache (will be modified to add timestamp).
        date_key: Key to use for storing the cache date.

    Returns:
        True if save was successful, False otherwise.
    """
    # Ensure directory exists
    directory = os.path.dirname(cache_file)
    if directory:
        os.makedirs(directory, exist_ok=True)

    # Add cache timestamp
    data[date_key] = datetime.now().strftime('%Y-%m-%d')

    try:
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False)
        return True
    except (IOError, OSError, TypeError):
        return False


def get_cache_path(
    cache_dir: str,
    category: str,
    key: str
) -> str:
    """
    Get a cache file path for a given category and key.

    Sanitizes the key to be filesystem-safe.

    Args:
        cache_dir: Base cache directory.
        category: Category subdirectory (e.g., 'fundamentals', 'prices').
        key: Unique key for the cached item (e.g., ticker symbol).

    Returns:
        Full path to the cache file.

    Examples:
        >>> get_cache_path("/cache", "prices", "AAPL.PA")
        '/cache/prices/AAPL_PA.json'
    """
    # Sanitize key for filesystem
    safe_key = key.replace('.', '_').replace('^', '_').replace('/', '_')

    # Ensure directory exists
    category_dir = os.path.join(cache_dir, category)
    os.makedirs(category_dir, exist_ok=True)

    return os.path.join(category_dir, f'{safe_key}.json')


# =============================================================================
# EXCHANGE/COUNTRY MAPPINGS
# =============================================================================

# Exchange to country code mapping
EXCHANGE_COUNTRY_MAP: Dict[str, str] = {
    # France
    'PA': 'FR', 'XPAR': 'FR', 'Paris': 'FR',
    # Netherlands
    'AS': 'NL', 'XAMS': 'NL', 'Amsterdam': 'NL',
    # Belgium
    'BR': 'BE', 'XBRU': 'BE', 'Brussels': 'BE',
    # Italy
    'MI': 'IT', 'XMIL': 'IT', 'Milan': 'IT',
    # Spain
    'MC': 'ES', 'XMAD': 'ES', 'Madrid': 'ES',
    # Germany
    'XETRA': 'DE', 'XFRA': 'DE', 'Frankfurt': 'DE',
    # United Kingdom
    'LSE': 'UK', 'XLON': 'UK', 'London': 'UK',
    # Switzerland
    'SW': 'CH', 'XSWX': 'CH', 'Swiss': 'CH',
    # Austria
    'VI': 'AT', 'XWBO': 'AT', 'Vienna': 'AT',
    # Finland
    'HE': 'FI', 'XHEL': 'FI', 'Helsinki': 'FI',
    # Sweden
    'ST': 'SE', 'XSTO': 'SE', 'Stockholm': 'SE',
    # Norway
    'OL': 'NO', 'XOSL': 'NO', 'Oslo': 'NO',
    # Denmark
    'CO': 'DK', 'XCSE': 'DK', 'Copenhagen': 'DK',
    # Portugal
    'LS': 'PT', 'XLIS': 'PT', 'Lisbon': 'PT',
    # Greece
    'AT': 'GR', 'XATH': 'GR', 'Athens': 'GR',
}


def get_country_from_exchange(exchange: str, default: str = 'EU') -> str:
    """
    Get country code from exchange identifier.

    Args:
        exchange: Exchange identifier (e.g., 'PA', 'XPAR', 'Paris').
        default: Default country code if exchange is not found.

    Returns:
        Two-letter country code.

    Examples:
        >>> get_country_from_exchange('PA')
        'FR'
        >>> get_country_from_exchange('XETRA')
        'DE'
        >>> get_country_from_exchange('UNKNOWN')
        'EU'
    """
    # Try exact match first
    if exchange in EXCHANGE_COUNTRY_MAP:
        return EXCHANGE_COUNTRY_MAP[exchange]

    # Try case-insensitive partial match
    exchange_lower = exchange.lower()
    for key, country in EXCHANGE_COUNTRY_MAP.items():
        if key.lower() in exchange_lower:
            return country

    return default


# =============================================================================
# FILE UTILITIES
# =============================================================================

def ensure_dir(directory: str) -> bool:
    """
    Ensure a directory exists, creating it if necessary.

    Args:
        directory: Path to the directory.

    Returns:
        True if directory exists or was created, False on error.
    """
    try:
        os.makedirs(directory, exist_ok=True)
        return True
    except OSError:
        return False


def sanitize_filename(filename: str, replacement: str = '_') -> str:
    """
    Sanitize a string to be safe for use as a filename.

    Args:
        filename: The string to sanitize.
        replacement: Character to replace invalid characters with.

    Returns:
        Sanitized filename string.

    Examples:
        >>> sanitize_filename("my/file:name.txt")
        'my_file_name.txt'
    """
    # Characters not allowed in filenames on Windows
    invalid_chars = '<>:"/\\|?*'

    result = filename
    for char in invalid_chars:
        result = result.replace(char, replacement)

    # Remove leading/trailing spaces and dots
    result = result.strip(' .')

    return result


# =============================================================================
# VALIDATION UTILITIES
# =============================================================================

def is_valid_ticker(ticker: str) -> bool:
    """
    Check if a string looks like a valid ticker symbol.

    Args:
        ticker: The ticker symbol to validate.

    Returns:
        True if the ticker appears valid, False otherwise.
    """
    if not ticker or not isinstance(ticker, str):
        return False

    # Basic validation: alphanumeric with possible dots
    ticker = ticker.strip()
    if len(ticker) < 1 or len(ticker) > 20:
        return False

    # Allow alphanumeric, dots, and hyphens
    allowed_chars = set('ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789.-')
    return all(c in allowed_chars for c in ticker.upper())


def clamp(value: float, min_val: float, max_val: float) -> float:
    """
    Clamp a value between minimum and maximum bounds.

    Args:
        value: The value to clamp.
        min_val: Minimum allowed value.
        max_val: Maximum allowed value.

    Returns:
        The clamped value.

    Examples:
        >>> clamp(15, 0, 10)
        10
        >>> clamp(-5, 0, 10)
        0
        >>> clamp(5, 0, 10)
        5
    """
    return max(min_val, min(max_val, value))


# =============================================================================
# SIGNAL/SCORE UTILITIES
# =============================================================================

def determine_signal(
    pe: Optional[float],
    roe: Optional[float],
    score: float
) -> str:
    """
    Determine investment signal based on PE, ROE, and score criteria.

    Signal levels:
    - ACHAT: PE <= 12 AND ROE >= 10% AND score >= 50
    - WATCH: PE <= 15 AND ROE >= 8%
    - CHER: PE > 20 OR ROE < 5%
    - NEUTRE: Default

    Args:
        pe: Price-to-earnings ratio.
        roe: Return on equity (as decimal or percentage).
        score: Investment score (0-100).

    Returns:
        Signal string: 'ACHAT', 'WATCH', 'CHER', or 'NEUTRE'.

    Examples:
        >>> determine_signal(10, 0.15, 60)
        'ACHAT'
        >>> determine_signal(25, 0.03, 30)
        'CHER'
    """
    if pe is None or roe is None:
        return 'NEUTRE'

    # Normalize ROE to decimal (handle both 0.15 and 15 formats)
    roe_val = roe if roe < 1 else roe / 100

    # ACHAT: PE <= 12 AND ROE >= 10% AND score >= 50
    if pe <= 12 and roe_val >= 0.10 and score >= 50:
        return 'ACHAT'

    # WATCH: PE <= 15 AND ROE >= 8%
    if pe <= 15 and roe_val >= 0.08:
        return 'WATCH'

    # CHER: PE > 20 OR ROE < 5%
    if pe > 20 or roe_val < 0.05:
        return 'CHER'

    return 'NEUTRE'


# =============================================================================
# PRICE UTILITIES
# =============================================================================

def get_price_on_date(
    prices_dict: Dict[str, Dict[str, float]],
    target_date: str
) -> Optional[float]:
    """
    Get price on a specific date or the closest previous date.

    Args:
        prices_dict: Dictionary mapping date strings to price data.
                    Each value should have a 'close' key.
        target_date: Target date in 'YYYY-MM-DD' format.

    Returns:
        The closing price on or before the target date, or None if not found.

    Examples:
        >>> prices = {'2024-01-15': {'close': 100.0}, '2024-01-14': {'close': 99.0}}
        >>> get_price_on_date(prices, '2024-01-15')
        100.0
    """
    # Try exact match first
    if target_date in prices_dict:
        return prices_dict[target_date].get('close')

    # Find closest previous date
    target = datetime.strptime(target_date, '%Y-%m-%d')
    closest_date = None
    closest_price = None

    for date_str, data in prices_dict.items():
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d')
            if date <= target:
                if closest_date is None or date > closest_date:
                    closest_date = date
                    closest_price = data.get('close')
        except ValueError:
            continue

    return closest_price

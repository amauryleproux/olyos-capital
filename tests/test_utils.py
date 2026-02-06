"""
Unit tests for olyos/utils.py module.

Tests cover:
- Type conversion utilities (safe_float, safe_int, safe_str)
- JSON file operations (load_json, save_json)
- Value formatting (fmt_val, fmt_pct, fmt_currency, fmt_large_number)
- Date/time utilities (parse_date, format_date, get_date_range, is_market_open)
- Cache utilities (is_cache_valid, load_from_cache, save_to_cache, get_cache_path)
- Exchange/country mappings (get_country_from_exchange)
- File utilities (ensure_dir, sanitize_filename)
- Validation utilities (is_valid_ticker, clamp)
- Signal utilities (determine_signal)
- Price utilities (get_price_on_date)
"""

import json
import math
import os
from datetime import datetime, timedelta

import pytest

# Import the module under test
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from olyos.utils import (
    safe_float, safe_int, safe_str,
    load_json, save_json,
    fmt_val, fmt_pct, fmt_currency, fmt_large_number,
    parse_date, format_date, get_date_range, is_market_open,
    is_cache_valid, load_from_cache, save_to_cache, get_cache_path,
    get_country_from_exchange, EXCHANGE_COUNTRY_MAP,
    ensure_dir, sanitize_filename,
    is_valid_ticker, clamp,
    determine_signal,
    get_price_on_date
)


# =============================================================================
# SAFE_FLOAT TESTS
# =============================================================================

class TestSafeFloat:
    """Tests for safe_float() function."""

    def test_valid_float(self):
        """Test conversion of valid float."""
        assert safe_float(123.45) == 123.45

    def test_valid_integer(self):
        """Test conversion of integer to float."""
        assert safe_float(100) == 100.0

    def test_valid_string(self):
        """Test conversion of numeric string."""
        assert safe_float("123.45") == 123.45

    def test_none_returns_default(self):
        """Test that None returns the default value."""
        assert safe_float(None) is None
        assert safe_float(None, 0.0) == 0.0
        assert safe_float(None, -1.0) == -1.0

    def test_nan_returns_default(self):
        """Test that NaN returns the default value."""
        assert safe_float(float('nan')) is None
        assert safe_float(float('nan'), 0.0) == 0.0

    def test_invalid_string_returns_default(self):
        """Test that invalid string returns default."""
        assert safe_float("invalid") is None
        assert safe_float("abc", -1.0) == -1.0
        assert safe_float("", 0.0) == 0.0

    def test_invalid_type_returns_default(self):
        """Test that invalid types return default."""
        assert safe_float([1, 2, 3]) is None
        assert safe_float({}, 0.0) == 0.0
        assert safe_float(object(), -1.0) == -1.0

    def test_scientific_notation(self):
        """Test conversion of scientific notation strings."""
        assert safe_float("1.5e6") == 1500000.0
        assert safe_float("1E-3") == 0.001

    def test_negative_values(self):
        """Test conversion of negative values."""
        assert safe_float(-123.45) == -123.45
        assert safe_float("-456.78") == -456.78

    def test_zero(self):
        """Test conversion of zero values."""
        assert safe_float(0) == 0.0
        assert safe_float("0") == 0.0
        assert safe_float(0.0) == 0.0

    def test_infinity(self):
        """Test handling of infinity values."""
        assert safe_float(float('inf')) == float('inf')
        assert safe_float(float('-inf')) == float('-inf')


# =============================================================================
# SAFE_INT TESTS
# =============================================================================

class TestSafeInt:
    """Tests for safe_int() function."""

    def test_valid_int(self):
        """Test conversion of valid integer."""
        assert safe_int(123) == 123

    def test_valid_float_to_int(self):
        """Test conversion of float to int (truncates)."""
        assert safe_int(123.7) == 123
        assert safe_int(123.2) == 123

    def test_valid_string(self):
        """Test conversion of numeric string."""
        assert safe_int("456") == 456

    def test_none_returns_default(self):
        """Test that None returns the default value."""
        assert safe_int(None) is None
        assert safe_int(None, 0) == 0
        assert safe_int(None, -1) == -1

    def test_nan_returns_default(self):
        """Test that NaN returns the default value."""
        assert safe_int(float('nan')) is None
        assert safe_int(float('nan'), 0) == 0

    def test_invalid_string_returns_default(self):
        """Test that invalid string returns default."""
        assert safe_int("invalid") is None
        assert safe_int("abc", -1) == -1
        assert safe_int("12.34", 0) == 0  # Float string not directly convertible

    def test_invalid_type_returns_default(self):
        """Test that invalid types return default."""
        assert safe_int([1, 2, 3]) is None
        assert safe_int({}, 0) == 0

    def test_negative_values(self):
        """Test conversion of negative values."""
        assert safe_int(-123) == -123
        assert safe_int(-123.9) == -123

    def test_zero(self):
        """Test conversion of zero values."""
        assert safe_int(0) == 0
        assert safe_int("0") == 0
        assert safe_int(0.0) == 0


# =============================================================================
# SAFE_STR TESTS
# =============================================================================

class TestSafeStr:
    """Tests for safe_str() function."""

    def test_string_passthrough(self):
        """Test that strings pass through unchanged."""
        assert safe_str("hello") == "hello"

    def test_none_returns_default(self):
        """Test that None returns the default value."""
        assert safe_str(None) == ""
        assert safe_str(None, "N/A") == "N/A"

    def test_number_conversion(self):
        """Test conversion of numbers to strings."""
        assert safe_str(123) == "123"
        assert safe_str(123.45) == "123.45"

    def test_list_conversion(self):
        """Test conversion of list to string."""
        assert safe_str([1, 2, 3]) == "[1, 2, 3]"

    def test_dict_conversion(self):
        """Test conversion of dict to string."""
        result = safe_str({"key": "value"})
        assert "key" in result
        assert "value" in result


# =============================================================================
# LOAD_JSON / SAVE_JSON TESTS
# =============================================================================

class TestJsonOperations:
    """Tests for load_json() and save_json() functions."""

    def test_save_and_load_json(self, temp_json_file, sample_json_data):
        """Test saving and loading JSON data."""
        # Save data
        result = save_json(temp_json_file, sample_json_data)
        assert result is True
        assert os.path.exists(temp_json_file)

        # Load data
        loaded = load_json(temp_json_file, {})
        assert loaded == sample_json_data

    def test_load_nonexistent_file(self, temp_dir):
        """Test loading a file that doesn't exist returns default."""
        filepath = os.path.join(temp_dir, "nonexistent.json")
        result = load_json(filepath, {"default": True})
        assert result == {"default": True}

    def test_load_invalid_json(self, create_invalid_json_file):
        """Test loading invalid JSON returns default."""
        result = load_json(create_invalid_json_file, {"error": True})
        assert result == {"error": True}

    def test_save_creates_directory(self, temp_dir):
        """Test that save_json creates necessary directories."""
        nested_path = os.path.join(temp_dir, "subdir", "nested", "data.json")
        result = save_json(nested_path, {"test": "data"})
        assert result is True
        assert os.path.exists(nested_path)

    def test_save_with_custom_indent(self, temp_json_file):
        """Test saving with custom indentation."""
        data = {"key": "value"}
        save_json(temp_json_file, data, indent=4)

        with open(temp_json_file, 'r', encoding='utf-8') as f:
            content = f.read()
        # 4-space indent should be visible
        assert "    " in content or content.count(" ") >= 4

    def test_save_unicode_data(self, temp_json_file):
        """Test saving and loading unicode data."""
        data = {"name": "Societe Generale", "symbol": "euro sign"}
        save_json(temp_json_file, data)
        loaded = load_json(temp_json_file, {})
        assert loaded == data

    def test_save_non_serializable_returns_false(self, temp_json_file):
        """Test that saving non-JSON-serializable data returns False."""
        data = {"func": lambda x: x}  # Functions are not JSON serializable
        result = save_json(temp_json_file, data)
        assert result is False

    def test_load_default_list(self, temp_dir):
        """Test load_json with list as default."""
        filepath = os.path.join(temp_dir, "missing.json")
        result = load_json(filepath, [])
        assert result == []

    def test_load_default_none(self, temp_dir):
        """Test load_json with None as default."""
        filepath = os.path.join(temp_dir, "missing.json")
        result = load_json(filepath, None)
        assert result is None


# =============================================================================
# FMT_VAL TESTS
# =============================================================================

class TestFmtVal:
    """Tests for fmt_val() function."""

    def test_basic_formatting(self):
        """Test basic number formatting."""
        assert fmt_val(1234.56) == "1 234.56"

    def test_large_number(self):
        """Test formatting of large numbers with French-style separators."""
        assert fmt_val(1234567.89) == "1 234 567.89"

    def test_none_returns_placeholder(self):
        """Test that None returns the placeholder."""
        assert fmt_val(None) == "-"
        assert fmt_val(None, placeholder="N/A") == "N/A"

    def test_nan_returns_placeholder(self):
        """Test that NaN returns the placeholder."""
        assert fmt_val(float('nan')) == "-"

    def test_custom_decimals(self):
        """Test custom decimal places."""
        assert fmt_val(1234.5678, decimals=0) == "1 235"
        assert fmt_val(1234.5678, decimals=1) == "1 234.6"
        assert fmt_val(1234.5678, decimals=4) == "1 234.5678"

    def test_zero(self):
        """Test formatting of zero."""
        assert fmt_val(0) == "0.00"
        assert fmt_val(0, decimals=0) == "0"

    def test_negative_numbers(self):
        """Test formatting of negative numbers."""
        result = fmt_val(-1234.56)
        assert "1 234.56" in result
        assert "-" in result

    def test_small_numbers(self):
        """Test formatting of small numbers."""
        assert fmt_val(0.12) == "0.12"
        assert fmt_val(0.001, decimals=3) == "0.001"

    def test_invalid_value_returns_placeholder(self):
        """Test that invalid values return placeholder."""
        assert fmt_val("invalid") == "-"
        assert fmt_val([1, 2, 3]) == "-"


# =============================================================================
# FMT_PCT TESTS
# =============================================================================

class TestFmtPct:
    """Tests for fmt_pct() function."""

    def test_basic_percentage(self):
        """Test basic percentage formatting."""
        assert fmt_pct(0.1567) == "15.67%"

    def test_hundred_percent(self):
        """Test 100% formatting."""
        assert fmt_pct(1.0) == "100.00%"

    def test_none_returns_placeholder(self):
        """Test that None returns placeholder."""
        assert fmt_pct(None) == "-"

    def test_nan_returns_placeholder(self):
        """Test that NaN returns placeholder."""
        assert fmt_pct(float('nan')) == "-"

    def test_custom_decimals(self):
        """Test custom decimal places."""
        assert fmt_pct(0.1567, decimals=0) == "16%"
        assert fmt_pct(0.1567, decimals=1) == "15.7%"

    def test_negative_percentage(self):
        """Test negative percentage."""
        result = fmt_pct(-0.15)
        assert "-15.00%" == result

    def test_small_percentage(self):
        """Test small percentage values."""
        assert fmt_pct(0.001) == "0.10%"

    def test_large_percentage(self):
        """Test large percentage values."""
        assert fmt_pct(5.0) == "500.00%"


# =============================================================================
# FMT_CURRENCY TESTS
# =============================================================================

class TestFmtCurrency:
    """Tests for fmt_currency() function."""

    def test_default_eur(self):
        """Test default EUR currency."""
        assert fmt_currency(1234.56) == "1 234.56 EUR"

    def test_custom_currency(self):
        """Test custom currency symbol."""
        assert fmt_currency(1234.56, currency="$") == "1 234.56 $"
        assert fmt_currency(1234.56, currency="USD") == "1 234.56 USD"

    def test_none_returns_placeholder(self):
        """Test that None returns placeholder."""
        assert fmt_currency(None) == "-"

    def test_custom_decimals(self):
        """Test custom decimal places."""
        assert fmt_currency(1234.567, decimals=0) == "1 235 EUR"


# =============================================================================
# FMT_LARGE_NUMBER TESTS
# =============================================================================

class TestFmtLargeNumber:
    """Tests for fmt_large_number() function."""

    def test_billions(self):
        """Test billion formatting."""
        assert fmt_large_number(2500000000) == "2.50B"

    def test_millions(self):
        """Test million formatting."""
        assert fmt_large_number(1500000) == "1.50M"

    def test_thousands(self):
        """Test thousand formatting."""
        assert fmt_large_number(1500) == "1.50K"

    def test_small_numbers(self):
        """Test numbers below 1000."""
        assert fmt_large_number(500) == "500.00"

    def test_none_returns_placeholder(self):
        """Test that None returns placeholder."""
        assert fmt_large_number(None) == "-"

    def test_nan_returns_placeholder(self):
        """Test that NaN returns placeholder."""
        assert fmt_large_number(float('nan')) == "-"

    def test_negative_numbers(self):
        """Test negative large numbers."""
        assert fmt_large_number(-1500000) == "-1.50M"

    def test_exactly_one_billion(self):
        """Test exactly 1 billion."""
        assert fmt_large_number(1000000000) == "1.00B"


# =============================================================================
# PARSE_DATE TESTS
# =============================================================================

class TestParseDate:
    """Tests for parse_date() function."""

    def test_iso_format(self):
        """Test ISO date format (YYYY-MM-DD)."""
        result = parse_date("2024-01-15")
        assert result == datetime(2024, 1, 15)

    def test_european_format(self):
        """Test European date format (DD/MM/YYYY)."""
        result = parse_date("15/01/2024")
        assert result == datetime(2024, 1, 15)

    def test_european_dash_format(self):
        """Test European dash format (DD-MM-YYYY)."""
        result = parse_date("15-01-2024")
        assert result == datetime(2024, 1, 15)

    def test_european_dot_format(self):
        """Test European dot format (DD.MM.YYYY)."""
        result = parse_date("15.01.2024")
        assert result == datetime(2024, 1, 15)

    def test_datetime_format(self):
        """Test datetime with time component."""
        result = parse_date("2024-01-15T10:30:00")
        assert result == datetime(2024, 1, 15, 10, 30, 0)

    def test_empty_string_returns_none(self):
        """Test empty string returns None."""
        assert parse_date("") is None
        assert parse_date(None) is None

    def test_invalid_date_returns_none(self):
        """Test invalid date returns None."""
        assert parse_date("not-a-date") is None
        assert parse_date("2024-13-45") is None

    def test_custom_formats(self):
        """Test custom date formats."""
        result = parse_date("Jan 15, 2024", formats=["%b %d, %Y"])
        assert result == datetime(2024, 1, 15)


# =============================================================================
# FORMAT_DATE TESTS
# =============================================================================

class TestFormatDate:
    """Tests for format_date() function."""

    def test_default_format(self):
        """Test default ISO format."""
        dt = datetime(2024, 1, 15)
        assert format_date(dt) == "2024-01-15"

    def test_custom_format(self):
        """Test custom format."""
        dt = datetime(2024, 1, 15)
        assert format_date(dt, fmt="%d/%m/%Y") == "15/01/2024"

    def test_none_returns_empty(self):
        """Test None returns empty string."""
        assert format_date(None) == ""

    def test_with_time(self):
        """Test formatting with time component."""
        dt = datetime(2024, 1, 15, 10, 30, 45)
        assert format_date(dt, fmt="%Y-%m-%d %H:%M:%S") == "2024-01-15 10:30:45"


# =============================================================================
# GET_DATE_RANGE TESTS
# =============================================================================

class TestGetDateRange:
    """Tests for get_date_range() function."""

    def test_basic_range(self, test_datetime):
        """Test basic date range calculation."""
        start, end = get_date_range(30, end_date=test_datetime)
        assert end == "2024-01-15"
        # Start should be 30 days before
        expected_start = (test_datetime - timedelta(days=30)).strftime('%Y-%m-%d')
        assert start == expected_start

    def test_default_end_date(self):
        """Test with default end date (today)."""
        start, end = get_date_range(7)
        today = datetime.now().strftime('%Y-%m-%d')
        assert end == today

    def test_zero_days(self, test_datetime):
        """Test zero days back."""
        start, end = get_date_range(0, end_date=test_datetime)
        assert start == end == "2024-01-15"


# =============================================================================
# IS_MARKET_OPEN TESTS
# =============================================================================

class TestIsMarketOpen:
    """Tests for is_market_open() function."""

    def test_weekday_during_hours(self, weekday_datetime):
        """Test market open on weekday during trading hours."""
        assert is_market_open(weekday_datetime) is True

    def test_weekend_closed(self, weekend_datetime):
        """Test market closed on weekend."""
        assert is_market_open(weekend_datetime) is False

    def test_before_open(self):
        """Test market closed before opening time."""
        early = datetime(2024, 1, 17, 7, 0, 0)  # Wednesday 7 AM
        assert is_market_open(early) is False

    def test_after_close(self):
        """Test market closed after closing time."""
        late = datetime(2024, 1, 17, 18, 0, 0)  # Wednesday 6 PM
        assert is_market_open(late) is False

    def test_custom_hours(self):
        """Test custom market hours."""
        dt = datetime(2024, 1, 17, 8, 0, 0)  # Wednesday 8 AM
        # Default hours: closed at 8 AM
        assert is_market_open(dt, market_open_hour=9) is False
        # Custom hours: open at 8 AM
        assert is_market_open(dt, market_open_hour=8) is True

    def test_weekend_open_if_allowed(self, weekend_datetime):
        """Test weekend can be open if weekend_closed=False."""
        # Adjust time to be during market hours
        sat_trading = datetime(2024, 1, 20, 10, 0, 0)
        assert is_market_open(sat_trading, weekend_closed=False) is True


# =============================================================================
# IS_CACHE_VALID TESTS
# =============================================================================

class TestIsCacheValid:
    """Tests for is_cache_valid() function."""

    def test_valid_cache(self, temp_dir, sample_cache_data):
        """Test detection of valid cache."""
        cache_file = os.path.join(temp_dir, "cache.json")
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(sample_cache_data, f)

        assert is_cache_valid(cache_file, max_days=7) is True

    def test_expired_cache(self, temp_dir, expired_cache_data):
        """Test detection of expired cache."""
        cache_file = os.path.join(temp_dir, "old_cache.json")
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(expired_cache_data, f)

        assert is_cache_valid(cache_file, max_days=30) is False

    def test_nonexistent_cache(self, temp_dir):
        """Test nonexistent cache file."""
        cache_file = os.path.join(temp_dir, "missing.json")
        assert is_cache_valid(cache_file, max_days=7) is False

    def test_invalid_json_cache(self, create_invalid_json_file):
        """Test invalid JSON cache file."""
        assert is_cache_valid(create_invalid_json_file, max_days=7) is False

    def test_missing_date_key(self, temp_dir):
        """Test cache file missing date key uses fallback."""
        cache_file = os.path.join(temp_dir, "no_date.json")
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump({"data": "value"}, f)

        # Should use 2000-01-01 as default, which is expired
        assert is_cache_valid(cache_file, max_days=7) is False

    def test_custom_date_key(self, temp_dir):
        """Test custom date key."""
        cache_file = os.path.join(temp_dir, "custom_cache.json")
        data = {
            "custom_date": datetime.now().strftime('%Y-%m-%d'),
            "data": "value"
        }
        with open(cache_file, 'w', encoding='utf-8') as f:
            json.dump(data, f)

        assert is_cache_valid(cache_file, max_days=7, date_key="custom_date") is True


# =============================================================================
# LOAD_FROM_CACHE / SAVE_TO_CACHE TESTS
# =============================================================================

class TestCacheOperations:
    """Tests for load_from_cache() and save_to_cache() functions."""

    def test_save_and_load_cache(self, temp_cache_file):
        """Test saving and loading cache data."""
        data = {"ticker": "TEST.PA", "price": 100.50}
        result = save_to_cache(temp_cache_file, data)
        assert result is True

        loaded = load_from_cache(temp_cache_file)
        assert loaded is not None
        assert loaded["ticker"] == "TEST.PA"
        assert "_cache_date" in loaded

    def test_load_nonexistent_cache(self, temp_dir):
        """Test loading nonexistent cache returns None."""
        cache_file = os.path.join(temp_dir, "missing.json")
        assert load_from_cache(cache_file) is None

    def test_save_creates_directory(self, temp_dir):
        """Test save_to_cache creates necessary directories."""
        nested_cache = os.path.join(temp_dir, "sub", "dir", "cache.json")
        result = save_to_cache(nested_cache, {"test": True})
        assert result is True
        assert os.path.exists(nested_cache)

    def test_cache_date_added(self, temp_cache_file):
        """Test that cache date is automatically added."""
        data = {"test": "value"}
        save_to_cache(temp_cache_file, data)

        loaded = load_from_cache(temp_cache_file)
        assert "_cache_date" in loaded
        assert loaded["_cache_date"] == datetime.now().strftime('%Y-%m-%d')


# =============================================================================
# GET_CACHE_PATH TESTS
# =============================================================================

class TestGetCachePath:
    """Tests for get_cache_path() function."""

    def test_basic_path(self, temp_dir):
        """Test basic cache path generation."""
        path = get_cache_path(temp_dir, "prices", "AAPL")
        assert path.endswith("AAPL.json")
        assert "prices" in path

    def test_sanitizes_dots(self, temp_dir):
        """Test that dots in keys are replaced with underscores."""
        path = get_cache_path(temp_dir, "fundamentals", "AAPL.PA")
        assert "AAPL_PA.json" in path
        assert ".PA" not in path

    def test_sanitizes_special_chars(self, temp_dir):
        """Test that special characters are sanitized."""
        path = get_cache_path(temp_dir, "prices", "^FCHI")
        assert "^" not in os.path.basename(path)
        assert "_FCHI.json" in path

    def test_creates_category_directory(self, temp_dir):
        """Test that category directory is created."""
        path = get_cache_path(temp_dir, "new_category", "TEST")
        category_dir = os.path.dirname(path)
        assert os.path.exists(category_dir)
        assert "new_category" in category_dir


# =============================================================================
# GET_COUNTRY_FROM_EXCHANGE TESTS
# =============================================================================

class TestGetCountryFromExchange:
    """Tests for get_country_from_exchange() function."""

    def test_known_exchanges(self):
        """Test known exchange mappings."""
        assert get_country_from_exchange('PA') == 'FR'
        assert get_country_from_exchange('XPAR') == 'FR'
        assert get_country_from_exchange('XETRA') == 'DE'
        assert get_country_from_exchange('LSE') == 'UK'
        assert get_country_from_exchange('MI') == 'IT'
        assert get_country_from_exchange('AS') == 'NL'

    def test_unknown_exchange_returns_default(self):
        """Test unknown exchange returns default."""
        assert get_country_from_exchange('UNKNOWN') == 'EU'
        assert get_country_from_exchange('XYZ', default='US') == 'US'

    def test_case_insensitive_partial_match(self):
        """Test case-insensitive partial matching."""
        # These should find partial matches
        assert get_country_from_exchange('paris') == 'FR'
        assert get_country_from_exchange('PARIS') == 'FR'


# =============================================================================
# ENSURE_DIR TESTS
# =============================================================================

class TestEnsureDir:
    """Tests for ensure_dir() function."""

    def test_create_new_directory(self, temp_dir):
        """Test creating a new directory."""
        new_dir = os.path.join(temp_dir, "new_folder")
        assert not os.path.exists(new_dir)

        result = ensure_dir(new_dir)
        assert result is True
        assert os.path.exists(new_dir)

    def test_existing_directory(self, temp_dir):
        """Test with existing directory."""
        result = ensure_dir(temp_dir)
        assert result is True

    def test_nested_directories(self, temp_dir):
        """Test creating nested directories."""
        nested = os.path.join(temp_dir, "a", "b", "c")
        result = ensure_dir(nested)
        assert result is True
        assert os.path.exists(nested)


# =============================================================================
# SANITIZE_FILENAME TESTS
# =============================================================================

class TestSanitizeFilename:
    """Tests for sanitize_filename() function."""

    def test_removes_invalid_chars(self):
        """Test removal of invalid characters."""
        result = sanitize_filename("my/file:name.txt")
        assert "/" not in result
        assert ":" not in result
        assert ".txt" in result

    def test_replaces_with_custom_char(self):
        """Test custom replacement character."""
        result = sanitize_filename("file<>name", replacement="-")
        assert "<" not in result
        assert ">" not in result
        assert "-" in result

    def test_removes_leading_trailing(self):
        """Test removal of leading/trailing spaces and dots."""
        result = sanitize_filename("  .filename.  ")
        assert not result.startswith(" ")
        assert not result.endswith(" ")
        assert not result.endswith(".")

    def test_preserves_valid_filename(self):
        """Test that valid filenames are preserved."""
        result = sanitize_filename("valid_filename.txt")
        assert result == "valid_filename.txt"


# =============================================================================
# IS_VALID_TICKER TESTS
# =============================================================================

class TestIsValidTicker:
    """Tests for is_valid_ticker() function."""

    def test_valid_tickers(self):
        """Test valid ticker symbols."""
        assert is_valid_ticker("AAPL") is True
        assert is_valid_ticker("AAPL.PA") is True
        assert is_valid_ticker("BRK-B") is True
        assert is_valid_ticker("3M") is True

    def test_invalid_tickers(self):
        """Test invalid ticker symbols."""
        assert is_valid_ticker("") is False
        assert is_valid_ticker(None) is False
        assert is_valid_ticker("A" * 25) is False  # Too long
        assert is_valid_ticker("AAPL$") is False  # Invalid char

    def test_edge_cases(self):
        """Test edge cases."""
        assert is_valid_ticker("A") is True  # Single char OK
        assert is_valid_ticker("  AAPL  ") is True  # Whitespace stripped


# =============================================================================
# CLAMP TESTS
# =============================================================================

class TestClamp:
    """Tests for clamp() function."""

    def test_value_in_range(self):
        """Test value within range stays unchanged."""
        assert clamp(5, 0, 10) == 5

    def test_value_below_min(self):
        """Test value below minimum is clamped."""
        assert clamp(-5, 0, 10) == 0

    def test_value_above_max(self):
        """Test value above maximum is clamped."""
        assert clamp(15, 0, 10) == 10

    def test_value_at_boundaries(self):
        """Test values at exact boundaries."""
        assert clamp(0, 0, 10) == 0
        assert clamp(10, 0, 10) == 10

    def test_negative_range(self):
        """Test clamping with negative range."""
        assert clamp(-5, -10, -1) == -5
        assert clamp(-15, -10, -1) == -10
        assert clamp(0, -10, -1) == -1


# =============================================================================
# DETERMINE_SIGNAL TESTS
# =============================================================================

class TestDetermineSignal:
    """Tests for determine_signal() function."""

    def test_achat_signal(self, achat_signal_data):
        """Test ACHAT signal conditions."""
        result = determine_signal(
            achat_signal_data["pe"],
            achat_signal_data["roe"],
            achat_signal_data["score"]
        )
        assert result == "ACHAT"

    def test_watch_signal(self, watch_signal_data):
        """Test WATCH signal conditions."""
        result = determine_signal(
            watch_signal_data["pe"],
            watch_signal_data["roe"],
            watch_signal_data["score"]
        )
        assert result == "WATCH"

    def test_cher_signal_high_pe(self):
        """Test CHER signal with high PE."""
        result = determine_signal(pe=25, roe=0.10, score=50)
        assert result == "CHER"

    def test_cher_signal_low_roe(self):
        """Test CHER signal with low ROE."""
        result = determine_signal(pe=15, roe=0.03, score=50)
        assert result == "CHER"

    def test_neutre_signal(self, neutre_signal_data):
        """Test NEUTRE signal (default)."""
        result = determine_signal(
            neutre_signal_data["pe"],
            neutre_signal_data["roe"],
            neutre_signal_data["score"]
        )
        assert result == "NEUTRE"

    def test_none_pe_returns_neutre(self):
        """Test None PE returns NEUTRE."""
        assert determine_signal(None, 0.15, 60) == "NEUTRE"

    def test_none_roe_returns_neutre(self):
        """Test None ROE returns NEUTRE."""
        assert determine_signal(10, None, 60) == "NEUTRE"

    def test_roe_percentage_format(self):
        """Test ROE in percentage format (e.g., 15 instead of 0.15)."""
        # Should handle both 0.15 and 15 for 15%
        result1 = determine_signal(10, 0.15, 60)
        result2 = determine_signal(10, 15, 60)
        assert result1 == result2 == "ACHAT"

    def test_boundary_conditions(self):
        """Test boundary conditions for signals."""
        # Exactly at ACHAT boundary
        assert determine_signal(12, 0.10, 50) == "ACHAT"
        # Just outside ACHAT (PE too high)
        assert determine_signal(13, 0.10, 50) == "WATCH"
        # Just outside WATCH (ROE too low)
        assert determine_signal(15, 0.07, 50) == "NEUTRE"


# =============================================================================
# GET_PRICE_ON_DATE TESTS
# =============================================================================

class TestGetPriceOnDate:
    """Tests for get_price_on_date() function."""

    def test_exact_date_match(self, sample_prices_dict):
        """Test getting price on exact date."""
        result = get_price_on_date(sample_prices_dict, "2024-01-15")
        assert result == 102.0

    def test_closest_previous_date(self, sample_prices_dict):
        """Test getting price from closest previous date."""
        # 2024-01-13 doesn't exist, should return 2024-01-12 price
        result = get_price_on_date(sample_prices_dict, "2024-01-13")
        assert result == 98.0

    def test_date_before_all_data(self, sample_prices_dict):
        """Test date before all available data returns None."""
        result = get_price_on_date(sample_prices_dict, "2024-01-01")
        assert result is None

    def test_empty_prices_dict(self):
        """Test empty prices dictionary."""
        result = get_price_on_date({}, "2024-01-15")
        assert result is None

    def test_missing_close_key(self):
        """Test data without close key."""
        prices = {"2024-01-15": {"open": 100.0}}  # No 'close' key
        result = get_price_on_date(prices, "2024-01-15")
        assert result is None


# =============================================================================
# INTEGRATION TESTS
# =============================================================================

class TestIntegration:
    """Integration tests combining multiple utilities."""

    def test_json_cache_workflow(self, temp_dir):
        """Test complete cache workflow."""
        cache_file = os.path.join(temp_dir, "integration_cache.json")
        data = {"ticker": "TEST.PA", "price": 150.0}

        # Save to cache
        save_to_cache(cache_file, data)

        # Verify cache is valid
        assert is_cache_valid(cache_file, max_days=7) is True

        # Load from cache
        loaded = load_from_cache(cache_file)
        assert loaded["ticker"] == "TEST.PA"
        assert loaded["price"] == 150.0

    def test_signal_with_formatting(self):
        """Test signal determination with formatted output."""
        pe = 10.5
        roe = 0.15
        score = 65

        signal = determine_signal(pe, roe, score)
        formatted_pe = fmt_val(pe, decimals=1)
        formatted_roe = fmt_pct(roe)

        assert signal == "ACHAT"
        assert formatted_pe == "10.5"
        assert formatted_roe == "15.00%"

    def test_date_and_price_workflow(self, sample_prices_dict):
        """Test date parsing and price lookup."""
        date_str = "15/01/2024"
        parsed = parse_date(date_str)
        formatted = format_date(parsed)

        price = get_price_on_date(sample_prices_dict, formatted)
        assert price == 102.0

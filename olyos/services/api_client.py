"""
PARALLEL API CLIENT
====================
High-performance API client with parallel fetching capabilities,
rate limiting, and exponential backoff for robust data retrieval.

Usage:
    from services.api_client import ParallelAPIClient

    client = ParallelAPIClient(max_workers=10, rate_limit=2.0)

    # Batch fetch fundamentals
    results = client.fetch_fundamentals_batch(tickers, use_cache=True)

    # Batch fetch prices
    prices = client.fetch_prices_batch(tickers, start_date, end_date)
"""

from concurrent.futures import ThreadPoolExecutor, as_completed
import threading
import time
import random
from typing import List, Dict, Tuple, Optional, Callable, Any
from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class FetchResult:
    """Result container for API fetch operations"""
    ticker: str
    data: Optional[Any] = None
    error: Optional[str] = None
    success: bool = False
    from_cache: bool = False
    retry_count: int = 0
    fetch_time: float = 0.0


@dataclass
class BatchProgress:
    """Progress tracker for batch operations"""
    total: int = 0
    completed: int = 0
    successful: int = 0
    failed: int = 0
    current_ticker: str = ""
    start_time: float = field(default_factory=time.time)

    @property
    def progress_pct(self) -> float:
        return (self.completed / self.total * 100) if self.total > 0 else 0

    @property
    def elapsed_time(self) -> float:
        return time.time() - self.start_time

    @property
    def estimated_remaining(self) -> float:
        if self.completed == 0:
            return 0
        rate = self.completed / self.elapsed_time
        remaining = self.total - self.completed
        return remaining / rate if rate > 0 else 0


class RateLimiter:
    """Thread-safe rate limiter with sliding window"""

    def __init__(self, calls_per_second: float = 5.0, burst_limit: int = 10):
        """
        Initialize rate limiter.

        Args:
            calls_per_second: Maximum sustained call rate
            burst_limit: Maximum burst of calls allowed
        """
        self.min_interval = 1.0 / calls_per_second
        self.burst_limit = burst_limit
        self._lock = threading.Lock()
        self._last_call = 0.0
        self._call_times: List[float] = []

    def acquire(self) -> float:
        """
        Acquire permission to make an API call.
        Returns the time waited (in seconds).
        """
        with self._lock:
            now = time.time()

            # Clean old call times (older than 1 second)
            self._call_times = [t for t in self._call_times if now - t < 1.0]

            # Check burst limit
            if len(self._call_times) >= self.burst_limit:
                oldest = self._call_times[0]
                wait_time = 1.0 - (now - oldest)
                if wait_time > 0:
                    time.sleep(wait_time)
                    now = time.time()
                    self._call_times = [t for t in self._call_times if now - t < 1.0]

            # Ensure minimum interval
            elapsed = now - self._last_call
            if elapsed < self.min_interval:
                wait_time = self.min_interval - elapsed
                time.sleep(wait_time)
                now = time.time()

            waited = now - (self._last_call + self.min_interval) if self._last_call > 0 else 0
            self._last_call = now
            self._call_times.append(now)

            return max(0, waited)


class ExponentialBackoff:
    """Exponential backoff calculator with jitter"""

    def __init__(
        self,
        base_delay: float = 1.0,
        max_delay: float = 60.0,
        max_retries: int = 3,
        jitter: bool = True
    ):
        """
        Initialize backoff calculator.

        Args:
            base_delay: Initial delay in seconds
            max_delay: Maximum delay cap in seconds
            max_retries: Maximum number of retry attempts
            jitter: Whether to add random jitter to delays
        """
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.max_retries = max_retries
        self.jitter = jitter

    def get_delay(self, attempt: int) -> float:
        """
        Calculate delay for a given retry attempt.

        Args:
            attempt: Current attempt number (0-based)

        Returns:
            Delay in seconds before next retry
        """
        if attempt >= self.max_retries:
            return -1  # Signal to stop retrying

        delay = self.base_delay * (2 ** attempt)
        delay = min(delay, self.max_delay)

        if self.jitter:
            # Add random jitter (0% to 25% of delay)
            jitter_amount = delay * random.uniform(0, 0.25)
            delay += jitter_amount

        return delay

    def should_retry(self, attempt: int) -> bool:
        """Check if another retry should be attempted"""
        return attempt < self.max_retries


class ParallelAPIClient:
    """
    High-performance parallel API client for batch operations.

    Features:
    - Parallel fetching with configurable worker count
    - Rate limiting to avoid API throttling
    - Exponential backoff with jitter for failed requests
    - Progress tracking and callbacks
    - Thread-safe operation
    """

    def __init__(
        self,
        max_workers: int = 10,
        rate_limit: float = 5.0,
        batch_delay: float = 0.5,
        max_retries: int = 3,
        timeout: float = 30.0
    ):
        """
        Initialize the parallel API client.

        Args:
            max_workers: Maximum concurrent workers (threads)
            rate_limit: Maximum API calls per second
            batch_delay: Delay between batches in seconds
            max_retries: Maximum retry attempts per ticker
            timeout: Request timeout in seconds
        """
        self.max_workers = max_workers
        self.rate_limit = rate_limit
        self.batch_delay = batch_delay
        self.max_retries = max_retries
        self.timeout = timeout

        self._rate_limiter = RateLimiter(calls_per_second=rate_limit, burst_limit=max_workers)
        self._backoff = ExponentialBackoff(max_retries=max_retries)
        self._progress = BatchProgress()
        self._lock = threading.Lock()
        self._cancelled = False

        # Callbacks
        self._progress_callback: Optional[Callable[[BatchProgress], None]] = None
        self._item_callback: Optional[Callable[[FetchResult], None]] = None

    def set_progress_callback(self, callback: Callable[[BatchProgress], None]) -> None:
        """Set callback for progress updates"""
        self._progress_callback = callback

    def set_item_callback(self, callback: Callable[[FetchResult], None]) -> None:
        """Set callback for individual item completions"""
        self._item_callback = callback

    def cancel(self) -> None:
        """Cancel ongoing batch operation"""
        self._cancelled = True

    def reset(self) -> None:
        """Reset client state"""
        self._cancelled = False
        self._progress = BatchProgress()

    def _update_progress(
        self,
        ticker: str = "",
        success: bool = False,
        failed: bool = False
    ) -> None:
        """Thread-safe progress update"""
        with self._lock:
            if ticker:
                self._progress.current_ticker = ticker
            if success or failed:
                self._progress.completed += 1
            if success:
                self._progress.successful += 1
            if failed:
                self._progress.failed += 1

        if self._progress_callback:
            self._progress_callback(self._progress)

    def _fetch_with_retry(
        self,
        fetch_func: Callable[[str], Tuple[Any, Optional[str]]],
        ticker: str,
        use_cache: bool = True,
        force_refresh: bool = False
    ) -> FetchResult:
        """
        Fetch data for a single ticker with retry logic.

        Args:
            fetch_func: Function to call for fetching (ticker) -> (data, error)
            ticker: Ticker symbol
            use_cache: Whether to use cached data
            force_refresh: Whether to force refresh from API

        Returns:
            FetchResult with data or error
        """
        result = FetchResult(ticker=ticker)
        start_time = time.time()

        for attempt in range(self.max_retries + 1):
            if self._cancelled:
                result.error = "Cancelled"
                return result

            # Rate limit (except for first attempt of first ticker)
            self._rate_limiter.acquire()

            try:
                # Call the actual fetch function
                # Handle different function signatures
                if force_refresh:
                    data, error = fetch_func(ticker, use_cache=use_cache, force_refresh=force_refresh)
                else:
                    data, error = fetch_func(ticker, use_cache=use_cache)

                if data and not error:
                    result.data = data
                    result.success = True
                    result.retry_count = attempt
                    result.fetch_time = time.time() - start_time
                    return result

                # API returned an error
                if error and not self._backoff.should_retry(attempt):
                    result.error = error
                    result.retry_count = attempt
                    result.fetch_time = time.time() - start_time
                    return result

                # Retry with backoff
                delay = self._backoff.get_delay(attempt)
                if delay > 0:
                    time.sleep(delay)

            except Exception as e:
                if not self._backoff.should_retry(attempt):
                    result.error = str(e)
                    result.retry_count = attempt
                    result.fetch_time = time.time() - start_time
                    return result

                delay = self._backoff.get_delay(attempt)
                if delay > 0:
                    time.sleep(delay)

        result.error = f"Max retries ({self.max_retries}) exceeded"
        result.fetch_time = time.time() - start_time
        return result

    def fetch_fundamentals_batch(
        self,
        tickers: List[str],
        fetch_func: Callable,
        use_cache: bool = True,
        force_refresh: bool = False,
        progress_interval: int = 20
    ) -> Dict[str, FetchResult]:
        """
        Fetch fundamentals for multiple tickers in parallel.

        Args:
            tickers: List of ticker symbols
            fetch_func: Function to fetch fundamentals (eod_get_fundamentals)
            use_cache: Whether to use cached data
            force_refresh: Whether to force refresh from API
            progress_interval: Log progress every N tickers

        Returns:
            Dict mapping ticker -> FetchResult
        """
        self.reset()
        self._progress.total = len(tickers)
        self._progress.start_time = time.time()

        results: Dict[str, FetchResult] = {}

        print(f"[PARALLEL] Starting batch fetch for {len(tickers)} tickers "
              f"(workers={self.max_workers}, rate_limit={self.rate_limit}/s)")

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            # Submit all tasks
            future_to_ticker = {
                executor.submit(
                    self._fetch_with_retry,
                    fetch_func,
                    ticker,
                    use_cache,
                    force_refresh
                ): ticker
                for ticker in tickers
            }

            # Process completed tasks
            for future in as_completed(future_to_ticker):
                if self._cancelled:
                    executor.shutdown(wait=False, cancel_futures=True)
                    break

                ticker = future_to_ticker[future]

                try:
                    result = future.result()
                    results[ticker] = result

                    self._update_progress(
                        ticker=ticker,
                        success=result.success,
                        failed=not result.success
                    )

                    if self._item_callback:
                        self._item_callback(result)

                    # Progress logging
                    if self._progress.completed % progress_interval == 0:
                        elapsed = self._progress.elapsed_time
                        rate = self._progress.completed / elapsed if elapsed > 0 else 0
                        print(f"   [PARALLEL] Progress: {self._progress.completed}/{self._progress.total} "
                              f"({self._progress.progress_pct:.1f}%) - "
                              f"Success: {self._progress.successful}, Failed: {self._progress.failed} - "
                              f"Rate: {rate:.1f}/s")

                except Exception as e:
                    results[ticker] = FetchResult(ticker=ticker, error=str(e))
                    self._update_progress(ticker=ticker, failed=True)

        elapsed = self._progress.elapsed_time
        print(f"[PARALLEL] Batch complete: {self._progress.successful}/{self._progress.total} successful "
              f"in {elapsed:.1f}s ({self._progress.successful/elapsed:.1f}/s)")

        return results

    def fetch_prices_batch(
        self,
        tickers: List[str],
        start_date: str,
        end_date: str,
        fetch_func: Callable,
        use_cache: bool = True,
        force_refresh: bool = False,
        progress_interval: int = 20
    ) -> Dict[str, FetchResult]:
        """
        Fetch historical prices for multiple tickers in parallel.

        Args:
            tickers: List of ticker symbols
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            fetch_func: Function to fetch prices (eod_get_historical_prices)
            use_cache: Whether to use cached data
            force_refresh: Whether to force refresh from API
            progress_interval: Log progress every N tickers

        Returns:
            Dict mapping ticker -> FetchResult
        """
        self.reset()
        self._progress.total = len(tickers)
        self._progress.start_time = time.time()

        results: Dict[str, FetchResult] = {}

        print(f"[PARALLEL] Starting price fetch for {len(tickers)} tickers "
              f"({start_date} to {end_date})")

        def fetch_with_dates(ticker, use_cache=True, force_refresh=False):
            """Wrapper to include date parameters"""
            return fetch_func(ticker, start_date, end_date, use_cache=use_cache, force_refresh=force_refresh)

        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_ticker = {
                executor.submit(
                    self._fetch_with_retry,
                    fetch_with_dates,
                    ticker,
                    use_cache,
                    force_refresh
                ): ticker
                for ticker in tickers
            }

            for future in as_completed(future_to_ticker):
                if self._cancelled:
                    executor.shutdown(wait=False, cancel_futures=True)
                    break

                ticker = future_to_ticker[future]

                try:
                    result = future.result()
                    results[ticker] = result

                    self._update_progress(
                        ticker=ticker,
                        success=result.success,
                        failed=not result.success
                    )

                    if self._item_callback:
                        self._item_callback(result)

                    if self._progress.completed % progress_interval == 0:
                        elapsed = self._progress.elapsed_time
                        rate = self._progress.completed / elapsed if elapsed > 0 else 0
                        print(f"   [PARALLEL] Progress: {self._progress.completed}/{self._progress.total} "
                              f"({self._progress.progress_pct:.1f}%) - "
                              f"Rate: {rate:.1f}/s")

                except Exception as e:
                    results[ticker] = FetchResult(ticker=ticker, error=str(e))
                    self._update_progress(ticker=ticker, failed=True)

        elapsed = self._progress.elapsed_time
        print(f"[PARALLEL] Price fetch complete: {self._progress.successful}/{self._progress.total} "
              f"in {elapsed:.1f}s")

        return results

    def fetch_fundamentals_and_prices(
        self,
        tickers: List[str],
        start_date: str,
        end_date: str,
        fundamentals_func: Callable,
        prices_func: Callable,
        use_cache: bool = True,
        extract_func: Optional[Callable] = None
    ) -> Tuple[Dict[str, dict], Dict[str, dict]]:
        """
        Fetch both fundamentals and prices with optimal parallelization.

        This method fetches fundamentals first, then only fetches prices
        for tickers that have valid fundamental data.

        Args:
            tickers: List of ticker symbols
            start_date: Start date for prices
            end_date: End date for prices
            fundamentals_func: Function to fetch fundamentals
            prices_func: Function to fetch prices
            use_cache: Whether to use cached data
            extract_func: Optional function to extract/validate fundamentals

        Returns:
            Tuple of (ticker_fundamentals, ticker_prices) dicts
        """
        print(f"[PARALLEL] Fetching fundamentals and prices for {len(tickers)} tickers")

        # Phase 1: Fetch fundamentals
        fund_results = self.fetch_fundamentals_batch(
            tickers=tickers,
            fetch_func=fundamentals_func,
            use_cache=use_cache
        )

        # Process fundamental results
        ticker_fundamentals = {}
        tickers_with_fundamentals = []

        for ticker, result in fund_results.items():
            if result.success and result.data:
                fund = result.data

                # Apply extraction/validation if provided
                if extract_func:
                    hist = extract_func(fund)
                    if hist:
                        ticker_fundamentals[ticker] = {
                            'name': fund.get('General', {}).get('Name', ticker),
                            'sector': fund.get('General', {}).get('Sector', 'Unknown'),
                            'fundamentals': hist,
                            'fund_by_year': {f['year']: f for f in hist}
                        }
                        tickers_with_fundamentals.append(ticker)
                else:
                    ticker_fundamentals[ticker] = fund
                    tickers_with_fundamentals.append(ticker)

        print(f"[PARALLEL] Loaded fundamentals for {len(ticker_fundamentals)} tickers")

        # Phase 2: Fetch prices only for tickers with valid fundamentals
        if not tickers_with_fundamentals:
            return ticker_fundamentals, {}

        price_results = self.fetch_prices_batch(
            tickers=tickers_with_fundamentals,
            start_date=start_date,
            end_date=end_date,
            fetch_func=prices_func,
            use_cache=use_cache
        )

        # Process price results
        ticker_prices = {}
        for ticker, result in price_results.items():
            if result.success and result.data and len(result.data) > 0:
                ticker_prices[ticker] = {p['date']: p for p in result.data}

        print(f"[PARALLEL] Loaded prices for {len(ticker_prices)} tickers")

        return ticker_fundamentals, ticker_prices


class BatchRefresher:
    """
    Specialized class for refreshing ticker data in batches.
    Designed for the ticker refresh workflow.
    """

    def __init__(
        self,
        client: Optional[ParallelAPIClient] = None,
        max_workers: int = 8,
        rate_limit: float = 4.0
    ):
        """
        Initialize batch refresher.

        Args:
            client: Existing ParallelAPIClient or None to create new
            max_workers: Workers for new client
            rate_limit: Rate limit for new client
        """
        self.client = client or ParallelAPIClient(
            max_workers=max_workers,
            rate_limit=rate_limit
        )
        self._status = {
            'running': False,
            'total': 0,
            'progress': 0,
            'current_ticker': '',
            'message': ''
        }
        self._lock = threading.Lock()

    @property
    def status(self) -> dict:
        """Get current refresh status"""
        with self._lock:
            return self._status.copy()

    def _update_status(self, **kwargs) -> None:
        """Update status fields"""
        with self._lock:
            self._status.update(kwargs)

    def refresh_tickers(
        self,
        tickers: List[dict],
        fundamentals_func: Callable,
        prices_func: Callable,
        get_cache_path_func: Callable,
        is_cache_valid_func: Callable,
        price_days: int = 380,
        cache_validity_days: int = 7,
        on_progress: Optional[Callable[[int, int, str], None]] = None
    ) -> Dict[str, FetchResult]:
        """
        Refresh data for multiple tickers in parallel.

        Args:
            tickers: List of ticker dicts with 'ticker' key
            fundamentals_func: Function to fetch fundamentals
            prices_func: Function to fetch prices
            get_cache_path_func: Function to get cache file path
            is_cache_valid_func: Function to check cache validity
            price_days: Days of price history to fetch
            cache_validity_days: Days before cache is considered stale
            on_progress: Optional callback(completed, total, ticker)

        Returns:
            Dict of ticker -> FetchResult
        """
        from datetime import datetime, timedelta
        import os

        self._update_status(
            running=True,
            total=len(tickers),
            progress=0,
            message='Starting parallel refresh...'
        )

        ticker_symbols = [t['ticker'] for t in tickers]

        # Calculate date range for prices
        end_date = datetime.now().strftime('%Y-%m-%d')
        start_date = (datetime.now() - timedelta(days=price_days)).strftime('%Y-%m-%d')

        # Filter tickers that need price refresh
        tickers_needing_prices = []
        for ticker in ticker_symbols:
            price_cache_file = get_cache_path_func('prices', f"{ticker}_{start_date}_{end_date}")
            if not is_cache_valid_func(price_cache_file, cache_validity_days):
                tickers_needing_prices.append(ticker)

        print(f"[REFRESH] {len(tickers_needing_prices)} tickers need price refresh")

        # Set up progress tracking
        def on_item_complete(result: FetchResult):
            self._update_status(
                progress=self.client._progress.completed,
                current_ticker=result.ticker
            )
            if on_progress:
                on_progress(
                    self.client._progress.completed,
                    self.client._progress.total,
                    result.ticker
                )

        self.client.set_item_callback(on_item_complete)

        # Phase 1: Refresh fundamentals (all tickers)
        self._update_status(message='Refreshing fundamentals...')
        fund_results = self.client.fetch_fundamentals_batch(
            tickers=ticker_symbols,
            fetch_func=fundamentals_func,
            use_cache=True,
            force_refresh=True
        )

        # Phase 2: Refresh prices (only stale ones)
        if tickers_needing_prices:
            self._update_status(message='Refreshing prices...')
            self.client.fetch_prices_batch(
                tickers=tickers_needing_prices,
                start_date=start_date,
                end_date=end_date,
                fetch_func=prices_func,
                use_cache=True,
                force_refresh=True
            )

        self._update_status(
            running=False,
            message='Refresh complete!'
        )

        return fund_results

    def cancel(self) -> None:
        """Cancel ongoing refresh"""
        self.client.cancel()
        self._update_status(
            running=False,
            message='Refresh cancelled'
        )


# Convenience functions for easy integration
def create_parallel_client(
    max_workers: int = 10,
    rate_limit: float = 5.0
) -> ParallelAPIClient:
    """Create a configured parallel API client"""
    return ParallelAPIClient(
        max_workers=max_workers,
        rate_limit=rate_limit,
        max_retries=3,
        timeout=30.0
    )


def parallel_fetch_fundamentals(
    tickers: List[str],
    fetch_func: Callable,
    max_workers: int = 10,
    use_cache: bool = True
) -> Dict[str, Any]:
    """
    Quick parallel fetch of fundamentals.

    Returns dict of ticker -> fundamental data (or None if failed)
    """
    client = create_parallel_client(max_workers=max_workers)
    results = client.fetch_fundamentals_batch(tickers, fetch_func, use_cache=use_cache)

    return {
        ticker: result.data
        for ticker, result in results.items()
        if result.success
    }


def parallel_fetch_prices(
    tickers: List[str],
    start_date: str,
    end_date: str,
    fetch_func: Callable,
    max_workers: int = 10,
    use_cache: bool = True
) -> Dict[str, list]:
    """
    Quick parallel fetch of prices.

    Returns dict of ticker -> price list (or None if failed)
    """
    client = create_parallel_client(max_workers=max_workers)
    results = client.fetch_prices_batch(
        tickers, start_date, end_date, fetch_func, use_cache=use_cache
    )

    return {
        ticker: result.data
        for ticker, result in results.items()
        if result.success
    }


# ============================================================
# USAGE EXAMPLES
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("PARALLEL API CLIENT - Demo")
    print("=" * 60)

    # Demo with mock function
    def mock_fetch(ticker, use_cache=True, force_refresh=False):
        """Mock fetch function for testing"""
        time.sleep(random.uniform(0.1, 0.3))  # Simulate API latency
        if random.random() < 0.1:  # 10% failure rate
            return None, f"Mock error for {ticker}"
        return {'ticker': ticker, 'data': 'mock_data'}, None

    def mock_price_fetch(ticker, start, end, use_cache=True, force_refresh=False):
        """Mock price fetch for testing"""
        time.sleep(random.uniform(0.1, 0.3))
        if random.random() < 0.1:
            return None, f"Mock price error for {ticker}"
        return [{'date': '2024-01-01', 'close': 100.0}], None

    # Test tickers
    test_tickers = [f"TEST{i}" for i in range(50)]

    print(f"\nTesting with {len(test_tickers)} mock tickers...")

    client = ParallelAPIClient(max_workers=10, rate_limit=20.0)

    # Test fundamentals fetch
    print("\n--- Fundamentals Fetch ---")
    results = client.fetch_fundamentals_batch(test_tickers, mock_fetch)

    success_count = sum(1 for r in results.values() if r.success)
    print(f"Results: {success_count}/{len(test_tickers)} successful")

    # Test price fetch
    print("\n--- Price Fetch ---")
    price_results = client.fetch_prices_batch(
        test_tickers[:20],
        '2024-01-01',
        '2024-12-31',
        mock_price_fetch
    )

    success_count = sum(1 for r in price_results.values() if r.success)
    print(f"Results: {success_count}/{20} successful")

    print("\n" + "=" * 60)
    print("Demo complete!")

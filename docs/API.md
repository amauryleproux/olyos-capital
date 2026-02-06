# Olyos Capital API Documentation

This document describes the HTTP API endpoints available in the Olyos Capital Portfolio Terminal.

## Table of Contents

- [Overview](#overview)
- [Base URL](#base-url)
- [Response Formats](#response-formats)
- [Page Endpoints (GET)](#page-endpoints-get)
  - [GET / - Portfolio Dashboard](#get---portfolio-dashboard)
  - [GET /screener - Screener Page](#get-screener---screener-page)
  - [GET /screener_cache.json - Screener Cache](#get-screener_cachejson---screener-cache)
  - [GET /detail - Security Detail Page](#get-detail---security-detail-page)
  - [GET /backtest - Backtest Page](#get-backtest---backtest-page)
  - [GET /ai-optimization - AI Optimization Page](#get-ai-optimization---ai-optimization-page)
- [API Endpoints (GET)](#api-endpoints-get)
  - [Watchlist Management](#watchlist-management)
  - [Portfolio Management](#portfolio-management)
  - [Data Refresh](#data-refresh)
  - [Cache Operations](#cache-operations)
  - [Screener Data](#screener-data)
  - [Backtest History](#backtest-history)
  - [File Download](#file-download)
- [API Endpoints (POST)](#api-endpoints-post)
  - [Memo Operations](#memo-operations)
  - [Backtest Operations](#backtest-operations)
  - [Data Operations](#data-operations)
  - [AI Operations](#ai-operations)
  - [Cache Management](#cache-management)

---

## Overview

The Olyos Capital API provides endpoints for managing a stock portfolio, running screeners, executing backtests, and generating investment memos. The API uses a combination of query parameters and POST body data depending on the endpoint.

## Base URL

```
http://localhost:8080
```

The server runs on port 8080 by default (configurable in CONFIG).

## Response Formats

The API returns responses in two primary formats:

- **HTML**: Full page content for browser rendering
- **JSON**: Structured data for programmatic access

JSON responses typically follow this structure:

```json
{
  "success": true,
  "data": { ... }
}
```

Or for errors:

```json
{
  "success": false,
  "error": "Error message description"
}
```

---

## Page Endpoints (GET)

### GET / - Portfolio Dashboard

Returns the main portfolio dashboard HTML page.

**Request**

```
GET /
```

**Optional Query Parameters**

| Parameter | Type | Description |
|-----------|------|-------------|
| `refresh` | flag | Refresh portfolio data from market sources |
| `screener` | flag | Force refresh of screener data |
| `scope` | string | Screener scope: `france`, `europe` (default: `france`) |
| `mode` | string | Screener mode: `standard`, `advanced` (default: `standard`) |

**Response**

- Content-Type: `text/html; charset=utf-8`
- Returns the portfolio dashboard HTML

**Example**

```
GET /?refresh
GET /?screener&scope=europe&mode=advanced
```

---

### GET /screener - Screener Page

Returns the stock screener page HTML.

**Request**

```
GET /screener
```

**Response**

- Content-Type: `text/html; charset=utf-8`
- Cache-Control: `no-cache`
- Returns the screener page HTML (from `screener_v2.html`)

---

### GET /screener_cache.json - Screener Cache

Returns the cached screener data as JSON.

**Request**

```
GET /screener_cache.json
```

**Response**

- Content-Type: `application/json`
- Cache-Control: `public, max-age=1800`
- Returns cached screener data or 404 if cache doesn't exist

---

### GET /detail - Security Detail Page

Returns a detailed view page for a specific security/ticker.

**Request**

```
GET /detail?t=TICKER
```

**Query Parameters**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `t` | string | Yes | Ticker symbol (e.g., `AAPL`, `MC.PA`) |

**Response**

- Content-Type: `text/html; charset=utf-8`
- Returns the security detail page HTML

**Example**

```
GET /detail?t=MC.PA
```

---

### GET /backtest - Backtest Page

Returns the backtest configuration and results page HTML.

**Request**

```
GET /backtest
```

**Response**

- Content-Type: `text/html; charset=utf-8`
- Cache-Control: `no-cache`
- Returns the backtest page HTML (from `backtest.html`) or null if not found

---

### GET /ai-optimization - AI Optimization Page

Returns the AI optimization page HTML.

**Request**

```
GET /ai-optimization
```

**Response**

- Content-Type: `text/html; charset=utf-8`
- Cache-Control: `no-cache`
- Returns the AI optimization page HTML (from `ai_optimization.html`) or null if not found

---

## API Endpoints (GET)

### Watchlist Management

#### Add to Watchlist

Adds a ticker to the user's watchlist.

**Request**

```
GET /?action=add_watchlist&ticker=XXX&name=YYY&country=ZZZ&sector=SSS
```

**Query Parameters**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | Yes | Must be `add_watchlist` |
| `ticker` | string | Yes | Ticker symbol |
| `name` | string | No | Company name (URL-encoded) |
| `country` | string | No | Country code |
| `sector` | string | No | Sector name (URL-encoded) |

**Response**

- Status: 200
- Body: Empty on success

**Example**

```
GET /?action=add_watchlist&ticker=MC.PA&name=LVMH&country=FR&sector=Consumer%20Goods
```

---

#### Remove from Watchlist

Removes a ticker from the user's watchlist.

**Request**

```
GET /?action=remove_watchlist&ticker=XXX
```

**Query Parameters**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | Yes | Must be `remove_watchlist` |
| `ticker` | string | Yes | Ticker symbol to remove |

**Response**

- Status: 200
- Body: Empty on success

**Example**

```
GET /?action=remove_watchlist&ticker=MC.PA
```

---

### Portfolio Management

#### Add Portfolio Position

Adds a new position to the portfolio.

**Request**

```
GET /?action=add_portfolio&ticker=XXX&name=YYY&qty=N&avg_cost=M
```

**Query Parameters**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | Yes | Must be `add_portfolio` |
| `ticker` | string | Yes | Ticker symbol |
| `name` | string | Yes | Company name (URL-encoded) |
| `qty` | number | Yes | Number of shares |
| `avg_cost` | number | Yes | Average cost per share |

**Response**

- Content-Type: `text/plain`
- Status: 200 on success, 400 on error
- Body: `OK` on success, error message on failure

**Example**

```
GET /?action=add_portfolio&ticker=MC.PA&name=LVMH&qty=10&avg_cost=750.50
```

---

#### Edit Portfolio Position

Edits an existing position in the portfolio.

**Request**

```
GET /?action=edit_portfolio&ticker=XXX&qty=N&avg_cost=M
```

**Query Parameters**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | Yes | Must be `edit_portfolio` |
| `ticker` | string | Yes | Ticker symbol |
| `qty` | number | Yes | New number of shares |
| `avg_cost` | number | Yes | New average cost per share |

**Response**

- Content-Type: `text/plain`
- Status: 200 on success, 400 on error
- Body: `OK` on success, error message on failure

**Example**

```
GET /?action=edit_portfolio&ticker=MC.PA&qty=15&avg_cost=720.00
```

---

#### Remove Portfolio Position

Removes a position from the portfolio.

**Request**

```
GET /?action=remove_portfolio&ticker=XXX
```

**Query Parameters**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | Yes | Must be `remove_portfolio` |
| `ticker` | string | Yes | Ticker symbol to remove |

**Response**

- Content-Type: `text/plain`
- Status: 200 on success, 400 on error
- Body: `OK` on success, error message on failure

**Example**

```
GET /?action=remove_portfolio&ticker=MC.PA
```

---

### Data Refresh

#### Start Screener Data Refresh

Initiates a background refresh of screener data.

**Request**

```
GET /?action=refresh_screener_data&scope=XXX
```

**Query Parameters**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | Yes | Must be `refresh_screener_data` |
| `scope` | string | No | Market scope: `france`, `europe` (default: `france`) |

**Response**

- Content-Type: `application/json`

Success:
```json
{
  "status": "started"
}
```

Error (refresh already running):
```json
{
  "error": "Refresh already running"
}
```

---

#### Get Refresh Status

Gets the current status of a running data refresh operation.

**Request**

```
GET /?action=refresh_status
```

**Response**

- Content-Type: `application/json`

```json
{
  "running": true,
  "progress": 45,
  "total": 100,
  "current_ticker": "MC.PA",
  "message": "Refreshing data..."
}
```

| Field | Type | Description |
|-------|------|-------------|
| `running` | boolean | Whether refresh is currently active |
| `progress` | number | Number of tickers processed |
| `total` | number | Total tickers to process |
| `current_ticker` | string | Currently processing ticker |
| `message` | string | Status message |

---

### Cache Operations

#### Get Cache Statistics

Returns statistics about the data cache.

**Request**

```
GET /?action=cache_stats
```

**Response**

- Content-Type: `application/json`

```json
{
  "cache_size": 1024000,
  "file_count": 150,
  "oldest_file": "2024-01-01",
  "newest_file": "2024-02-01"
}
```

---

### Screener Data

#### Get Screener Data as JSON

Returns screener results as JSON data.

**Request**

```
GET /?action=screener_json&scope=XXX&mode=YYY&force
```

**Query Parameters**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `action` | string | Yes | Must be `screener_json` |
| `scope` | string | No | Market scope: `france`, `europe` (default: `france`) |
| `mode` | string | No | Screening mode: `standard`, `advanced` (default: `standard`) |
| `force` | flag | No | Force fresh data (bypass cache) |

**Response**

- Content-Type: `application/json`
- Cache-Control: `public, max-age=3600`
- Access-Control-Allow-Origin: `*`

```json
{
  "screener": [
    {
      "ticker": "MC.PA",
      "name": "LVMH",
      "price": 750.50,
      "pe": 25.3,
      "roe": 18.5,
      "score": 85
    }
  ],
  "watchlist": ["MC.PA", "OR.PA"],
  "meta": {
    "scope": "france",
    "mode": "standard",
    "count": 150,
    "timestamp": "2024-02-01T12:00:00",
    "cached": true
  }
}
```

---

### Backtest History

#### Get Backtest History

Returns the history of saved backtests.

**Request**

```
GET /?action=backtest_history
```

**Response**

- Content-Type: `application/json`

```json
[
  {
    "id": "bt_20240201_120000",
    "name": "France Small Caps",
    "date": "2024-02-01",
    "metrics": {
      "total_return": 125.5,
      "sharpe_ratio": 1.45,
      "max_drawdown": -15.2
    }
  }
]
```

---

### File Download

#### Download File

Downloads a generated file (e.g., memo document).

**Request**

```
GET /?download=PATH
```

**Query Parameters**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `download` | string | Yes | File path (URL-encoded) |

**Response**

- Content-Type: `application/vnd.openxmlformats-officedocument.wordprocessingml.document`
- Content-Disposition: `attachment; filename="filename.docx"`
- Body: Binary file content

**Security**

- Path traversal is prevented - only files within the configured `memo_dir` can be downloaded
- Returns 403 for blocked paths, 404 for non-existent files

---

## API Endpoints (POST)

### Memo Operations

#### Create Memo

Creates an investment memo document from form data.

**Request**

```
POST /?action=create_memo
Content-Type: application/x-www-form-urlencoded
```

**Form Parameters**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `ticker` | string | Yes | Ticker symbol |
| `name` | string | Yes | Company name |
| `sector` | string | No | Sector |
| `country` | string | No | Country |
| `signal` | string | No | Investment signal (default: `Surveillance`) |
| `target_price` | string | No | Target price |
| `thesis` | string | No | Investment thesis |
| `strengths` | string | No | Key strengths |
| `risks` | string | No | Key risks |
| `valuation` | string | No | Valuation notes |
| `notes` | string | No | Additional notes |

**Response**

- Content-Type: `application/json`

Success:
```json
{
  "success": true,
  "filepath": "/path/to/memo.docx"
}
```

Error:
```json
{
  "success": false,
  "error": "Error description"
}
```

---

#### Generate AI Memo

Generates an investment memo using AI based on security data.

**Request**

```
POST /?action=generate_ai_memo&ticker=XXX
```

**Query Parameters**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `ticker` | string | Yes | Ticker symbol |

**Response**

- Content-Type: `application/json`

Success:
```json
{
  "success": true,
  "filepath": "/path/to/ai_memo.docx"
}
```

Error:
```json
{
  "success": false,
  "error": "Error description"
}
```

---

### Backtest Operations

#### Run Backtest

Executes a backtest with the specified parameters.

**Request**

```
POST /?action=run_backtest
Content-Type: application/json
```

**Request Body**

```json
{
  "start_date": "2015-01-01",
  "end_date": "2024-01-01",
  "universe_scope": "france",
  "universe": "MC.PA,OR.PA,SAN.PA",
  "pe_max": 12,
  "roe_min": 10,
  "pe_sell": 17,
  "roe_min_hold": 8,
  "debt_equity_max": 100,
  "rebalance_freq": "quarterly",
  "initial_capital": 100000,
  "max_positions": 20,
  "benchmark": "^FCHI"
}
```

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `start_date` | string | `2015-01-01` | Backtest start date (YYYY-MM-DD) |
| `end_date` | string | Today | Backtest end date (YYYY-MM-DD) |
| `universe_scope` | string | `france` | Market scope: `france`, `europe`, `custom` |
| `universe` | string | - | Comma-separated tickers (for custom mode) |
| `pe_max` | number | `12` | Maximum P/E ratio for buy signal |
| `roe_min` | number | `10` | Minimum ROE (%) for buy signal |
| `pe_sell` | number | `17` | P/E ratio threshold for sell signal |
| `roe_min_hold` | number | `8` | Minimum ROE (%) to hold position |
| `debt_equity_max` | number | `100` | Maximum debt/equity ratio (%) |
| `rebalance_freq` | string | `quarterly` | Rebalancing frequency: `monthly`, `quarterly`, `yearly` |
| `initial_capital` | number | `100000` | Starting capital |
| `max_positions` | number | `20` | Maximum number of positions |
| `benchmark` | string | `^FCHI` | Benchmark index ticker |

**Response**

- Content-Type: `application/json`

Success:
```json
{
  "metrics": {
    "total_return": 125.5,
    "annualized_return": 12.3,
    "sharpe_ratio": 1.45,
    "sortino_ratio": 1.82,
    "max_drawdown": -15.2,
    "win_rate": 65.5
  },
  "equity_curve": [...],
  "trades": [...],
  "saved_id": "bt_20240201_120000"
}
```

Error:
```json
{
  "error": "Backtest error occurred"
}
```

---

#### Rename Backtest

Renames a saved backtest.

**Request**

```
POST /?action=rename_backtest&id=XXX&name=YYY
```

**Query Parameters**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `id` | string | Yes | Backtest ID |
| `name` | string | Yes | New name (URL-encoded) |

**Response**

- Content-Type: `application/json`

```json
{
  "success": true
}
```

---

#### Delete Backtest

Deletes a saved backtest.

**Request**

```
POST /?action=delete_backtest&id=XXX
```

**Query Parameters**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `id` | string | Yes | Backtest ID |

**Response**

- Content-Type: `application/json`

```json
{
  "success": true
}
```

---

### Data Operations

#### Download All Data

Downloads and caches all market data for a scope.

**Request**

```
POST /?action=download_data&scope=XXX
```

**Query Parameters**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `scope` | string | No | Market scope: `france`, `europe` (default: `france`) |

**Response**

- Content-Type: `application/json`

Success:
```json
{
  "status": "completed",
  "tickers_downloaded": 150,
  "duration_seconds": 120
}
```

Error:
```json
{
  "error": "Download error occurred"
}
```

---

### AI Operations

#### Run AI Optimization

Runs AI-powered portfolio optimization.

**Request**

```
POST /?action=ai_optimize&scope=XXX&goal=YYY
```

**Query Parameters**

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| `scope` | string | No | Market scope: `france`, `europe` (default: `france`) |
| `goal` | string | No | Optimization goal: `balanced`, `growth`, `income`, `defensive` (default: `balanced`) |

**Response**

- Content-Type: `application/json`

```json
{
  "recommendations": [
    {
      "ticker": "MC.PA",
      "name": "LVMH",
      "weight": 0.15,
      "rationale": "Strong fundamentals..."
    }
  ],
  "metrics": {
    "expected_return": 12.5,
    "expected_volatility": 18.2,
    "sharpe_ratio": 0.68
  }
}
```

Error:
```json
{
  "error": "Optimization error occurred"
}
```

---

### Cache Management

#### Clear Cache

Clears all cached data.

**Request**

```
POST /?action=clear_cache
```

**Response**

- Content-Type: `application/json`

Success:
```json
{
  "message": "Cache cleared successfully"
}
```

Error:
```json
{
  "error": "Cache clear error occurred"
}
```

---

## Error Handling

All API endpoints return appropriate HTTP status codes:

| Status Code | Description |
|-------------|-------------|
| 200 | Success |
| 400 | Bad Request - Invalid parameters |
| 403 | Forbidden - Security violation (e.g., path traversal) |
| 404 | Not Found - Resource doesn't exist |
| 500 | Internal Server Error |

For JSON endpoints, errors include an `error` field with a description:

```json
{
  "success": false,
  "error": "Detailed error message"
}
```

---

## Configuration

Default configuration values (from `CONFIG`):

| Key | Default | Description |
|-----|---------|-------------|
| `portfolio_file` | `portfolio.xlsx` | Portfolio data file |
| `watchlist_file` | `watchlist.json` | Watchlist data file |
| `screener_cache_file` | `screener_cache.json` | Screener cache file |
| `nav_history_file` | `nav_history.json` | NAV history file |
| `backtest_cache_dir` | `backtest_cache` | Backtest cache directory |
| `backtest_history_file` | `backtest_history.json` | Backtest history file |
| `memo_dir` | `.` | Memo output directory |
| `port` | `8080` | Server port |
| `cache_days` | `30` | Cache validity in days |

---

## Environment Variables

| Variable | Description |
|----------|-------------|
| `EOD_API_KEY` | EOD Historical Data API key for market data |

#!/usr/bin/env python3
"""
Olyos Portfolio Advisor Agent

CLI analysis tool for a European small/mid caps portfolio with a
value/growth/cyclical framework inspired by William Higgons.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import requests
from bs4 import BeautifulSoup

try:
    import yfinance as yf
except ImportError:  # pragma: no cover - dependency issue at runtime
    yf = None


try:
    from rich.console import Console
    from rich.markdown import Markdown
except ImportError:  # pragma: no cover - optional rendering fallback
    Console = None
    Markdown = None


LOG = logging.getLogger("olyos_portfolio_advisor")

try:
    from olyos.olyos_config import (
        ADVISOR_MACRO_QUERIES,
        ADVISOR_MODEL_MAX_TOKENS,
        ADVISOR_MODEL_NAME,
        ADVISOR_REPORT_DIR,
        ADVISOR_SCRATCHPAD_DIR,
    )
except Exception:  # pragma: no cover - fallback when imported standalone
    ADVISOR_MODEL_NAME = "claude-sonnet-4-6"
    ADVISOR_MODEL_MAX_TOKENS = 3000
    ADVISOR_REPORT_DIR = "olyos_reports"
    ADVISOR_SCRATCHPAD_DIR = "olyos_scratchpad"
    ADVISOR_MACRO_QUERIES = [
        "small caps europeennes performance 2026",
        "taux BCE 2026 perspectives",
        "value investing small caps outperformance 2026",
    ]

CATEGORY_KEYS = ("value", "croissance", "cyclique", "mixte")

COUNTRY_SUFFIX_MAP = {
    "FR": ".PA",
    "DE": ".DE",
    "IT": ".MI",
    "ES": ".MC",
    "NL": ".AS",
    "BE": ".BR",
    "PT": ".LS",
    "CH": ".SW",
    "UK": ".L",
    "GB": ".L",
    "AT": ".VI",
    "SE": ".ST",
    "DK": ".CO",
    "FI": ".HE",
    "NO": ".OL",
}

def _to_float(value: Any, default: Optional[float] = None) -> Optional[float]:
    if value is None:
        return default
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace(" ", "").replace(",", ".")
        if cleaned == "":
            return default
        try:
            return float(cleaned)
        except ValueError:
            return default
    return default


def _first_existing(dct: Dict[str, Any], keys: List[str]) -> Any:
    for key in keys:
        if key in dct and dct[key] not in (None, ""):
            return dct[key]
    return None


def _normalize_country(country: Any) -> Optional[str]:
    if country is None:
        return None
    value = str(country).strip().upper()
    if len(value) == 2:
        return value
    aliases = {
        "FRANCE": "FR",
        "GERMANY": "DE",
        "ALLEMAGNE": "DE",
        "ITALY": "IT",
        "ITALIE": "IT",
        "SPAIN": "ES",
        "ESPAGNE": "ES",
        "NETHERLANDS": "NL",
        "PAYS-BAS": "NL",
        "BELGIUM": "BE",
        "BELGIQUE": "BE",
        "PORTUGAL": "PT",
        "SWITZERLAND": "CH",
        "SUISSE": "CH",
        "UNITED KINGDOM": "UK",
        "ROYAUME-UNI": "UK",
        "AUSTRIA": "AT",
        "AUTRICHE": "AT",
        "SWEDEN": "SE",
        "SUEDE": "SE",
        "DENMARK": "DK",
        "DANEMARK": "DK",
        "FINLAND": "FI",
        "FINLANDE": "FI",
        "NORWAY": "NO",
        "NORVEGE": "NO",
    }
    return aliases.get(value, value if len(value) == 2 else None)


def _normalize_category(value: Any) -> str:
    if value is None:
        return "mixte"

    text = str(value).strip().lower()
    mapping = {
        "value": "value",
        "valeur": "value",
        "growth": "croissance",
        "croissance": "croissance",
        "cyclique": "cyclique",
        "cyclical": "cyclique",
        "cyclic": "cyclique",
        "mixte": "mixte",
        "mixed": "mixte",
        "blend": "mixte",
    }
    return mapping.get(text, "mixte")


def load_portfolio(json_path: str) -> Dict[str, Any]:
    """
    Load portfolio JSON file and normalize structure.
    Required fields per position: ticker, shares, avg_price.
    """
    with open(json_path, "r", encoding="utf-8") as f:
        raw = json.load(f)

    warnings: List[str] = []

    if isinstance(raw, list):
        raw_positions = raw
        cash = 0.0
        currency = "EUR"
    elif isinstance(raw, dict):
        raw_positions = None
        for key in ("portfolio", "positions", "holdings", "data", "items"):
            candidate = raw.get(key)
            if isinstance(candidate, list):
                raw_positions = candidate
                break
        if raw_positions is None:
            list_candidates = [v for v in raw.values() if isinstance(v, list)]
            raw_positions = list_candidates[0] if list_candidates else []
        cash = _to_float(_first_existing(raw, ["cash", "liquidity", "available_cash"]), 0.0) or 0.0
        currency = str(_first_existing(raw, ["currency", "devise"]) or "EUR").upper()
    else:
        raise ValueError("Unsupported JSON format. Expected dict or list.")

    if not isinstance(raw_positions, list) or not raw_positions:
        raise ValueError("No portfolio positions found in JSON.")

    normalized_positions: List[Dict[str, Any]] = []

    for idx, row in enumerate(raw_positions):
        if not isinstance(row, dict):
            warnings.append(f"Line {idx + 1}: invalid row type skipped.")
            continue

        ticker = _first_existing(row, ["ticker", "symbol", "code"])
        shares = _to_float(_first_existing(row, ["shares", "qty", "quantity", "position"]), None)
        avg_price = _to_float(_first_existing(row, ["avg_price", "avg_cost", "average_price", "cost_basis"]), None)

        if not ticker or shares is None or avg_price is None:
            warnings.append(
                f"Line {idx + 1}: missing required fields (ticker/shares/avg_price), row skipped."
            )
            continue

        country = _normalize_country(_first_existing(row, ["country", "pays", "market_country"]))
        position = {
            "ticker": str(ticker).strip().upper(),
            "name": _first_existing(row, ["name", "company", "company_name"]),
            "isin": _first_existing(row, ["isin", "ISIN"]),
            "category": _normalize_category(_first_existing(row, ["category", "style", "bucket"])),
            "shares": shares,
            "avg_price": avg_price,
            "current_price": _to_float(_first_existing(row, ["current_price", "price", "last_price"]), None),
            "sector": _first_existing(row, ["sector", "industry"]),
            "country": country,
            "notes": _first_existing(row, ["notes", "comment", "thesis"]),
            "weight_initial": 0.0,
        }
        normalized_positions.append(position)

    if not normalized_positions:
        raise ValueError("No valid positions after validation.")

    total_invested = sum((p["shares"] * p["avg_price"]) for p in normalized_positions)
    for position in normalized_positions:
        if total_invested > 0:
            position["weight_initial"] = (position["shares"] * position["avg_price"]) / total_invested
        else:
            position["weight_initial"] = 0.0

    return {
        "portfolio": normalized_positions,
        "cash": cash,
        "currency": currency,
        "warnings": warnings,
    }


def _build_yahoo_candidates(ticker: str, country_code: Optional[str]) -> List[str]:
    base = ticker.strip().upper()
    if "." in base:
        return [base]

    candidates: List[str] = []
    candidates.append(f"{base}.PA")

    suffix = COUNTRY_SUFFIX_MAP.get((country_code or "").upper(), "")
    if suffix and suffix != ".PA":
        candidates.append(f"{base}{suffix}")

    candidates.append(base)  # keep last fallback without suffix
    return candidates


def _fetch_symbol_snapshot(symbol: str) -> Optional[Dict[str, Any]]:
    if yf is None:
        raise RuntimeError("yfinance is not installed. Install with: pip install yfinance")

    try:
        ticker_obj = yf.Ticker(symbol)
        history = ticker_obj.history(period="1y", interval="1d", auto_adjust=False)
        if history is None or history.empty:
            return None

        close_series = history.get("Close")
        if close_series is None or close_series.dropna().empty:
            return None

        current_price = float(close_series.dropna().iloc[-1])
        volume_series = history.get("Volume")
        avg_volume_30d = (
            float(volume_series.dropna().tail(30).mean())
            if volume_series is not None and not volume_series.dropna().empty
            else None
        )
        high_52w = float(history["High"].dropna().max()) if "High" in history and not history["High"].dropna().empty else None
        low_52w = float(history["Low"].dropna().min()) if "Low" in history and not history["Low"].dropna().empty else None

        info = ticker_obj.info or {}
        if info:
            high_52w = _to_float(info.get("fiftyTwoWeekHigh"), high_52w)
            low_52w = _to_float(info.get("fiftyTwoWeekLow"), low_52w)

        return {
            "price": current_price,
            "avg_volume_30d": avg_volume_30d,
            "52w_high": high_52w,
            "52w_low": low_52w,
            "pe": _to_float(info.get("trailingPE"), None),
            "market_cap": _to_float(info.get("marketCap"), None),
            "dividend_yield": _to_float(info.get("dividendYield"), None),
            "yahoo_symbol": symbol,
        }
    except Exception:
        return None


def fetch_current_prices(tickers: List[str], country_by_ticker: Optional[Dict[str, str]] = None) -> Dict[str, Dict[str, Any]]:
    """
    Fetch market data from Yahoo Finance.

    Returned fields:
    - price
    - avg_volume_30d
    - 52w_high / 52w_low
    - pe
    - market_cap
    - dividend_yield
    """
    prices: Dict[str, Dict[str, Any]] = {}

    for raw_ticker in tickers:
        ticker = str(raw_ticker).strip().upper()
        country = (country_by_ticker or {}).get(ticker)
        candidates = _build_yahoo_candidates(ticker, country)
        snapshot = None
        chosen = None

        for candidate in candidates:
            snapshot = _fetch_symbol_snapshot(candidate)
            if snapshot and snapshot.get("price") is not None:
                chosen = candidate
                break

        if snapshot and chosen:
            prices[ticker] = snapshot
        else:
            LOG.warning("Ticker not found on Yahoo Finance: %s", ticker)
            prices[ticker] = {
                "price": None,
                "avg_volume_30d": None,
                "52w_high": None,
                "52w_low": None,
                "pe": None,
                "market_cap": None,
                "dividend_yield": None,
                "yahoo_symbol": None,
                "error": "Ticker not found on Yahoo Finance",
            }

    return prices


def compute_portfolio_metrics(
    portfolio: List[Dict[str, Any]],
    prices: Dict[str, Dict[str, Any]],
    cash: float = 0.0,
    currency: str = "EUR",
) -> Dict[str, Any]:
    provisional_positions: List[Dict[str, Any]] = []
    total_invested = 0.0
    total_current_value = 0.0

    for position in portfolio:
        ticker = position["ticker"]
        market = prices.get(ticker, {})

        current_price = _to_float(market.get("price"), None)
        if current_price is None:
            current_price = _to_float(position.get("current_price"), None)
        if current_price is None:
            current_price = _to_float(position.get("avg_price"), 0.0) or 0.0

        shares = _to_float(position.get("shares"), 0.0) or 0.0
        avg_price = _to_float(position.get("avg_price"), 0.0) or 0.0

        cost_basis = shares * avg_price
        current_value = shares * current_price
        pnl_eur = current_value - cost_basis
        pnl_pct = (pnl_eur / cost_basis) if cost_basis > 0 else 0.0

        total_invested += cost_basis
        total_current_value += current_value

        provisional_positions.append(
            {
                "ticker": ticker,
                "name": position.get("name"),
                "category": _normalize_category(position.get("category")),
                "sector": position.get("sector") or "Unknown",
                "country": position.get("country") or "Unknown",
                "shares": shares,
                "avg_price": avg_price,
                "current_price": current_price,
                "cost_basis": cost_basis,
                "current_value": current_value,
                "pnl_eur": pnl_eur,
                "pnl_pct": pnl_pct,
                "weight_pct": 0.0,
                "vs_52w_high": None,
                "vs_52w_low": None,
            }
        )

    for row in provisional_positions:
        ticker = row["ticker"]
        market = prices.get(ticker, {})

        if total_current_value > 0:
            row["weight_pct"] = row["current_value"] / total_current_value
        else:
            row["weight_pct"] = 0.0

        high_52w = _to_float(market.get("52w_high"), None)
        low_52w = _to_float(market.get("52w_low"), None)
        px = _to_float(row.get("current_price"), None)

        if px is not None and high_52w and high_52w > 0:
            row["vs_52w_high"] = (px - high_52w) / high_52w
        if px is not None and low_52w and low_52w > 0:
            row["vs_52w_low"] = (px - low_52w) / low_52w

    total_pnl_eur = total_current_value - total_invested
    total_pnl_pct = (total_pnl_eur / total_invested) if total_invested > 0 else 0.0

    return {
        "currency": currency,
        "cash": cash,
        "total_invested": total_invested,
        "total_current_value": total_current_value,
        "total_value_with_cash": total_current_value + cash,
        "total_pnl_eur": total_pnl_eur,
        "total_pnl_pct": total_pnl_pct,
        "positions": provisional_positions,
    }


def analyze_concentration(metrics: Dict[str, Any]) -> Dict[str, Any]:
    positions = metrics.get("positions", [])
    if not positions:
        return {
            "max_single_position": 0.0,
            "top3_concentration": 0.0,
            "sector_breakdown": {},
            "country_breakdown": {},
            "alerts": [],
        }

    sorted_positions = sorted(positions, key=lambda x: x.get("weight_pct", 0.0), reverse=True)
    max_single = sorted_positions[0].get("weight_pct", 0.0)
    top3 = sum(row.get("weight_pct", 0.0) for row in sorted_positions[:3])

    sector_breakdown: Dict[str, float] = {}
    country_breakdown: Dict[str, float] = {}
    alerts: List[str] = []

    for row in positions:
        sector = row.get("sector") or "Unknown"
        country = row.get("country") or "Unknown"
        weight = row.get("weight_pct", 0.0)
        sector_breakdown[sector] = sector_breakdown.get(sector, 0.0) + weight
        country_breakdown[country] = country_breakdown.get(country, 0.0) + weight

    if max_single > 0.20:
        alerts.append("Position unique > 20% du portefeuille")
    if top3 > 0.50:
        alerts.append("Top 3 positions > 50% - concentration elevee")

    for sector, weight in sorted(sector_breakdown.items(), key=lambda x: x[1], reverse=True):
        if weight > 0.40:
            alerts.append(f"Secteur {sector} represente {weight:.0%} du portefeuille")

    return {
        "max_single_position": max_single,
        "top3_concentration": top3,
        "sector_breakdown": sector_breakdown,
        "country_breakdown": country_breakdown,
        "alerts": alerts,
    }


def analyze_category_balance(metrics: Dict[str, Any]) -> Dict[str, Any]:
    categories: Dict[str, Dict[str, Any]] = {
        "value": {"weight": 0.0, "avg_pnl": 0.0, "positions": []},
        "croissance": {"weight": 0.0, "avg_pnl": 0.0, "positions": []},
        "cyclique": {"weight": 0.0, "avg_pnl": 0.0, "positions": []},
        "mixte": {"weight": 0.0, "avg_pnl": 0.0, "positions": []},
    }

    for pos in metrics.get("positions", []):
        category = _normalize_category(pos.get("category"))
        categories[category]["positions"].append(pos)
        categories[category]["weight"] += pos.get("weight_pct", 0.0)

    for key in CATEGORY_KEYS:
        pnl_values = [p.get("pnl_pct", 0.0) for p in categories[key]["positions"]]
        categories[key]["avg_pnl"] = (sum(pnl_values) / len(pnl_values)) if pnl_values else 0.0

    alerts: List[str] = []
    if categories["value"]["weight"] < 0.50:
        alerts.append("Core value < 50% - verifier l'alignement strategique")

    for pos in categories["cyclique"]["positions"]:
        if pos.get("pnl_pct", 0.0) > 0.40:
            alerts.append(f"{pos['ticker']} cyclique +{pos['pnl_pct']:.0%} - envisager allegement")

    for pos in categories["value"]["positions"]:
        if pos.get("pnl_pct", 0.0) < -0.20:
            alerts.append(f"{pos['ticker']} value -{abs(pos['pnl_pct']):.0%} - these a revalider")

    return {"categories": categories, "alerts": alerts}


def _duckduckgo_search(query: str, limit: int = 2) -> List[Dict[str, str]]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0 Safari/537.36"
        )
    }
    response = requests.get(
        "https://duckduckgo.com/html/",
        params={"q": query},
        headers=headers,
        timeout=10,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")

    results: List[Dict[str, str]] = []
    for block in soup.select("div.result"):
        title_tag = block.select_one("a.result__a")
        if title_tag is None:
            continue
        snippet_tag = block.select_one(".result__snippet")
        title = title_tag.get_text(" ", strip=True)
        link = (title_tag.get("href") or "").strip()
        snippet = snippet_tag.get_text(" ", strip=True) if snippet_tag else ""
        results.append({"title": title, "link": link, "snippet": snippet})
        if len(results) >= limit:
            break
    return results


def fetch_macro_context() -> str:
    queries = ADVISOR_MACRO_QUERIES

    lines: List[str] = []

    try:
        for query in queries:
            items = _duckduckgo_search(query, limit=2)
            if not items:
                continue
            top = items[0]
            title = top.get("title", "").strip()
            snippet = top.get("snippet", "").strip()
            if title and snippet:
                lines.append(f"- {title}: {snippet}")
            elif title:
                lines.append(f"- {title}")
            if len(lines) >= 6:
                break
    except Exception as exc:
        LOG.warning("Macro context fetch failed: %s", exc)
        return "Contexte macro indisponible (erreur web search)."

    if not lines:
        return "Contexte macro indisponible (aucun resultat exploitable)."

    return "\n".join(lines[:6])


def generate_rebalancing_ideas(
    metrics: Dict[str, Any],
    concentration: Dict[str, Any],
    category_balance: Dict[str, Any],
    cash: float = 0.0,
) -> List[str]:
    ideas: List[str] = []
    positions = sorted(metrics.get("positions", []), key=lambda p: p.get("weight_pct", 0.0), reverse=True)

    if positions and concentration.get("max_single_position", 0.0) > 0.20:
        p = positions[0]
        ideas.append(
            f"Alleger {p['ticker']} ({p['weight_pct']:.1%} du portefeuille) pour reduire le risque idiosyncratique."
        )

    if concentration.get("top3_concentration", 0.0) > 0.50:
        ideas.append("Reduire progressivement le poids cumule des 3 plus grosses positions sous 50%.")

    sector_breakdown = concentration.get("sector_breakdown", {})
    if sector_breakdown:
        top_sector, top_weight = sorted(sector_breakdown.items(), key=lambda x: x[1], reverse=True)[0]
        if top_weight > 0.40:
            ideas.append(f"Limiter l'exposition au secteur {top_sector} ({top_weight:.1%}) via allegements selectifs.")

    categories = category_balance.get("categories", {})
    value_weight = categories.get("value", {}).get("weight", 0.0)
    if value_weight < 0.50:
        value_positions = categories.get("value", {}).get("positions", [])
        lagging_value = sorted(value_positions, key=lambda p: p.get("pnl_pct", 0.0))[:1]
        if lagging_value:
            ideas.append(
                f"Reexaminer {lagging_value[0]['ticker']} (value) pour potentiel renforcement si these intacte."
            )
        else:
            ideas.append("Renforcer le socle value avec une nouvelle ligne decotee pour revenir au-dessus de 50%.")

    cyclical_winners = [
        p for p in categories.get("cyclique", {}).get("positions", []) if p.get("pnl_pct", 0.0) > 0.40
    ]
    if cyclical_winners:
        best = sorted(cyclical_winners, key=lambda p: p.get("pnl_pct", 0.0), reverse=True)[0]
        ideas.append(f"Prendre partiellement des benefices sur {best['ticker']} (cyclique +{best['pnl_pct']:.0%}).")

    total_value_with_cash = metrics.get("total_value_with_cash", 0.0)
    if total_value_with_cash > 0 and cash / total_value_with_cash > 0.10:
        ideas.append("Deployer une partie du cash sur 1-2 dossiers en zone de rechargement pour diluer la concentration.")

    if not ideas:
        ideas.append("Aucun desequilibre majeur: conserver la trajectoire actuelle et surveiller les alertes macro.")

    return ideas[:5]


def _fmt_money(value: float, currency: str = "EUR") -> str:
    return f"{value:,.2f} {currency}".replace(",", " ")


def _fmt_pct(value: Optional[float]) -> str:
    if value is None:
        return "N/A"
    return f"{value:.2%}"


def _format_pos_line(pos: Dict[str, Any]) -> str:
    return (
        f"- {pos['ticker']} ({pos.get('name') or 'N/A'}) | "
        f"PnL {_fmt_pct(pos.get('pnl_pct'))} | "
        f"Poids {_fmt_pct(pos.get('weight_pct'))}"
    )


def generate_markdown_report(
    metrics: Dict[str, Any],
    concentration: Dict[str, Any],
    category_balance: Dict[str, Any],
    actions: List[str],
    macro_context: str,
) -> str:
    positions = metrics.get("positions", [])
    top = sorted(positions, key=lambda p: p.get("pnl_pct", -999), reverse=True)[:3]
    bottom = sorted(positions, key=lambda p: p.get("pnl_pct", 999))[:3]
    currency = metrics.get("currency", "EUR")

    categories = category_balance.get("categories", {})

    lines: List[str] = []
    lines.append("## Vue d'ensemble")
    lines.append(
        f"- Valeur des positions: {_fmt_money(metrics.get('total_current_value', 0.0), currency)}"
    )
    lines.append(f"- Cash: {_fmt_money(metrics.get('cash', 0.0), currency)}")
    lines.append(
        f"- Valeur totale (cash inclus): {_fmt_money(metrics.get('total_value_with_cash', 0.0), currency)}"
    )
    lines.append(
        f"- PnL global: {_fmt_money(metrics.get('total_pnl_eur', 0.0), currency)} ({_fmt_pct(metrics.get('total_pnl_pct', 0.0))})"
    )
    lines.append(f"- Nombre de positions: {len(positions)}")
    lines.append("")

    lines.append("## Top performers & Laggards")
    lines.append("Top 3:")
    lines.extend(_format_pos_line(p) for p in top)
    lines.append("")
    lines.append("Bottom 3:")
    lines.extend(_format_pos_line(p) for p in bottom)
    lines.append("")

    lines.append("## Risques identifies")
    lines.append(f"- Plus grosse position: {_fmt_pct(concentration.get('max_single_position', 0.0))}")
    lines.append(f"- Concentration top 3: {_fmt_pct(concentration.get('top3_concentration', 0.0))}")
    for alert in concentration.get("alerts", []):
        lines.append(f"- {alert}")
    if not concentration.get("alerts"):
        lines.append("- Aucun signal de concentration critique selon les seuils definis.")
    lines.append("")

    lines.append("## Equilibre strategique")
    for key in CATEGORY_KEYS:
        bucket = categories.get(key, {})
        lines.append(
            f"- {key}: poids {_fmt_pct(bucket.get('weight', 0.0))}, "
            f"pnl moyen {_fmt_pct(bucket.get('avg_pnl', 0.0))}, "
            f"{len(bucket.get('positions', []))} positions"
        )
    for alert in category_balance.get("alerts", []):
        lines.append(f"- {alert}")
    if not category_balance.get("alerts"):
        lines.append("- Equilibre categorie coherent avec les regles definies.")
    lines.append("")

    lines.append("## Actions suggerees")
    for action in actions:
        lines.append(f"- {action}")
    lines.append("")

    lines.append("## Contexte macro et impact sur le portefeuille")
    if macro_context.strip():
        lines.append(macro_context)
    else:
        lines.append("Contexte macro non disponible.")
    lines.append("")
    lines.append(
        "_Note: observations analytiques uniquement, pas de recommandation d'investissement formelle._"
    )

    return "\n".join(lines)


def synthesize_with_llm(scratchpad: Dict[str, Any], verbose: bool = False) -> Optional[str]:
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        if verbose:
            LOG.info("ANTHROPIC_API_KEY missing: skipping LLM synthesis.")
        return None

    try:
        import anthropic
    except Exception as exc:  # pragma: no cover - runtime dependency issue
        LOG.warning("Anthropic import failed: %s", exc)
        return None

    system_prompt = (
        "Tu es un conseiller en gestion de portefeuille specialise en value investing "
        "sur les small et mid caps europeennes.\n"
        "Tu analyses le portefeuille d'Olyos Capital dont la strategie est inspiree de William Higgons :\n"
        "- Socle value sur des societes decotees avec bilan sain\n"
        "- Complement croissance et cycliques en zone de rechargement\n"
        "- Focus small/mid caps francaises et europeennes\n"
        "- Horizon long terme 2-4 ans\n\n"
        "Sois factuel, concis, et conclusif. Pas de discours generique.\n"
        "Formule des observations specifiques a CE portefeuille."
    )
    user_prompt = (
        "Voici l'etat complet du portefeuille Olyos Capital :\n"
        f"{json.dumps(scratchpad, ensure_ascii=False, indent=2)}\n\n"
        "Produis l'analyse suivante en markdown :\n"
        "## Vue d'ensemble (snapshot chiffre : valeur totale, PnL global, nb positions)\n"
        "## Top performers & Laggards (top 3 / bottom 3)\n"
        "## Risques identifies (concentration, biais sectoriels, desequilibres)\n"
        "## Equilibre strategique (value/croissance/cyclique - commentaire)\n"
        "## Actions suggerees (max 5 idees concretes : alleger X, renforcer Y, surveiller Z)\n"
        "## Contexte macro et impact sur le portefeuille\n"
    )

    try:
        client = anthropic.Anthropic(api_key=api_key)
        response = client.messages.create(
            model=ADVISOR_MODEL_NAME,
            max_tokens=ADVISOR_MODEL_MAX_TOKENS,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}],
        )
        chunks = []
        for block in getattr(response, "content", []):
            text = getattr(block, "text", None)
            if text:
                chunks.append(text)
        result = "\n".join(chunks).strip()
        return result or None
    except Exception as exc:
        LOG.warning("LLM synthesis failed: %s", exc)
        return None


def _render_markdown(text: str) -> None:
    if Console is not None and Markdown is not None:
        console = Console()
        console.print(Markdown(text))
    else:
        print(text)


def _save_outputs(
    report_markdown: str,
    scratchpad: Dict[str, Any],
    output_override: Optional[str],
) -> Tuple[Path, Path, Optional[Path]]:
    stamp = datetime.now().strftime("%Y%m%d")
    reports_dir = Path(ADVISOR_REPORT_DIR)
    scratchpad_dir = Path(ADVISOR_SCRATCHPAD_DIR)
    reports_dir.mkdir(parents=True, exist_ok=True)
    scratchpad_dir.mkdir(parents=True, exist_ok=True)

    default_report_path = reports_dir / f"portfolio_{stamp}.md"
    default_scratchpad_path = scratchpad_dir / f"portfolio_{stamp}.json"

    default_report_path.write_text(report_markdown, encoding="utf-8")
    default_scratchpad_path.write_text(
        json.dumps(scratchpad, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    custom_path = None
    if output_override:
        custom_path = Path(output_override)
        custom_path.parent.mkdir(parents=True, exist_ok=True)
        custom_path.write_text(report_markdown, encoding="utf-8")

    return default_report_path, default_scratchpad_path, custom_path


def _build_scratchpad(
    portfolio_data: Dict[str, Any],
    prices: Dict[str, Dict[str, Any]],
    metrics: Dict[str, Any],
    concentration: Dict[str, Any],
    category_balance: Dict[str, Any],
    macro_context: str,
    actions: List[str],
) -> Dict[str, Any]:
    return {
        "generated_at": datetime.now().isoformat(),
        "portfolio": portfolio_data,
        "prices": prices,
        "metrics": metrics,
        "concentration": concentration,
        "category_balance": category_balance,
        "macro_context": macro_context,
        "rebalancing_ideas": actions,
    }


def _log_tool_result(tool_name: str, payload: Any, verbose: bool) -> None:
    if not verbose:
        return
    try:
        pretty = json.dumps(payload, ensure_ascii=False, indent=2)
    except TypeError:
        pretty = str(payload)
    LOG.info("%s ->\n%s", tool_name, pretty)


def run_analysis(
    portfolio_path: str,
    use_llm: bool = True,
    verbose: bool = False,
    output_override: Optional[str] = None,
    render_output: bool = True,
    fetch_prices_enabled: bool = True,
) -> Dict[str, Any]:
    portfolio_data = load_portfolio(portfolio_path)
    _log_tool_result("load_portfolio", portfolio_data, verbose)

    positions = portfolio_data["portfolio"]

    country_by_ticker = {p["ticker"]: (p.get("country") or "") for p in positions}
    tickers = [p["ticker"] for p in positions]

    if fetch_prices_enabled:
        prices = fetch_current_prices(tickers, country_by_ticker=country_by_ticker)
    else:
        prices = {
            ticker: {
                "price": next(
                    (p.get("current_price") for p in positions if p.get("ticker") == ticker),
                    None,
                ),
                "avg_volume_30d": None,
                "52w_high": None,
                "52w_low": None,
                "pe": None,
                "market_cap": None,
                "dividend_yield": None,
                "yahoo_symbol": None,
                "error": "Price fetch disabled",
            }
            for ticker in tickers
        }
    _log_tool_result("fetch_current_prices", prices, verbose)

    metrics = compute_portfolio_metrics(
        positions,
        prices,
        cash=_to_float(portfolio_data.get("cash"), 0.0) or 0.0,
        currency=str(portfolio_data.get("currency") or "EUR"),
    )
    _log_tool_result("compute_portfolio_metrics", metrics, verbose)

    concentration = analyze_concentration(metrics)
    _log_tool_result("analyze_concentration", concentration, verbose)

    category_balance = analyze_category_balance(metrics)
    _log_tool_result("analyze_category_balance", category_balance, verbose)

    macro_context = fetch_macro_context()
    _log_tool_result("fetch_macro_context", macro_context, verbose)

    rebalancing_ideas = generate_rebalancing_ideas(
        metrics,
        concentration,
        category_balance,
        cash=metrics.get("cash", 0.0),
    )
    _log_tool_result("generate_rebalancing_ideas", rebalancing_ideas, verbose)

    scratchpad = _build_scratchpad(
        portfolio_data=portfolio_data,
        prices=prices,
        metrics=metrics,
        concentration=concentration,
        category_balance=category_balance,
        macro_context=macro_context,
        actions=rebalancing_ideas,
    )

    report_markdown = generate_markdown_report(
        metrics=metrics,
        concentration=concentration,
        category_balance=category_balance,
        actions=rebalancing_ideas,
        macro_context=macro_context,
    )
    _log_tool_result("fallback_report_preview", report_markdown[:1200], verbose)

    llm_used = False
    if use_llm:
        llm_report = synthesize_with_llm(scratchpad, verbose=verbose)
        if llm_report:
            report_markdown = llm_report
            llm_used = True

    report_path, scratchpad_path, custom_path = _save_outputs(
        report_markdown=report_markdown,
        scratchpad=scratchpad,
        output_override=output_override,
    )

    if render_output:
        _render_markdown(report_markdown)

    return {
        "report_path": str(report_path),
        "scratchpad_path": str(scratchpad_path),
        "custom_report_path": str(custom_path) if custom_path else None,
        "llm_used": llm_used,
        "report_markdown": report_markdown,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Olyos Portfolio Advisor Agent")
    parser.add_argument("--portfolio", required=True, help="Path to portfolio JSON file")
    parser.add_argument("--no-llm", action="store_true", help="Disable LLM synthesis")
    parser.add_argument("--verbose", action="store_true", help="Verbose logs")
    parser.add_argument("--output", help="Optional report output path")
    return parser.parse_args()


def main() -> int:
    args = parse_args()

    logging.basicConfig(
        level=logging.INFO if args.verbose else logging.WARNING,
        format="[%(levelname)s] %(message)s",
    )
    for noisy_logger in ("yfinance", "yfinance.base", "urllib3", "peewee"):
        logging.getLogger(noisy_logger).setLevel(logging.CRITICAL)

    try:
        result = run_analysis(
            portfolio_path=args.portfolio,
            use_llm=not args.no_llm,
            verbose=args.verbose,
            output_override=args.output,
        )
        print(f"\nReport saved: {result['report_path']}")
        if result["custom_report_path"]:
            print(f"Custom report saved: {result['custom_report_path']}")
        print(f"Scratchpad saved: {result['scratchpad_path']}")
        return 0
    except Exception as exc:
        LOG.error("Portfolio analysis failed: %s", exc)
        print(f"Error: {exc}")
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

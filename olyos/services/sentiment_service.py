"""
Sentiment & Macro Intelligence Service
=======================================
Uses Anthropic Claude API with web_search tool to provide:
1. Geopolitical theme analysis with cross-asset impacts
2. Global sentiment scores per currency/asset (-10 to +10)
3. Higgons regime analysis (market conditions for value investing)
"""

import os
import re
import json
import time
import logging
from datetime import datetime
from typing import Dict, List, Optional, Any

log = logging.getLogger('olyos.sentiment')

# ── Cache Configuration ──────────────────────────────────────────────────────

_BASE_DIR = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_CACHE_DIR = os.path.join(_BASE_DIR, 'data', 'cache', 'sentiment')
os.makedirs(_CACHE_DIR, exist_ok=True)

CACHE_TTL_GEO = 6 * 3600       # 6 hours for geopolitical themes
CACHE_TTL_GLOBAL = 4 * 3600    # 4 hours for global sentiment
CACHE_TTL_HIGGONS = 6 * 3600   # 6 hours for Higgons regime

# ── Geopolitical Themes ──────────────────────────────────────────────────────

GEOPOLITICAL_THEMES = [
    {
        "id": "oil_conflict",
        "label": "Conflits Moyen-Orient / Petrole",
        "assets": ["OIL", "CAD", "USD", "EUR"],
    },
    {
        "id": "china_trade",
        "label": "Tensions commerciales US/Chine",
        "assets": ["CNY", "AUD", "USD", "GOLD"],
    },
    {
        "id": "fed_ecb",
        "label": "Divergence Fed / BCE",
        "assets": ["EUR", "USD"],
    },
    {
        "id": "risk_off",
        "label": "Risk-Off / Flight to Safety",
        "assets": ["JPY", "CHF", "GOLD", "VIX"],
    },
    {
        "id": "europe_energy",
        "label": "Crise energie Europe",
        "assets": ["EUR", "GBP", "TTF"],
    },
]

# ── Cache Helpers ────────────────────────────────────────────────────────────

def _cache_path(key: str) -> str:
    safe = key.replace('/', '_').replace(' ', '_')
    return os.path.join(_CACHE_DIR, f"{safe}.json")


def _load_cache(key: str, ttl: int) -> Optional[Dict]:
    path = _cache_path(key)
    if not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        if time.time() - data.get('_ts', 0) < ttl:
            data['value']['from_cache'] = True
            return data['value']
    except Exception:
        pass
    return None


def _save_cache(key: str, value: Dict):
    path = _cache_path(key)
    value['generated_at'] = datetime.now().isoformat(timespec='seconds')
    try:
        with open(path, 'w', encoding='utf-8') as f:
            json.dump({'_ts': time.time(), 'value': value}, f, ensure_ascii=False)
    except Exception as e:
        log.warning(f"Cache write failed for {key}: {e}")


# ── Anthropic API Call ───────────────────────────────────────────────────────

SYSTEM_PROMPT = """Tu es un analyste macro senior chez un hedge fund europeen specialise dans la methode Higgons (value investing, small caps europeennes, PE < 12, ROE > 12%, momentum).
Utilise le web_search tool pour chercher les dernieres actualites et donnees pertinentes AVANT de repondre.
Reponds UNIQUEMENT en JSON valide, sans markdown, sans texte avant ou apres le JSON."""


def _call_anthropic(user_prompt: str, api_key: str) -> Optional[Dict]:
    """Call Anthropic Claude API with web_search tool enabled."""
    try:
        import anthropic
        client = anthropic.Anthropic(api_key=api_key)

        response = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=2048,
            tools=[{"type": "web_search_20250305", "name": "web_search"}],
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}],
        )

        # Extract text blocks only (skip tool_use and tool_result)
        text = ""
        for block in response.content:
            if block.type == "text":
                text += block.text

        if not text.strip():
            log.warning("Anthropic returned empty text response")
            return None

        # Parse JSON (remove markdown backticks if present)
        clean = re.sub(r'```json?\s*|```', '', text).strip()
        return json.loads(clean)

    except json.JSONDecodeError as e:
        log.error(f"JSON parse error from Anthropic: {e}\nRaw text: {text[:500]}")
        return None
    except Exception as e:
        log.error(f"Anthropic API call failed: {e}")
        return None


# ── Analysis Methods ─────────────────────────────────────────────────────────

def analyze_geopolitical_theme(theme_id: str, api_key: str) -> Dict:
    """Analyze a geopolitical theme and its cross-asset impacts."""
    # Find theme config
    theme = next((t for t in GEOPOLITICAL_THEMES if t["id"] == theme_id), None)
    if not theme:
        return {"error": f"Theme '{theme_id}' not found"}

    # Check cache
    cache_key = f"sentiment_geo_{theme_id}"
    cached = _load_cache(cache_key, CACHE_TTL_GEO)
    if cached:
        return cached

    if not api_key:
        return {"error": "API Anthropic non configuree"}

    prompt = f"""Analyse le theme geopolitique/macro suivant : "{theme['label']}"
Assets concernes : {', '.join(theme['assets'])}

Recherche les dernieres actualites sur ce sujet et reponds en JSON :
{{
  "signal": "BULLISH" ou "BEARISH" ou "NEUTRAL" ou "STRONG_BULLISH" ou "STRONG_BEARISH",
  "text": "Analyse 2-3 phrases sur la situation actuelle basee sur les dernieres actualites",
  "impacts": [
    {{"asset": "NOM_ASSET", "direction": "positive" ou "negative", "reason": "raison courte"}}
  ],
  "higgons_impact": "Impact specifique pour les small caps value europeennes style Higgons (1-2 phrases)"
}}"""

    log.info(f"Analyzing geopolitical theme: {theme['label']}")
    result = _call_anthropic(prompt, api_key)

    if result:
        result['theme_id'] = theme_id
        result['theme_label'] = theme['label']
        result['assets'] = theme['assets']
        _save_cache(cache_key, result)
        return result

    return {
        "error": "Analyse indisponible",
        "theme_id": theme_id,
        "theme_label": theme['label'],
    }


def analyze_global_sentiment(api_key: str) -> Dict:
    """Get sentiment scores for major currencies and assets."""
    cache_key = "sentiment_global"
    cached = _load_cache(cache_key, CACHE_TTL_GLOBAL)
    if cached:
        return cached

    if not api_key:
        return {"error": "API Anthropic non configuree"}

    prompt = """Recherche les dernieres actualites macro-economiques et donne les scores de sentiment actuels.

Pour chaque devise/asset, donne un score de -10 (tres bearish) a +10 (tres bullish).
Assets a analyser : USD, EUR, GBP, JPY, CAD, AUD, OIL, GOLD

Reponds en JSON :
{
  "scores": {
    "USD": {"score": 0, "signal": "NEUTRAL", "summary": "resume 1 phrase"},
    "EUR": {"score": 0, "signal": "NEUTRAL", "summary": "resume 1 phrase"},
    "GBP": {"score": 0, "signal": "NEUTRAL", "summary": "resume 1 phrase"},
    "JPY": {"score": 0, "signal": "NEUTRAL", "summary": "resume 1 phrase"},
    "CAD": {"score": 0, "signal": "NEUTRAL", "summary": "resume 1 phrase"},
    "AUD": {"score": 0, "signal": "NEUTRAL", "summary": "resume 1 phrase"},
    "OIL": {"score": 0, "signal": "NEUTRAL", "summary": "resume 1 phrase"},
    "GOLD": {"score": 0, "signal": "NEUTRAL", "summary": "resume 1 phrase"}
  },
  "market_summary": "Resume general du sentiment de marche en 2-3 phrases"
}

Signal doit etre : "STRONG_BULLISH" (>5), "BULLISH" (2-5), "NEUTRAL" (-1 a 1), "BEARISH" (-5 a -2), "STRONG_BEARISH" (<-5)"""

    log.info("Analyzing global sentiment")
    result = _call_anthropic(prompt, api_key)

    if result:
        _save_cache(cache_key, result)
        return result

    return {"error": "Analyse indisponible"}


def analyze_higgons_regime(api_key: str, custom_context: str = "") -> Dict:
    """Analyze market regime for Higgons value investing strategy."""
    cache_key = "sentiment_higgons"
    cached = _load_cache(cache_key, CACHE_TTL_HIGGONS)
    if cached:
        return cached

    if not api_key:
        return {"error": "API Anthropic non configuree"}

    ctx = f"\nContexte additionnel : {custom_context}" if custom_context else ""

    prompt = f"""Recherche les dernieres actualites et conditions de marche pour analyser le regime actuel.

Analyse le regime de marche actuel pour la strategie William Higgons :
- Value investing europeen (small/mid caps)
- Criteres : PE < 12, ROE > 12%, dette faible, marge elevee
- Zones : principalement France, Benelux, Italie, Scandinavie{ctx}

Reponds en JSON :
{{
  "market_regime": "FAVORABLE" ou "DEFAVORABLE" ou "NEUTRE",
  "regime_score": 0,
  "regime_explanation": "Explication du regime en 2-3 phrases",
  "key_risks": [
    {{"title": "Titre du risque", "description": "Description courte", "severity": "HIGH" ou "MEDIUM" ou "LOW"}}
  ],
  "key_opportunities": [
    {{"title": "Titre opportunite", "description": "Description courte", "conviction": "HIGH" ou "MEDIUM" ou "LOW"}}
  ],
  "sectors_favored": ["Secteur 1", "Secteur 2"],
  "sectors_avoid": ["Secteur 1", "Secteur 2"],
  "tactical_note": "Note tactique actionnable pour un investisseur Higgons (2-3 phrases)"
}}

regime_score : de -5 (tres defavorable) a +5 (tres favorable)"""

    log.info("Analyzing Higgons regime")
    result = _call_anthropic(prompt, api_key)

    if result:
        _save_cache(cache_key, result)
        return result

    return {"error": "Analyse indisponible"}


# ── Utility ──────────────────────────────────────────────────────────────────

def get_themes() -> List[Dict]:
    """Return the list of configured geopolitical themes."""
    return GEOPOLITICAL_THEMES


def get_cache_status() -> Dict:
    """Check which analyses are cached and their age."""
    status = {}
    checks = [
        ("global", "sentiment_global", CACHE_TTL_GLOBAL),
        ("higgons", "sentiment_higgons", CACHE_TTL_HIGGONS),
    ]
    for theme in GEOPOLITICAL_THEMES:
        checks.append((f"geo_{theme['id']}", f"sentiment_geo_{theme['id']}", CACHE_TTL_GEO))

    for name, key, ttl in checks:
        path = _cache_path(key)
        if os.path.exists(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                age = time.time() - data.get('_ts', 0)
                status[name] = {
                    "cached": True,
                    "age_minutes": round(age / 60),
                    "expires_in_minutes": max(0, round((ttl - age) / 60)),
                    "generated_at": data.get('value', {}).get('generated_at', '?'),
                }
            except Exception:
                status[name] = {"cached": False}
        else:
            status[name] = {"cached": False}

    return status


def clear_cache() -> int:
    """Clear all sentiment cache files."""
    count = 0
    for f in os.listdir(_CACHE_DIR):
        if f.endswith('.json'):
            os.remove(os.path.join(_CACHE_DIR, f))
            count += 1
    log.info(f"Cleared {count} sentiment cache files")
    return count

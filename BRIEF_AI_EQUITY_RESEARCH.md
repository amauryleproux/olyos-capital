# BRIEF TECHNIQUE — Fonctionnalité "Analyse IA Equity Research"

## Projet : Olyos Capital (GitHub: amauryleproux/olyos-capital)
## Date : 07/02/2026
## Priorité : Haute

---

## 1. OBJECTIF

Ajouter un **bouton "◆ Analyser"** sur la page détail d'une valeur (stock detail page) qui déclenche un appel à l'**API Claude d'Anthropic** pour générer un **rapport d'equity research complet** au format HTML Bloomberg Terminal, directement dans l'interface.

Le rapport doit évaluer si la valeur est éligible au fonds selon la **méthode William Higgons** (PER bas, small cap, ROE élevé, dette faible, momentum haussier).

---

## 2. ARCHITECTURE & FLUX DE DONNÉES

```
┌─────────────────┐     ┌──────────────┐     ┌─────────────────┐
│  Page Détail     │────▶│  Flask Route  │────▶│  Claude API     │
│  (bouton HTML)   │     │  /api/analyze │     │  claude-sonnet  │
│                  │◀────│              │◀────│  -4-5-20250929  │
│  Rendu HTML      │     │  + données    │     │  (messages)     │
│  dans modal/page │     │  financières  │     │                 │
└─────────────────┘     └──────────────┘     └─────────────────┘
```

### Étapes :
1. L'utilisateur clique sur **"◆ Analyser"** depuis la page détail d'un ticker
2. Le frontend envoie une requête POST à `/api/analyze/<ticker>`
3. Le backend Flask :
   - Récupère les données financières existantes (déjà en cache ou via EOD/Yahoo)
   - Construit un prompt structuré avec toutes les données chiffrées
   - Appelle l'API Claude avec ce prompt
   - Retourne le HTML généré au frontend
4. Le frontend affiche le rapport dans un **modal fullscreen** ou une **page dédiée**

---

## 3. BACKEND — Route Flask

### 3.1 Nouvelle route : `/api/analyze/<ticker>`

```python
@app.route('/api/analyze/<ticker>', methods=['POST'])
def analyze_stock(ticker):
    """
    Génère un rapport d'equity research IA pour un ticker donné.
    Utilise les données financières en cache + appel Claude API.
    """
    try:
        # 1. Récupérer les données financières
        stock_data = get_stock_analysis_data(ticker)
        
        if not stock_data:
            return jsonify({'error': 'Données financières indisponibles'}), 404
        
        # 2. Construire le prompt
        prompt = build_analysis_prompt(stock_data)
        
        # 3. Appeler Claude API
        analysis_html = call_claude_analysis(prompt)
        
        # 4. Retourner le HTML
        return jsonify({
            'success': True,
            'html': analysis_html,
            'ticker': ticker,
            'timestamp': datetime.now().isoformat()
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500
```

### 3.2 Fonction de collecte de données : `get_stock_analysis_data(ticker)`

Cette fonction doit agréger TOUTES les données disponibles sur la valeur. Elle utilise les sources déjà intégrées dans l'app (EOD Historical Data API, Yahoo Finance fallback).

```python
def get_stock_analysis_data(ticker):
    """
    Collecte toutes les données financières nécessaires pour l'analyse.
    Retourne un dict structuré.
    """
    data = {}
    
    # --- Données de marché ---
    data['market'] = {
        'ticker': ticker,
        'name': '',              # Nom complet de la société
        'exchange': '',          # Euronext Paris, etc.
        'isin': '',
        'sector': '',
        'industry': '',
        'currency': 'EUR',
        'price': 0.0,            # Cours actuel
        'price_change_1d': 0.0,  # Variation jour %
        'high_52w': 0.0,         # Plus haut 52 semaines
        'low_52w': 0.0,          # Plus bas 52 semaines
        'market_cap': 0.0,       # Capitalisation en M€
        'shares_outstanding': 0, # Nombre d'actions
        'beta': 0.0,
        'volume_avg': 0,
    }
    
    # --- Ratios de valorisation ---
    data['valuation'] = {
        'per_ttm': 0.0,          # PER trailing 12 mois
        'per_forward': 0.0,      # PER prévisionnel
        'price_to_book': 0.0,    # Price / Book
        'price_to_sales': 0.0,   # Price / Sales
        'ev_ebitda': 0.0,        # EV / EBITDA
        'price_to_fcf': 0.0,     # Price / Free Cash Flow
    }
    
    # --- Rentabilité ---
    data['profitability'] = {
        'roe': 0.0,              # Return on Equity %
        'roa': 0.0,              # Return on Assets %
        'roic': 0.0,             # Return on Invested Capital %
        'gross_margin': 0.0,     # Marge brute %
        'operating_margin': 0.0, # Marge opérationnelle %
        'net_margin': 0.0,       # Marge nette %
    }
    
    # --- Bilan ---
    data['balance_sheet'] = {
        'total_assets': 0.0,
        'total_liabilities': 0.0,
        'total_equity': 0.0,     # Fonds propres
        'total_debt': 0.0,       # Dette totale
        'net_cash': 0.0,         # Trésorerie nette (négatif = dette nette)
        'debt_to_equity': 0.0,   # Dette / Fonds propres %
        'current_ratio': 0.0,
    }
    
    # --- Compte de résultat (3-5 dernières années) ---
    data['income_history'] = []  # Liste de dicts par année
    # Chaque entrée : {
    #   'year': 2024,
    #   'revenue': 0.0,
    #   'revenue_growth': 0.0,  # % YoY
    #   'ebitda': 0.0,
    #   'ebit': 0.0,
    #   'net_income': 0.0,
    #   'eps': 0.0,
    #   'fcf': 0.0,
    # }
    
    # --- Dividendes ---
    data['dividends'] = {
        'dividend_per_share': 0.0,
        'dividend_yield': 0.0,
        'payout_ratio': 0.0,
    }
    
    # --- Momentum (pour la méthode Higgons) ---
    data['momentum'] = {
        'perf_1m': 0.0,          # Performance 1 mois %
        'perf_3m': 0.0,          # Performance 3 mois %
        'perf_6m': 0.0,          # Performance 6 mois %
        'perf_1y': 0.0,          # Performance 1 an %
        'perf_ytd': 0.0,         # Performance YTD %
        'vs_sma50': 0.0,         # Distance à la SMA 50 %
        'vs_sma200': 0.0,        # Distance à la SMA 200 %
        'trend': '',             # 'bullish', 'bearish', 'neutral'
    }
    
    # Remplir avec les sources existantes
    # ... (utiliser get_fundamentals(), get_price_data(), etc. déjà dans l'app)
    
    return data
```

### 3.3 Fonction de construction du prompt : `build_analysis_prompt(stock_data)`

**C'est la partie la plus critique.** Le prompt doit être structuré pour que Claude génère exactement le format HTML attendu.

```python
def build_analysis_prompt(stock_data):
    """
    Construit le prompt système + utilisateur pour l'analyse Claude.
    """
    
    system_prompt = """Tu es un analyste equity research senior travaillant pour Olyos Capital, un fonds d'investissement value inspiré de la méthode William Higgons.

MÉTHODE HIGGONS — CRITÈRES DE SÉLECTION :
1. PER très faible : idéalement < 10, acceptable < 12
2. Petite capitalisation : small/mid cap européennes
3. ROE élevé : > 15% idéalement, > 12% acceptable
4. Dette faible : dette/equity < 50%, idéalement trésorerie nette positive
5. Momentum haussier : tendance technique positive, au-dessus des moyennes mobiles

MISSION : Générer un rapport d'equity research COMPLET au format HTML Bloomberg Terminal pour la valeur fournie.

FORMAT DE SORTIE OBLIGATOIRE :
Tu dois retourner UNIQUEMENT du HTML valide (pas de markdown, pas de ```html), qui sera injecté directement dans un conteneur.

Le HTML doit utiliser le design system suivant :
- Font : 'JetBrains Mono', monospace (déjà chargée dans la page parente)
- Background : transparent (le conteneur parent gère le fond #0a0e14)
- Couleurs CSS variables disponibles dans le parent :
  --bg-primary: #0a0e14
  --bg-secondary: #111822
  --bg-tertiary: #1a2332
  --border: #1e2d3d
  --text-primary: #e6edf3
  --text-secondary: #8b949e
  --text-muted: #484f58
  --green: #00ff88
  --red: #ff4444
  --orange: #ff9500
  --yellow: #ffd700
  --blue: #58a6ff
  --cyan: #00d4ff

STRUCTURE DU RAPPORT (toutes les sections sont OBLIGATOIRES) :

1. **HEADER TICKER** : Nom société, ticker, exchange, ISIN, secteur, tags (recommendation + type cap + type secteur), prix actuel avec variation

2. **VERDICT HIGGONS** (bannière colorée) : Résumé en 3-4 lignes avec score X/5 et conclusion claire (Éligible / Watchlist / Non éligible)

3. **MÉTRIQUES CLÉS** (panel gauche) : Capitalisation, cours vs 52w, PER, P/B, P/S, EV/EBITDA, ROE, ROIC, trésorerie nette, FCF, marge nette, beta, dividende

4. **SCORE HIGGONS DÉTAILLÉ** (panel droit) : Les 5 critères avec ✓/✗/~ et valeurs cibles vs réelles, score badge X/5, note explicative

5. **ÉVOLUTION FINANCIÈRE** (tableau) : 3-5 ans de CA, croissance, EBITDA, résultat op, marge, résultat net, FCF, trésorerie nette avec code couleur vert/rouge

6. **CONSENSUS ANALYSTES** (si disponible) : Objectif moyen/haut/bas, répartition achat/neutre/vente, valorisation par les actifs

7. **ANALYSE SWOT** (grille 2x2) : Forces, Faiblesses, Opportunités, Menaces — minimum 5 points par catégorie

8. **ANALYSE NARRATIVE** : 4-6 paragraphes d'analyse approfondie couvrant :
   - Situation actuelle de la société
   - Évaluation méthode Higgons détaillée
   - Points de blocage ou critères manquants
   - Catalyseurs de retournement
   - Target de prix (approche par les actifs, par les multiples, par DCF simplifié)
   - Recommandation finale Olyos Capital

9. **CATALYSEURS HAUSSIERS & RISQUES BAISSIERS** (2 panels côte à côte) : 5-6 points chacun

10. **ÉVÉNEMENTS CLÉS** : Prochaines dates à surveiller (résultats, dividendes, salons, etc.)

CLASSES CSS À UTILISER (définies dans le parent) :
- .panel, .panel-title, .panel-body
- .metric-row, .metric-label, .metric-value (.good/.warning/.bad/.neutral)
- .higgons-criteria (.pass/.fail/.partial)
- .criteria-icon (.pass/.fail/.partial)
- .tag (.buy/.hold/.sell/.info)
- .swot-grid, .swot-box (.strength/.weakness/.opportunity/.threat)
- .fin-table pour les tableaux financiers
- .grid-2, .grid-3 pour les layouts en grille
- .narrative pour le texte d'analyse
- .score-badge pour le score Higgons
- .verdict-banner pour la bannière de verdict
- .sep pour les séparateurs
- .progress-container, .progress-bar, .progress-fill

RÈGLES IMPÉRATIVES :
- Sois FACTUEL : ne pas inventer de données. Si une donnée manque, indique "N/D"
- Sois CRITIQUE : ne pas hésiter à déconseiller une valeur si elle ne valide pas la méthode
- Utilise le code couleur de manière cohérente : vert = positif, rouge = négatif, orange = attention
- Les chiffres doivent être formatés avec séparateurs de milliers et symboles €/%
- Toute recommandation doit être "Éligible", "Watchlist", ou "Non éligible" selon Higgons
- Le rapport doit être directement actionable pour un gérant de fonds
- N'ajoute PAS de balises <html>, <head>, <body> — retourne uniquement le contenu interne
- N'ajoute PAS de <style> — toutes les classes CSS sont déjà définies dans le parent
- Ajoute un footer disclaimer Olyos Capital en bas du rapport"""

    # Construction du prompt utilisateur avec les données
    user_prompt = f"""Génère le rapport d'equity research complet pour la valeur suivante :

## DONNÉES DE MARCHÉ
- Ticker : {stock_data['market']['ticker']}
- Nom : {stock_data['market']['name']}
- Exchange : {stock_data['market']['exchange']}
- ISIN : {stock_data['market'].get('isin', 'N/D')}
- Secteur : {stock_data['market']['sector']}
- Industrie : {stock_data['market'].get('industry', 'N/D')}
- Devise : {stock_data['market']['currency']}
- Cours actuel : {stock_data['market']['price']}
- Variation jour : {stock_data['market']['price_change_1d']}%
- Plus haut 52s : {stock_data['market']['high_52w']}
- Plus bas 52s : {stock_data['market']['low_52w']}
- Capitalisation : {stock_data['market']['market_cap']} M
- Actions en circulation : {stock_data['market']['shares_outstanding']}
- Beta : {stock_data['market']['beta']}
- Volume moyen : {stock_data['market']['volume_avg']}

## RATIOS DE VALORISATION
- PER TTM : {stock_data['valuation']['per_ttm']}
- PER Forward : {stock_data['valuation']['per_forward']}
- Price / Book : {stock_data['valuation']['price_to_book']}
- Price / Sales : {stock_data['valuation']['price_to_sales']}
- EV / EBITDA : {stock_data['valuation']['ev_ebitda']}
- Price / FCF : {stock_data['valuation'].get('price_to_fcf', 'N/D')}

## RENTABILITÉ
- ROE : {stock_data['profitability']['roe']}%
- ROA : {stock_data['profitability']['roa']}%
- ROIC : {stock_data['profitability']['roic']}%
- Marge brute : {stock_data['profitability']['gross_margin']}%
- Marge opérationnelle : {stock_data['profitability']['operating_margin']}%
- Marge nette : {stock_data['profitability']['net_margin']}%

## BILAN
- Actif total : {stock_data['balance_sheet']['total_assets']} M
- Passif total : {stock_data['balance_sheet']['total_liabilities']} M
- Fonds propres : {stock_data['balance_sheet']['total_equity']} M
- Dette totale : {stock_data['balance_sheet']['total_debt']} M
- Trésorerie nette : {stock_data['balance_sheet']['net_cash']} M
- Dette / Equity : {stock_data['balance_sheet']['debt_to_equity']}%
- Current ratio : {stock_data['balance_sheet']['current_ratio']}

## HISTORIQUE COMPTE DE RÉSULTAT
{format_income_history(stock_data['income_history'])}

## DIVIDENDES
- DPS : {stock_data['dividends']['dividend_per_share']}
- Rendement : {stock_data['dividends']['dividend_yield']}%
- Payout ratio : {stock_data['dividends']['payout_ratio']}%

## MOMENTUM
- Perf 1 mois : {stock_data['momentum']['perf_1m']}%
- Perf 3 mois : {stock_data['momentum']['perf_3m']}%
- Perf 6 mois : {stock_data['momentum']['perf_6m']}%
- Perf 1 an : {stock_data['momentum']['perf_1y']}%
- Perf YTD : {stock_data['momentum']['perf_ytd']}%
- vs SMA50 : {stock_data['momentum']['vs_sma50']}%
- vs SMA200 : {stock_data['momentum']['vs_sma200']}%
- Tendance : {stock_data['momentum']['trend']}

Génère le rapport complet maintenant. Retourne UNIQUEMENT le HTML."""

    return system_prompt, user_prompt
```

### 3.4 Fonction d'appel Claude API : `call_claude_analysis(prompt)`

```python
import anthropic

def call_claude_analysis(system_prompt, user_prompt):
    """
    Appelle l'API Claude pour générer le rapport d'analyse.
    """
    client = anthropic.Anthropic(api_key=app.config['ANTHROPIC_API_KEY'])
    
    message = client.messages.create(
        model="claude-sonnet-4-5-20250929",
        max_tokens=12000,  # Le rapport est long, prévoir large
        system=system_prompt,
        messages=[
            {"role": "user", "content": user_prompt}
        ]
    )
    
    # Extraire le contenu HTML de la réponse
    html_content = message.content[0].text
    
    # Nettoyage basique : retirer les éventuels backticks markdown
    html_content = html_content.strip()
    if html_content.startswith('```html'):
        html_content = html_content[7:]
    if html_content.startswith('```'):
        html_content = html_content[3:]
    if html_content.endswith('```'):
        html_content = html_content[:-3]
    
    return html_content.strip()
```

### 3.5 Helper pour formater l'historique

```python
def format_income_history(history):
    """Formate l'historique financier en texte pour le prompt."""
    if not history:
        return "Aucune donnée historique disponible."
    
    lines = []
    for year_data in history:
        lines.append(f"""Année {year_data['year']}:
  - CA : {year_data['revenue']} M | Croissance : {year_data['revenue_growth']}%
  - EBITDA : {year_data['ebitda']} M
  - EBIT : {year_data['ebit']} M
  - Résultat net : {year_data['net_income']} M
  - BPA : {year_data['eps']}
  - FCF : {year_data.get('fcf', 'N/D')} M""")
    
    return '\n'.join(lines)
```

---

## 4. FRONTEND — Bouton et Modal

### 4.1 Bouton "Analyser" sur la page détail

Ajouter le bouton dans le template de la page détail du stock (probablement dans le header de la page, à côté des autres actions).

```html
<!-- Bouton Analyser IA — à placer dans le header de la page détail -->
<button id="btn-ai-analyze" class="btn-analyze" onclick="launchAnalysis('{{ ticker }}')">
    <span class="analyze-icon">◆</span>
    <span class="analyze-text">Analyser</span>
    <span class="analyze-badge">IA</span>
</button>
```

```css
/* Style du bouton Analyser */
.btn-analyze {
    display: inline-flex;
    align-items: center;
    gap: 6px;
    padding: 8px 16px;
    background: linear-gradient(135deg, #1a2332 0%, #111822 100%);
    border: 1px solid #00ff88;
    border-radius: 4px;
    color: #00ff88;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    font-weight: 600;
    cursor: pointer;
    transition: all 0.2s ease;
    letter-spacing: 0.5px;
}

.btn-analyze:hover {
    background: linear-gradient(135deg, #00ff88 0%, #00cc6a 100%);
    color: #0a0e14;
    box-shadow: 0 0 20px rgba(0, 255, 136, 0.3);
}

.btn-analyze:active {
    transform: scale(0.98);
}

.btn-analyze .analyze-icon {
    font-size: 14px;
}

.btn-analyze .analyze-badge {
    background: rgba(0, 255, 136, 0.15);
    padding: 1px 6px;
    border-radius: 2px;
    font-size: 9px;
    letter-spacing: 1px;
}

.btn-analyze:hover .analyze-badge {
    background: rgba(10, 14, 20, 0.3);
}

/* État loading */
.btn-analyze.loading {
    pointer-events: none;
    opacity: 0.7;
    border-color: #ff9500;
    color: #ff9500;
}

.btn-analyze.loading .analyze-badge {
    background: rgba(255, 149, 0, 0.15);
    animation: pulse 1.5s infinite;
}

@keyframes pulse {
    0%, 100% { opacity: 1; }
    50% { opacity: 0.4; }
}
```

### 4.2 Modal Fullscreen pour le Rapport

```html
<!-- Modal Analyse IA — à ajouter en bas du body -->
<div id="analysis-modal" class="analysis-modal" style="display: none;">
    <div class="analysis-modal-header">
        <div class="analysis-modal-logo">◆ OLYOS CAPITAL</div>
        <div class="analysis-modal-meta">
            EQUITY RESEARCH │ <span id="analysis-ticker"></span> │ 
            <span id="analysis-timestamp"></span>
        </div>
        <div class="analysis-modal-actions">
            <button onclick="printAnalysis()" class="modal-btn" title="Imprimer">⎙</button>
            <button onclick="downloadAnalysis()" class="modal-btn" title="Télécharger HTML">↓</button>
            <button onclick="closeAnalysis()" class="modal-btn modal-btn-close" title="Fermer">✕</button>
        </div>
    </div>
    
    <!-- Zone de loading -->
    <div id="analysis-loading" class="analysis-loading" style="display: none;">
        <div class="loading-spinner"></div>
        <div class="loading-text">Analyse en cours...</div>
        <div class="loading-subtext">Claude génère le rapport d'equity research</div>
        <div class="loading-steps">
            <div class="loading-step active" id="step-data">▸ Collecte des données financières</div>
            <div class="loading-step" id="step-analysis">▸ Analyse méthode Higgons</div>
            <div class="loading-step" id="step-report">▸ Génération du rapport</div>
        </div>
    </div>
    
    <!-- Zone de contenu du rapport -->
    <div id="analysis-content" class="analysis-content" style="display: none;"></div>
    
    <!-- Zone d'erreur -->
    <div id="analysis-error" class="analysis-error" style="display: none;">
        <div class="error-icon">⚠</div>
        <div class="error-text" id="error-message"></div>
        <button onclick="retryAnalysis()" class="btn-analyze">◆ Réessayer</button>
    </div>
</div>
```

```css
/* Modal Fullscreen */
.analysis-modal {
    position: fixed;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: #0a0e14;
    z-index: 10000;
    display: flex;
    flex-direction: column;
    overflow: hidden;
}

.analysis-modal-header {
    background: #111822;
    border-bottom: 1px solid #1e2d3d;
    padding: 8px 16px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    flex-shrink: 0;
}

.analysis-modal-logo {
    color: #00ff88;
    font-weight: 700;
    font-size: 13px;
    letter-spacing: 2px;
}

.analysis-modal-meta {
    color: #484f58;
    font-size: 10px;
}

.analysis-modal-meta span {
    color: #ff9500;
}

.analysis-modal-actions {
    display: flex;
    gap: 4px;
}

.modal-btn {
    background: transparent;
    border: 1px solid #1e2d3d;
    color: #8b949e;
    padding: 4px 10px;
    border-radius: 3px;
    cursor: pointer;
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px;
    transition: all 0.15s;
}

.modal-btn:hover {
    border-color: #00ff88;
    color: #00ff88;
}

.modal-btn-close:hover {
    border-color: #ff4444;
    color: #ff4444;
}

/* Contenu du rapport (scrollable) */
.analysis-content {
    flex: 1;
    overflow-y: auto;
    padding: 16px;
    max-width: 1400px;
    margin: 0 auto;
    width: 100%;
}

/* Loading */
.analysis-loading {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 16px;
}

.loading-spinner {
    width: 40px;
    height: 40px;
    border: 3px solid #1e2d3d;
    border-top-color: #00ff88;
    border-radius: 50%;
    animation: spin 1s linear infinite;
}

@keyframes spin {
    to { transform: rotate(360deg); }
}

.loading-text {
    color: #e6edf3;
    font-size: 14px;
    font-weight: 600;
}

.loading-subtext {
    color: #484f58;
    font-size: 11px;
}

.loading-steps {
    margin-top: 16px;
    display: flex;
    flex-direction: column;
    gap: 8px;
}

.loading-step {
    color: #484f58;
    font-size: 11px;
    transition: color 0.3s;
}

.loading-step.active {
    color: #00ff88;
}

.loading-step.done {
    color: #8b949e;
}

/* Erreur */
.analysis-error {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 12px;
}

.error-icon {
    font-size: 32px;
    color: #ff4444;
}

.error-text {
    color: #ff4444;
    font-size: 12px;
}
```

### 4.3 JavaScript — Logique Frontend

```javascript
let currentAnalysisTicker = null;

function launchAnalysis(ticker) {
    currentAnalysisTicker = ticker;
    
    // Ouvrir le modal
    const modal = document.getElementById('analysis-modal');
    modal.style.display = 'flex';
    
    // Afficher loading
    document.getElementById('analysis-loading').style.display = 'flex';
    document.getElementById('analysis-content').style.display = 'none';
    document.getElementById('analysis-error').style.display = 'none';
    
    // Mettre à jour le header
    document.getElementById('analysis-ticker').textContent = ticker;
    document.getElementById('analysis-timestamp').textContent = 
        new Date().toLocaleDateString('fr-FR', { 
            day: '2-digit', month: 'short', year: 'numeric', 
            hour: '2-digit', minute: '2-digit' 
        });
    
    // Changer l'état du bouton
    const btn = document.getElementById('btn-ai-analyze');
    btn.classList.add('loading');
    btn.querySelector('.analyze-text').textContent = 'Analyse...';
    
    // Animation des étapes de loading
    animateLoadingSteps();
    
    // Appel API
    fetch(`/api/analyze/${ticker}`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
    })
    .then(response => response.json())
    .then(data => {
        if (data.success) {
            // Afficher le rapport
            document.getElementById('analysis-loading').style.display = 'none';
            const contentEl = document.getElementById('analysis-content');
            contentEl.innerHTML = data.html;
            contentEl.style.display = 'block';
        } else {
            showAnalysisError(data.error || 'Erreur inconnue');
        }
    })
    .catch(error => {
        showAnalysisError('Erreur de connexion : ' + error.message);
    })
    .finally(() => {
        // Restaurer le bouton
        const btn = document.getElementById('btn-ai-analyze');
        btn.classList.remove('loading');
        btn.querySelector('.analyze-text').textContent = 'Analyser';
    });
}

function animateLoadingSteps() {
    const steps = ['step-data', 'step-analysis', 'step-report'];
    let current = 0;
    
    const interval = setInterval(() => {
        if (current > 0) {
            document.getElementById(steps[current - 1]).classList.remove('active');
            document.getElementById(steps[current - 1]).classList.add('done');
        }
        if (current < steps.length) {
            document.getElementById(steps[current]).classList.add('active');
            current++;
        } else {
            clearInterval(interval);
        }
    }, 3000);  // Toutes les 3 secondes (le call Claude prend ~10-15s)
    
    // Stocker l'interval pour pouvoir l'arrêter
    window._loadingInterval = interval;
}

function showAnalysisError(message) {
    document.getElementById('analysis-loading').style.display = 'none';
    document.getElementById('analysis-content').style.display = 'none';
    document.getElementById('analysis-error').style.display = 'flex';
    document.getElementById('error-message').textContent = message;
    
    if (window._loadingInterval) clearInterval(window._loadingInterval);
}

function closeAnalysis() {
    document.getElementById('analysis-modal').style.display = 'none';
    if (window._loadingInterval) clearInterval(window._loadingInterval);
}

function retryAnalysis() {
    if (currentAnalysisTicker) {
        launchAnalysis(currentAnalysisTicker);
    }
}

function printAnalysis() {
    const content = document.getElementById('analysis-content').innerHTML;
    const printWindow = window.open('', '_blank');
    printWindow.document.write(`
        <html>
        <head>
            <title>Olyos Capital — Equity Research</title>
            <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&display=swap" rel="stylesheet">
            <style>
                /* Copier ici les styles CSS du design system Bloomberg */
                body { font-family: 'JetBrains Mono', monospace; background: #0a0e14; color: #e6edf3; font-size: 12px; padding: 16px; }
                /* ... inclure toutes les classes CSS nécessaires ... */
            </style>
        </head>
        <body>${content}</body>
        </html>
    `);
    printWindow.document.close();
    printWindow.print();
}

function downloadAnalysis() {
    const content = document.getElementById('analysis-content').innerHTML;
    const ticker = currentAnalysisTicker;
    const date = new Date().toISOString().split('T')[0];
    
    const fullHtml = `<!DOCTYPE html>
<html lang="fr">
<head>
<meta charset="UTF-8">
<title>Olyos Capital — ${ticker} — Equity Research</title>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@300;400;500;600;700&display=swap" rel="stylesheet">
<style>
/* Inclure ici TOUTES les classes CSS du design system */
:root {
    --bg-primary: #0a0e14; --bg-secondary: #111822; --bg-tertiary: #1a2332;
    --border: #1e2d3d; --text-primary: #e6edf3; --text-secondary: #8b949e;
    --text-muted: #484f58; --green: #00ff88; --red: #ff4444; --orange: #ff9500;
    --yellow: #ffd700; --blue: #58a6ff; --cyan: #00d4ff;
}
* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'JetBrains Mono', monospace; background: var(--bg-primary); color: var(--text-primary); font-size: 12px; line-height: 1.6; padding: 16px; max-width: 1400px; margin: 0 auto; }
/* ... TOUTES les classes CSS de l'analyse doivent être ici ... */
</style>
</head>
<body>${content}</body>
</html>`;

    const blob = new Blob([fullHtml], { type: 'text/html' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${ticker}_equity_research_${date}.html`;
    a.click();
    URL.revokeObjectURL(url);
}

// Fermer le modal avec Escape
document.addEventListener('keydown', (e) => {
    if (e.key === 'Escape') closeAnalysis();
});
```

---

## 5. CSS DU DESIGN SYSTEM BLOOMBERG

**IMPORTANT :** Toutes ces classes CSS doivent être définies dans le CSS global de l'application (ou dans le template de la page détail) pour que le HTML retourné par Claude s'affiche correctement.

Copier **intégralement** les styles du fichier de référence `BEN_PA_Equity_Research_Olyos.html` (fourni séparément). Les classes critiques à inclure sont :

```
.panel, .panel-title, .panel-body
.metric-row, .metric-label, .metric-value, .metric-value.good/warning/bad/neutral
.higgons-grid, .higgons-criteria, .higgons-criteria.pass/fail/partial
.criteria-icon, .criteria-icon.pass/fail/partial
.criteria-name, .criteria-target, .criteria-actual
.score-badge, .score-num, .score-label
.fin-table (table complète)
.swot-grid, .swot-box, .swot-box.strength/weakness/opportunity/threat
.grid-2, .grid-3
.tag, .tag.buy/hold/sell/info
.verdict-banner, .verdict-label, .verdict-text
.narrative, .narrative .highlight-green/red/orange
.progress-container, .progress-bar, .progress-fill, .progress-label
.section-title, .sep, .full-width
.footer, .disclaimer
```

---

## 6. CONFIGURATION

### 6.1 Variable d'environnement

```bash
# .env ou config
ANTHROPIC_API_KEY=sk-ant-...
```

### 6.2 Dépendance Python

```bash
pip install anthropic
```

### 6.3 Config Flask

```python
# Dans app.py ou config.py
app.config['ANTHROPIC_API_KEY'] = os.environ.get('ANTHROPIC_API_KEY')
```

---

## 7. GESTION DU CACHE

Pour éviter de rappeler Claude API à chaque clic (coûteux + lent) :

```python
import hashlib
import json
from datetime import datetime, timedelta

ANALYSIS_CACHE_DIR = 'cache/analyses'

def get_cached_analysis(ticker):
    """Retourne l'analyse en cache si elle date de moins de 24h."""
    cache_file = os.path.join(ANALYSIS_CACHE_DIR, f'{ticker}_analysis.json')
    
    if os.path.exists(cache_file):
        with open(cache_file, 'r') as f:
            cached = json.load(f)
        
        cached_time = datetime.fromisoformat(cached['timestamp'])
        if datetime.now() - cached_time < timedelta(hours=24):
            return cached['html']
    
    return None

def cache_analysis(ticker, html):
    """Sauvegarde l'analyse en cache."""
    os.makedirs(ANALYSIS_CACHE_DIR, exist_ok=True)
    cache_file = os.path.join(ANALYSIS_CACHE_DIR, f'{ticker}_analysis.json')
    
    with open(cache_file, 'w') as f:
        json.dump({
            'ticker': ticker,
            'html': html,
            'timestamp': datetime.now().isoformat()
        }, f)
```

Modifier la route pour utiliser le cache :

```python
@app.route('/api/analyze/<ticker>', methods=['POST'])
def analyze_stock(ticker):
    # Vérifier le cache d'abord
    force_refresh = request.json.get('force_refresh', False) if request.json else False
    
    if not force_refresh:
        cached = get_cached_analysis(ticker)
        if cached:
            return jsonify({
                'success': True,
                'html': cached,
                'ticker': ticker,
                'from_cache': True,
                'timestamp': datetime.now().isoformat()
            })
    
    # ... reste de la logique (appel Claude)
    
    # Après génération, mettre en cache
    cache_analysis(ticker, analysis_html)
    
    return jsonify({
        'success': True,
        'html': analysis_html,
        'ticker': ticker,
        'from_cache': False,
        'timestamp': datetime.now().isoformat()
    })
```

---

## 8. FICHIER DE RÉFÉRENCE

Le fichier `BEN_PA_Equity_Research_Olyos.html` accompagne ce brief. C'est le **résultat exact attendu** pour une analyse de Bénéteau (BEN.PA). Il sert de :

1. **Template de référence visuelle** — le rendu HTML généré par Claude doit ressembler à ça
2. **Source des classes CSS** — copier toutes les classes CSS dans le design system global
3. **Exemple de contenu** — le niveau de détail et de critique attendu dans l'analyse

---

## 9. TESTS & VALIDATION

### Checklist de validation :

- [ ] Le bouton "Analyser" est visible et correctement stylé sur la page détail
- [ ] Le clic ouvre le modal fullscreen avec animation de loading
- [ ] Les étapes de loading s'animent progressivement
- [ ] L'appel API Flask → Claude fonctionne (vérifier la clé API)
- [ ] Le HTML retourné par Claude s'affiche correctement dans le modal
- [ ] Le score Higgons est calculé correctement (5 critères)
- [ ] Les couleurs vert/rouge/orange sont cohérentes
- [ ] Le bouton "Télécharger" génère un fichier HTML autonome
- [ ] Le bouton "Imprimer" ouvre la boîte de dialogue d'impression
- [ ] Le cache fonctionne (2ème clic = instantané)
- [ ] La touche Escape ferme le modal
- [ ] Les erreurs API sont gérées proprement (timeout, clé invalide, etc.)
- [ ] Le responsive fonctionne (modal lisible sur mobile)

### Tickers de test :
- `BEN.PA` (Bénéteau) — le fichier de référence
- `CATG.PA` (Catana) — comparable direct
- `RMS.PA` (Hermès) — pour tester avec une large cap non éligible
- `ALO.PA` (Alstom) — pour tester avec une valeur endettée

---

## 10. NOTES IMPORTANTES

1. **Modèle Claude recommandé** : `claude-sonnet-4-5-20250929` — bon rapport qualité/coût pour ce use case. Pas besoin d'Opus pour de la génération HTML structurée.

2. **max_tokens** : 12000 minimum. Les rapports complets font entre 8000 et 11000 tokens de sortie.

3. **Coût estimé** : ~0,03-0,05€ par analyse (Sonnet). Avec le cache 24h, le coût est négligeable.

4. **Temps de réponse** : 10-20 secondes pour la génération. D'où l'importance du loading animé et du cache.

5. **Le prompt système est la clé** : Si le format de sortie n'est pas satisfaisant, ajuster le system prompt, pas le code. Le HTML de référence dans ce brief est le gold standard.

6. **Pas de streaming nécessaire** : Le rapport est affiché d'un bloc après génération. Le streaming ajouterait de la complexité sans valeur ajoutée ici (contrairement à un chat).

7. **Sécurité** : La clé API Anthropic ne doit JAMAIS être exposée côté frontend. Tout passe par la route Flask backend.

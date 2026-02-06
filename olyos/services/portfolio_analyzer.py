"""
PORTFOLIO ANALYZER - Système d'analyse Value + Price Action
============================================================
Inspiré de la méthodologie William Higgons (Indépendance AM)
+ Zones de rechargement Fibonacci pour le timing

Usage:
    python portfolio_analyzer.py [--update-prices] [--full-report]

Auteur: Votre nom
Version: 1.0
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# Configuration des seuils Higgons
HIGGONS_CONFIG = {
    # Critères VALUE
    'pe_max_excellent': 10,
    'pe_max_acceptable': 12,
    'pe_max_limit': 15,
    'pcf_max_excellent': 7,  # Prix/Cash-flow
    'pcf_max_acceptable': 10,
    
    # Critères QUALITY
    'roe_min_excellent': 0.15,
    'roe_min_acceptable': 0.10,
    'roce_min_excellent': 0.15,
    'roce_min_acceptable': 0.10,
    'operating_margin_min': 0.04,
    
    # Critères LEVERAGE
    'net_debt_ebitda_max_excellent': 1.5,
    'net_debt_ebitda_max_acceptable': 3.0,
    'equity_ratio_min': 0.25,
    
    # Critères FCF
    'fcf_yield_min_excellent': 0.08,
    'fcf_yield_min_acceptable': 0.05,
    'fcf_to_ni_min': 0.7,  # FCF/Net Income
    
    # Momentum (éviter les value traps)
    'momentum_12m_min': -0.20,  # Pas plus de -20% sur 12 mois
    
    # Seuils de vente
    'pe_sell_threshold': 20,
    'momentum_sell_threshold': -0.25,
}

# Configuration Fibonacci
FIBONACCI_LEVELS = {
    'golden_zone_high': 0.618,
    'golden_zone_low': 0.786,
    'extension_1': 1.0,
    'extension_1618': 1.618,
    'extension_2618': 2.618,
}


class FundamentalAnalyzer:
    """Analyse fondamentale selon les critères Higgons"""
    
    def __init__(self, config=HIGGONS_CONFIG):
        self.config = config
    
    def score_pe(self, pe):
        """Score PE (0-100)"""
        if pd.isna(pe) or pe <= 0:
            return 0
        if pe <= self.config['pe_max_excellent']:
            return 100
        elif pe <= self.config['pe_max_acceptable']:
            return 80 - (pe - self.config['pe_max_excellent']) * 10
        elif pe <= self.config['pe_max_limit']:
            return 50 - (pe - self.config['pe_max_acceptable']) * 10
        else:
            return max(0, 30 - (pe - self.config['pe_max_limit']) * 2)
    
    def score_roe(self, roe):
        """Score ROE (0-100)"""
        if pd.isna(roe) or roe <= 0:
            return 0
        if roe >= self.config['roe_min_excellent']:
            return min(100, 80 + (roe - self.config['roe_min_excellent']) * 100)
        elif roe >= self.config['roe_min_acceptable']:
            return 60 + (roe - self.config['roe_min_acceptable']) * 400
        else:
            return max(0, roe * 600)
    
    def score_leverage(self, net_debt_ebitda, equity_ratio):
        """Score Leverage (0-100)"""
        score = 0
        
        # Net Debt/EBITDA (50 points max)
        if pd.isna(net_debt_ebitda):
            score += 25
        elif net_debt_ebitda <= 0:  # Trésorerie nette
            score += 50
        elif net_debt_ebitda <= self.config['net_debt_ebitda_max_excellent']:
            score += 40
        elif net_debt_ebitda <= self.config['net_debt_ebitda_max_acceptable']:
            score += 25
        else:
            score += max(0, 15 - (net_debt_ebitda - 3) * 5)
        
        # Equity Ratio (50 points max)
        if pd.isna(equity_ratio):
            score += 25
        elif equity_ratio >= 0.50:
            score += 50
        elif equity_ratio >= self.config['equity_ratio_min']:
            score += 30 + (equity_ratio - 0.25) * 80
        else:
            score += max(0, equity_ratio * 120)
        
        return score
    
    def score_fcf(self, fcf_yield, fcf_to_ni):
        """Score Free Cash Flow (0-100)"""
        score = 0
        
        # FCF Yield (60 points max)
        if pd.isna(fcf_yield):
            score += 30
        elif fcf_yield >= self.config['fcf_yield_min_excellent']:
            score += 60
        elif fcf_yield >= self.config['fcf_yield_min_acceptable']:
            score += 40 + (fcf_yield - 0.05) * 666
        else:
            score += max(0, fcf_yield * 800)
        
        # FCF/Net Income (40 points max)
        if pd.isna(fcf_to_ni):
            score += 20
        elif fcf_to_ni >= 1.0:
            score += 40
        elif fcf_to_ni >= self.config['fcf_to_ni_min']:
            score += 25 + (fcf_to_ni - 0.7) * 50
        else:
            score += max(0, fcf_to_ni * 35)
        
        return score
    
    def score_margin(self, operating_margin):
        """Score Marge opérationnelle (0-100)"""
        if pd.isna(operating_margin):
            return 50
        if operating_margin >= 0.20:
            return 100
        elif operating_margin >= 0.10:
            return 70 + (operating_margin - 0.10) * 300
        elif operating_margin >= self.config['operating_margin_min']:
            return 40 + (operating_margin - 0.04) * 500
        else:
            return max(0, operating_margin * 1000)
    
    def calculate_higgons_score(self, row):
        """
        Calcul du score Higgons global (0-100)
        Pondération:
        - VALUE (PE): 25%
        - QUALITY (ROE + Margin): 30%
        - LEVERAGE: 20%
        - FCF: 25%
        """
        pe_score = self.score_pe(row.get('pe_ttm', None))
        roe_score = self.score_roe(row.get('roe_ttm', None))
        leverage_score = self.score_leverage(
            row.get('net_debt_to_ebitda', None),
            row.get('equity_ratio', None)
        )
        fcf_score = self.score_fcf(
            row.get('fcf_yield', None),
            row.get('fcf_to_net_income', None)
        )
        margin_score = self.score_margin(row.get('operating_margin', None))
        
        # Score pondéré
        total_score = (
            pe_score * 0.25 +
            roe_score * 0.15 +
            margin_score * 0.15 +
            leverage_score * 0.20 +
            fcf_score * 0.25
        )
        
        return {
            'score_total': round(total_score, 1),
            'score_pe': round(pe_score, 1),
            'score_roe': round(roe_score, 1),
            'score_margin': round(margin_score, 1),
            'score_leverage': round(leverage_score, 1),
            'score_fcf': round(fcf_score, 1),
        }
    
    def check_gates(self, row):
        """
        Vérifie les "gates" Higgons (critères éliminatoires)
        Retourne un dict avec les résultats de chaque gate
        """
        gates = {
            'profitable': True,
            'quality': True,
            'value': True,
            'leverage': True,
        }
        
        # Gate Profitable: PE positif
        pe = row.get('pe_ttm', None)
        if pd.isna(pe) or pe <= 0:
            gates['profitable'] = False
        
        # Gate Quality: ROE > 10%
        roe = row.get('roe_ttm', None)
        if pd.isna(roe) or roe < self.config['roe_min_acceptable']:
            gates['quality'] = False
        
        # Gate Value: PE < 15
        if not pd.isna(pe) and pe > self.config['pe_max_limit']:
            gates['value'] = False
        
        # Gate Leverage: Dette raisonnable
        net_debt = row.get('net_debt_to_ebitda', None)
        if not pd.isna(net_debt) and net_debt > self.config['net_debt_ebitda_max_acceptable']:
            gates['leverage'] = False
        
        gates['all_passed'] = all(gates.values())
        return gates


class TechnicalAnalyzer:
    """Analyse technique avec focus sur Fibonacci et zones de rechargement"""
    
    def __init__(self):
        self.fib_levels = FIBONACCI_LEVELS
    
    def calculate_fibonacci_retracement(self, high, low, current_price):
        """
        Calcule les niveaux de retracement Fibonacci
        et détermine dans quelle zone se trouve le prix actuel
        """
        if pd.isna(high) or pd.isna(low) or pd.isna(current_price):
            return None
        
        range_size = high - low
        if range_size <= 0:
            return None
        
        levels = {
            '0.0': high,
            '0.236': high - range_size * 0.236,
            '0.382': high - range_size * 0.382,
            '0.5': high - range_size * 0.5,
            '0.618': high - range_size * 0.618,
            '0.786': high - range_size * 0.786,
            '1.0': low,
        }
        
        # Déterminer la zone actuelle
        retracement_pct = (high - current_price) / range_size if range_size > 0 else 0
        
        zone = 'UNKNOWN'
        zone_quality = 0  # 0-100
        
        if retracement_pct < 0:
            zone = 'ABOVE_HIGH'
            zone_quality = 20
        elif retracement_pct <= 0.236:
            zone = 'EXTENSION'
            zone_quality = 30
        elif retracement_pct <= 0.382:
            zone = 'SHALLOW_PULLBACK'
            zone_quality = 50
        elif retracement_pct <= 0.5:
            zone = 'NORMAL_PULLBACK'
            zone_quality = 60
        elif retracement_pct <= 0.618:
            zone = 'DEEP_PULLBACK'
            zone_quality = 75
        elif retracement_pct <= 0.786:
            zone = 'GOLDEN_ZONE'  # Zone de rechargement idéale
            zone_quality = 100
        elif retracement_pct <= 1.0:
            zone = 'EXTREME_ZONE'
            zone_quality = 85
        else:
            zone = 'BELOW_LOW'
            zone_quality = 40  # Risqué mais potentiellement intéressant
        
        return {
            'levels': levels,
            'retracement_pct': round(retracement_pct * 100, 1),
            'zone': zone,
            'zone_quality': zone_quality,
            'distance_to_golden': round((0.618 - retracement_pct) * 100, 1) if retracement_pct < 0.618 else 0,
            'in_reload_zone': zone in ['GOLDEN_ZONE', 'EXTREME_ZONE', 'DEEP_PULLBACK'],
        }
    
    def calculate_trend_strength(self, prices_series):
        """
        Calcule la force de la tendance basée sur les moyennes mobiles
        Retourne un score de -100 (très bearish) à +100 (très bullish)
        """
        if prices_series is None or len(prices_series) < 200:
            return {'trend_score': 0, 'trend': 'UNKNOWN', 'ma_alignment': 'UNKNOWN'}
        
        current = prices_series.iloc[-1]
        ma20 = prices_series.rolling(20).mean().iloc[-1]
        ma50 = prices_series.rolling(50).mean().iloc[-1]
        ma200 = prices_series.rolling(200).mean().iloc[-1]
        
        score = 0
        
        # Position par rapport aux MAs
        if current > ma20:
            score += 25
        else:
            score -= 25
        
        if current > ma50:
            score += 25
        else:
            score -= 25
        
        if current > ma200:
            score += 25
        else:
            score -= 25
        
        # Alignement des MAs
        if ma20 > ma50 > ma200:
            score += 25
            alignment = 'BULLISH_ALIGNED'
        elif ma20 < ma50 < ma200:
            score -= 25
            alignment = 'BEARISH_ALIGNED'
        else:
            alignment = 'MIXED'
        
        # Déterminer la tendance
        if score >= 75:
            trend = 'STRONG_BULLISH'
        elif score >= 25:
            trend = 'BULLISH'
        elif score >= -25:
            trend = 'NEUTRAL'
        elif score >= -75:
            trend = 'BEARISH'
        else:
            trend = 'STRONG_BEARISH'
        
        return {
            'trend_score': score,
            'trend': trend,
            'ma_alignment': alignment,
            'price_vs_ma20': round((current / ma20 - 1) * 100, 1) if ma20 > 0 else 0,
            'price_vs_ma50': round((current / ma50 - 1) * 100, 1) if ma50 > 0 else 0,
            'price_vs_ma200': round((current / ma200 - 1) * 100, 1) if ma200 > 0 else 0,
        }
    
    def calculate_rsi(self, prices_series, period=14):
        """Calcule le RSI"""
        if prices_series is None or len(prices_series) < period + 1:
            return None
        
        delta = prices_series.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        
        return round(rsi.iloc[-1], 1) if not pd.isna(rsi.iloc[-1]) else None
    
    def calculate_volatility(self, prices_series, period=20):
        """Calcule la volatilité (écart-type des rendements)"""
        if prices_series is None or len(prices_series) < period:
            return None
        
        returns = prices_series.pct_change()
        volatility = returns.rolling(window=period).std().iloc[-1]
        annualized_vol = volatility * np.sqrt(252)
        
        return round(annualized_vol * 100, 1) if not pd.isna(annualized_vol) else None


class SignalGenerator:
    """Génère des signaux d'achat/vente basés sur l'analyse combinée"""
    
    def __init__(self):
        self.fundamental = FundamentalAnalyzer()
        self.technical = TechnicalAnalyzer()
    
    def generate_signal(self, fundamental_data, technical_data=None):
        """
        Génère un signal global avec recommandation
        
        Retourne:
        - signal: STRONG_BUY, BUY, HOLD, REDUCE, SELL
        - action: ENTER, RELOAD, HOLD, TRIM, EXIT
        - confidence: 0-100
        - reasons: liste des raisons
        """
        reasons = []
        scores = {'fundamental': 0, 'technical': 0, 'timing': 0}
        
        # 1. Analyse fondamentale
        fund_scores = self.fundamental.calculate_higgons_score(fundamental_data)
        gates = self.fundamental.check_gates(fundamental_data)
        
        scores['fundamental'] = fund_scores['score_total']
        
        if not gates['all_passed']:
            failed_gates = [k for k, v in gates.items() if not v and k != 'all_passed']
            reasons.append(f"Gates non passés: {', '.join(failed_gates)}")
        
        if fund_scores['score_total'] >= 70:
            reasons.append(f"Score Higgons excellent ({fund_scores['score_total']}/100)")
        elif fund_scores['score_total'] >= 50:
            reasons.append(f"Score Higgons acceptable ({fund_scores['score_total']}/100)")
        else:
            reasons.append(f"Score Higgons faible ({fund_scores['score_total']}/100)")
        
        # 2. Analyse technique (si disponible)
        if technical_data:
            fib = technical_data.get('fibonacci')
            trend = technical_data.get('trend')
            rsi = technical_data.get('rsi')
            
            if fib:
                scores['timing'] = fib.get('zone_quality', 50)
                if fib.get('in_reload_zone'):
                    reasons.append(f"Dans zone de rechargement Fibonacci ({fib['zone']})")
                else:
                    reasons.append(f"Zone Fibonacci: {fib['zone']} ({fib['retracement_pct']}%)")
            
            if trend:
                scores['technical'] = (trend.get('trend_score', 0) + 100) / 2
                reasons.append(f"Tendance: {trend['trend']}")
            
            if rsi:
                if rsi < 30:
                    reasons.append(f"RSI survendu ({rsi})")
                    scores['technical'] += 10
                elif rsi > 70:
                    reasons.append(f"RSI suracheté ({rsi})")
                    scores['technical'] -= 10
        
        # 3. Calcul du signal final
        # Pondération: 50% fondamental, 30% technique, 20% timing
        if technical_data:
            total_score = (
                scores['fundamental'] * 0.50 +
                scores['technical'] * 0.30 +
                scores['timing'] * 0.20
            )
        else:
            total_score = scores['fundamental']
        
        # Détermination du signal
        if not gates['all_passed']:
            signal = 'AVOID'
            action = 'DO_NOT_ENTER'
            confidence = 30
        elif total_score >= 80:
            signal = 'STRONG_BUY'
            action = 'ENTER' if technical_data and technical_data.get('fibonacci', {}).get('in_reload_zone') else 'ACCUMULATE'
            confidence = 90
        elif total_score >= 65:
            signal = 'BUY'
            action = 'RELOAD' if technical_data and technical_data.get('fibonacci', {}).get('in_reload_zone') else 'HOLD_ADD'
            confidence = 75
        elif total_score >= 50:
            signal = 'HOLD'
            action = 'HOLD'
            confidence = 60
        elif total_score >= 35:
            signal = 'REDUCE'
            action = 'TRIM'
            confidence = 65
        else:
            signal = 'SELL'
            action = 'EXIT'
            confidence = 70
        
        # Ajustements basés sur le PE (critère de vente Higgons)
        pe = fundamental_data.get('pe_ttm', None)
        if not pd.isna(pe) and pe > HIGGONS_CONFIG['pe_sell_threshold']:
            signal = 'SELL'
            action = 'EXIT'
            reasons.append(f"PE trop élevé ({pe} > {HIGGONS_CONFIG['pe_sell_threshold']})")
            confidence = 80
        
        return {
            'signal': signal,
            'action': action,
            'confidence': confidence,
            'total_score': round(total_score, 1),
            'scores': scores,
            'reasons': reasons,
            'fund_scores': fund_scores,
            'gates': gates,
        }


class PortfolioAnalyzer:
    """Classe principale pour analyser le portefeuille"""
    
    def __init__(self, portfolio_df):
        self.portfolio = portfolio_df.copy()
        self.signal_gen = SignalGenerator()
        self.results = []
    
    def analyze_all(self):
        """Analyse toutes les positions du portefeuille"""
        results = []
        
        for idx, row in self.portfolio.iterrows():
            ticker = row.get('ticker', f'ROW_{idx}')
            name = row.get('name', ticker)
            
            # Données fondamentales
            fund_data = row.to_dict()
            
            # Pour l'instant, pas de données techniques en temps réel
            # Tu pourras ajouter l'intégration avec yfinance plus tard
            tech_data = None
            
            # Générer le signal
            signal_result = self.signal_gen.generate_signal(fund_data, tech_data)
            
            # Calculer la P&L si position existante
            qty = row.get('qty', 0)
            current_price = row.get('price_eur', 0)
            avg_cost = row.get('avg_cost_eur', 0)
            
            if qty > 0 and avg_cost > 0:
                pnl_pct = (current_price / avg_cost - 1) * 100
                pnl_eur = (current_price - avg_cost) * qty
                position_value = current_price * qty
            else:
                pnl_pct = 0
                pnl_eur = 0
                position_value = 0
            
            results.append({
                'ticker': ticker,
                'name': name,
                'qty': qty,
                'price': current_price,
                'avg_cost': avg_cost,
                'position_value': round(position_value, 2),
                'pnl_pct': round(pnl_pct, 1),
                'pnl_eur': round(pnl_eur, 2),
                'signal': signal_result['signal'],
                'action': signal_result['action'],
                'confidence': signal_result['confidence'],
                'score_total': signal_result['total_score'],
                'score_pe': signal_result['fund_scores']['score_pe'],
                'score_roe': signal_result['fund_scores']['score_roe'],
                'score_leverage': signal_result['fund_scores']['score_leverage'],
                'score_fcf': signal_result['fund_scores']['score_fcf'],
                'score_piotroski': row.get('score_piotroski', 0),  # F-Score Piotroski
                'gates_passed': signal_result['gates']['all_passed'],
                'reasons': ' | '.join(signal_result['reasons'][:3]),
                # Données brutes pour référence
                'pe_ttm': row.get('pe_ttm'),
                'roe_ttm': row.get('roe_ttm'),
                'net_debt_ebitda': row.get('net_debt_to_ebitda'),
                'fcf_yield': row.get('fcf_yield'),
            })
        
        self.results = pd.DataFrame(results)
        return self.results
    
    def get_summary(self):
        """Génère un résumé du portefeuille"""
        if self.results is None or len(self.results) == 0:
            return None
        
        df = self.results[self.results['qty'] > 0]  # Positions actives seulement
        
        total_value = df['position_value'].sum()
        total_pnl = df['pnl_eur'].sum()
        
        signal_counts = df['signal'].value_counts().to_dict()
        
        return {
            'total_positions': len(df),
            'total_value': round(total_value, 2),
            'total_pnl_eur': round(total_pnl, 2),
            'total_pnl_pct': round(total_pnl / (total_value - total_pnl) * 100, 2) if total_value > total_pnl else 0,
            'avg_score': round(df['score_total'].mean(), 1),
            'signals': signal_counts,
            'best_score': df.loc[df['score_total'].idxmax()]['ticker'] if len(df) > 0 else None,
            'worst_score': df.loc[df['score_total'].idxmin()]['ticker'] if len(df) > 0 else None,
        }
    
    def get_recommendations(self):
        """Génère les recommandations d'actions"""
        if self.results is None or len(self.results) == 0:
            return []
        
        recommendations = []
        
        # Positions à renforcer (STRONG_BUY avec position existante)
        to_reload = self.results[
            (self.results['signal'].isin(['STRONG_BUY', 'BUY'])) & 
            (self.results['qty'] > 0) &
            (self.results['gates_passed'] == True)
        ].sort_values('score_total', ascending=False)
        
        for _, row in to_reload.iterrows():
            recommendations.append({
                'type': 'RELOAD',
                'priority': 'HIGH' if row['signal'] == 'STRONG_BUY' else 'MEDIUM',
                'ticker': row['ticker'],
                'name': row['name'],
                'current_price': row['price'],
                'score': row['score_total'],
                'reason': row['reasons'],
            })
        
        # Nouvelles positions à initier
        to_enter = self.results[
            (self.results['signal'].isin(['STRONG_BUY', 'BUY'])) & 
            (self.results['qty'] == 0) &
            (self.results['gates_passed'] == True)
        ].sort_values('score_total', ascending=False)
        
        for _, row in to_enter.iterrows():
            recommendations.append({
                'type': 'ENTER',
                'priority': 'HIGH' if row['signal'] == 'STRONG_BUY' else 'MEDIUM',
                'ticker': row['ticker'],
                'name': row['name'],
                'current_price': row['price'],
                'score': row['score_total'],
                'reason': row['reasons'],
            })
        
        # Positions à alléger/vendre
        to_exit = self.results[
            (self.results['signal'].isin(['REDUCE', 'SELL'])) & 
            (self.results['qty'] > 0)
        ].sort_values('score_total', ascending=True)
        
        for _, row in to_exit.iterrows():
            recommendations.append({
                'type': 'EXIT' if row['signal'] == 'SELL' else 'TRIM',
                'priority': 'HIGH' if row['signal'] == 'SELL' else 'MEDIUM',
                'ticker': row['ticker'],
                'name': row['name'],
                'current_price': row['price'],
                'pnl_pct': row['pnl_pct'],
                'score': row['score_total'],
                'reason': row['reasons'],
            })
        
        return recommendations


def generate_html_report(analyzer, output_path='portfolio_report.html'):
    """Génère un rapport HTML du portefeuille"""
    results = analyzer.results
    summary = analyzer.get_summary()
    recommendations = analyzer.get_recommendations()
    
    # Couleurs pour les signaux
    signal_colors = {
        'STRONG_BUY': '#16a34a',
        'BUY': '#22c55e',
        'HOLD': '#f59e0b',
        'REDUCE': '#f97316',
        'SELL': '#dc2626',
        'AVOID': '#6b7280',
    }
    
    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Portfolio Analysis Report - {datetime.now().strftime('%Y-%m-%d')}</title>
    <style>
        * {{ margin: 0; padding: 0; box-sizing: border-box; }}
        body {{ font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; background: #f8fafc; color: #1e293b; line-height: 1.6; }}
        .container {{ max-width: 1400px; margin: 0 auto; padding: 20px; }}
        h1 {{ color: #1e40af; margin-bottom: 10px; }}
        h2 {{ color: #334155; margin: 30px 0 15px; padding-bottom: 10px; border-bottom: 2px solid #e2e8f0; }}
        .header {{ background: linear-gradient(135deg, #1e40af, #3b82f6); color: white; padding: 30px; border-radius: 12px; margin-bottom: 30px; }}
        .header h1 {{ color: white; }}
        .header p {{ opacity: 0.9; }}
        .summary-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 20px; margin-bottom: 30px; }}
        .summary-card {{ background: white; padding: 20px; border-radius: 12px; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        .summary-card .label {{ font-size: 12px; text-transform: uppercase; color: #64748b; letter-spacing: 0.5px; }}
        .summary-card .value {{ font-size: 28px; font-weight: bold; color: #1e293b; }}
        .summary-card .value.positive {{ color: #16a34a; }}
        .summary-card .value.negative {{ color: #dc2626; }}
        table {{ width: 100%; border-collapse: collapse; background: white; border-radius: 12px; overflow: hidden; box-shadow: 0 1px 3px rgba(0,0,0,0.1); }}
        th {{ background: #1e40af; color: white; padding: 12px; text-align: left; font-weight: 600; font-size: 12px; text-transform: uppercase; }}
        td {{ padding: 12px; border-bottom: 1px solid #e2e8f0; }}
        tr:hover {{ background: #f8fafc; }}
        .signal {{ padding: 4px 10px; border-radius: 20px; font-size: 11px; font-weight: 600; text-transform: uppercase; }}
        .score-bar {{ width: 60px; height: 8px; background: #e2e8f0; border-radius: 4px; overflow: hidden; }}
        .score-bar-fill {{ height: 100%; border-radius: 4px; }}
        .recommendation {{ background: white; padding: 15px 20px; border-radius: 8px; margin-bottom: 10px; border-left: 4px solid; display: flex; justify-content: space-between; align-items: center; }}
        .recommendation.ENTER, .recommendation.RELOAD {{ border-color: #16a34a; }}
        .recommendation.EXIT, .recommendation.TRIM {{ border-color: #dc2626; }}
        .priority {{ font-size: 10px; padding: 2px 8px; border-radius: 10px; text-transform: uppercase; }}
        .priority.HIGH {{ background: #fee2e2; color: #dc2626; }}
        .priority.MEDIUM {{ background: #fef3c7; color: #d97706; }}
        .timestamp {{ text-align: center; color: #94a3b8; font-size: 12px; margin-top: 30px; }}
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>📊 Portfolio Analysis Report</h1>
            <p>Analyse Value + Price Action • Méthodologie Higgons</p>
            <p style="margin-top: 10px; font-size: 14px;">Généré le {datetime.now().strftime('%d/%m/%Y à %H:%M')}</p>
        </div>
        
        <h2>📈 Résumé du Portefeuille</h2>
        <div class="summary-grid">
            <div class="summary-card">
                <div class="label">Positions Actives</div>
                <div class="value">{summary['total_positions']}</div>
            </div>
            <div class="summary-card">
                <div class="label">Valeur Totale</div>
                <div class="value">{summary['total_value']:,.0f} €</div>
            </div>
            <div class="summary-card">
                <div class="label">P&L Total</div>
                <div class="value {'positive' if summary['total_pnl_eur'] >= 0 else 'negative'}">{'+' if summary['total_pnl_eur'] >= 0 else ''}{summary['total_pnl_eur']:,.0f} €</div>
            </div>
            <div class="summary-card">
                <div class="label">P&L %</div>
                <div class="value {'positive' if summary['total_pnl_pct'] >= 0 else 'negative'}">{'+' if summary['total_pnl_pct'] >= 0 else ''}{summary['total_pnl_pct']:.1f}%</div>
            </div>
            <div class="summary-card">
                <div class="label">Score Moyen Higgons</div>
                <div class="value">{summary['avg_score']}/100</div>
            </div>
        </div>
        
        <h2>🎯 Recommandations</h2>
        <div style="margin-bottom: 30px;">
    """
    
    for rec in recommendations[:10]:  # Top 10 recommandations
        html += f"""
            <div class="recommendation {rec['type']}">
                <div>
                    <strong>{rec['ticker']}</strong> - {rec['name']}<br>
                    <span style="font-size: 12px; color: #64748b;">{rec.get('reason', '')[:80]}...</span>
                </div>
                <div style="text-align: right;">
                    <span class="priority {rec['priority']}">{rec['priority']}</span><br>
                    <span style="font-size: 20px; font-weight: bold;">{rec['type']}</span><br>
                    <span style="font-size: 12px;">Score: {rec['score']}/100</span>
                </div>
            </div>
        """
    
    html += """
        </div>
        
        <h2>📋 Détail des Positions</h2>
        <table>
            <thead>
                <tr>
                    <th>Ticker</th>
                    <th>Nom</th>
                    <th>Qty</th>
                    <th>Prix</th>
                    <th>P&L</th>
                    <th>Signal</th>
                    <th>Score</th>
                    <th>F-Score</th>
                    <th>PE</th>
                    <th>ROE</th>
                    <th>Gates</th>
                </tr>
            </thead>
            <tbody>
    """
    
    for _, row in results.iterrows():
        signal_color = signal_colors.get(row['signal'], '#6b7280')
        pnl_class = 'positive' if row['pnl_pct'] >= 0 else 'negative'
        score_color = '#16a34a' if row['score_total'] >= 60 else '#f59e0b' if row['score_total'] >= 40 else '#dc2626'
        
        # F-Score avec couleur
        f_score = row.get('score_piotroski', 0) or 0
        f_score_color = '#16a34a' if f_score >= 6 else '#f59e0b' if f_score >= 4 else '#dc2626'
        f_score_display = f"{f_score:.0f}/9" if f_score > 0 else '-'
        
        html += f"""
                <tr>
                    <td><strong>{row['ticker']}</strong></td>
                    <td>{row['name'][:20]}</td>
                    <td>{row['qty']:.0f}</td>
                    <td>{row['price']:.2f} €</td>
                    <td class="{pnl_class}">{'+' if row['pnl_pct'] >= 0 else ''}{row['pnl_pct']:.1f}%</td>
                    <td><span class="signal" style="background: {signal_color}; color: white;">{row['signal']}</span></td>
                    <td>
                        <div style="display: flex; align-items: center; gap: 8px;">
                            <div class="score-bar"><div class="score-bar-fill" style="width: {row['score_total']}%; background: {score_color};"></div></div>
                            <span style="font-size: 12px;">{row['score_total']:.0f}</span>
                        </div>
                    </td>
                    <td style="color: {f_score_color}; font-weight: bold;">{f_score_display}</td>
                    <td>{f"{row['pe_ttm']:.1f}" if pd.notna(row['pe_ttm']) else '-'}</td>
                    <td>{f"{row['roe_ttm']*100:.1f}%" if pd.notna(row['roe_ttm']) else '-'}</td>
                    <td>{'✅' if row['gates_passed'] else '❌'}</td>
                </tr>
        """
    
    html += f"""
            </tbody>
        </table>
        
        <p class="timestamp">
            Généré par Portfolio Analyzer v1.0 • Méthodologie William Higgons<br>
            Ce rapport ne constitue pas un conseil en investissement
        </p>
    </div>
</body>
</html>
    """
    
    with open(output_path, 'w', encoding='utf-8') as f:
        f.write(html)
    
    return output_path


# ============================================================
# MAIN
# ============================================================

if __name__ == "__main__":
    import sys
    
    print("=" * 60)
    print("PORTFOLIO ANALYZER - Méthodologie Higgons + Price Action")
    print("=" * 60)
    
    # Charger le portefeuille
    # Par défaut, cherche le fichier dans le répertoire courant
    portfolio_path = "portfolio.xlsx"
    
    if len(sys.argv) > 1:
        portfolio_path = sys.argv[1]
    
    try:
        df = pd.read_excel(portfolio_path)
        print(f"\n✅ Portefeuille chargé: {len(df)} valeurs")
    except FileNotFoundError:
        print(f"\n❌ Fichier non trouvé: {portfolio_path}")
        print("Usage: python portfolio_analyzer.py [chemin_vers_portfolio.xlsx]")
        sys.exit(1)
    
    # Analyser
    analyzer = PortfolioAnalyzer(df)
    results = analyzer.analyze_all()
    
    # Résumé
    summary = analyzer.get_summary()
    print(f"\n📊 RÉSUMÉ DU PORTEFEUILLE")
    print(f"   Positions actives: {summary['total_positions']}")
    print(f"   Valeur totale: {summary['total_value']:,.0f} €")
    print(f"   P&L total: {summary['total_pnl_eur']:+,.0f} € ({summary['total_pnl_pct']:+.1f}%)")
    print(f"   Score moyen: {summary['avg_score']}/100")
    
    # Top recommandations
    recommendations = analyzer.get_recommendations()
    print(f"\n🎯 TOP RECOMMANDATIONS")
    for rec in recommendations[:5]:
        print(f"   [{rec['type']}] {rec['ticker']} - Score: {rec['score']}/100 - {rec['priority']}")
    
    # Générer le rapport HTML
    report_path = generate_html_report(analyzer, 'portfolio_report.html')
    print(f"\n📄 Rapport généré: {report_path}")
    
    print("\n" + "=" * 60)

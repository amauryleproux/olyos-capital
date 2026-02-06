"""
ADVANCED SCORING MODULE
========================
Module de scoring avancé incluant:
- Piotroski F-Score (0-9)
- Score Higgons amélioré
- Score de Momentum
- Score combiné multi-factoriel

Le Piotroski F-Score est un score de 0 à 9 qui mesure la santé financière
d'une entreprise basé sur 9 critères binaires (0 ou 1 point chacun).

Référence: Joseph Piotroski, "Value Investing: The Use of Historical 
Financial Statement Information to Separate Winners from Losers" (2000)

Usage:
    from advanced_scoring import AdvancedScorer
    
    scorer = AdvancedScorer()
    scores = scorer.calculate_all_scores(stock_data)

Auteur: Votre nom
Version: 1.0
"""

import pandas as pd
import numpy as np
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')


# ============================================================
# PIOTROSKI F-SCORE
# ============================================================

class PiotroskiScorer:
    """
    Calcule le Piotroski F-Score (0-9)
    
    Le score est composé de 9 critères binaires répartis en 3 catégories:
    
    RENTABILITÉ (4 points):
    1. ROA positif (Résultat net / Total actifs > 0)
    2. Cash-flow opérationnel positif
    3. ROA en amélioration vs année précédente
    4. CFO > Résultat net (qualité des bénéfices)
    
    LEVERAGE & LIQUIDITÉ (3 points):
    5. Dette long terme en baisse vs année précédente
    6. Current ratio en amélioration
    7. Pas de dilution (actions en circulation stables ou en baisse)
    
    EFFICACITÉ OPÉRATIONNELLE (2 points):
    8. Marge brute en amélioration
    9. Rotation des actifs en amélioration
    
    Interprétation:
    - 8-9: Excellent (Strong Buy)
    - 6-7: Bon (Buy)
    - 4-5: Neutre (Hold)
    - 2-3: Faible (Sell)
    - 0-1: Très faible (Strong Sell)
    
    NOTE: Quand les données historiques ne sont pas disponibles,
    on utilise des critères alternatifs basés sur les niveaux absolus.
    """
    
    def __init__(self):
        self.components = {}
    
    def calculate_f_score(self, current_data, previous_data=None):
        """
        Calcule le F-Score complet
        
        Args:
            current_data: dict avec les données financières actuelles
            previous_data: dict avec les données de l'année précédente (optionnel)
        
        Returns:
            dict avec le score total et le détail de chaque composante
        """
        self.components = {}
        
        if previous_data is None:
            previous_data = {}
        
        # ========== RENTABILITÉ (4 points) ==========
        
        # 1. ROA positif
        roa = current_data.get('roa') or current_data.get('roa_ttm') or current_data.get('returnOnAssets')
        if roa is not None and roa > 0:
            self.components['F1_ROA_positive'] = 1
        elif roa is not None:
            self.components['F1_ROA_positive'] = 0
        else:
            # Fallback: utiliser ROE si ROA non disponible
            roe = current_data.get('roe') or current_data.get('roe_ttm') or current_data.get('returnOnEquity')
            if roe is not None and roe > 0:
                self.components['F1_ROA_positive'] = 1
            else:
                self.components['F1_ROA_positive'] = 0
        
        # 2. CFO positif
        cfo = current_data.get('operating_cash_flow') or current_data.get('cfo') or current_data.get('operatingCashflow')
        if cfo is not None and cfo > 0:
            self.components['F2_CFO_positive'] = 1
        elif cfo is None:
            # Fallback: si FCF positif, CFO probablement positif aussi
            fcf = current_data.get('free_cash_flow') or current_data.get('freeCashflow')
            if fcf is not None and fcf > 0:
                self.components['F2_CFO_positive'] = 1
            else:
                self.components['F2_CFO_positive'] = 0.5  # Incertain
        else:
            self.components['F2_CFO_positive'] = 0
        
        # 3. ROA en amélioration (ou niveau élevé si pas d'historique)
        prev_roa = previous_data.get('roa') or previous_data.get('roa_ttm')
        if roa is not None and prev_roa is not None:
            self.components['F3_ROA_improving'] = 1 if roa > prev_roa else 0
        elif roa is not None:
            # Pas d'historique: utiliser le niveau absolu
            # ROA > 5% est considéré comme bon
            if roa > 0.08:
                self.components['F3_ROA_improving'] = 1
            elif roa > 0.05:
                self.components['F3_ROA_improving'] = 0.5
            else:
                self.components['F3_ROA_improving'] = 0
        else:
            self.components['F3_ROA_improving'] = 0.5
        
        # 4. Qualité des bénéfices (CFO > Net Income)
        net_income = current_data.get('net_income') or current_data.get('netIncomeToCommon')
        if cfo is not None and net_income is not None:
            if cfo > net_income:
                self.components['F4_accruals'] = 1
            elif cfo > 0 and net_income > 0:
                self.components['F4_accruals'] = 0.5  # Les deux positifs mais CFO < NI
            else:
                self.components['F4_accruals'] = 0
        else:
            # Fallback: FCF/NI ratio
            fcf = current_data.get('free_cash_flow') or current_data.get('freeCashflow')
            fcf_to_ni = current_data.get('fcf_to_net_income')
            if fcf_to_ni is not None and fcf_to_ni > 0.7:
                self.components['F4_accruals'] = 1
            elif fcf is not None and fcf > 0:
                self.components['F4_accruals'] = 0.5
            else:
                self.components['F4_accruals'] = 0.5
        
        # ========== LEVERAGE & LIQUIDITÉ (3 points) ==========
        
        # 5. Dette en baisse ou niveau faible
        total_debt = current_data.get('total_debt') or current_data.get('totalDebt')
        prev_debt = previous_data.get('total_debt') or previous_data.get('totalDebt')
        debt_to_equity = current_data.get('debt_to_equity') or current_data.get('debtToEquity')
        net_debt_ebitda = current_data.get('net_debt_to_ebitda')
        
        if total_debt is not None and prev_debt is not None:
            self.components['F5_leverage_down'] = 1 if total_debt <= prev_debt else 0
        elif net_debt_ebitda is not None:
            # Utiliser le niveau absolu de dette
            if net_debt_ebitda <= 0:
                self.components['F5_leverage_down'] = 1  # Trésorerie nette
            elif net_debt_ebitda <= 1.5:
                self.components['F5_leverage_down'] = 1
            elif net_debt_ebitda <= 3:
                self.components['F5_leverage_down'] = 0.5
            else:
                self.components['F5_leverage_down'] = 0
        elif debt_to_equity is not None:
            if debt_to_equity <= 50:
                self.components['F5_leverage_down'] = 1
            elif debt_to_equity <= 100:
                self.components['F5_leverage_down'] = 0.5
            else:
                self.components['F5_leverage_down'] = 0
        else:
            self.components['F5_leverage_down'] = 0.5
        
        # 6. Current ratio en amélioration ou niveau acceptable
        current_ratio = current_data.get('current_ratio') or current_data.get('currentRatio')
        prev_current_ratio = previous_data.get('current_ratio')
        
        if current_ratio is not None and prev_current_ratio is not None:
            self.components['F6_liquidity_improving'] = 1 if current_ratio > prev_current_ratio else 0
        elif current_ratio is not None:
            # Utiliser le niveau absolu
            if current_ratio >= 2.0:
                self.components['F6_liquidity_improving'] = 1
            elif current_ratio >= 1.5:
                self.components['F6_liquidity_improving'] = 0.75
            elif current_ratio >= 1.0:
                self.components['F6_liquidity_improving'] = 0.5
            else:
                self.components['F6_liquidity_improving'] = 0
        else:
            self.components['F6_liquidity_improving'] = 0.5
        
        # 7. Pas de dilution
        shares = current_data.get('shares_outstanding') or current_data.get('sharesOutstanding')
        prev_shares = previous_data.get('shares_outstanding')
        
        if shares is not None and prev_shares is not None:
            # Tolérance de 2% pour les stock options
            if shares <= prev_shares * 1.02:
                self.components['F7_no_dilution'] = 1
            else:
                self.components['F7_no_dilution'] = 0
        else:
            # Par défaut, on suppose pas de dilution majeure
            self.components['F7_no_dilution'] = 0.5
        
        # ========== EFFICACITÉ OPÉRATIONNELLE (2 points) ==========
        
        # 8. Marge brute en amélioration ou niveau élevé
        gross_margin = current_data.get('gross_margin') or current_data.get('grossMargins')
        prev_gross_margin = previous_data.get('gross_margin')
        
        if gross_margin is not None and prev_gross_margin is not None:
            self.components['F8_margin_improving'] = 1 if gross_margin > prev_gross_margin else 0
        elif gross_margin is not None:
            # Utiliser le niveau absolu
            if gross_margin >= 0.40:
                self.components['F8_margin_improving'] = 1
            elif gross_margin >= 0.25:
                self.components['F8_margin_improving'] = 0.5
            else:
                self.components['F8_margin_improving'] = 0
        else:
            # Fallback: utiliser operating margin
            op_margin = current_data.get('operating_margin') or current_data.get('operatingMargins')
            if op_margin is not None:
                if op_margin >= 0.15:
                    self.components['F8_margin_improving'] = 1
                elif op_margin >= 0.08:
                    self.components['F8_margin_improving'] = 0.5
                else:
                    self.components['F8_margin_improving'] = 0
            else:
                self.components['F8_margin_improving'] = 0.5
        
        # 9. Rotation des actifs en amélioration ou niveau acceptable
        revenue = current_data.get('revenue') or current_data.get('totalRevenue')
        assets = current_data.get('total_assets') or current_data.get('totalAssets')
        prev_revenue = previous_data.get('revenue')
        prev_assets = previous_data.get('total_assets')
        
        asset_turnover = None
        if revenue and assets and assets > 0:
            asset_turnover = revenue / assets
        
        prev_asset_turnover = None
        if prev_revenue and prev_assets and prev_assets > 0:
            prev_asset_turnover = prev_revenue / prev_assets
        
        if asset_turnover is not None and prev_asset_turnover is not None:
            self.components['F9_turnover_improving'] = 1 if asset_turnover > prev_asset_turnover else 0
        elif asset_turnover is not None:
            # Utiliser le niveau absolu
            if asset_turnover >= 1.0:
                self.components['F9_turnover_improving'] = 1
            elif asset_turnover >= 0.5:
                self.components['F9_turnover_improving'] = 0.5
            else:
                self.components['F9_turnover_improving'] = 0
        else:
            self.components['F9_turnover_improving'] = 0.5
        
        # ========== CALCUL DU SCORE TOTAL ==========
        
        total_score = sum(self.components.values())
        
        # Interprétation
        if total_score >= 7:
            interpretation = 'EXCELLENT'
            recommendation = 'STRONG_BUY'
        elif total_score >= 5.5:
            interpretation = 'BON'
            recommendation = 'BUY'
        elif total_score >= 4:
            interpretation = 'NEUTRE'
            recommendation = 'HOLD'
        elif total_score >= 2.5:
            interpretation = 'FAIBLE'
            recommendation = 'REDUCE'
        else:
            interpretation = 'TRES_FAIBLE'
            recommendation = 'SELL'
        
        return {
            'f_score': round(total_score, 1),
            'f_score_max': 9,
            'f_score_pct': round(total_score / 9 * 100, 1),
            'interpretation': interpretation,
            'recommendation': recommendation,
            'components': self.components,
            'profitability_score': round(sum([
                self.components.get('F1_ROA_positive', 0),
                self.components.get('F2_CFO_positive', 0),
                self.components.get('F3_ROA_improving', 0),
                self.components.get('F4_accruals', 0),
            ]), 1),
            'leverage_score': round(sum([
                self.components.get('F5_leverage_down', 0),
                self.components.get('F6_liquidity_improving', 0),
                self.components.get('F7_no_dilution', 0),
            ]), 1),
            'efficiency_score': round(sum([
                self.components.get('F8_margin_improving', 0),
                self.components.get('F9_turnover_improving', 0),
            ]), 1),
        }
    
    def calculate_from_yahoo_data(self, yahoo_data):
        """
        Calcule le F-Score à partir des données Yahoo Finance
        
        Args:
            yahoo_data: dict retourné par yfinance
        
        Returns:
            dict avec le F-Score
        """
        # Mapper les données Yahoo vers notre format
        current_data = {
            'roa': yahoo_data.get('returnOnAssets'),
            'roe': yahoo_data.get('returnOnEquity'),
            'operating_cash_flow': yahoo_data.get('operatingCashflow'),
            'free_cash_flow': yahoo_data.get('freeCashflow'),
            'net_income': yahoo_data.get('netIncomeToCommon'),
            'total_debt': yahoo_data.get('totalDebt'),
            'total_cash': yahoo_data.get('totalCash'),
            'current_ratio': yahoo_data.get('currentRatio'),
            'shares_outstanding': yahoo_data.get('sharesOutstanding'),
            'gross_margin': yahoo_data.get('grossMargins'),
            'operating_margin': yahoo_data.get('operatingMargins'),
            'revenue': yahoo_data.get('totalRevenue'),
            'total_assets': yahoo_data.get('totalAssets'),
            'debt_to_equity': yahoo_data.get('debtToEquity'),
            'ebitda': yahoo_data.get('ebitda'),
        }
        
        # Calculer net_debt_to_ebitda si possible
        if current_data['total_debt'] and current_data['total_cash'] and current_data.get('ebitda'):
            ebitda = current_data['ebitda']
            if ebitda and ebitda > 0:
                net_debt = (current_data['total_debt'] or 0) - (current_data['total_cash'] or 0)
                current_data['net_debt_to_ebitda'] = net_debt / ebitda
        
        return self.calculate_f_score(current_data, previous_data=None)
    
    def calculate_from_portfolio_row(self, row_data):
        """
        Calcule le F-Score à partir d'une ligne du portefeuille Excel
        Utilise les vraies données si disponibles, sinon estime
        
        Args:
            row_data: dict ou Series avec les données du portefeuille
        
        Returns:
            dict avec le F-Score
        """
        if hasattr(row_data, 'to_dict'):
            row_data = row_data.to_dict()
        
        # Mapper les colonnes du portefeuille
        # Priorité aux vraies données Yahoo Finance si présentes
        current_data = {
            # Rentabilité
            'roa': row_data.get('roa_ttm'),  # Vraie donnée Yahoo
            'roe': row_data.get('roe_ttm'),
            
            # Cash Flow
            'operating_cash_flow': row_data.get('operating_cashflow'),  # Vraie donnée Yahoo
            'free_cash_flow': row_data.get('free_cashflow'),  # Vraie donnée Yahoo
            
            # Résultat
            'net_income': row_data.get('net_income'),  # Vraie donnée Yahoo
            
            # Bilan
            'total_debt': row_data.get('total_debt'),  # Vraie donnée Yahoo
            'total_cash': row_data.get('total_cash'),
            'current_ratio': row_data.get('current_ratio'),  # Vraie donnée Yahoo
            'total_assets': row_data.get('total_assets'),  # Vraie donnée Yahoo
            
            # Actions
            'shares_outstanding': row_data.get('shares_outstanding'),  # Vraie donnée Yahoo
            
            # Marges
            'gross_margin': row_data.get('gross_margin'),  # Vraie donnée Yahoo
            'operating_margin': row_data.get('operating_margin'),
            
            # Autres
            'revenue': row_data.get('revenue'),
            'ebitda': row_data.get('ebitda'),
            'net_debt_to_ebitda': row_data.get('net_debt_to_ebitda'),
            'fcf_yield': row_data.get('fcf_yield'),
            'equity_ratio': row_data.get('equity_ratio'),
            'fcf_to_net_income': row_data.get('fcf_to_net_income'),
            'debt_to_equity': row_data.get('debt_to_equity'),
        }
        
        # Vérifier si on a les vraies données Piotroski
        real_data_fields = ['roa', 'operating_cash_flow', 'gross_margin', 'current_ratio', 'total_assets']
        real_data_count = sum(1 for f in real_data_fields if current_data.get(f) is not None)
        
        # Si on n'a pas les vraies données, estimer certaines métriques
        if real_data_count < 3:
            # ROA approximé depuis ROE et equity_ratio
            if current_data.get('roa') is None:
                roe = current_data.get('roe')
                equity_ratio = current_data.get('equity_ratio')
                if roe and equity_ratio and equity_ratio > 0:
                    current_data['roa'] = roe * equity_ratio
            
            # Gross margin estimé depuis operating margin
            if current_data.get('gross_margin') is None:
                op_margin = current_data.get('operating_margin')
                if op_margin:
                    current_data['gross_margin'] = min(op_margin * 2, 0.6)
            
            # Current ratio estimé depuis equity_ratio
            if current_data.get('current_ratio') is None:
                equity_ratio = current_data.get('equity_ratio')
                if equity_ratio:
                    if equity_ratio >= 0.5:
                        current_data['current_ratio'] = 2.0
                    elif equity_ratio >= 0.3:
                        current_data['current_ratio'] = 1.5
                    else:
                        current_data['current_ratio'] = 1.0
        
        result = self.calculate_f_score(current_data, previous_data=None)
        
        # Ajouter l'indicateur de qualité des données
        result['data_quality'] = 'REAL' if real_data_count >= 3 else 'ESTIMATED'
        result['real_data_count'] = real_data_count
        
        return result


# ============================================================
# SCORING COMBINÉ AVANCÉ
# ============================================================

class AdvancedScorer:
    """
    Scoring multi-factoriel combinant:
    - Score Higgons (Value + Quality)
    - Piotroski F-Score
    - Momentum Score
    - Score technique (si données disponibles)
    """
    
    def __init__(self):
        self.piotroski = PiotroskiScorer()
        
        # Configuration des poids
        self.weights = {
            'higgons': 0.40,      # 40% - Critères Value/Quality Higgons
            'piotroski': 0.25,    # 25% - Santé financière
            'momentum': 0.20,     # 20% - Momentum prix
            'technical': 0.15,    # 15% - Timing technique
        }
        
        # Seuils Higgons
        self.higgons_config = {
            'pe_max_excellent': 10,
            'pe_max_acceptable': 12,
            'pe_max_limit': 15,
            'roe_min_excellent': 0.15,
            'roe_min_acceptable': 0.10,
            'margin_min': 0.04,
            'debt_ebitda_max': 3.0,
            'fcf_yield_min': 0.05,
        }
    
    def score_higgons(self, data):
        """
        Calcule le score Higgons (0-100)
        """
        scores = {}
        
        # PE Score (25 points max)
        pe = data.get('pe_ttm')
        if pe is None or pe <= 0:
            scores['pe'] = 0
        elif pe <= self.higgons_config['pe_max_excellent']:
            scores['pe'] = 25
        elif pe <= self.higgons_config['pe_max_acceptable']:
            scores['pe'] = 20
        elif pe <= self.higgons_config['pe_max_limit']:
            scores['pe'] = 12
        elif pe <= 20:
            scores['pe'] = 5
        else:
            scores['pe'] = 0
        
        # ROE Score (25 points max)
        roe = data.get('roe_ttm') or data.get('roe')
        if roe is None or roe <= 0:
            scores['roe'] = 0
        elif roe >= self.higgons_config['roe_min_excellent']:
            scores['roe'] = 25
        elif roe >= self.higgons_config['roe_min_acceptable']:
            scores['roe'] = 18
        elif roe >= 0.05:
            scores['roe'] = 8
        else:
            scores['roe'] = 0
        
        # Margin Score (15 points max)
        margin = data.get('operating_margin')
        if margin is None:
            scores['margin'] = 7
        elif margin >= 0.20:
            scores['margin'] = 15
        elif margin >= 0.10:
            scores['margin'] = 12
        elif margin >= self.higgons_config['margin_min']:
            scores['margin'] = 8
        else:
            scores['margin'] = 0
        
        # Leverage Score (15 points max)
        debt_ebitda = data.get('net_debt_to_ebitda')
        if debt_ebitda is None:
            scores['leverage'] = 7
        elif debt_ebitda <= 0:  # Trésorerie nette
            scores['leverage'] = 15
        elif debt_ebitda <= 1.5:
            scores['leverage'] = 12
        elif debt_ebitda <= self.higgons_config['debt_ebitda_max']:
            scores['leverage'] = 7
        else:
            scores['leverage'] = 0
        
        # FCF Score (20 points max)
        fcf_yield = data.get('fcf_yield')
        if fcf_yield is None:
            scores['fcf'] = 10
        elif fcf_yield >= 0.10:
            scores['fcf'] = 20
        elif fcf_yield >= self.higgons_config['fcf_yield_min']:
            scores['fcf'] = 15
        elif fcf_yield >= 0.02:
            scores['fcf'] = 8
        else:
            scores['fcf'] = 0
        
        total = sum(scores.values())
        
        return {
            'score': total,
            'max_score': 100,
            'components': scores,
        }
    
    def score_momentum(self, data):
        """
        Calcule le score de momentum (0-100)
        """
        scores = {}
        
        # Momentum 12 mois (50 points max)
        mom_12m = data.get('momentum_12m')
        if mom_12m is None:
            scores['mom_12m'] = 25
        elif mom_12m >= 0.30:
            scores['mom_12m'] = 50
        elif mom_12m >= 0.15:
            scores['mom_12m'] = 40
        elif mom_12m >= 0:
            scores['mom_12m'] = 30
        elif mom_12m >= -0.15:
            scores['mom_12m'] = 20
        elif mom_12m >= -0.25:
            scores['mom_12m'] = 10
        else:
            scores['mom_12m'] = 0  # Momentum très négatif = danger
        
        # Momentum 6 mois (30 points max)
        mom_6m = data.get('momentum_6m')
        if mom_6m is None:
            scores['mom_6m'] = 15
        elif mom_6m >= 0.15:
            scores['mom_6m'] = 30
        elif mom_6m >= 0:
            scores['mom_6m'] = 22
        elif mom_6m >= -0.10:
            scores['mom_6m'] = 12
        else:
            scores['mom_6m'] = 0
        
        # Momentum 1 mois - court terme (20 points max)
        mom_1m = data.get('momentum_1m')
        if mom_1m is None:
            scores['mom_1m'] = 10
        elif mom_1m >= 0.05:
            scores['mom_1m'] = 20
        elif mom_1m >= 0:
            scores['mom_1m'] = 15
        elif mom_1m >= -0.05:
            scores['mom_1m'] = 10
        else:
            scores['mom_1m'] = 5
        
        total = sum(scores.values())
        
        return {
            'score': total,
            'max_score': 100,
            'components': scores,
        }
    
    def score_technical(self, data):
        """
        Calcule le score technique/timing (0-100)
        Basé sur Fibonacci, RSI, tendance
        """
        scores = {}
        
        # Zone Fibonacci (40 points max)
        fib_zone = data.get('fib_zone') or data.get('zone')
        fib_quality = data.get('fib_zone_quality') or data.get('zone_quality')
        
        if fib_quality is not None:
            scores['fibonacci'] = fib_quality * 0.4
        elif fib_zone:
            zone_scores = {
                'GOLDEN_ZONE': 40,
                'DEEP_VALUE': 40,
                'EXTREME_DISCOUNT': 35,
                'HALF_RETRACEMENT': 30,
                'DEEP_PULLBACK': 35,
                'SHALLOW_PULLBACK': 20,
                'MINOR_PULLBACK': 15,
                'NEW_HIGH': 10,
                'NEW_LOW': 25,
            }
            scores['fibonacci'] = zone_scores.get(fib_zone, 20)
        else:
            scores['fibonacci'] = 20
        
        # RSI (30 points max)
        rsi = data.get('rsi')
        if rsi is None:
            scores['rsi'] = 15
        elif rsi < 30:
            scores['rsi'] = 30  # Survendu = opportunité
        elif rsi < 40:
            scores['rsi'] = 25
        elif rsi < 60:
            scores['rsi'] = 20  # Neutre
        elif rsi < 70:
            scores['rsi'] = 12
        else:
            scores['rsi'] = 5  # Suracheté = danger
        
        # Tendance (30 points max)
        trend = data.get('trend') or data.get('trend_score')
        if isinstance(trend, str):
            trend_scores = {
                'STRONG_UPTREND': 30,
                'UPTREND': 25,
                'SIDEWAYS': 15,
                'DOWNTREND': 10,
                'STRONG_DOWNTREND': 5,
            }
            scores['trend'] = trend_scores.get(trend, 15)
        elif isinstance(trend, (int, float)):
            # Score de -100 à +100 -> converti en 0-30
            scores['trend'] = max(0, min(30, (trend + 100) / 200 * 30))
        else:
            scores['trend'] = 15
        
        total = sum(scores.values())
        
        return {
            'score': total,
            'max_score': 100,
            'components': scores,
        }
    
    def calculate_all_scores(self, data, yahoo_data=None):
        """
        Calcule tous les scores et le score combiné
        
        Args:
            data: dict avec les données de base (PE, ROE, etc.)
            yahoo_data: dict avec les données Yahoo Finance (optionnel, pour Piotroski)
        
        Returns:
            dict avec tous les scores
        """
        results = {}
        
        # 1. Score Higgons
        higgons = self.score_higgons(data)
        results['higgons'] = higgons
        
        # 2. Piotroski F-Score
        # Priorité: Yahoo data > données du portefeuille
        if yahoo_data and any(yahoo_data.get(k) for k in ['returnOnAssets', 'operatingCashflow', 'grossMargins']):
            piotroski = self.piotroski.calculate_from_yahoo_data(yahoo_data)
        else:
            # Utiliser les données du portefeuille
            piotroski = self.piotroski.calculate_from_portfolio_row(data)
        
        results['piotroski'] = piotroski
        
        # 3. Score Momentum
        momentum = self.score_momentum(data)
        results['momentum'] = momentum
        
        # 4. Score Technique
        technical = self.score_technical(data)
        results['technical'] = technical
        
        # 5. Score Combiné
        combined_score = (
            higgons['score'] * self.weights['higgons'] +
            (piotroski['f_score_pct']) * self.weights['piotroski'] +
            momentum['score'] * self.weights['momentum'] +
            technical['score'] * self.weights['technical']
        )
        
        # 6. Signal final
        if combined_score >= 75:
            signal = 'STRONG_BUY'
        elif combined_score >= 60:
            signal = 'BUY'
        elif combined_score >= 45:
            signal = 'HOLD'
        elif combined_score >= 30:
            signal = 'REDUCE'
        else:
            signal = 'SELL'
        
        # Ajustement si F-Score très faible (red flag)
        if piotroski['f_score'] <= 3:
            if signal in ['STRONG_BUY', 'BUY']:
                signal = 'HOLD'
                results['warning'] = 'F-Score faible: santé financière douteuse'
        
        # Ajustement si momentum très négatif (value trap risk)
        mom_12m = data.get('momentum_12m', 0)
        if mom_12m is not None and mom_12m < -0.25:
            if signal in ['STRONG_BUY', 'BUY']:
                signal = 'HOLD'
                results['warning'] = 'Momentum très négatif: risque de value trap'
        
        results['combined'] = {
            'score': round(combined_score, 1),
            'signal': signal,
            'weights': self.weights,
        }
        
        return results
    
    def get_score_summary(self, results):
        """
        Génère un résumé lisible des scores
        """
        summary = []
        summary.append(f"═══ SCORE COMBINÉ: {results['combined']['score']}/100 ({results['combined']['signal']}) ═══")
        summary.append("")
        summary.append(f"  Higgons (40%):    {results['higgons']['score']}/100")
        summary.append(f"  Piotroski (25%):  {results['piotroski']['f_score']}/9 ({results['piotroski']['f_score_pct']}%)")
        summary.append(f"  Momentum (20%):   {results['momentum']['score']}/100")
        summary.append(f"  Technique (15%):  {results['technical']['score']}/100")
        
        if 'warning' in results:
            summary.append("")
            summary.append(f"  ⚠️  {results['warning']}")
        
        return "\n".join(summary)


# ============================================================
# FONCTION UTILITAIRE
# ============================================================

def calculate_advanced_score(row_data, yahoo_data=None):
    """
    Fonction utilitaire pour calculer le score avancé d'une ligne de portefeuille
    
    Args:
        row_data: dict ou Series avec les données de base
        yahoo_data: dict avec données Yahoo Finance (optionnel)
    
    Returns:
        dict avec tous les scores
    """
    scorer = AdvancedScorer()
    
    # Convertir Series en dict si nécessaire
    if hasattr(row_data, 'to_dict'):
        row_data = row_data.to_dict()
    
    return scorer.calculate_all_scores(row_data, yahoo_data)


# ============================================================
# TESTS
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("TEST ADVANCED SCORING MODULE")
    print("=" * 60)
    
    # Données de test (exemple: LVMH)
    test_data = {
        'ticker': 'MC',
        'name': 'LVMH',
        'pe_ttm': 27.0,
        'roe_ttm': 0.187,
        'operating_margin': 0.23,
        'net_debt_to_ebitda': 1.1,
        'fcf_yield': 0.22,
        'momentum_12m': -0.15,
        'momentum_6m': -0.08,
        'momentum_1m': 0.02,
        'rsi': 45,
        'fib_zone': 'GOLDEN_ZONE',
        # Pour Piotroski
        'roa': 0.12,
        'operating_cash_flow': 15000000000,
        'net_income': 12000000000,
        'current_ratio': 1.4,
        'gross_margin': 0.68,
    }
    
    scorer = AdvancedScorer()
    results = scorer.calculate_all_scores(test_data)
    
    print("\n" + scorer.get_score_summary(results))
    
    print("\n\nDétail Piotroski:")
    for key, value in results['piotroski']['components'].items():
        status = "✅" if value >= 0.5 else "❌"
        print(f"  {status} {key}: {value}")
    
    print("\n" + "=" * 60)

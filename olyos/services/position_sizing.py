"""
POSITION SIZING & REBALANCING MODULE
=====================================
Module pour:
- Calculer la taille optimale des positions basée sur le risque
- Gérer le rebalancing automatique du portefeuille
- Définir les règles de sortie (stop-loss, take-profit)

Principes:
1. Position sizing basé sur la volatilité (pas sur la conviction seule)
2. Diversification: limites par position, secteur, pays
3. Rebalancing quand une position s'écarte trop de sa cible
4. Stops adaptatifs basés sur l'ATR

Usage:
    from position_sizing import PositionSizer, RebalanceManager
    
    sizer = PositionSizer(total_capital=10000)
    size = sizer.calculate_position_size(score=75, volatility=25)

Auteur: Votre nom
Version: 1.0
"""

import pandas as pd
import numpy as np
from datetime import datetime
import warnings
warnings.filterwarnings('ignore')


# ============================================================
# CONFIGURATION
# ============================================================

DEFAULT_CONFIG = {
    # Limites de position
    'max_position_pct': 10.0,       # Max 10% par position
    'min_position_pct': 1.0,        # Min 1% par position (sinon pas la peine)
    'target_positions': 15,          # Nombre cible de positions
    
    # Limites de concentration
    'max_sector_pct': 25.0,         # Max 25% par secteur
    'max_country_pct': 40.0,        # Max 40% par pays
    'max_single_stock_pct': 10.0,   # Max 10% une seule action
    
    # Cash
    'min_cash_pct': 5.0,            # Toujours garder 5% en cash
    'max_cash_pct': 30.0,           # Max 30% en cash (sinon sous-investi)
    
    # Rebalancing
    'rebalance_threshold_pct': 3.0,  # Rebalancer si écart > 3% vs cible
    'rebalance_min_trade': 100,      # Trade minimum en EUR
    
    # Risk management
    'max_portfolio_volatility': 20.0,  # Volatilité cible du portefeuille
    'stop_loss_atr_multiple': 2.5,     # Stop-loss = 2.5x ATR
    'trailing_stop_atr_multiple': 2.0, # Trailing stop = 2x ATR
}


# ============================================================
# POSITION SIZING
# ============================================================

class PositionSizer:
    """
    Calcule la taille optimale des positions basée sur:
    - Le score de la valeur (Higgons + Piotroski)
    - La volatilité de l'action
    - Les limites de risque du portefeuille
    """
    
    def __init__(self, total_capital, config=None):
        """
        Args:
            total_capital: Capital total du portefeuille en EUR
            config: Configuration personnalisée (optionnel)
        """
        self.total_capital = total_capital
        self.config = config or DEFAULT_CONFIG.copy()
    
    def calculate_base_allocation(self, score):
        """
        Calcule l'allocation de base en fonction du score (0-100)
        
        Score élevé = allocation plus grande
        
        Args:
            score: Score combiné de la valeur (0-100)
        
        Returns:
            float: Allocation cible en % du portefeuille
        """
        if score >= 80:
            # Excellent: 5-7%
            return 5.0 + (score - 80) / 20 * 2
        elif score >= 65:
            # Bon: 3-5%
            return 3.0 + (score - 65) / 15 * 2
        elif score >= 50:
            # Acceptable: 2-3%
            return 2.0 + (score - 50) / 15 * 1
        elif score >= 35:
            # Faible: 1-2%
            return 1.0 + (score - 35) / 15 * 1
        else:
            # Très faible: pas d'allocation
            return 0
    
    def adjust_for_volatility(self, base_allocation, volatility):
        """
        Ajuste l'allocation en fonction de la volatilité
        
        Plus volatile = position plus petite (à risque égal)
        
        Args:
            base_allocation: Allocation de base en %
            volatility: Volatilité annualisée en % (ex: 25 pour 25%)
        
        Returns:
            float: Allocation ajustée en %
        """
        if volatility is None or volatility <= 0:
            return base_allocation
        
        # Volatilité de référence: 20%
        # Si vol > 20%, on réduit la position
        # Si vol < 20%, on peut augmenter (mais limité)
        
        reference_vol = 20.0
        adjustment_factor = reference_vol / max(volatility, 10)  # Min 10% vol
        
        # Limiter l'ajustement entre 0.5x et 1.5x
        adjustment_factor = max(0.5, min(1.5, adjustment_factor))
        
        adjusted = base_allocation * adjustment_factor
        
        return adjusted
    
    def apply_limits(self, allocation):
        """
        Applique les limites min/max de position
        
        Args:
            allocation: Allocation calculée en %
        
        Returns:
            float: Allocation limitée en %
        """
        if allocation < self.config['min_position_pct']:
            return 0  # Trop petit, pas la peine
        
        return min(allocation, self.config['max_position_pct'])
    
    def calculate_position_size(self, score, volatility=None, current_price=None):
        """
        Calcule la taille de position recommandée
        
        Args:
            score: Score combiné (0-100)
            volatility: Volatilité annualisée en % (optionnel)
            current_price: Prix actuel de l'action (optionnel)
        
        Returns:
            dict avec les détails de la position
        """
        # 1. Allocation de base selon le score
        base_allocation = self.calculate_base_allocation(score)
        
        # 2. Ajustement pour la volatilité
        if volatility:
            adjusted_allocation = self.adjust_for_volatility(base_allocation, volatility)
        else:
            adjusted_allocation = base_allocation
        
        # 3. Appliquer les limites
        final_allocation = self.apply_limits(adjusted_allocation)
        
        # 4. Calculer les montants
        amount_eur = self.total_capital * final_allocation / 100
        
        # 5. Calculer le nombre d'actions si prix connu
        if current_price and current_price > 0:
            shares = int(amount_eur / current_price)
            actual_amount = shares * current_price
            actual_allocation = actual_amount / self.total_capital * 100
        else:
            shares = None
            actual_amount = amount_eur
            actual_allocation = final_allocation
        
        return {
            'score': score,
            'volatility': volatility,
            'base_allocation_pct': round(base_allocation, 2),
            'volatility_adjusted_pct': round(adjusted_allocation, 2) if volatility else None,
            'final_allocation_pct': round(final_allocation, 2),
            'amount_eur': round(amount_eur, 2),
            'shares': shares,
            'actual_amount_eur': round(actual_amount, 2) if shares else round(amount_eur, 2),
            'actual_allocation_pct': round(actual_allocation, 2),
            'recommendation': self._get_size_recommendation(final_allocation),
        }
    
    def _get_size_recommendation(self, allocation):
        """Retourne une recommandation textuelle"""
        if allocation >= 5:
            return 'CONVICTION_FORTE'
        elif allocation >= 3:
            return 'POSITION_STANDARD'
        elif allocation >= 1:
            return 'POSITION_REDUITE'
        else:
            return 'NE_PAS_ACHETER'
    
    def calculate_portfolio_sizes(self, positions_df, score_col='score_total', vol_col='volatility'):
        """
        Calcule les tailles de position pour tout le portefeuille
        
        Args:
            positions_df: DataFrame avec les positions
            score_col: Nom de la colonne score
            vol_col: Nom de la colonne volatilité
        
        Returns:
            DataFrame avec les tailles recommandées
        """
        results = []
        
        for idx, row in positions_df.iterrows():
            score = row.get(score_col, 50)
            volatility = row.get(vol_col)
            price = row.get('price_eur') or row.get('price')
            
            size = self.calculate_position_size(score, volatility, price)
            
            results.append({
                'ticker': row.get('ticker', idx),
                'name': row.get('name', ''),
                **size
            })
        
        return pd.DataFrame(results)


# ============================================================
# STOP-LOSS & TAKE-PROFIT
# ============================================================

class RiskManager:
    """
    Gère les stops et les prises de profit
    """
    
    def __init__(self, config=None):
        self.config = config or DEFAULT_CONFIG.copy()
    
    def calculate_stop_loss(self, entry_price, atr, method='atr'):
        """
        Calcule le niveau de stop-loss
        
        Args:
            entry_price: Prix d'entrée
            atr: Average True Range (volatilité journalière)
            method: 'atr' ou 'percentage'
        
        Returns:
            dict avec les niveaux de stop
        """
        if method == 'atr' and atr:
            # Stop basé sur ATR (adaptatif à la volatilité)
            stop_distance = atr * self.config['stop_loss_atr_multiple']
            stop_price = entry_price - stop_distance
            stop_pct = (stop_distance / entry_price) * 100
        else:
            # Stop fixe en pourcentage (fallback)
            stop_pct = 15  # -15% par défaut
            stop_price = entry_price * (1 - stop_pct / 100)
            stop_distance = entry_price - stop_price
        
        return {
            'stop_price': round(stop_price, 2),
            'stop_distance': round(stop_distance, 2),
            'stop_pct': round(stop_pct, 1),
            'method': method,
            'atr_multiple': self.config['stop_loss_atr_multiple'] if method == 'atr' else None,
        }
    
    def calculate_trailing_stop(self, highest_price, atr, entry_price=None):
        """
        Calcule le trailing stop (stop suiveur)
        
        Args:
            highest_price: Plus haut atteint depuis l'achat
            atr: Average True Range
            entry_price: Prix d'entrée (pour calculer le profit)
        
        Returns:
            dict avec le trailing stop
        """
        if atr:
            stop_distance = atr * self.config['trailing_stop_atr_multiple']
            trailing_stop = highest_price - stop_distance
        else:
            # Fallback: 10% sous le plus haut
            trailing_stop = highest_price * 0.90
            stop_distance = highest_price - trailing_stop
        
        result = {
            'trailing_stop': round(trailing_stop, 2),
            'highest_price': round(highest_price, 2),
            'stop_distance': round(stop_distance, 2),
        }
        
        if entry_price:
            result['profit_locked_pct'] = round((trailing_stop / entry_price - 1) * 100, 1)
            result['current_profit_pct'] = round((highest_price / entry_price - 1) * 100, 1)
        
        return result
    
    def calculate_take_profit_levels(self, entry_price, target_price=None):
        """
        Calcule les niveaux de prise de profit partielle
        
        Stratégie pyramidale inversée:
        - +30%: Vendre 25% (récupérer une partie de la mise)
        - +50%: Vendre 25% supplémentaire
        - +100%: Vendre 25% (position quasi gratuite)
        - Le reste: Laisser courir avec trailing stop
        
        Args:
            entry_price: Prix d'entrée
            target_price: Prix cible (optionnel)
        
        Returns:
            list de dict avec les niveaux
        """
        levels = [
            {'level': 1, 'gain_pct': 30, 'sell_pct': 25, 'price': round(entry_price * 1.30, 2)},
            {'level': 2, 'gain_pct': 50, 'sell_pct': 25, 'price': round(entry_price * 1.50, 2)},
            {'level': 3, 'gain_pct': 100, 'sell_pct': 25, 'price': round(entry_price * 2.00, 2)},
            {'level': 4, 'gain_pct': 150, 'sell_pct': 25, 'price': round(entry_price * 2.50, 2)},
        ]
        
        # Ajouter le target price si fourni
        if target_price and target_price > entry_price:
            target_gain = (target_price / entry_price - 1) * 100
            levels.append({
                'level': 'TARGET',
                'gain_pct': round(target_gain, 1),
                'sell_pct': 50,  # Vendre 50% au target
                'price': round(target_price, 2),
            })
        
        return sorted(levels, key=lambda x: x['price'] if isinstance(x['gain_pct'], (int, float)) else 999)
    
    def check_exit_signals(self, position_data):
        """
        Vérifie si une position doit être vendue
        
        Args:
            position_data: dict avec les données de la position
        
        Returns:
            dict avec les signaux de sortie
        """
        signals = []
        action = 'HOLD'
        urgency = 'LOW'
        
        current_price = position_data.get('current_price')
        entry_price = position_data.get('entry_price') or position_data.get('avg_cost_eur')
        stop_loss = position_data.get('stop_loss')
        trailing_stop = position_data.get('trailing_stop')
        pe = position_data.get('pe_ttm')
        score = position_data.get('score_total') or position_data.get('score')
        momentum_12m = position_data.get('momentum_12m')
        
        if current_price and entry_price:
            pnl_pct = (current_price / entry_price - 1) * 100
        else:
            pnl_pct = 0
        
        # 1. Stop-loss touché
        if stop_loss and current_price and current_price <= stop_loss:
            signals.append('STOP_LOSS_HIT')
            action = 'SELL_ALL'
            urgency = 'HIGH'
        
        # 2. Trailing stop touché
        if trailing_stop and current_price and current_price <= trailing_stop and pnl_pct > 0:
            signals.append('TRAILING_STOP_HIT')
            action = 'SELL_ALL'
            urgency = 'HIGH'
        
        # 3. PE trop élevé (critère Higgons)
        if pe and pe > 25:
            signals.append('PE_TOO_HIGH')
            action = 'SELL_ALL' if pe > 30 else 'REDUCE'
            urgency = 'MEDIUM'
        elif pe and pe > 20:
            signals.append('PE_ELEVATED')
            if action == 'HOLD':
                action = 'REDUCE'
                urgency = 'LOW'
        
        # 4. Score dégradé
        if score and score < 30:
            signals.append('SCORE_DEGRADED')
            if action == 'HOLD':
                action = 'REDUCE'
                urgency = 'MEDIUM'
        
        # 5. Momentum très négatif
        if momentum_12m and momentum_12m < -0.30:
            signals.append('MOMENTUM_COLLAPSE')
            if action == 'HOLD':
                action = 'REDUCE'
                urgency = 'MEDIUM'
        
        # 6. Take profit
        if pnl_pct >= 100:
            signals.append('DOUBLE_BAGGER')
            if action == 'HOLD':
                action = 'TAKE_PARTIAL_PROFIT'
                urgency = 'LOW'
        elif pnl_pct >= 50:
            signals.append('LARGE_GAIN')
            if action == 'HOLD':
                action = 'CONSIDER_TAKING_PROFIT'
                urgency = 'LOW'
        
        return {
            'action': action,
            'urgency': urgency,
            'signals': signals,
            'pnl_pct': round(pnl_pct, 1),
            'current_price': current_price,
            'stop_loss': stop_loss,
            'trailing_stop': trailing_stop,
        }


# ============================================================
# REBALANCING
# ============================================================

class RebalanceManager:
    """
    Gère le rebalancing du portefeuille
    """
    
    def __init__(self, config=None):
        self.config = config or DEFAULT_CONFIG.copy()
    
    def calculate_target_allocations(self, positions_df, sizer):
        """
        Calcule les allocations cibles pour chaque position
        
        Args:
            positions_df: DataFrame du portefeuille
            sizer: Instance de PositionSizer
        
        Returns:
            DataFrame avec allocations actuelles et cibles
        """
        results = []
        
        # Calculer la valeur totale
        total_value = positions_df['position_value'].sum() if 'position_value' in positions_df.columns else 0
        
        for idx, row in positions_df.iterrows():
            ticker = row.get('ticker', idx)
            score = row.get('score_total') or row.get('score', 50)
            volatility = row.get('volatility')
            price = row.get('price_eur') or row.get('price', 0)
            qty = row.get('qty', 0)
            
            # Position actuelle
            current_value = price * qty if price and qty else 0
            current_pct = (current_value / total_value * 100) if total_value > 0 else 0
            
            # Position cible
            target = sizer.calculate_position_size(score, volatility, price)
            target_pct = target['final_allocation_pct']
            
            # Écart
            diff_pct = current_pct - target_pct
            
            # Action requise
            if abs(diff_pct) < self.config['rebalance_threshold_pct']:
                action = 'OK'
            elif diff_pct > 0:
                action = 'REDUCE'
            else:
                action = 'INCREASE'
            
            results.append({
                'ticker': ticker,
                'name': row.get('name', ''),
                'score': score,
                'current_value': round(current_value, 2),
                'current_pct': round(current_pct, 2),
                'target_pct': round(target_pct, 2),
                'diff_pct': round(diff_pct, 2),
                'action': action,
            })
        
        return pd.DataFrame(results)
    
    def generate_rebalance_trades(self, allocations_df, total_capital):
        """
        Génère les ordres de rebalancing
        
        Args:
            allocations_df: DataFrame avec les allocations (de calculate_target_allocations)
            total_capital: Capital total
        
        Returns:
            list de trades à effectuer
        """
        trades = []
        
        for idx, row in allocations_df.iterrows():
            if row['action'] == 'OK':
                continue
            
            current_value = row['current_value']
            target_value = total_capital * row['target_pct'] / 100
            diff_value = target_value - current_value
            
            # Ignorer les trades trop petits
            if abs(diff_value) < self.config['rebalance_min_trade']:
                continue
            
            if diff_value > 0:
                trade_type = 'BUY'
                amount = diff_value
            else:
                trade_type = 'SELL'
                amount = abs(diff_value)
            
            trades.append({
                'ticker': row['ticker'],
                'name': row['name'],
                'type': trade_type,
                'amount_eur': round(amount, 2),
                'current_pct': row['current_pct'],
                'target_pct': row['target_pct'],
                'reason': f"Rebalance: {row['current_pct']:.1f}% → {row['target_pct']:.1f}%",
            })
        
        # Trier: ventes d'abord (pour avoir du cash), puis achats
        trades.sort(key=lambda x: (0 if x['type'] == 'SELL' else 1, -x['amount_eur']))
        
        return trades
    
    def check_concentration_limits(self, positions_df):
        """
        Vérifie les limites de concentration (secteur, pays, position unique)
        
        Args:
            positions_df: DataFrame du portefeuille
        
        Returns:
            dict avec les alertes de concentration
        """
        alerts = []
        
        total_value = positions_df['position_value'].sum() if 'position_value' in positions_df.columns else 0
        
        if total_value <= 0:
            return {'alerts': [], 'status': 'NO_DATA'}
        
        # 1. Vérifier chaque position
        for idx, row in positions_df.iterrows():
            position_value = row.get('position_value', 0)
            position_pct = position_value / total_value * 100
            
            if position_pct > self.config['max_single_stock_pct']:
                alerts.append({
                    'type': 'POSITION_TOO_LARGE',
                    'ticker': row.get('ticker'),
                    'current_pct': round(position_pct, 1),
                    'limit_pct': self.config['max_single_stock_pct'],
                    'action': f"Réduire de {position_pct - self.config['max_single_stock_pct']:.1f}%",
                })
        
        # 2. Vérifier par secteur
        if 'sector' in positions_df.columns:
            sector_totals = positions_df.groupby('sector')['position_value'].sum()
            for sector, value in sector_totals.items():
                sector_pct = value / total_value * 100
                if sector_pct > self.config['max_sector_pct']:
                    alerts.append({
                        'type': 'SECTOR_TOO_CONCENTRATED',
                        'sector': sector,
                        'current_pct': round(sector_pct, 1),
                        'limit_pct': self.config['max_sector_pct'],
                        'action': f"Réduire l'exposition au secteur {sector}",
                    })
        
        # 3. Vérifier par pays
        if 'country' in positions_df.columns:
            country_totals = positions_df.groupby('country')['position_value'].sum()
            for country, value in country_totals.items():
                country_pct = value / total_value * 100
                if country_pct > self.config['max_country_pct']:
                    alerts.append({
                        'type': 'COUNTRY_TOO_CONCENTRATED',
                        'country': country,
                        'current_pct': round(country_pct, 1),
                        'limit_pct': self.config['max_country_pct'],
                        'action': f"Diversifier géographiquement",
                    })
        
        return {
            'alerts': alerts,
            'status': 'ALERTS' if alerts else 'OK',
            'total_alerts': len(alerts),
        }


# ============================================================
# PORTFOLIO OPTIMIZER
# ============================================================

class PortfolioOptimizer:
    """
    Classe principale qui combine tout:
    - Position sizing
    - Risk management
    - Rebalancing
    """
    
    def __init__(self, total_capital, config=None):
        self.total_capital = total_capital
        self.config = config or DEFAULT_CONFIG.copy()
        
        self.sizer = PositionSizer(total_capital, self.config)
        self.risk_manager = RiskManager(self.config)
        self.rebalancer = RebalanceManager(self.config)
    
    def analyze_portfolio(self, positions_df):
        """
        Analyse complète du portefeuille
        
        Args:
            positions_df: DataFrame avec les positions
        
        Returns:
            dict avec l'analyse complète
        """
        results = {
            'timestamp': datetime.now().isoformat(),
            'total_capital': self.total_capital,
        }
        
        # 1. Calculer les valeurs de position si manquantes
        if 'position_value' not in positions_df.columns:
            positions_df['position_value'] = positions_df.apply(
                lambda row: (row.get('price_eur', 0) or row.get('price', 0)) * (row.get('qty', 0) or 0),
                axis=1
            )
        
        # 2. Statistiques de base
        total_invested = positions_df['position_value'].sum()
        cash = self.total_capital - total_invested
        cash_pct = cash / self.total_capital * 100
        
        results['summary'] = {
            'total_invested': round(total_invested, 2),
            'cash': round(cash, 2),
            'cash_pct': round(cash_pct, 1),
            'num_positions': len(positions_df[positions_df['position_value'] > 0]),
            'avg_position_size': round(total_invested / max(1, len(positions_df[positions_df['position_value'] > 0])), 2),
        }
        
        # 3. Allocations cibles vs actuelles
        allocations = self.rebalancer.calculate_target_allocations(positions_df, self.sizer)
        results['allocations'] = allocations.to_dict('records')
        
        # 4. Trades de rebalancing
        trades = self.rebalancer.generate_rebalance_trades(allocations, self.total_capital)
        results['rebalance_trades'] = trades
        
        # 5. Vérifier les limites de concentration
        concentration = self.rebalancer.check_concentration_limits(positions_df)
        results['concentration'] = concentration
        
        # 6. Signaux de sortie pour chaque position
        exit_signals = []
        for idx, row in positions_df.iterrows():
            if row.get('qty', 0) > 0:
                signal = self.risk_manager.check_exit_signals(row.to_dict())
                signal['ticker'] = row.get('ticker')
                exit_signals.append(signal)
        
        results['exit_signals'] = [s for s in exit_signals if s['action'] != 'HOLD']
        
        # 7. Recommandations prioritaires
        recommendations = self._generate_recommendations(results)
        results['recommendations'] = recommendations
        
        return results
    
    def _generate_recommendations(self, analysis):
        """Génère les recommandations prioritaires"""
        recommendations = []
        
        # 1. Exits urgents
        for signal in analysis.get('exit_signals', []):
            if signal['urgency'] == 'HIGH':
                recommendations.append({
                    'priority': 1,
                    'type': 'EXIT',
                    'ticker': signal['ticker'],
                    'action': signal['action'],
                    'reason': ', '.join(signal['signals']),
                })
        
        # 2. Concentration alerts
        for alert in analysis.get('concentration', {}).get('alerts', []):
            recommendations.append({
                'priority': 2,
                'type': 'CONCENTRATION',
                'ticker': alert.get('ticker', alert.get('sector', alert.get('country'))),
                'action': 'REDUCE',
                'reason': alert['action'],
            })
        
        # 3. Rebalancing
        for trade in analysis.get('rebalance_trades', [])[:5]:  # Top 5
            recommendations.append({
                'priority': 3,
                'type': 'REBALANCE',
                'ticker': trade['ticker'],
                'action': trade['type'],
                'amount': trade['amount_eur'],
                'reason': trade['reason'],
            })
        
        # 4. Cash management
        cash_pct = analysis.get('summary', {}).get('cash_pct', 0)
        if cash_pct > self.config['max_cash_pct']:
            recommendations.append({
                'priority': 2,
                'type': 'CASH',
                'action': 'DEPLOY',
                'reason': f"Cash trop élevé ({cash_pct:.1f}% > {self.config['max_cash_pct']}%)",
            })
        elif cash_pct < self.config['min_cash_pct']:
            recommendations.append({
                'priority': 2,
                'type': 'CASH',
                'action': 'RAISE',
                'reason': f"Cash trop faible ({cash_pct:.1f}% < {self.config['min_cash_pct']}%)",
            })
        
        # Trier par priorité
        recommendations.sort(key=lambda x: x['priority'])
        
        return recommendations
    
    def print_analysis(self, analysis):
        """Affiche l'analyse de manière lisible"""
        print("\n" + "=" * 70)
        print("   📊 ANALYSE DU PORTEFEUILLE - POSITION SIZING & REBALANCING")
        print("=" * 70)
        
        # Summary
        s = analysis['summary']
        print(f"\n💰 RÉSUMÉ")
        print(f"   Capital total: {self.total_capital:,.0f} €")
        print(f"   Investi: {s['total_invested']:,.0f} € ({100 - s['cash_pct']:.1f}%)")
        print(f"   Cash: {s['cash']:,.0f} € ({s['cash_pct']:.1f}%)")
        print(f"   Positions: {s['num_positions']}")
        print(f"   Taille moyenne: {s['avg_position_size']:,.0f} €")
        
        # Allocations
        print(f"\n📋 ALLOCATIONS (Top déviations)")
        allocations = sorted(analysis['allocations'], key=lambda x: abs(x['diff_pct']), reverse=True)
        for a in allocations[:7]:
            if a['action'] != 'OK':
                arrow = "↑" if a['action'] == 'INCREASE' else "↓"
                print(f"   {arrow} {a['ticker']:8} {a['current_pct']:5.1f}% → {a['target_pct']:5.1f}% ({a['diff_pct']:+.1f}%)")
        
        # Trades
        if analysis['rebalance_trades']:
            print(f"\n🔄 TRADES DE REBALANCING")
            for t in analysis['rebalance_trades'][:5]:
                emoji = "🟢" if t['type'] == 'BUY' else "🔴"
                print(f"   {emoji} {t['type']:4} {t['ticker']:8} {t['amount_eur']:>8,.0f} € | {t['reason']}")
        
        # Alerts
        if analysis['concentration']['alerts']:
            print(f"\n⚠️  ALERTES DE CONCENTRATION")
            for a in analysis['concentration']['alerts']:
                print(f"   • {a['type']}: {a.get('ticker', a.get('sector', a.get('country')))}")
                print(f"     {a['current_pct']:.1f}% > {a['limit_pct']:.1f}% - {a['action']}")
        
        # Exit signals
        if analysis['exit_signals']:
            print(f"\n🚨 SIGNAUX DE SORTIE")
            for s in analysis['exit_signals']:
                urgency_emoji = "🔴" if s['urgency'] == 'HIGH' else "🟡"
                print(f"   {urgency_emoji} {s['ticker']:8} {s['action']:15} | {', '.join(s['signals'])}")
        
        # Recommendations
        if analysis['recommendations']:
            print(f"\n🎯 RECOMMANDATIONS PRIORITAIRES")
            for i, r in enumerate(analysis['recommendations'][:5], 1):
                print(f"   {i}. [{r['type']}] {r.get('ticker', '')} - {r['action']}")
                print(f"      {r['reason']}")
        
        print("\n" + "=" * 70)


# ============================================================
# TESTS
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("TEST POSITION SIZING & REBALANCING")
    print("=" * 60)
    
    # Test Position Sizer
    print("\n--- Test Position Sizer ---")
    sizer = PositionSizer(total_capital=10000)
    
    test_cases = [
        {'score': 85, 'vol': 15, 'price': 100},
        {'score': 70, 'vol': 25, 'price': 50},
        {'score': 50, 'vol': 35, 'price': 200},
        {'score': 30, 'vol': 20, 'price': 30},
    ]
    
    for tc in test_cases:
        result = sizer.calculate_position_size(tc['score'], tc['vol'], tc['price'])
        print(f"Score {tc['score']}, Vol {tc['vol']}%: {result['final_allocation_pct']}% = {result['amount_eur']}€ ({result['shares']} actions)")
    
    # Test Risk Manager
    print("\n--- Test Risk Manager ---")
    rm = RiskManager()
    
    stop = rm.calculate_stop_loss(entry_price=100, atr=3.5)
    print(f"Stop-loss: {stop['stop_price']}€ (-{stop['stop_pct']}%)")
    
    tp_levels = rm.calculate_take_profit_levels(entry_price=100, target_price=140)
    print("Take-profit levels:")
    for level in tp_levels:
        print(f"  +{level['gain_pct']}%: {level['price']}€ → Vendre {level['sell_pct']}%")
    
    # Test avec DataFrame
    print("\n--- Test Portfolio Optimizer ---")
    
    test_portfolio = pd.DataFrame([
        {'ticker': 'MC', 'name': 'LVMH', 'price_eur': 600, 'qty': 2, 'score_total': 75, 'volatility': 22, 'pe_ttm': 25},
        {'ticker': 'TTE', 'name': 'Total', 'price_eur': 55, 'qty': 20, 'score_total': 85, 'volatility': 18, 'pe_ttm': 8},
        {'ticker': 'ALREW', 'name': 'Reworld', 'price_eur': 1.7, 'qty': 500, 'score_total': 70, 'volatility': 45, 'pe_ttm': 5},
    ])
    
    optimizer = PortfolioOptimizer(total_capital=5000)
    analysis = optimizer.analyze_portfolio(test_portfolio)
    optimizer.print_analysis(analysis)
    
    print("\n" + "=" * 60)

"""
MARKET DATA FETCHER & TECHNICAL ANALYZER
==========================================
Module pour récupérer les données de marché et calculer
les indicateurs techniques (Fibonacci, tendances, etc.)

Nécessite: pip install yfinance pandas numpy

Usage:
    from market_data import MarketDataFetcher, TechnicalAnalyzer
    
    fetcher = MarketDataFetcher()
    data = fetcher.get_stock_data('MC.PA', period='2y')
    
    analyzer = TechnicalAnalyzer(data)
    fib = analyzer.calculate_fibonacci_zones()
"""

import pandas as pd
import numpy as np
from datetime import datetime, timedelta
import warnings
warnings.filterwarnings('ignore')

# Mapping des tickers pour Yahoo Finance
TICKER_MAPPING = {
    # Actions françaises (Euronext Paris)
    'ALREW': 'ALREW.PA',
    'BEN': 'BEN.PA',
    'TTE': 'TTE.PA',
    'VK': 'VK.PA',
    'SW': 'SW.PA',
    'STF': 'STF.PA',
    'RI': 'RI.PA',
    'ALHOP': 'ALHOP.PA',
    'FGR': 'FGR.PA',
    'SK': 'SK.PA',
    'MC': 'MC.PA',
    'VIE': 'VIE.PA',
    'ARG': 'ARG.PA',
    'ALVAP': 'ALVAP.PA',
    'GFC': 'GFC.PA',
    'ICAD': 'ICAD.PA',
    'CARM': 'CARM.PA',
    'ELEC': 'ELEC.PA',
    'ALWEC': 'ALWEC.PA',
    # UK
    'RIO.L': 'RIO.L',
    'BA.L': 'BA.L',
    'IMB.L': 'IMB.L',
    # Suisse
    'ZURN.SW': 'ZURN.SW',
    'NEAG': 'NEAG.SW',
    # Belgique
    'SIP': 'SIP.BR',
    # Danemark
    'PNDORA': 'PNDORA.CO',
}


class MarketDataFetcher:
    """Récupère les données de marché via yfinance"""
    
    def __init__(self):
        self.cache = {}
        self._check_yfinance()
    
    def _check_yfinance(self):
        """Vérifie si yfinance est installé"""
        try:
            import yfinance as yf
            self.yf = yf
            self.available = True
        except ImportError:
            print("⚠️  yfinance non installé. Exécutez: pip install yfinance")
            self.available = False
    
    def get_yahoo_ticker(self, ticker):
        """Convertit un ticker local en ticker Yahoo Finance"""
        if ticker in TICKER_MAPPING:
            return TICKER_MAPPING[ticker]
        # Si le ticker contient déjà un suffixe, on le garde
        if '.' in ticker:
            return ticker
        # Par défaut, on ajoute .PA pour Paris
        return f"{ticker}.PA"
    
    def get_stock_data(self, ticker, period='2y', interval='1d'):
        """
        Récupère les données historiques d'une action
        
        Args:
            ticker: Code de l'action (ex: 'MC' ou 'MC.PA')
            period: Période ('1mo', '3mo', '6mo', '1y', '2y', '5y', 'max')
            interval: Intervalle ('1d', '1wk', '1mo')
        
        Returns:
            DataFrame avec OHLCV
        """
        if not self.available:
            return None
        
        yahoo_ticker = self.get_yahoo_ticker(ticker)
        cache_key = f"{yahoo_ticker}_{period}_{interval}"
        
        if cache_key in self.cache:
            return self.cache[cache_key]
        
        try:
            stock = self.yf.Ticker(yahoo_ticker)
            data = stock.history(period=period, interval=interval)
            
            if data.empty:
                print(f"⚠️  Pas de données pour {yahoo_ticker}")
                return None
            
            # Renommer les colonnes en minuscules
            data.columns = [c.lower() for c in data.columns]
            
            self.cache[cache_key] = data
            return data
        
        except Exception as e:
            print(f"❌ Erreur lors de la récupération de {yahoo_ticker}: {e}")
            return None
    
    def get_current_price(self, ticker):
        """Récupère le prix actuel"""
        data = self.get_stock_data(ticker, period='5d', interval='1d')
        if data is not None and len(data) > 0:
            return data['close'].iloc[-1]
        return None
    
    def get_52w_high_low(self, ticker):
        """Récupère le plus haut et plus bas 52 semaines"""
        data = self.get_stock_data(ticker, period='1y', interval='1d')
        if data is not None and len(data) > 0:
            return {
                'high_52w': data['high'].max(),
                'low_52w': data['low'].min(),
                'current': data['close'].iloc[-1],
            }
        return None
    
    def update_portfolio_prices(self, portfolio_df, ticker_col='ticker', price_col='price_eur'):
        """
        Met à jour les prix du portefeuille avec les données actuelles
        
        Args:
            portfolio_df: DataFrame du portefeuille
            ticker_col: Nom de la colonne contenant les tickers
            price_col: Nom de la colonne à mettre à jour
        
        Returns:
            DataFrame mis à jour
        """
        df = portfolio_df.copy()
        
        for idx, row in df.iterrows():
            ticker = row[ticker_col]
            if pd.isna(ticker):
                continue
            
            price = self.get_current_price(ticker)
            if price is not None:
                df.loc[idx, price_col] = price
                print(f"✅ {ticker}: {price:.2f}")
            else:
                print(f"⚠️  {ticker}: prix non disponible")
        
        return df


class AdvancedTechnicalAnalyzer:
    """Analyse technique avancée avec focus sur Fibonacci"""
    
    def __init__(self, price_data=None):
        """
        Args:
            price_data: DataFrame avec colonnes 'open', 'high', 'low', 'close', 'volume'
        """
        self.data = price_data
    
    def set_data(self, price_data):
        """Définit les données de prix"""
        self.data = price_data
    
    def calculate_fibonacci_zones(self, lookback_period=None):
        """
        Calcule les zones de Fibonacci basées sur le swing haut/bas
        
        Args:
            lookback_period: Nombre de jours pour calculer le swing (None = max disponible)
        
        Returns:
            dict avec les niveaux Fibonacci et la zone actuelle
        """
        if self.data is None or len(self.data) < 20:
            return None
        
        df = self.data.copy()
        
        if lookback_period:
            df = df.tail(lookback_period)
        
        swing_high = df['high'].max()
        swing_low = df['low'].min()
        current_price = df['close'].iloc[-1]
        
        # Date des extremums
        high_date = df['high'].idxmax()
        low_date = df['low'].idxmin()
        
        # Déterminer si on est en tendance haussière ou baissière
        is_uptrend = high_date > low_date
        
        range_size = swing_high - swing_low
        
        if range_size <= 0:
            return None
        
        # Niveaux de retracement (du haut vers le bas)
        fib_levels = {
            '0%': swing_high,
            '23.6%': swing_high - range_size * 0.236,
            '38.2%': swing_high - range_size * 0.382,
            '50%': swing_high - range_size * 0.5,
            '61.8%': swing_high - range_size * 0.618,
            '78.6%': swing_high - range_size * 0.786,
            '100%': swing_low,
        }
        
        # Extensions (au-delà du swing)
        extensions = {
            '-23.6%': swing_high + range_size * 0.236,
            '-38.2%': swing_high + range_size * 0.382,
            '123.6%': swing_low - range_size * 0.236,
            '138.2%': swing_low - range_size * 0.382,
            '161.8%': swing_low - range_size * 0.618,
        }
        
        # Calculer le retracement actuel
        retracement = (swing_high - current_price) / range_size
        
        # Déterminer la zone
        zone_info = self._determine_zone(retracement, is_uptrend)
        
        # Prochains niveaux de support/résistance
        supports = [v for k, v in fib_levels.items() if v < current_price]
        resistances = [v for k, v in fib_levels.items() if v > current_price]
        
        return {
            'swing_high': round(swing_high, 2),
            'swing_low': round(swing_low, 2),
            'high_date': high_date,
            'low_date': low_date,
            'is_uptrend': is_uptrend,
            'current_price': round(current_price, 2),
            'retracement_pct': round(retracement * 100, 1),
            'fib_levels': {k: round(v, 2) for k, v in fib_levels.items()},
            'extensions': {k: round(v, 2) for k, v in extensions.items()},
            'zone': zone_info['zone'],
            'zone_quality': zone_info['quality'],
            'zone_description': zone_info['description'],
            'in_golden_zone': zone_info['in_golden_zone'],
            'in_reload_zone': zone_info['in_reload_zone'],
            'next_support': round(max(supports), 2) if supports else None,
            'next_resistance': round(min(resistances), 2) if resistances else None,
            'distance_to_support_pct': round((current_price - max(supports)) / current_price * 100, 1) if supports else None,
            'distance_to_resistance_pct': round((min(resistances) - current_price) / current_price * 100, 1) if resistances else None,
        }
    
    def _determine_zone(self, retracement, is_uptrend):
        """Détermine la zone de prix actuelle"""
        
        if retracement < 0:
            return {
                'zone': 'NEW_HIGH',
                'quality': 30,
                'description': 'Au-dessus du dernier sommet - Attention aux achats',
                'in_golden_zone': False,
                'in_reload_zone': False,
            }
        elif retracement <= 0.236:
            return {
                'zone': 'MINOR_PULLBACK',
                'quality': 40,
                'description': 'Faible retracement - Attendre une meilleure entrée',
                'in_golden_zone': False,
                'in_reload_zone': False,
            }
        elif retracement <= 0.382:
            return {
                'zone': 'SHALLOW_PULLBACK',
                'quality': 55,
                'description': 'Retracement classique 38.2% - Zone neutre',
                'in_golden_zone': False,
                'in_reload_zone': False,
            }
        elif retracement <= 0.5:
            return {
                'zone': 'HALF_RETRACEMENT',
                'quality': 65,
                'description': 'Retracement 50% - Zone intéressante si tendance forte',
                'in_golden_zone': False,
                'in_reload_zone': True,
            }
        elif retracement <= 0.618:
            return {
                'zone': 'GOLDEN_RATIO',
                'quality': 85,
                'description': '⭐ Zone de rechargement 61.8% - Opportunité d\'achat',
                'in_golden_zone': True,
                'in_reload_zone': True,
            }
        elif retracement <= 0.786:
            return {
                'zone': 'DEEP_VALUE',
                'quality': 95,
                'description': '🎯 Zone de rechargement optimale 61.8-78.6% - Meilleure entrée',
                'in_golden_zone': True,
                'in_reload_zone': True,
            }
        elif retracement <= 1.0:
            return {
                'zone': 'EXTREME_DISCOUNT',
                'quality': 80,
                'description': 'Proche du dernier creux - Risqué mais fort potentiel',
                'in_golden_zone': False,
                'in_reload_zone': True,
            }
        else:
            return {
                'zone': 'NEW_LOW',
                'quality': 50,
                'description': 'Sous le dernier creux - Prudence (tendance baissière)',
                'in_golden_zone': False,
                'in_reload_zone': False,
            }
    
    def calculate_trend_analysis(self):
        """
        Analyse complète de la tendance
        
        Returns:
            dict avec score de tendance, direction, alignement des MAs
        """
        if self.data is None or len(self.data) < 200:
            return None
        
        df = self.data.copy()
        close = df['close']
        
        # Moyennes mobiles
        ma20 = close.rolling(20).mean()
        ma50 = close.rolling(50).mean()
        ma100 = close.rolling(100).mean()
        ma200 = close.rolling(200).mean()
        
        current = close.iloc[-1]
        
        # Calcul du score de tendance (-100 à +100)
        score = 0
        
        # Position vs MAs
        if current > ma20.iloc[-1]: score += 15
        else: score -= 15
        if current > ma50.iloc[-1]: score += 20
        else: score -= 20
        if current > ma100.iloc[-1]: score += 25
        else: score -= 25
        if current > ma200.iloc[-1]: score += 25
        else: score -= 25
        
        # Alignement des MAs
        if ma20.iloc[-1] > ma50.iloc[-1] > ma100.iloc[-1] > ma200.iloc[-1]:
            score += 15
            alignment = 'PERFECT_BULLISH'
        elif ma20.iloc[-1] < ma50.iloc[-1] < ma100.iloc[-1] < ma200.iloc[-1]:
            score -= 15
            alignment = 'PERFECT_BEARISH'
        elif ma20.iloc[-1] > ma50.iloc[-1]:
            score += 5
            alignment = 'SHORT_TERM_BULLISH'
        elif ma20.iloc[-1] < ma50.iloc[-1]:
            score -= 5
            alignment = 'SHORT_TERM_BEARISH'
        else:
            alignment = 'MIXED'
        
        # Pente des MAs (momentum)
        ma50_slope = (ma50.iloc[-1] - ma50.iloc[-20]) / ma50.iloc[-20] * 100
        ma200_slope = (ma200.iloc[-1] - ma200.iloc[-50]) / ma200.iloc[-50] * 100
        
        # Déterminer la tendance
        if score >= 70:
            trend = 'STRONG_UPTREND'
        elif score >= 30:
            trend = 'UPTREND'
        elif score >= -30:
            trend = 'SIDEWAYS'
        elif score >= -70:
            trend = 'DOWNTREND'
        else:
            trend = 'STRONG_DOWNTREND'
        
        return {
            'trend_score': score,
            'trend': trend,
            'ma_alignment': alignment,
            'current_price': round(current, 2),
            'ma20': round(ma20.iloc[-1], 2),
            'ma50': round(ma50.iloc[-1], 2),
            'ma100': round(ma100.iloc[-1], 2),
            'ma200': round(ma200.iloc[-1], 2),
            'price_vs_ma50_pct': round((current / ma50.iloc[-1] - 1) * 100, 1),
            'price_vs_ma200_pct': round((current / ma200.iloc[-1] - 1) * 100, 1),
            'ma50_slope': round(ma50_slope, 2),
            'ma200_slope': round(ma200_slope, 2),
            'above_ma20': current > ma20.iloc[-1],
            'above_ma50': current > ma50.iloc[-1],
            'above_ma200': current > ma200.iloc[-1],
        }
    
    def calculate_momentum_indicators(self):
        """
        Calcule les indicateurs de momentum (RSI, MACD, etc.)
        
        Returns:
            dict avec RSI, MACD, signal, histogramme
        """
        if self.data is None or len(self.data) < 50:
            return None
        
        close = self.data['close']
        
        # RSI
        rsi = self._calculate_rsi(close, 14)
        
        # MACD
        macd, signal, histogram = self._calculate_macd(close)
        
        # Momentum 1M, 3M, 6M, 12M
        momentum = {}
        for period, label in [(21, '1m'), (63, '3m'), (126, '6m'), (252, '12m')]:
            if len(close) > period:
                momentum[label] = round((close.iloc[-1] / close.iloc[-period] - 1) * 100, 1)
            else:
                momentum[label] = None
        
        # Signaux
        rsi_signal = 'OVERSOLD' if rsi < 30 else 'OVERBOUGHT' if rsi > 70 else 'NEUTRAL'
        macd_signal = 'BULLISH' if histogram > 0 else 'BEARISH'
        
        return {
            'rsi': round(rsi, 1),
            'rsi_signal': rsi_signal,
            'macd': round(macd, 3),
            'macd_signal_line': round(signal, 3),
            'macd_histogram': round(histogram, 3),
            'macd_direction': macd_signal,
            'momentum_1m': momentum.get('1m'),
            'momentum_3m': momentum.get('3m'),
            'momentum_6m': momentum.get('6m'),
            'momentum_12m': momentum.get('12m'),
        }
    
    def _calculate_rsi(self, prices, period=14):
        """Calcule le RSI"""
        delta = prices.diff()
        gain = (delta.where(delta > 0, 0)).rolling(window=period).mean()
        loss = (-delta.where(delta < 0, 0)).rolling(window=period).mean()
        rs = gain / loss
        rsi = 100 - (100 / (1 + rs))
        return rsi.iloc[-1]
    
    def _calculate_macd(self, prices, fast=12, slow=26, signal=9):
        """Calcule le MACD"""
        ema_fast = prices.ewm(span=fast, adjust=False).mean()
        ema_slow = prices.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        return macd_line.iloc[-1], signal_line.iloc[-1], histogram.iloc[-1]
    
    def calculate_volatility_analysis(self):
        """
        Analyse de la volatilité
        
        Returns:
            dict avec volatilité historique, ATR, Bollinger
        """
        if self.data is None or len(self.data) < 30:
            return None
        
        df = self.data.copy()
        close = df['close']
        high = df['high']
        low = df['low']
        
        # Volatilité historique (annualisée)
        returns = close.pct_change()
        vol_20d = returns.rolling(20).std().iloc[-1] * np.sqrt(252) * 100
        vol_60d = returns.rolling(60).std().iloc[-1] * np.sqrt(252) * 100 if len(returns) >= 60 else None
        
        # ATR (Average True Range)
        tr1 = high - low
        tr2 = abs(high - close.shift(1))
        tr3 = abs(low - close.shift(1))
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        atr_pct = (atr / close.iloc[-1]) * 100
        
        # Bollinger Bands
        ma20 = close.rolling(20).mean()
        std20 = close.rolling(20).std()
        upper_band = ma20 + 2 * std20
        lower_band = ma20 - 2 * std20
        
        current = close.iloc[-1]
        bb_position = (current - lower_band.iloc[-1]) / (upper_band.iloc[-1] - lower_band.iloc[-1])
        
        return {
            'volatility_20d': round(vol_20d, 1),
            'volatility_60d': round(vol_60d, 1) if vol_60d else None,
            'atr': round(atr, 2),
            'atr_pct': round(atr_pct, 2),
            'bollinger_upper': round(upper_band.iloc[-1], 2),
            'bollinger_middle': round(ma20.iloc[-1], 2),
            'bollinger_lower': round(lower_band.iloc[-1], 2),
            'bollinger_position': round(bb_position * 100, 1),  # 0% = lower band, 100% = upper band
            'is_volatile': vol_20d > 30,
            'near_upper_band': bb_position > 0.8,
            'near_lower_band': bb_position < 0.2,
        }
    
    def get_full_analysis(self):
        """
        Retourne une analyse technique complète
        
        Returns:
            dict avec toutes les analyses
        """
        return {
            'fibonacci': self.calculate_fibonacci_zones(),
            'trend': self.calculate_trend_analysis(),
            'momentum': self.calculate_momentum_indicators(),
            'volatility': self.calculate_volatility_analysis(),
        }


def analyze_stock(ticker, period='2y'):
    """
    Fonction utilitaire pour analyser rapidement une action
    
    Args:
        ticker: Code de l'action
        period: Période d'analyse
    
    Returns:
        dict avec l'analyse complète
    """
    fetcher = MarketDataFetcher()
    data = fetcher.get_stock_data(ticker, period=period)
    
    if data is None:
        return None
    
    analyzer = AdvancedTechnicalAnalyzer(data)
    analysis = analyzer.get_full_analysis()
    
    return {
        'ticker': ticker,
        'analysis_date': datetime.now().strftime('%Y-%m-%d'),
        'data_points': len(data),
        **analysis
    }


# ============================================================
# MAIN - Tests et démonstration
# ============================================================

if __name__ == "__main__":
    print("=" * 60)
    print("MARKET DATA FETCHER & TECHNICAL ANALYZER")
    print("=" * 60)
    
    # Test avec une action
    test_ticker = 'MC'  # LVMH
    
    print(f"\n📊 Analyse de {test_ticker}...")
    
    result = analyze_stock(test_ticker)
    
    if result:
        print(f"\n✅ Analyse réussie ({result['data_points']} points de données)")
        
        if result['fibonacci']:
            fib = result['fibonacci']
            print(f"\n📈 FIBONACCI:")
            print(f"   Swing High: {fib['swing_high']} ({fib['high_date'].strftime('%Y-%m-%d')})")
            print(f"   Swing Low: {fib['swing_low']} ({fib['low_date'].strftime('%Y-%m-%d')})")
            print(f"   Prix actuel: {fib['current_price']}")
            print(f"   Retracement: {fib['retracement_pct']}%")
            print(f"   Zone: {fib['zone']} (Qualité: {fib['zone_quality']}/100)")
            print(f"   Description: {fib['zone_description']}")
            print(f"   Dans zone de rechargement: {'✅' if fib['in_reload_zone'] else '❌'}")
        
        if result['trend']:
            trend = result['trend']
            print(f"\n📊 TENDANCE:")
            print(f"   Score: {trend['trend_score']}/100")
            print(f"   Tendance: {trend['trend']}")
            print(f"   Alignement MAs: {trend['ma_alignment']}")
            print(f"   Prix vs MA50: {trend['price_vs_ma50_pct']:+.1f}%")
            print(f"   Prix vs MA200: {trend['price_vs_ma200_pct']:+.1f}%")
        
        if result['momentum']:
            mom = result['momentum']
            print(f"\n⚡ MOMENTUM:")
            print(f"   RSI: {mom['rsi']} ({mom['rsi_signal']})")
            print(f"   MACD: {mom['macd_direction']}")
            print(f"   Perf 1M: {mom['momentum_1m']:+.1f}%" if mom['momentum_1m'] else "   Perf 1M: N/A")
            print(f"   Perf 12M: {mom['momentum_12m']:+.1f}%" if mom['momentum_12m'] else "   Perf 12M: N/A")
    else:
        print("❌ Échec de l'analyse")
    
    print("\n" + "=" * 60)

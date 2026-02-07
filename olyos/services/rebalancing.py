"""
OLYOS CAPITAL - Portfolio Rebalancing Service
==============================================
Detect portfolio imbalances and propose rebalancing actions.

Rules:
- Position > max_weight% → TRIM
- Position < min_weight% → Consider exit
- Sector > 30% → Overexposure warning
- Higgons score < 4/10 → Deterioration warning
- PE > 17 → Sell signal
"""

import os
import json
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass, field, asdict
from enum import Enum

from olyos.logger import get_logger

log = get_logger('rebalancing')


# ============================================================================
# DATA CLASSES
# ============================================================================

class ImbalanceType(str, Enum):
    """Types of portfolio imbalances"""
    OVERWEIGHT = "OVERWEIGHT"           # Position too heavy
    UNDERWEIGHT = "UNDERWEIGHT"         # Position too light
    SECTOR_OVEREXPOSURE = "SECTOR_OVEREXPOSURE"  # Sector > 30%
    SCORE_DETERIORATION = "SCORE_DETERIORATION"  # Higgons score dropped
    PE_HIGH = "PE_HIGH"                 # PE above threshold
    VERDICT_CHANGED = "VERDICT_CHANGED" # Verdict changed to negative


class ActionType(str, Enum):
    """Suggested action types"""
    TRIM = "TRIM"           # Reduce position
    ADD = "ADD"             # Increase position
    SELL = "SELL"           # Full exit
    HOLD = "HOLD"           # No action needed
    REVIEW = "REVIEW"       # Manual review needed


@dataclass
class RebalanceConfig:
    """Rebalancing thresholds configuration"""
    max_position_weight: float = 10.0      # Max 10% per position
    min_position_weight: float = 2.0       # Min 2% per position (consider exit)
    max_sector_weight: float = 30.0        # Max 30% per sector
    target_positions: int = 15             # Target number of positions
    min_higgons_score: int = 4             # Minimum acceptable Higgons score
    max_pe: float = 17.0                   # Max PE before sell signal
    deviation_warning: float = 1.5         # Orange warning threshold (%)
    deviation_critical: float = 3.0        # Red critical threshold (%)
    equal_weight: bool = False             # Use equal weighting vs score-based


@dataclass
class Imbalance:
    """Detected portfolio imbalance"""
    ticker: str
    name: str
    imbalance_type: ImbalanceType
    current_value: float        # Current weight, PE, score, etc.
    threshold_value: float      # Threshold that was breached
    severity: str               # 'warning' or 'critical'
    message: str
    suggested_action: ActionType

    def to_dict(self) -> Dict:
        d = asdict(self)
        d['imbalance_type'] = self.imbalance_type.value
        d['suggested_action'] = self.suggested_action.value
        return d


@dataclass
class TradeProposal:
    """Proposed trade for rebalancing"""
    ticker: str
    name: str
    action: ActionType
    current_weight: float
    target_weight: float
    deviation: float            # target - current
    current_value: float        # Current position value in EUR
    trade_value: float          # Amount to buy (positive) or sell (negative)
    shares_to_trade: float      # Number of shares (estimated)
    current_price: float
    reason: str

    def to_dict(self) -> Dict:
        d = asdict(self)
        d['action'] = self.action.value
        return d


@dataclass
class RebalanceResult:
    """Complete rebalancing analysis result"""
    timestamp: str
    total_portfolio_value: float
    num_positions: int
    imbalances: List[Imbalance] = field(default_factory=list)
    trade_proposals: List[TradeProposal] = field(default_factory=list)
    total_buy_value: float = 0
    total_sell_value: float = 0
    net_trade_value: float = 0
    is_balanced: bool = True

    def to_dict(self) -> Dict:
        return {
            'timestamp': self.timestamp,
            'total_portfolio_value': self.total_portfolio_value,
            'num_positions': self.num_positions,
            'imbalances': [i.to_dict() for i in self.imbalances],
            'trade_proposals': [t.to_dict() for t in self.trade_proposals],
            'total_buy_value': self.total_buy_value,
            'total_sell_value': self.total_sell_value,
            'net_trade_value': self.net_trade_value,
            'is_balanced': self.is_balanced
        }


# ============================================================================
# REBALANCING SERVICE
# ============================================================================

class RebalancingService:
    """Service for portfolio rebalancing analysis"""

    def __init__(self, config: RebalanceConfig = None):
        self.config = config or RebalanceConfig()

    def check_portfolio_balance(
        self,
        positions: List[Dict],
        total_value: float = None
    ) -> List[Imbalance]:
        """
        Check portfolio for imbalances.

        Args:
            positions: List of position dicts with keys:
                - ticker, name, weight, value, price, pe, roe, gearing,
                - higgons_score, sector, verdict
            total_value: Total portfolio value (calculated if not provided)

        Returns:
            List of detected imbalances
        """
        if not positions:
            return []

        # Calculate total value if not provided
        if total_value is None:
            total_value = sum(p.get('value', 0) or 0 for p in positions)

        if total_value <= 0:
            return []

        imbalances = []
        sector_weights = {}

        for pos in positions:
            ticker = pos.get('ticker', '')
            name = pos.get('name', ticker)
            weight = pos.get('weight', 0) or 0
            value = pos.get('value', 0) or 0
            pe = pos.get('pe') or pos.get('pe_ttm')
            higgons_score = pos.get('higgons_score', pos.get('score_higgins', 5))
            sector = pos.get('sector', 'Other')
            verdict = pos.get('verdict', '')

            # Recalculate weight if needed
            if weight == 0 and value > 0:
                weight = (value / total_value) * 100

            # Track sector weights
            if sector:
                sector_weights[sector] = sector_weights.get(sector, 0) + weight

            # Check position weight - OVERWEIGHT
            if weight > self.config.max_position_weight:
                severity = 'critical' if weight > self.config.max_position_weight + self.config.deviation_critical else 'warning'
                imbalances.append(Imbalance(
                    ticker=ticker,
                    name=name,
                    imbalance_type=ImbalanceType.OVERWEIGHT,
                    current_value=round(weight, 1),
                    threshold_value=self.config.max_position_weight,
                    severity=severity,
                    message=f"Position {ticker} surpondérée: {weight:.1f}% (max {self.config.max_position_weight}%)",
                    suggested_action=ActionType.TRIM
                ))

            # Check position weight - UNDERWEIGHT
            if 0 < weight < self.config.min_position_weight and value > 0:
                imbalances.append(Imbalance(
                    ticker=ticker,
                    name=name,
                    imbalance_type=ImbalanceType.UNDERWEIGHT,
                    current_value=round(weight, 1),
                    threshold_value=self.config.min_position_weight,
                    severity='warning',
                    message=f"Position {ticker} trop légère: {weight:.1f}% (min {self.config.min_position_weight}%)",
                    suggested_action=ActionType.REVIEW
                ))

            # Check Higgons score deterioration
            if higgons_score is not None and higgons_score < self.config.min_higgons_score:
                severity = 'critical' if higgons_score <= 2 else 'warning'
                imbalances.append(Imbalance(
                    ticker=ticker,
                    name=name,
                    imbalance_type=ImbalanceType.SCORE_DETERIORATION,
                    current_value=higgons_score,
                    threshold_value=self.config.min_higgons_score,
                    severity=severity,
                    message=f"Score Higgons dégradé: {higgons_score}/10 (min {self.config.min_higgons_score})",
                    suggested_action=ActionType.REVIEW if higgons_score >= 3 else ActionType.SELL
                ))

            # Check PE too high
            if pe is not None and pe > self.config.max_pe:
                severity = 'critical' if pe > self.config.max_pe * 1.5 else 'warning'
                imbalances.append(Imbalance(
                    ticker=ticker,
                    name=name,
                    imbalance_type=ImbalanceType.PE_HIGH,
                    current_value=round(pe, 1),
                    threshold_value=self.config.max_pe,
                    severity=severity,
                    message=f"PE élevé: {pe:.1f} (max {self.config.max_pe})",
                    suggested_action=ActionType.TRIM if pe < 25 else ActionType.SELL
                ))

            # Check verdict changed to negative
            if verdict and verdict.lower() in ['ecarter', 'vendre', 'sell', 'avoid']:
                imbalances.append(Imbalance(
                    ticker=ticker,
                    name=name,
                    imbalance_type=ImbalanceType.VERDICT_CHANGED,
                    current_value=0,
                    threshold_value=0,
                    severity='critical',
                    message=f"Verdict changé en '{verdict}'",
                    suggested_action=ActionType.SELL
                ))

        # Check sector overexposure
        for sector, weight in sector_weights.items():
            if weight > self.config.max_sector_weight:
                severity = 'critical' if weight > self.config.max_sector_weight + 10 else 'warning'
                imbalances.append(Imbalance(
                    ticker=sector,
                    name=f"Secteur {sector}",
                    imbalance_type=ImbalanceType.SECTOR_OVEREXPOSURE,
                    current_value=round(weight, 1),
                    threshold_value=self.config.max_sector_weight,
                    severity=severity,
                    message=f"Secteur {sector} surexposé: {weight:.1f}% (max {self.config.max_sector_weight}%)",
                    suggested_action=ActionType.TRIM
                ))

        # Sort by severity (critical first) then by type
        imbalances.sort(key=lambda x: (0 if x.severity == 'critical' else 1, x.imbalance_type.value))

        return imbalances

    def calculate_target_weights(
        self,
        positions: List[Dict],
        method: str = 'equal'
    ) -> Dict[str, float]:
        """
        Calculate target weights for each position.

        Args:
            positions: List of position dicts
            method: 'equal' for equal weighting, 'score' for score-based

        Returns:
            Dict mapping ticker -> target weight %
        """
        if not positions:
            return {}

        n = len(positions)
        targets = {}

        if method == 'equal':
            # Equal weighting, capped at max_position_weight
            target = min(100.0 / n, self.config.max_position_weight)
            for pos in positions:
                targets[pos.get('ticker', '')] = target

        elif method == 'score':
            # Weight by Higgons score
            total_score = sum(
                max(1, pos.get('higgons_score', pos.get('score_higgins', 5)) or 5)
                for pos in positions
            )

            for pos in positions:
                ticker = pos.get('ticker', '')
                score = max(1, pos.get('higgons_score', pos.get('score_higgins', 5)) or 5)
                raw_weight = (score / total_score) * 100
                # Cap at max weight
                targets[ticker] = min(raw_weight, self.config.max_position_weight)

        elif method == 'conviction':
            # Higher weight for high-conviction (high score + low PE)
            scores = []
            for pos in positions:
                higgons = pos.get('higgons_score', pos.get('score_higgins', 5)) or 5
                pe = pos.get('pe') or pos.get('pe_ttm') or 15
                # Conviction = score / PE ratio (higher is better)
                conviction = higgons / max(1, min(pe, 30))
                scores.append((pos.get('ticker', ''), conviction))

            total_conviction = sum(s[1] for s in scores)
            for ticker, conviction in scores:
                raw_weight = (conviction / total_conviction) * 100
                targets[ticker] = min(raw_weight, self.config.max_position_weight)

        return targets

    def propose_rebalancing(
        self,
        positions: List[Dict],
        target_weights: Dict[str, float] = None,
        total_value: float = None
    ) -> List[TradeProposal]:
        """
        Propose trades to rebalance the portfolio.

        Args:
            positions: Current positions
            target_weights: Target weight for each ticker
            total_value: Total portfolio value

        Returns:
            List of TradeProposal objects
        """
        if not positions:
            return []

        # Calculate total value if not provided
        if total_value is None:
            total_value = sum(p.get('value', 0) or 0 for p in positions)

        if total_value <= 0:
            return []

        # Calculate target weights if not provided
        if target_weights is None:
            target_weights = self.calculate_target_weights(positions, 'equal')

        proposals = []

        for pos in positions:
            ticker = pos.get('ticker', '')
            name = pos.get('name', ticker)
            value = pos.get('value', 0) or 0
            price = pos.get('price', pos.get('price_eur', 0)) or 0

            current_weight = (value / total_value * 100) if total_value > 0 else 0
            target_weight = target_weights.get(ticker, current_weight)
            deviation = target_weight - current_weight

            # Skip if deviation is small
            if abs(deviation) < 0.5:
                continue

            # Calculate trade value
            target_value = (target_weight / 100) * total_value
            trade_value = target_value - value

            # Estimate shares to trade
            shares_to_trade = (trade_value / price) if price > 0 else 0

            # Determine action
            if deviation > self.config.deviation_critical:
                action = ActionType.ADD
                reason = f"Sous-pondéré de {abs(deviation):.1f}%"
            elif deviation < -self.config.deviation_critical:
                action = ActionType.TRIM
                reason = f"Surpondéré de {abs(deviation):.1f}%"
            elif deviation > self.config.deviation_warning:
                action = ActionType.ADD
                reason = f"Légèrement sous-pondéré"
            elif deviation < -self.config.deviation_warning:
                action = ActionType.TRIM
                reason = f"Légèrement surpondéré"
            else:
                action = ActionType.HOLD
                reason = "Dans la cible"

            if action != ActionType.HOLD:
                proposals.append(TradeProposal(
                    ticker=ticker,
                    name=name,
                    action=action,
                    current_weight=round(current_weight, 2),
                    target_weight=round(target_weight, 2),
                    deviation=round(deviation, 2),
                    current_value=round(value, 0),
                    trade_value=round(trade_value, 0),
                    shares_to_trade=round(shares_to_trade, 2),
                    current_price=round(price, 2),
                    reason=reason
                ))

        # Sort by absolute deviation (largest first)
        proposals.sort(key=lambda x: abs(x.deviation), reverse=True)

        return proposals

    def analyze_portfolio(
        self,
        positions: List[Dict],
        total_value: float = None
    ) -> RebalanceResult:
        """
        Complete portfolio rebalancing analysis.

        Returns:
            RebalanceResult with imbalances and trade proposals
        """
        if total_value is None:
            total_value = sum(p.get('value', 0) or 0 for p in positions)

        # Check for imbalances
        imbalances = self.check_portfolio_balance(positions, total_value)

        # Calculate target weights and propose trades
        target_weights = self.calculate_target_weights(positions, 'equal')
        proposals = self.propose_rebalancing(positions, target_weights, total_value)

        # Calculate totals
        total_buy = sum(t.trade_value for t in proposals if t.trade_value > 0)
        total_sell = sum(abs(t.trade_value) for t in proposals if t.trade_value < 0)

        result = RebalanceResult(
            timestamp=datetime.now().isoformat(),
            total_portfolio_value=round(total_value, 0),
            num_positions=len(positions),
            imbalances=imbalances,
            trade_proposals=proposals,
            total_buy_value=round(total_buy, 0),
            total_sell_value=round(total_sell, 0),
            net_trade_value=round(total_buy - total_sell, 0),
            is_balanced=len(imbalances) == 0 and len(proposals) == 0
        )

        return result

    def simulate_trades(
        self,
        positions: List[Dict],
        proposals: List[TradeProposal]
    ) -> Dict:
        """
        Simulate the impact of proposed trades.

        Returns:
            Dict with before/after comparison
        """
        # Current state
        current_weights = {p['ticker']: p.get('weight', 0) for p in positions}
        current_sectors = {}
        for p in positions:
            sector = p.get('sector', 'Other')
            current_sectors[sector] = current_sectors.get(sector, 0) + p.get('weight', 0)

        # After state (simulated)
        after_weights = current_weights.copy()
        for proposal in proposals:
            after_weights[proposal.ticker] = proposal.target_weight

        # Recalculate sector weights
        after_sectors = {}
        for p in positions:
            ticker = p['ticker']
            sector = p.get('sector', 'Other')
            after_sectors[sector] = after_sectors.get(sector, 0) + after_weights.get(ticker, 0)

        return {
            'before': {
                'weights': current_weights,
                'sectors': current_sectors,
                'max_weight': max(current_weights.values()) if current_weights else 0,
                'min_weight': min(v for v in current_weights.values() if v > 0) if current_weights else 0,
            },
            'after': {
                'weights': after_weights,
                'sectors': after_sectors,
                'max_weight': max(after_weights.values()) if after_weights else 0,
                'min_weight': min(v for v in after_weights.values() if v > 0) if after_weights else 0,
            },
            'trades_count': len(proposals),
            'improvement': {
                'max_weight_reduced': (
                    max(current_weights.values()) - max(after_weights.values())
                    if current_weights and after_weights else 0
                ),
                'balance_improved': True  # Simplified
            }
        }


# ============================================================================
# FACTORY FUNCTION
# ============================================================================

def create_rebalancing_service(config: RebalanceConfig = None) -> RebalancingService:
    """Factory function to create RebalancingService"""
    return RebalancingService(config=config)

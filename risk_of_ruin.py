"""
Risk of Ruin Calculation.

Calculates the probability of losing entire account.
Essential for responsible trading size management.

Formula uses Monte Carlo simulation:
- Simulate trading N times with your win rate and avg win/loss
- Count how many simulations result in account blowup
- Calculate probability

Example:
    - Win rate: 55%, Avg win: +2%, Avg loss: -2%
    - Probability of ruin over 100 trades: 15%
    - Probability of ruin over 200 trades: 35%

CRITICAL: If ruin probability > 20%, don't trade. If > 50%, definitely don't.
"""

import numpy as np
from dataclasses import dataclass
import logging

logger = logging.getLogger(__name__)


@dataclass
class RuinAnalysis:
    """Results of risk of ruin calculation."""
    probability_of_ruin: float  # 0.0 to 1.0
    trades_until_safe: int  # Trades until ruin probability < 1%
    expected_time_to_ruin_days: float  # Average days until ruin
    critical_drawdown: float  # Max drawdown that causes ruin
    required_win_rate: float  # Min win rate to avoid ruin at 1:1 reward/risk
    
    def __str__(self) -> str:
        lines = [
            "\n" + "=" * 70,
            "💀 RISK OF RUIN ANALYSIS",
            "=" * 70,
            f"Probability of blowing up account: {self.probability_of_ruin:.1%}",
            f"Trades until safe (<1% ruin): {self.trades_until_safe:,}",
            f"Expected days until ruin: {self.expected_time_to_ruin_days:.0f}",
            f"Critical drawdown level: {self.critical_drawdown:.1%}",
            f"Minimum required win rate: {self.required_win_rate:.1%}",
            "=" * 70,
        ]
        return "\n".join(lines)
    
    def summary(self) -> str:
        """Get safe/unsafe summary."""
        if self.probability_of_ruin > 0.20:
            return "🔴 UNSAFE - Do NOT trade"
        elif self.probability_of_ruin > 0.10:
            return "🟡 RISKY - Only with caution"
        elif self.probability_of_ruin > 0.05:
            return "🟢 MODERATE - Acceptable risk"
        else:
            return "✅ SAFE - Low ruin probability"


class RiskOfRuinCalculator:
    """Calculate probability of account blowup."""
    
    @staticmethod
    def calculate(
        win_rate: float,
        avg_win_pct: float,
        avg_loss_pct: float,
        risk_per_trade: float = 0.02,
        starting_capital: float = 10000.0,
        blowup_threshold: float = 0.01,  # Stop when account at 1% of starting
        num_simulations: int = 10000,
    ) -> RuinAnalysis:
        """
        Calculate risk of ruin using Monte Carlo simulation.
        
        Args:
            win_rate: Historical win rate (0.0-1.0)
            avg_win_pct: Average win size (% of capital)
            avg_loss_pct: Average loss size (% of capital)
            risk_per_trade: Risk per trade (2% = 0.02) - informational
            starting_capital: Starting account size
            blowup_threshold: Account value threshold before "blowup" (1%)
            num_simulations: Monte Carlo simulations
        
        Returns:
            RuinAnalysis with probabilities
        """
        # Sanity checks
        if win_rate < 0.3:
            logger.warning(f"⚠️ Win rate {win_rate:.1%} is very low (typically need >40%)")
        
        if win_rate <= 0.5 and (avg_loss_pct >= avg_win_pct):
            logger.critical(
                f"❌ UNPROFITABLE: {win_rate:.1%} win rate with losses >= wins. "
                f"This strategy will blow up."
            )
            return RuinAnalysis(
                probability_of_ruin=1.0,
                trades_until_safe=0,
                expected_time_to_ruin_days=0,
                critical_drawdown=1.0,
                required_win_rate=0.5 + avg_loss_pct / (avg_win_pct + avg_loss_pct),
            )
        
        # ========== Monte Carlo Simulation ==========
        ruined_count = 0
        max_trades_before_ruin = []
        
        for sim in range(num_simulations):
            capital = starting_capital
            trades = 0
            
            # Simulate trading until ruin or 1000 trades
            while capital > starting_capital * blowup_threshold and trades < 1000:
                # Flip coin: win or loss?
                if np.random.random() < win_rate:
                    # Win: capital increases
                    capital *= (1 + avg_win_pct)
                else:
                    # Loss: capital decreases
                    capital *= max(0.0, 1 - avg_loss_pct)
                
                trades += 1
            
            # Did account blow up?
            if capital <= starting_capital * blowup_threshold:
                ruined_count += 1
                max_trades_before_ruin.append(trades)
        
        # ========== Calculate Results ==========
        probability_of_ruin = ruined_count / num_simulations
        
        # Trades until probability drops below 1%
        trades_until_safe = 50  # Default fallback
        for n in range(1, 5000):
            p = RiskOfRuinCalculator._ruin_probability_kelly(
                win_rate, avg_win_pct, avg_loss_pct, n
            )
            if p < 0.01:
                trades_until_safe = n
                break
        
        # Expected time to ruin
        expected_time_to_ruin = (
            (np.mean(max_trades_before_ruin) if max_trades_before_ruin else 1000) / 250
        )  # Trading days per year
        
        # Critical drawdown (1% of starting capital)
        critical_dd = 1 - blowup_threshold
        
        # Required win rate (for breakeven with equal risk/reward: 1:1)
        # At breakeven: win_rate * win = (1-win_rate) * loss
        # win_rate = loss / (win + loss)
        required_wr = avg_loss_pct / (avg_win_pct + avg_loss_pct) if (avg_win_pct + avg_loss_pct) > 0 else 0.5
        
        return RuinAnalysis(
            probability_of_ruin=probability_of_ruin,
            trades_until_safe=trades_until_safe,
            expected_time_to_ruin_days=expected_time_to_ruin,
            critical_drawdown=critical_dd,
            required_win_rate=required_wr,
        )
    
    @staticmethod
    def _ruin_probability_kelly(
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        num_trades: int,
    ) -> float:
        """
        Calculate ruin probability using Kelly Criterion.
        
        More accurate for predicting probability over many trades.
        """
        if avg_loss <= 0 or avg_win <= 0 or win_rate <= 0:
            return 1.0  # Can't win
        
        if win_rate > 0.5:
            # You have edge
            win_pct = win_rate
            loss_pct = 1 - win_rate
            ratio = avg_win / avg_loss
            
            # Kelly fraction
            kelly_f = (win_pct * ratio - loss_pct) / ratio
            
            if kelly_f <= 0:
                return 1.0  # Can't profitably trade (even winning strategy)
            
            # Ruin probability ≈ (loss_pct/win_pct) ^ (f * num_trades)
            probability = ((loss_pct / win_pct) ** (kelly_f * num_trades)) if win_pct > 0 else 1.0
        else:
            # You're losing
            probability = 1.0
        
        return min(max(probability, 0.0), 1.0)


def check_strategy_safety(
    win_rate: float,
    avg_win: float,
    avg_loss: float,
    max_drawdown: float = None,
    verbose: bool = True,
) -> bool:
    """
    Safety check before trading strategy.
    
    Args:
        win_rate: Historical win rate (0-1)
        avg_win: Average win ($)
        avg_loss: Average loss ($) - should be positive number
        max_drawdown: Max allowed drawdown (None = don't check)
        verbose: Print analysis
    
    Returns:
        True if safe to trade, False if too risky
    """
    # Convert to percentages
    avg_win_pct = avg_win / 10000.0  # Assume 10k account
    avg_loss_pct = avg_loss / 10000.0
    
    analysis = RiskOfRuinCalculator.calculate(
        win_rate=win_rate,
        avg_win_pct=avg_win_pct,
        avg_loss_pct=avg_loss_pct,
        starting_capital=10000.0,
    )
    
    if verbose:
        print(analysis)
        print(f"\nStatus: {analysis.summary()}")
    
    # ========== Safety Thresholds ==========
    
    # 1. Ruin probability check
    if analysis.probability_of_ruin > 0.20:
        logger.error(f"❌ Ruin probability {analysis.probability_of_ruin:.1%} too high (>20%)")
        return False
    
    # 2. Time to ruin check
    if analysis.expected_time_to_ruin_days < 180 and win_rate > 0.45:
        logger.warning(f"⚠️ Expected ruin in {analysis.expected_time_to_ruin_days:.0f} days (<6 months)")
    
    # 3. Win rate check
    if win_rate < 0.40:
        logger.warning(f"⚠️ Win rate {win_rate:.1%} is low (typically want >45%)")
    
    # 4. Drawdown check
    if max_drawdown and max_drawdown > 0.25:
        logger.warning(f"⚠️ Max drawdown {max_drawdown:.1%} is high (want <20%)")
    
    logger.info("✅ Strategy passes safety checks")
    return True


if __name__ == "__main__":
    # Example usage
    print("\n" + "=" * 70)
    print("EXAMPLE: Strategy with 55% win rate")
    print("=" * 70)
    
    # Scenario 1: Good strategy
    analysis1 = RiskOfRuinCalculator.calculate(
        win_rate=0.55,
        avg_win_pct=0.02,  # +2% average win
        avg_loss_pct=0.02,  # -2% average loss
        num_simulations=10000,
    )
    print(analysis1)
    print(f"Status: {analysis1.summary()}")
    
    print("\n" + "=" * 70)
    print("EXAMPLE: Strategy with 50% win rate (breakeven)")
    print("=" * 70)
    
    # Scenario 2: Breakeven strategy (will lose on costs)
    analysis2 = RiskOfRuinCalculator.calculate(
        win_rate=0.50,
        avg_win_pct=0.02,
        avg_loss_pct=0.02,
        num_simulations=10000,
    )
    print(analysis2)
    print(f"Status: {analysis2.summary()}")
    
    print("\n" + "=" * 70)
    print("EXAMPLE: Risky strategy (large wins/losses)")
    print("=" * 70)
    
    # Scenario 3: High volatility strategy
    analysis3 = RiskOfRuinCalculator.calculate(
        win_rate=0.45,
        avg_win_pct=0.10,  # +10% wins
        avg_loss_pct=0.05,  # -5% losses (smaller)
        num_simulations=10000,
    )
    print(analysis3)
    print(f"Status: {analysis3.summary()}")

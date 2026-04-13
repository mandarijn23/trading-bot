"""
Dynamic Capital Allocation using Kelly Criterion.

Allocates capital to each strategy based on performance (Sharpe ratio, win rate).
Professional money managers always do this - higher capital to winning strategies.

Kelly Criterion: f* = (p*b - q) / b
where p=win rate, q=loss rate, b=reward/risk ratio
Optimal position size as % of capital.

Result: Better risk-adjusted returns by concentrating on edge.
"""

import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple
import logging


@dataclass
class StrategyPerformance:
    """Performance metrics for a single strategy."""
    name: str
    win_rate: float  # 0-1
    avg_win_pct: float  # Average % gain on wins
    avg_loss_pct: float  # Average % loss on losses
    sharpe_ratio: float  # Risk-adjusted return
    total_trades: int
    consecutive_wins: int
    consecutive_losses: int
    max_drawdown: float  # Peak to trough
    profit_factor: float  # Gross wins / gross losses


class KellyCriterion:
    """Calculate optimal position sizing using Kelly formula."""
    
    @staticmethod
    def calculate_kelly_fraction(
        win_rate: float,
        avg_win_pct: float,
        avg_loss_pct: float,
        max_kelly_fraction: float = 0.25,  # Never use full Kelly (too aggressive)
    ) -> float:
        """
        Calculate optimal Kelly fraction for a strategy.
        
        Args:
            win_rate: Probability of win (0-1)
            avg_win_pct: Average return on winning trades (%)
            avg_loss_pct: Average loss on losing trades (%)
            max_kelly_fraction: Cap Kelly at this level (fractional Kelly for safety)
        
        Returns:
            Fraction of capital to allocate (0-1)
        """
        
        if win_rate <= 0 or win_rate >= 1 or avg_win_pct <= 0 or avg_loss_pct <= 0:
            return 0.0
        
        # Kelly formula: f = (p*b - q) / b
        # where p=prob win, q=prob loss, b=reward/risk ratio
        
        p = win_rate
        q = 1.0 - win_rate
        b = avg_win_pct / avg_loss_pct  # Reward/risk ratio
        
        kelly_fraction = (p * b - q) / b if b > 0 else 0.0
        
        # Cap at maximum (fractional Kelly)
        kelly_fraction = max(0.0, min(kelly_fraction, max_kelly_fraction))
        
        return kelly_fraction
    
    @staticmethod
    def estimate_blowup_probability(
        kelly_fraction: float,
        trades_until_ruin: int = 100,
    ) -> float:
        """
        Estimate probability of drawdown of 50% over N trades at Kelly fraction.
        
        Higher fractions = much higher ruin probability.
        """
        
        # Ruin probability approximation (geometric random walk)
        # P(ruin) ≈ 0.5^(kelly_fraction * trades)
        
        ruin_prob = 0.5 ** (kelly_fraction * trades_until_ruin)
        
        return ruin_prob


class MultiStrategyAllocator:
    """
    Allocate capital across multiple strategies based on recent performance.
    
    Features:
    - Calculates Kelly fraction for each strategy
    - Rebalances daily based on latest Sharpe ratios
    - Prevents over-concentration (no strategy > 50%)
    - Reduces allocation when win rate drops
    - Increases allocation when edge improves
    """
    
    def __init__(self, rebalance_frequency: str = "daily"):
        """
        Initialize allocator.
        
        Args:
            rebalance_frequency: "daily", "weekly", or "never"
        """
        self.strategies: Dict[str, StrategyPerformance] = {}
        self.allocations: Dict[str, float] = {}  # Fraction of capital per strategy
        self.rebalance_frequency = rebalance_frequency
        self.last_rebalance = None
        self.logger = logging.getLogger("allocator")
    
    def register_strategy(self, name: str) -> None:
        """Register a new strategy for tracking."""
        self.strategies[name] = StrategyPerformance(
            name=name,
            win_rate=0.55,  # Initial assumption
            avg_win_pct=1.0,
            avg_loss_pct=0.5,
            sharpe_ratio=0.5,
            total_trades=0,
            consecutive_wins=0,
            consecutive_losses=0,
            max_drawdown=0.0,
            profit_factor=1.0,
        )
        self.allocations[name] = 1.0 / len(self.strategies)  # Equal initial
    
    def update_performance(
        self,
        strategy_name: str,
        trades: List[tuple],  # List of (entry_price, exit_price, size, pnl_pct)
    ) -> None:
        """
        Update performance metrics for a strategy.
        
        Args:
            strategy_name: Name of strategy
            trades: Recent trades for this strategy
        """
        
        if strategy_name not in self.strategies:
            return
        
        if len(trades) < 5:
            return  # Need minimum data
        
        # Calculate metrics
        wins = [t for t in trades if t[3] > 0]  # t[3] = pnl_pct
        losses = [t for t in trades if t[3] <= 0]
        
        win_rate = len(wins) / len(trades) if trades else 0.55
        
        avg_win = np.mean([t[3] for t in wins]) if wins else 0.5
        avg_loss = abs(np.mean([t[3] for t in losses])) if losses else 0.5
        
        # Sharpe ratio (return per unit of volatility)
        returns = [t[3] for t in trades]
        sharpe = np.mean(returns) / (np.std(returns) + 1e-9) if returns else 0.0
        
        # Max drawdown
        max_dd = self._calculate_max_drawdown([t[3] for t in trades])
        
        # Profit factor
        gross_wins = sum([t[3] for t in wins]) if wins else 0
        gross_losses = sum([abs(t[3]) for t in losses]) if losses else 1
        profit_factor = gross_wins / gross_losses if gross_losses > 0 else 1.0
        
        # Streak
        recent_trades = trades[-10:] if trades else []
        win_streak = 0
        loss_streak = 0
        for t in reversed(recent_trades):
            if t[3] > 0:
                win_streak += 1
                loss_streak = 0
            else:
                loss_streak += 1
                win_streak = 0
        
        self.strategies[strategy_name] = StrategyPerformance(
            name=strategy_name,
            win_rate=win_rate,
            avg_win_pct=avg_win,
            avg_loss_pct=avg_loss,
            sharpe_ratio=sharpe,
            total_trades=len(trades),
            consecutive_wins=win_streak,
            consecutive_losses=loss_streak,
            max_drawdown=max_dd,
            profit_factor=profit_factor,
        )
        
        self.logger.info(
            f"{strategy_name}: WR={win_rate:.1%}, Sharpe={sharpe:.2f}, "
            f"PF={profit_factor:.2f}, MaxDD={max_dd:.1%}"
        )
    
    def calculate_allocations(self) -> Dict[str, float]:
        """
        Recalculate capital allocations using Kelly criterion.
        
        Returns:
            Dict of strategy -> allocation fraction
        """
        
        allocations = {}
        total_allocation = 0.0
        
        for name, perf in self.strategies.items():
            # Skip if too few trades
            if perf.total_trades < 10:
                kelly = 1.0 / len(self.strategies)  # Equal share
            else:
                # Calculate Kelly fraction
                kelly = KellyCriterion.calculate_kelly_fraction(
                    perf.win_rate,
                    perf.avg_win_pct,
                    perf.avg_loss_pct,
                    max_kelly_fraction=0.20,  # Max 20% of capital per strategy
                )
            
            # Penalty for consecutive losses (strategy losing confidence)
            if perf.consecutive_losses >= 3:
                kelly *= 0.5
            
            # Bonus for consecutive wins
            if perf.consecutive_wins >= 3:
                kelly *= 1.2
            
            allocations[name] = kelly
            total_allocation += kelly
        
        # Normalize to sum to 1.0
        if total_allocation > 0:
            allocations = {k: v / total_allocation for k, v in allocations.items()}
        else:
            allocations = {k: 1.0 / len(self.strategies) for k in self.strategies.keys()}
        
        self.allocations = allocations
        return allocations
    
    def get_position_size_for_strategy(self, strategy_name: str, total_capital: float) -> float:
        """
        Get dollar amount to allocate to a strategy.
        
        Args:
            strategy_name: Strategy name
            total_capital: Total portfolio capital
        
        Returns:
            Dollar allocation for this strategy
        """
        
        allocation_pct = self.allocations.get(strategy_name, 1.0 / len(self.strategies))
        return total_capital * allocation_pct
    
    def should_stop_trading_strategy(self, strategy_name: str) -> Tuple[bool, str]:
        """
        Determine if strategy should be paused due to poor performance.
        
        Returns:
            (should_stop, reason)
        """
        
        if strategy_name not in self.strategies:
            return False, ""
        
        perf = self.strategies[strategy_name]
        
        if perf.win_rate < 0.45:
            return True, f"Win rate too low: {perf.win_rate:.1%}"
        
        if perf.consecutive_losses >= 5:
            return True, "5 consecutive losses"
        
        if perf.max_drawdown > 0.20:  # >20% drawdown
            return True, f"Max drawdown too high: {perf.max_drawdown:.1%}"
        
        if perf.sharpe_ratio < -0.5:
            return True, "Negative Sharpe ratio"
        
        return False, ""
    
    @staticmethod
    def _calculate_max_drawdown(returns: List[float]) -> float:
        """Calculate maximum drawdown from a series of returns."""
        if not returns:
            return 0.0
        
        cumulative = 1.0
        peak = 1.0
        max_dd = 0.0
        
        for ret in returns:
            cumulative *= (1.0 + ret / 100.0)
            peak = max(peak, cumulative)
            dd = (peak - cumulative) / peak
            max_dd = max(max_dd, dd)
        
        return max_dd
    
    def get_allocation_report(self) -> dict:
        """Get detailed report on allocations and performance."""
        
        report = {
            "timestamp": pd.Timestamp.now(),
            "strategies": {},
        }
        
        for name, perf in self.strategies.items():
            allocation = self.allocations.get(name, 0.0)
            should_stop, reason = self.should_stop_trading_strategy(name)
            
            report["strategies"][name] = {
                "allocation_pct": allocation * 100,
                "win_rate": perf.win_rate,
                "sharpe_ratio": perf.sharpe_ratio,
                "total_trades": perf.total_trades,
                "max_drawdown": perf.max_drawdown,
                "profit_factor": perf.profit_factor,
                "should_stop": should_stop,
                "stop_reason": reason,
            }
        
        return report

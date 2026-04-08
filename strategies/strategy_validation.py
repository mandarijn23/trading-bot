"""
STRATEGY EDGE VALIDATION
========================

Backtest and validate strategies across different market regimes.
Calculate actual edge metrics:
- Win rate by regime
- Average win vs loss
- Expectancy calculation
- Sharpe ratio
- Maximum drawdown
- Consistency across time periods
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass, field
from typing import Dict, List, Tuple, Optional
from datetime import datetime, timedelta
import json

from strategy_edge import (
    EdgeStrategyManager,
    StrategySignal,
    MarketRegimeDetector,
    TradeEdge,
)


@dataclass
class Trade:
    """Single trade record."""
    entry_time: datetime
    entry_price: float
    exit_time: Optional[datetime] = None
    exit_price: Optional[float] = None
    strategy: str = ""
    regime: str = ""
    
    # Filled by analysis
    return_pct: float = 0.0
    winning: bool = False
    bars_held: int = 0
    
    def __post_init__(self):
        if self.exit_price and self.entry_price:
            self.return_pct = (self.exit_price - self.entry_price) / self.entry_price
            self.winning = self.return_pct > 0.0


@dataclass
class StrategyBacktestResults:
    """Results from backtesting a strategy."""
    strategy_name: str
    regime: str
    
    # Performance metrics
    total_trades: int = 0
    winning_trades: int = 0
    losing_trades: int = 0
    win_rate: float = 0.0
    
    # P&L metrics
    avg_win: float = 0.0  # Average % win
    avg_loss: float = 0.0  # Average % loss
    total_return: float = 0.0  # Sum % return
    expectancy: float = 0.0  # (win_rate * avg_win) - (loss_rate * avg_loss)
    
    # Risk metrics
    max_drawdown: float = 0.0
    sharpe_ratio: float = 0.0
    max_consecutive_losses: int = 0
    
    # Quality metrics
    avg_holding_bars: int = 0
    profit_factor: float = 0.0  # Gross wins / Gross losses
    
    trades: List[Trade] = field(default_factory=list)
    
    def calculate_from_trades(self):
        """Calculate all metrics from trade list."""
        if not self.trades:
            return
        
        self.total_trades = len(self.trades)
        self.winning_trades = sum(1 for t in self.trades if t.winning)
        self.losing_trades = self.total_trades - self.winning_trades
        
        if self.total_trades > 0:
            self.win_rate = self.winning_trades / self.total_trades
        
        # Average win/loss
        winning_returns = [t.return_pct for t in self.trades if t.winning]
        losing_returns = [t.return_pct for t in self.trades if not t.winning]
        
        self.avg_win = np.mean(winning_returns) if winning_returns else 0.0
        self.avg_loss = np.mean(losing_returns) if losing_returns else 0.0
        
        # Total return
        self.total_return = sum(t.return_pct for t in self.trades)
        
        # Expectancy
        loss_rate = 1.0 - self.win_rate
        self.expectancy = (self.win_rate * self.avg_win) - (loss_rate * abs(self.avg_loss))
        
        # Max drawdown
        cum_returns = np.cumsum([t.return_pct for t in self.trades])
        if len(cum_returns) > 0:
            peak = np.maximum.accumulate(cum_returns)
            drawdown = (cum_returns - peak) / (np.abs(peak) + 1e-10)
            self.max_drawdown = np.min(drawdown) if len(drawdown) > 0 else 0.0
        
        # Sharpe ratio (approximated)
        returns_array = np.array([t.return_pct for t in self.trades])
        if len(returns_array) > 1 and np.std(returns_array) > 0:
            self.sharpe_ratio = np.mean(returns_array) / np.std(returns_array) * np.sqrt(252)
        
        # Max consecutive losses
        consecutive_losses = 0
        self.max_consecutive_losses = 0
        for trade in self.trades:
            if not trade.winning:
                consecutive_losses += 1
                self.max_consecutive_losses = max(self.max_consecutive_losses, consecutive_losses)
            else:
                consecutive_losses = 0
        
        # Average holding period
        holding_periods = [t.bars_held for t in self.trades if t.bars_held > 0]
        self.avg_holding_bars = int(np.mean(holding_periods)) if holding_periods else 0
        
        # Profit factor
        total_wins = sum(t.return_pct for t in self.trades if t.winning)
        total_losses = abs(sum(t.return_pct for t in self.trades if not t.winning))
        self.profit_factor = total_wins / total_losses if total_losses > 0 else 0.0
    
    def to_dict(self) -> dict:
        """Convert to dictionary for JSON export."""
        return {
            "strategy": self.strategy_name,
            "regime": self.regime,
            "total_trades": self.total_trades,
            "winning_trades": self.winning_trades,
            "losing_trades": self.losing_trades,
            "win_rate": round(self.win_rate, 4),
            "avg_win_pct": round(self.avg_win * 100, 3),
            "avg_loss_pct": round(self.avg_loss * 100, 3),
            "total_return_pct": round(self.total_return * 100, 2),
            "expectancy_pct": round(self.expectancy * 100, 4),
            "max_drawdown": round(self.max_drawdown, 4),
            "sharpe_ratio": round(self.sharpe_ratio, 3),
            "max_consecutive_losses": self.max_consecutive_losses,
            "avg_holding_bars": self.avg_holding_bars,
            "profit_factor": round(self.profit_factor, 3),
        }


class StrategyBacktester:
    """
    Backtest strategies and calculate edge metrics.
    
    Usage:
        backtester = StrategyBacktester()
        results = backtester.backtest(df, "2023-01-01", "2024-01-01")
        backtester.print_results(results)
    """
    
    def __init__(self, commission: float = 0.001, slippage: float = 0.002):
        self.commission = commission
        self.slippage = slippage
        self.manager = EdgeStrategyManager()
    
    def backtest(
        self,
        df: pd.DataFrame,
        start_date: Optional[str] = None,
        end_date: Optional[str] = None,
        regime_filter: Optional[str] = None,
    ) -> Dict[str, StrategyBacktestResults]:
        """
        Full backtest across all strategies.
        
        Args:
            df: OHLCV dataframe with DatetimeIndex
            start_date: Start date for backtest (optional)
            end_date: End date for backtest (optional)
            regime_filter: Only test in specific regime (optional)
        
        Returns:
            Dict of StrategyBacktestResults by (strategy, regime)
        """
        # Filter data period
        if start_date:
            df = df[df.index >= start_date]
        if end_date:
            df = df[df.index <= end_date]
        
        if len(df) < 100:
            raise ValueError("Need at least 100 bars of data")
        
        results = {}
        current_trade: Optional[Trade] = None
        entry_bar: Optional[int] = None
        regimes_seen: Dict[str, List[int]] = {}
        
        # Simulate bar by bar
        for i in range(200, len(df)):  # Skip first 200 bars for indicator warmup
            bar_date = df.index[i]
            bar_df = df.iloc[:i+1]  # Data up to current bar
            
            # Get regime
            regime_info = MarketRegimeDetector.classify(bar_df)
            regime = regime_info["regime"]
            
            if regime not in regimes_seen:
                regimes_seen[regime] = []
            regimes_seen[regime].append(i)
            
            # Skip if filtering regimes
            if regime_filter and regime != regime_filter:
                continue
            
            # Get signal
            signal_obj = self.manager.get_signal(bar_df)
            current_price = df["close"].iloc[i]
            
            # Close existing trade if opposite signal
            if current_trade:
                if signal_obj.signal == "SELL" and current_trade.entry_price > 0:
                    # Close long
                    current_trade.exit_time = bar_date
                    current_trade.exit_price = current_price
                    current_trade.bars_held = i - entry_bar
                    results_key = (current_trade.strategy, current_trade.regime)
                    if results_key not in results:
                        results[results_key] = StrategyBacktestResults(
                            strategy_name=current_trade.strategy,
                            regime=current_trade.regime,
                        )
                    results[results_key].trades.append(current_trade)
                    current_trade = None
                
                elif signal_obj.signal == "BUY" and current_trade.entry_price < 0:
                    # Close short
                    current_trade.exit_time = bar_date
                    current_trade.exit_price = current_price
                    current_trade.bars_held = i - entry_bar
                    results_key = (current_trade.strategy, current_trade.regime)
                    if results_key not in results:
                        results[results_key] = StrategyBacktestResults(
                            strategy_name=current_trade.strategy,
                            regime=current_trade.regime,
                        )
                    results[results_key].trades.append(current_trade)
                    current_trade = None
            
            # Open new trade
            if signal_obj.signal in ["BUY", "SELL"] and current_trade is None:
                if signal_obj.confidence > 0.65:  # Only high confidence trades
                    current_trade = Trade(
                        entry_time=bar_date,
                        entry_price=current_price,
                        strategy=self.manager.last_selected,
                        regime=regime,
                    )
                    entry_bar = i
        
        # Calculate metrics for each strategy
        for key, result in results.items():
            result.calculate_from_trades()
        
        return results
    
    def print_results(self, results: Dict, strategy_filter: Optional[str] = None):
        """Pretty print backtest results."""
        print("\n" + "="*100)
        print("STRATEGY EDGE VALIDATION RESULTS".center(100))
        print("="*100)
        
        for (strategy, regime), result in sorted(results.items()):
            if strategy_filter and strategy != strategy_filter:
                continue
            
            print(f"\n{strategy.upper()} - Regime: {regime}")
            print("-" * 100)
            print(f"  Trades:              {result.total_trades} total ({result.winning_trades}W / {result.losing_trades}L)")
            print(f"  Win Rate:            {result.win_rate*100:.1f}%")
            print(f"  Avg Win/Loss:        +{result.avg_win*100:.2f}% / {result.avg_loss*100:.2f}%")
            print(f"  Expectancy:          {result.expectancy*100:+.4f}% per trade")
            print(f"  Total Return:        {result.total_return*100:+.2f}%")
            print(f"  Profit Factor:       {result.profit_factor:.2f}")
            print(f"  Max Drawdown:        {result.max_drawdown*100:.2f}%")
            print(f"  Sharpe Ratio:        {result.sharpe_ratio:.2f}")
            print(f"  Max Cons. Losses:    {result.max_consecutive_losses}")
            print(f"  Avg Holding:         {result.avg_holding_bars} bars")
    
    def export_results(self, results: Dict, filename: str = "strategy_validation.json"):
        """Export results to JSON."""
        export_data = {
            "timestamp": datetime.now().isoformat(),
            "backtest_params": {
                "commission": self.commission,
                "slippage": self.slippage,
            },
            "results": [v.to_dict() for v in results.values()],
        }
        
        with open(filename, "w") as f:
            json.dump(export_data, f, indent=2)
        
        print(f"\n✓ Results exported to {filename}")


class RegimeAnalyzer:
    """Analyze strategy performance by market regime."""
    
    @staticmethod
    def analyze_regime_performance(
        df: pd.DataFrame,
        results: Dict[str, StrategyBacktestResults],
    ) -> Dict[str, any]:
        """
        Analyze performance by regime.
        
        Returns:
            Dict with regime-specific statistics
        """
        regime_stats = {}
        
        for (strategy, regime), result in results.items():
            if regime not in regime_stats:
                regime_stats[regime] = {
                    "strategies": {},
                    "avg_expectancy": 0.0,
                    "best_strategy": "",
                }
            
            regime_stats[regime]["strategies"][strategy] = {
                "expectancy": result.expectancy,
                "win_rate": result.win_rate,
                "total_return": result.total_return,
                "trades": result.total_trades,
            }
        
        # Calculate regime-level stats
        for regime, stats in regime_stats.items():
            if stats["strategies"]:
                expectancies = [s["expectancy"] for s in stats["strategies"].values()]
                stats["avg_expectancy"] = np.mean(expectancies)
                
                # Best strategy for this regime
                best = max(stats["strategies"].items(), key=lambda x: x[1]["expectancy"])
                stats["best_strategy"] = best[0]
        
        return regime_stats
    
    @staticmethod
    def print_regime_analysis(regime_stats: Dict):
        """Pretty print regime analysis."""
        print("\n" + "="*100)
        print("REGIME-SPECIFIC STRATEGY PERFORMANCE".center(100))
        print("="*100)
        
        for regime in sorted(regime_stats.keys()):
            stats = regime_stats[regime]
            print(f"\n{regime}:")
            print(f"  Best Strategy: {stats['best_strategy']} (Expectancy: {stats['avg_expectancy']*100:+.4f}%)")
            
            for strategy, metrics in stats["strategies"].items():
                marker = "→" if strategy == stats["best_strategy"] else " "
                print(f"  {marker} {strategy:30s} | Exp: {metrics['expectancy']*100:+.4f}% "
                      f"| Win: {metrics['win_rate']*100:.1f}% | Ret: {metrics['total_return']*100:+.2f}%")


if __name__ == "__main__":
    # Example usage
    print("Strategy Edge Validation Framework")
    print("Use: backtester = StrategyBacktester()")
    print("     results = backtester.backtest(df)")
    print("     backtester.print_results(results)")

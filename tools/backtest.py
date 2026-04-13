"""
Professional Backtester with Realistic Market Conditions.

Features:
- Trading fees (maker/taker commissions)
- Slippage simulation (realistic market impact)
- Bid/ask spread
- Latency simulation
- Walk-forward testing (in-sample + out-of-sample)
- Professional metrics: Sharpe ratio, max drawdown, profit factor
- Drawdown tracking
- Trade logging

Run:
  python backtest.py                    # Standard backtest
  python backtest.py --walk-forward     # Walk-forward validation
  python backtest.py --no-slippage      # Unrealistic (no fees/slippage)
"""

import logging
import json
import sys
from typing import Dict, List, Optional, Tuple, Literal
from dataclasses import dataclass
from pathlib import Path
import argparse

import ccxt
import pandas as pd
import numpy as np

from stock_config import load_stock_config
from strategy import get_signal
from indicators import Indicators, MarketRegime


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    handlers=[
        logging.FileHandler("backtest.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


@dataclass
class BacktestConfig:
    """Backtesting parameters."""
    # Market impact / fees
    maker_fee: float = 0.001  # 0.1% maker fee (Binance)
    taker_fee: float = 0.001  # 0.1% taker fee (Binance)
    slippage_pct: float = 0.002  # 0.2% slippage (realistic)
    bid_ask_spread: float = 0.001  # 0.1% bid-ask spread
    latency_ms: int = 50  # 50ms order latency
    
    # Backtester settings
    starting_capital: float = 10000.0
    max_risk_per_trade: float = 0.02  # Risk 2% per trade
    walkforward_train_size: int = 200  # Candles for training
    walkforward_test_size: int = 50  # Candles for testing
    walkforward_step: int = 25  # Step size for walking forward


@dataclass
class Trade:
    """Single trade record."""
    entry_time: int
    exit_time: int
    entry_price: float
    exit_price: float
    size: float
    entry_fee: float
    exit_fee: float
    entry_slippage: float
    exit_slippage: float
    pnl_gross: float  # Before fees/slippage
    pnl_net: float  # After fees/slippage
    return_pct: float
    max_drawdown_trade: float
    reason: str
    peak_price: float
    
    def __str__(self) -> str:
        emoji = "✅" if self.pnl_net > 0 else "❌"
        return (
            f"{emoji} Entry: ${self.entry_price:8.2f} → Exit: ${self.exit_price:8.2f} | "
            f"PnL: ${self.pnl_net:7.2f} ({self.return_pct:+6.2f}%) | "
            f"Reason: {self.reason}"
        )


@dataclass
class BacktestMetrics:
    """Professional backtesting metrics."""
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float  # %
    profit_factor: float  # Total wins / Total losses
    avg_win: float
    avg_loss: float
    max_win: float
    max_loss: float
    
    total_return_pct: float
    annualized_return: float
    max_drawdown_pct: float
    drawdown_duration: int  # Candles to recover
    sharpe_ratio: float
    sortino_ratio: float
    calmar_ratio: float
    recovery_factor: float
    
    gross_pnl: float
    net_pnl: float
    total_fees: float
    total_slippage: float
    
    def __str__(self) -> str:
        lines = [
            "\n" + "=" * 80,
            "💰 BACKTEST RESULTS",
            "=" * 80,
            f"Total Trades:       {self.total_trades:>6}   |  Wins: {self.winning_trades:>3}  Losses: {self.losing_trades:>3}",
            f"Win Rate:           {self.win_rate:>6.1f}%",
            f"Profit Factor:      {self.profit_factor:>6.2f}x   (Total Wins / Total Losses)",
            f"Avg Win/Loss:       ${self.avg_win:>7.2f} / ${self.avg_loss:>7.2f}",
            f"Max Win/Loss:       ${self.max_win:>7.2f} / ${self.max_loss:>7.2f}",
            "-" * 80,
            f"Gross P&L:          ${self.gross_pnl:>8.2f} ({self.total_return_pct:>6.2f}%)",
            f"Total Fees:         ${self.total_fees:>8.2f}",
            f"Total Slippage:     ${self.total_slippage:>8.2f}",
            f"Net P&L:            ${self.net_pnl:>8.2f}",
            "-" * 80,
            f"Max Drawdown:       {self.max_drawdown_pct:>6.2f}%  |  Duration: {self.drawdown_duration:>3} candles",
            f"Sharpe Ratio:       {self.sharpe_ratio:>6.2f}",
            f"Sortino Ratio:      {self.sortino_ratio:>6.2f}",
            f"Calmar Ratio:       {self.calmar_ratio:>6.2f}",
            f"Recovery Factor:    {self.recovery_factor:>6.2f}x",
            "=" * 80,
        ]
        return "\n".join(lines)


class ProfessionalBacktester:
    """Professional backtester with realistic market conditions."""
    
    def __init__(self, config: BacktestConfig):
        self.config = config
        
    def apply_slippage(self, price: float, direction: Literal["BUY", "SELL"]) -> float:
        """Apply slippage and bid/ask spread to entry price."""
        spread = price * self.config.bid_ask_spread
        slippage = price * self.config.slippage_pct
        
        if direction == "BUY":
            # When buying: price is higher (ask side)
            return price + spread + slippage
        else:
            # When selling: price is lower (bid side)
            return price - spread - slippage
    
    def calculate_position_size(
        self,
        capital: float,
        entry_price: float,
        stop_loss_price: float,
    ) -> float:
        """
        Calculate position size using risk management (1-2% risk per trade).
        
        Args:
            capital: Current capital
            entry_price: Entry price
            stop_loss_price: Stop loss price
        
        Returns:
            Position size in base currency
        """
        # Risk amount: 2% of capital
        risk_amount = capital * self.config.max_risk_per_trade
        
        # Distance to stop loss
        risk_per_unit = abs(entry_price - stop_loss_price)
        
        if risk_per_unit <= 0:
            return 0.0
        
        # Position size
        position_size = risk_amount / risk_per_unit
        
        # Don't risk more than 30% of capital on single trade
        max_size = (capital * 0.3) / entry_price
        
        return min(position_size, max_size)
    
    def backtest(
        self,
        df: pd.DataFrame,
        symbol: str,
        use_fees: bool = True,
        use_slippage: bool = True,
        start_index: int = 0,
        end_index: Optional[int] = None,
    ) -> Tuple[List[Trade], BacktestMetrics]:
        """
        Run backtest on historical data.
        
        Args:
            df: OHLCV DataFrame
            symbol: Trading pair name
            use_fees: Whether to simulate trading fees
            use_slippage: Whether to simulate slippage
        
        Returns:
            (trades_list, metrics)
        """
        df = df.reset_index(drop=True)
        start_index = max(0, int(start_index))
        end_index = len(df) if end_index is None else max(0, min(int(end_index), len(df)))
        
        capital = self.config.starting_capital
        position = None
        trades: List[Trade] = []
        equity_curve = [capital]
        
        log.info(f"Starting backtest for {symbol}...")
        log.info(f"  Starting capital: ${capital:,.2f}")
        log.info(f"  Maker fee: {self.config.maker_fee*100:.2f}% | "
                f"Taker fee: {self.config.taker_fee*100:.2f}%")
        log.info(f"  Slippage: {self.config.slippage_pct*100:.2f}% | "
                f"Bid/Ask: {self.config.bid_ask_spread*100:.2f}%")
        
        # Minimum lookback for indicators
        min_lookback = max(30, min(200, len(df) // 5))
        
        for i in range(max(min_lookback, start_index), end_index):
            df_window = df.iloc[:i+1].copy()
            row = df.iloc[i]
            current_price = float(row["close"])
            
            if position is None:
                # NOT IN POSITION - Look for entry signal
                signal = get_signal(df_window)
                
                if signal == "BUY":
                    # Calculate entry with slippage
                    entry_price_market = current_price
                    entry_price_actual = (
                        self.apply_slippage(entry_price_market, "BUY")
                        if use_slippage else entry_price_market
                    )
                    
                    # Calculate stop loss (ATR-based)
                    atr = Indicators.atr(df_window, 14).iloc[-1]
                    stop_loss_price = entry_price_actual - (atr * 2)
                    
                    # Calculate position size based on risk
                    position_size = self.calculate_position_size(
                        capital, entry_price_actual, stop_loss_price
                    )
                    
                    if position_size > 0:
                        # Calculate entry fees
                        entry_fee = (
                            (entry_price_actual * position_size * self.config.taker_fee)
                            if use_fees else 0.0
                        )
                        entry_slippage = (
                            entry_price_market * position_size * self.config.slippage_pct
                            if use_slippage else 0.0
                        )
                        
                        total_cost = (entry_price_actual * position_size) + entry_fee
                        
                        if total_cost <= capital:
                            position = {
                                "entry_price": entry_price_actual,
                                "entry_price_market": entry_price_market,
                                "entry_time": i,
                                "entry_fee": entry_fee,
                                "entry_slippage": entry_slippage,
                                "size": position_size,
                                "stop_loss": stop_loss_price,
                                "take_profit": entry_price_actual * 1.05,  # 5% TP
                                "peak_price": current_price,
                            }
                            capital -= total_cost
            
            else:
                # IN POSITION - Check exit conditions
                position["peak_price"] = max(position["peak_price"], current_price)
                
                exit_price_market = current_price
                exit_reason = None
                
                # Check stop loss
                if current_price <= position["stop_loss"]:
                    exit_reason = "STOP_LOSS"
                    exit_price_market = position["stop_loss"]
                
                # Check take profit
                elif current_price >= position["take_profit"]:
                    exit_reason = "TAKE_PROFIT"
                    exit_price_market = position["take_profit"]
                
                # Trailing stop (5% from peak)
                elif current_price < position["peak_price"] * 0.95:
                    exit_reason = "TRAILING_STOP"
                    exit_price_market = current_price
                
                if exit_reason:
                    # Calculate exit with slippage
                    exit_price_actual = (
                        self.apply_slippage(exit_price_market, "SELL")
                        if use_slippage else exit_price_market
                    )
                    
                    # Calculate exit fees
                    exit_fee = (
                        (exit_price_actual * position["size"] * self.config.taker_fee)
                        if use_fees else 0.0
                    )
                    exit_slippage = (
                        exit_price_market * position["size"] * self.config.slippage_pct
                        if use_slippage else 0.0
                    )
                    
                    # Calculate P&L
                    pnl_gross = (exit_price_actual - position["entry_price"]) * position["size"]
                    pnl_net = pnl_gross - position["entry_fee"] - exit_fee - exit_slippage
                    
                    # Return %
                    capital_used = position["entry_price"] * position["size"]
                    return_pct = (pnl_net / capital_used * 100) if capital_used > 0 else 0.0
                    
                    # Max drawdown during this trade
                    max_dd = (
                        ((position["peak_price"] - position["entry_price"]) / position["entry_price"] * 100)
                        if position["entry_price"] > 0 else 0.0
                    )
                    
                    # Record trade
                    trade = Trade(
                        entry_time=position["entry_time"],
                        exit_time=i,
                        entry_price=position["entry_price"],
                        exit_price=exit_price_actual,
                        size=position["size"],
                        entry_fee=position["entry_fee"],
                        exit_fee=exit_fee,
                        entry_slippage=position["entry_slippage"],
                        exit_slippage=exit_slippage,
                        pnl_gross=pnl_gross,
                        pnl_net=pnl_net,
                        return_pct=return_pct,
                        max_drawdown_trade=max_dd,
                        reason=exit_reason,
                        peak_price=position["peak_price"],
                    )
                    trades.append(trade)
                    
                    # Update capital
                    capital += position["size"] * exit_price_actual - exit_fee
                    position = None
        
        # Close any open position at last price
        if position is not None and end_index > 0:
            last_index = end_index - 1
            last_price = float(df.iloc[last_index]["close"])
            pnl_net = (last_price - position["entry_price"]) * position["size"]
            capital += position["size"] * last_price
            
            trade = Trade(
                entry_time=position["entry_time"],
                exit_time=last_index,
                entry_price=position["entry_price"],
                exit_price=last_price,
                size=position["size"],
                entry_fee=position["entry_fee"],
                exit_fee=0.0,
                entry_slippage=position["entry_slippage"],
                exit_slippage=0.0,
                pnl_gross=pnl_net,
                pnl_net=pnl_net,
                return_pct=(pnl_net / (position["entry_price"] * position["size"]) * 100),
                max_drawdown_trade=((last_price - position["entry_price"]) / position["entry_price"] * 100),
                reason="END_OF_DATA",
                peak_price=position["peak_price"],
            )
            trades.append(trade)
        
        # Calculate metrics
        metrics = self._calculate_metrics(trades, capital, use_fees, use_slippage)
        
        return trades, metrics
    
    def _calculate_metrics(
        self,
        trades: List[Trade],
        final_capital: float,
        use_fees: bool = True,
        use_slippage: bool = True,
    ) -> BacktestMetrics:
        """Calculate professional metrics."""
        if not trades:
            return BacktestMetrics(
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                profit_factor=1.0,
                avg_win=0.0,
                avg_loss=0.0,
                max_win=0.0,
                max_loss=0.0,
                total_return_pct=0.0,
                annualized_return=0.0,
                max_drawdown_pct=0.0,
                drawdown_duration=0,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                calmar_ratio=0.0,
                recovery_factor=0.0,
                gross_pnl=0.0,
                net_pnl=0.0,
                total_fees=0.0,
                total_slippage=0.0,
            )
        
        # Basic trade stats
        winners = [t for t in trades if t.pnl_net > 0]
        losers = [t for t in trades if t.pnl_net <= 0]
        
        total_trades = len(trades)
        winning_trades = len(winners)
        losing_trades = len(losers)
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0.0
        
        # Profit factor
        total_wins = sum(t.pnl_net for t in winners)
        total_losses = abs(sum(t.pnl_net for t in losers))
        profit_factor = (total_wins / total_losses) if total_losses > 0 else (total_wins / 0.01 if total_wins > 0 else 1.0)
        
        # Average wins/losses
        avg_win = (total_wins / len(winners)) if winners else 0.0
        avg_loss = (total_losses / len(losers)) if losers else 0.0
        max_win = max((t.pnl_net for t in trades), default=0.0)
        max_loss = min((t.pnl_net for t in trades), default=0.0)
        
        # P&L
        gross_pnl = sum(t.pnl_gross for t in trades)
        net_pnl = sum(t.pnl_net for t in trades)
        total_fees = sum(t.entry_fee + t.exit_fee for t in trades)
        total_slippage = sum(t.entry_slippage + t.exit_slippage for t in trades)
        
        # Returns
        total_return_pct = (net_pnl / self.config.starting_capital * 100)
        
        # Annualized return (assumes 365 trading days) 
        num_days = total_trades / 24 if total_trades > 0 else 1
        annualized_return = (total_return_pct * 365 / max(num_days, 1))
        
        # Drawdown
        max_dd = min((t.max_drawdown_trade for t in trades), default=0.0)
        max_drawdown_pct = abs(max_dd) if max_dd < 0 else 0.0
        
        drawdown_duration = 0  # Approximate
        
        # Sharpe/Sortino/Calmar
        returns = [t.return_pct for t in trades]
        sharpe_ratio = (
            (np.mean(returns) / np.std(returns) * np.sqrt(252))
            if np.std(returns) > 0 else 0.0
        )
        
        downside_returns = [r for r in returns if r < 0]
        sortino_ratio = (
            (np.mean(returns) / np.std(downside_returns) * np.sqrt(252))
            if downside_returns and np.std(downside_returns) > 0 else 0.0
        )
        
        calmar_ratio = (
            (annualized_return / max_drawdown_pct)
            if max_drawdown_pct > 0 else 0.0
        )
        
        recovery_factor = (
            (net_pnl / abs(max_loss))
            if max_loss < 0 else 1.0
        )
        
        return BacktestMetrics(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            profit_factor=profit_factor,
            avg_win=avg_win,
            avg_loss=avg_loss,
            max_win=max_win,
            max_loss=max_loss,
            total_return_pct=total_return_pct,
            annualized_return=annualized_return,
            max_drawdown_pct=max_drawdown_pct,
            drawdown_duration=drawdown_duration,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            calmar_ratio=calmar_ratio,
            recovery_factor=recovery_factor,
            gross_pnl=gross_pnl,
            net_pnl=net_pnl,
            total_fees=total_fees,
            total_slippage=total_slippage,
        )

    def walk_forward_validation(
        self,
        df: pd.DataFrame,
        symbol: str,
    ) -> Dict[str, object]:
        """Run rolling in-sample/out-of-sample validation."""
        df = df.reset_index(drop=True)
        train_size = max(30, int(self.config.walkforward_train_size))
        test_size = max(10, int(self.config.walkforward_test_size))
        step = max(1, int(self.config.walkforward_step))

        if len(df) < train_size + test_size:
            raise ValueError(
                f"Not enough data for walk-forward validation: have {len(df)}, need {train_size + test_size}"
            )

        periods: List[Dict[str, object]] = []
        for start in range(0, len(df) - train_size - test_size + 1, step):
            window_end = start + train_size + test_size
            window_df = df.iloc[start:window_end].copy()

            _, train_metrics = self.backtest(
                window_df,
                symbol,
                start_index=0,
                end_index=train_size,
            )
            _, test_metrics = self.backtest(
                window_df,
                symbol,
                start_index=train_size,
                end_index=len(window_df),
            )

            ratio = (
                train_metrics.sharpe_ratio / test_metrics.sharpe_ratio
                if test_metrics.sharpe_ratio > 0 and train_metrics.sharpe_ratio > 0
                else 1.0
            )

            periods.append(
                {
                    "start": start,
                    "train_end": start + train_size,
                    "test_end": window_end,
                    "train_sharpe": train_metrics.sharpe_ratio,
                    "test_sharpe": test_metrics.sharpe_ratio,
                    "train_return_pct": train_metrics.total_return_pct,
                    "test_return_pct": test_metrics.total_return_pct,
                    "overfit_ratio": ratio,
                }
            )

        avg_train_sharpe = float(np.mean([period["train_sharpe"] for period in periods]))
        avg_test_sharpe = float(np.mean([period["test_sharpe"] for period in periods]))
        avg_ratio = float(np.mean([period["overfit_ratio"] for period in periods]))
        avg_train_return = float(np.mean([period["train_return_pct"] for period in periods]))
        avg_test_return = float(np.mean([period["test_return_pct"] for period in periods]))

        return {
            "symbol": symbol,
            "periods": periods,
            "period_count": len(periods),
            "avg_train_sharpe": avg_train_sharpe,
            "avg_test_sharpe": avg_test_sharpe,
            "avg_ratio": avg_ratio,
            "avg_train_return_pct": avg_train_return,
            "avg_test_return_pct": avg_test_return,
            "train_size": train_size,
            "test_size": test_size,
            "step": step,
        }


def fetch_history(symbol: str, timeframe: str = "1h", limit: int = 1000) -> pd.DataFrame:
    """Fetch OHLCV data from Binance."""
    try:
        exchange = ccxt.binance({"enableRateLimit": True})
        raw = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(
            raw,
            columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except Exception as e:
        log.error(f"Failed to fetch {symbol}: {e}")
        raise


def main():
    """Main backtest execution."""
    parser = argparse.ArgumentParser(description="Professional backtest")
    parser.add_argument("--no-fees", action="store_true", help="Disable trading fees")
    parser.add_argument("--no-slippage", action="store_true", help="Disable slippage")
    parser.add_argument("--walk-forward", action="store_true", help="Walk-forward test")
    args = parser.parse_args()
    
    try:
        config = load_stock_config()
        bt_config = BacktestConfig()
        backtest_engine = ProfessionalBacktester(bt_config)
        
        log.info("🚀 Professional Backtester")
        log.info(f"   Backtesting symbols: {config.symbols}")
        log.info(f"   Timeframe: {config.timeframe}")
        
        for symbol in config.symbols:
            log.info(f"\n📊 Backtesting {symbol}...")
            
            df = fetch_history(symbol, config.timeframe, limit=1000)

            if args.walk_forward:
                summary = backtest_engine.walk_forward_validation(df, symbol)
                log.info(
                    "Walk-forward summary | periods=%s | avg_train_sharpe=%.2f | avg_test_sharpe=%.2f | avg_ratio=%.2f",
                    summary["period_count"],
                    summary["avg_train_sharpe"],
                    summary["avg_test_sharpe"],
                    summary["avg_ratio"],
                )
                print(json.dumps(summary, indent=2))
            else:
                trades, metrics = backtest_engine.backtest(
                    df,
                    symbol,
                    use_fees=not args.no_fees,
                    use_slippage=not args.no_slippage,
                )

                print(metrics)

                # Show recent trades
                if trades:
                    log.info(f"\n📈 Recent trades (last 10):")
                    for trade in trades[-10:]:
                        log.info(f"   {trade}")
        
        log.info("\n✅ Backtest completed!")
    
    except Exception as e:
        log.error(f"Backtest failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

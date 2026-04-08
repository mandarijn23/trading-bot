"""
Portfolio Tracking Module

Tracks balance, positions, equity, and daily drawdown.
Critical for risk management and position sizing.
"""

from datetime import date
from typing import Dict
import logging


class Portfolio:
    """Track portfolio balance, equity, and positions."""
    
    def __init__(self, starting_balance: float):
        """
        Initialize portfolio.
        
        Args:
            starting_balance: Starting capital in USDT
        """
        self.starting_balance = starting_balance
        self.balance = starting_balance  # Cash balance (USDT)
        self.equity = starting_balance   # Total portfolio value (cash + open positions)
        self.buying_power = starting_balance
        self.portfolio_value = starting_balance
        self.unrealized_plpc = 0.0
        self.realized_plpc = 0.0
        self.positions = {}              # {symbol: {"active": bool, "entry_price": float, "size": float, "entry_time": datetime}}
        self.start_of_day_balance = starting_balance
        self.current_day = None
        self.logger = logging.getLogger("portfolio")
        
    def open_position(self, symbol: str, entry_price: float, size: float, entry_time):
        """
        Record opening of a position.
        
        Args:
            symbol: Trading pair (e.g., "BTC/USDT")
            entry_price: Entry price
            size: Position size (in base currency)
            entry_time: Timestamp of entry
        """
        if symbol not in self.positions:
            self.positions[symbol] = {}
        
        self.positions[symbol] = {
            "active": True,
            "entry_price": entry_price,
            "size": size,
            "entry_time": entry_time
        }
        
        self.logger.info(f"Position opened: {symbol} @ ${entry_price:.2f} (size: {size})")
    
    def close_position(self, symbol: str, exit_price: float, exit_time):
        """
        Record closing of a position.
        
        Args:
            symbol: Trading pair
            exit_price: Exit price
            exit_time: Timestamp of exit
            
        Returns:
            float: P&L in USDT
        """
        if symbol not in self.positions:
            self.logger.warning(f"Position {symbol} not found to close")
            return 0
        
        pos = self.positions[symbol]
        if not pos["active"]:
            self.logger.warning(f"Position {symbol} already closed")
            return 0
        
        # Calculate P&L
        pnl = (exit_price - pos["entry_price"]) * pos["size"]
        pnl_pct = (exit_price - pos["entry_price"]) / pos["entry_price"] * 100
        
        # Update balance
        self.balance += pnl
        
        # Mark closed
        pos["active"] = False
        pos["exit_price"] = exit_price
        pos["exit_time"] = exit_time
        pos["pnl"] = pnl
        pos["pnl_pct"] = pnl_pct
        
        self.logger.info(f"Position closed: {symbol} @ ${exit_price:.2f} | P&L: {pnl_pct:+.2f}% (${pnl:+.2f})")
        
        return pnl
    
    def update_equity(self, prices: Dict[str, float]):
        """
        Update total portfolio equity based on current market prices.
        
        Args:
            prices: {symbol: current_price}
        """
        total = self.balance  # Start with cash
        
        # Add unrealized P&L from open positions
        for symbol, pos in self.positions.items():
            if pos["active"] and symbol in prices:
                unrealized = (prices[symbol] - pos["entry_price"]) * pos["size"]
                total += unrealized
        
        self.equity = total

    def sync_from_account(self, account) -> None:
        """
        Sync portfolio cash/equity from a live broker account snapshot.

        Args:
            account: Alpaca account object or compatible snapshot
        """
        cash = getattr(account, "cash", None)
        equity = getattr(account, "equity", None)
        if equity is None:
            equity = getattr(account, "portfolio_value", None)

        if cash is None:
            cash = getattr(account, "buying_power", None)

        if cash is not None:
            try:
                self.balance = float(cash)
            except (TypeError, ValueError):
                pass

        if equity is not None:
            try:
                self.equity = float(equity)
            except (TypeError, ValueError):
                pass

        buying_power = getattr(account, "buying_power", None)
        if buying_power is not None:
            try:
                self.buying_power = float(buying_power)
            except (TypeError, ValueError):
                pass

        portfolio_value = getattr(account, "portfolio_value", None)
        if portfolio_value is not None:
            try:
                self.portfolio_value = float(portfolio_value)
            except (TypeError, ValueError):
                pass

        unrealized_plpc = getattr(account, "unrealized_plpc", None)
        if unrealized_plpc is not None:
            try:
                self.unrealized_plpc = float(unrealized_plpc) * 100.0
            except (TypeError, ValueError):
                pass

        realized_plpc = getattr(account, "realized_plpc", None)
        if realized_plpc is not None:
            try:
                self.realized_plpc = float(realized_plpc) * 100.0
            except (TypeError, ValueError):
                pass
    
    def new_day(self, today: date):
        """
        Called at start of new trading day - reset daily drawdown tracking.
        
        Args:
            today: Current date
        """
        if self.current_day != today:
            self.start_of_day_balance = self.equity
            self.current_day = today
            self.logger.info(f"New trading day: {today} | Starting balance: ${self.equity:.2f}")
    
    def daily_pnl(self) -> float:
        """Get today's P&L in USDT."""
        return self.equity - self.start_of_day_balance
    
    def daily_pnl_pct(self) -> float:
        """Get today's P&L as percentage."""
        if self.start_of_day_balance <= 0:
            return 0
        return (self.equity - self.start_of_day_balance) / self.start_of_day_balance * 100
    
    def daily_drawdown_pct(self) -> float:
        """Get today's drawdown as percentage (negative = loss)."""
        return self.daily_pnl_pct()
    
    def total_return_pct(self) -> float:
        """Get total return since start."""
        if self.starting_balance <= 0:
            return 0
        return (self.equity - self.starting_balance) / self.starting_balance * 100
    
    def get_active_positions_count(self) -> int:
        """Get count of currently open positions."""
        return sum(1 for pos in self.positions.values() if pos.get("active", False))
    
    def get_stats(self) -> dict:
        """Get portfolio statistics."""
        return {
            "equity": self.equity,
            "balance": self.balance,
            "daily_pnl": self.daily_pnl(),
            "daily_pnl_pct": self.daily_pnl_pct(),
            "total_return_pct": self.total_return_pct(),
            "active_positions": self.get_active_positions_count(),
            "all_positions": len(self.positions),
        }

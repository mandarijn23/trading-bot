"""
Risk Management Engine

Enforces trading limits, kill switches, and position sizing constraints.
This is THE gatekeeper for all trades.
"""

import logging
from typing import Optional
from portfolio import Portfolio


class RiskManager:
    """Enforce trading limits and risk constraints."""
    
    def __init__(self, config):
        """
        Initialize risk manager.
        
        Args:
            config: Trading config with limits
        """
        self.config = config
        self.trading_enabled = True
        self.kill_switch_reason = None
        self.logger = logging.getLogger("risk")
        
    def check_pre_trade(self, portfolio: Portfolio, open_positions: int) -> bool:
        """
        Check if trade is allowed BEFORE placing order.
        
        Args:
            portfolio: Portfolio object with current state
            open_positions: Number of currently open positions
            
        Returns:
            bool: True if trade is allowed, False otherwise
        """
        # 1. Check if kill switch was triggered
        if not self.trading_enabled:
            self.logger.warning(f"🔴 KILL SWITCH ACTIVE: {self.kill_switch_reason}")
            return False
        
        # 2. Check max open positions
        if open_positions >= self.config.max_open_positions:
            self.logger.warning(
                f"⚠️ Max open positions reached: {open_positions}/{self.config.max_open_positions}"
            )
            return False
        
        # 3. Check daily loss limit
        daily_dd_pct = portfolio.daily_drawdown_pct()
        if daily_dd_pct <= -self.config.max_daily_loss_pct:
            self.logger.critical(
                f"🔴 DAILY LOSS LIMIT HIT: {daily_dd_pct:.2f}% <= -{self.config.max_daily_loss_pct}%"
            )
            self.trading_enabled = False
            self.kill_switch_reason = "Daily loss limit exceeded"
            return False
        
        # 4. Check if enough balance
        min_position_size = self.config.min_trade_usdt if hasattr(self.config, 'min_trade_usdt') else 10
        if portfolio.balance < min_position_size:
            self.logger.warning(
                f"⚠️ Insufficient balance: ${portfolio.balance:.2f} < ${min_position_size:.2f}"
            )
            return False
        
        return True
    
    def check_exit_allowed(self) -> bool:
        """
        Check if exiting positions is allowed.
        Exits are always allowed (even with kill switch).
        
        Returns:
            bool: True (exits always allowed)
        """
        return True
    
    def calculate_position_size(self, portfolio: Portfolio, entry_price: float, symbol: str) -> Optional[float]:
        """
        Calculate safe position size based on risk management rules.
        
        Uses fixed position sizing (% of equity) or Kelly Criterion if enabled.
        
        Args:
            portfolio: Current portfolio
            entry_price: Price at which we'd enter
            symbol: Trading pair
            
        Returns:
            float: Position size in base currency (e.g., BTC), or None if too risky
        """
        # Risk per trade: fixed % of equity
        risk_per_trade_usd = portfolio.equity * 0.01  # 1% per trade
        
        # But don't exceed configured max
        max_per_trade = self.config.trade_amount_usdt if hasattr(self.config, 'trade_amount_usdt') else 100
        amount_usd = min(risk_per_trade_usd, max_per_trade)
        
        # Check minimum
        min_per_trade = self.config.min_trade_usdt if hasattr(self.config, 'min_trade_usdt') else 10
        if amount_usd < min_per_trade:
            self.logger.warning(f"⚠️ Position size too small: ${amount_usd:.2f} < ${min_per_trade:.2f}")
            return None
        
        # Convert USD to base currency
        position_size = amount_usd / entry_price
        
        self.logger.debug(f"Position size calculated: {position_size:.6f} {symbol} (${amount_usd:.2f})")
        
        return position_size
    
    def record_trade(self, symbol: str, side: str, pnl: float, pnl_pct: float):
        """
        Record trade outcome for adaptive risk management (future enhancement).
        
        Args:
            symbol: Trading pair
            side: "buy" or "sell"
            pnl: P&L in USDT
            pnl_pct: P&L as percentage
        """
        # Simple tracking for now
        # Can be extended with win rate tracking, position sizing adjustment, etc.
        self.logger.debug(f"Trade recorded: {symbol} {side} | {pnl_pct:+.2f}% (${pnl:+.2f})")
    
    def reset_daily_limits(self):
        """Reset daily limits (called at market open)."""
        self.logger.info("Daily limits reset")
    
    def get_status(self) -> dict:
        """Get current risk status."""
        return {
            "trading_enabled": self.trading_enabled,
            "kill_switch_reason": self.kill_switch_reason,
        }

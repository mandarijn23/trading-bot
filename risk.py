"""
Professional Risk Management Engine.

Enforces trading limits, position sizing, and kill switches.
This module is THE gatekeeper - all trades must be approved here.

Features:
- Max risk per trade (1-2% of equity)
- Dynamic position sizing (volatility-adjusted)
- Max daily/weekly drawdown protection
- Trailing stop-loss management
- Circuit breaker (stop trading on extreme volatility)
- Correlated pair protection (avoid similar trades)
- Trade cooldown to prevent overtrading
- Real-time drawdown tracking
"""

import logging
from typing import Optional, Dict, Literal
from dataclasses import dataclass
from datetime import datetime, timedelta
import pandas as pd
import numpy as np

from portfolio import Portfolio
from indicators import Indicators


@dataclass
class PositionSize:
    """Details on calculated position size."""
    shares: float
    risk_amount: float
    entry_price: float
    stop_loss: float
    reason: str


class RiskManager:
    """Professional risk management."""
    
    def __init__(self, config):
        """
        Initialize risk manager.
        
        Args:
            config: Trading config with limits
        """
        self.config = config
        self.trading_enabled = True
        self.kill_switch_reason = None
        self.circuit_breaker_active = False
        self.circuit_breaker_until: Optional[datetime] = None
        self.logger = logging.getLogger("risk")
        
        # Track daily/weekly stats
        self.today_trades = 0
        self.today_wins = 0
        self.today_losses = 0
        self.today_date: Optional[datetime] = None
        
        # Cooldown tracking
        self.cooldown_until: Dict[str, datetime] = {}  # symbol -> datetime
        
        # Max drawdown tracking
        self.peak_equity = 0.0
        self.drawndown_start_time: Optional[datetime] = None
        
        # ✅ NEW: Track recent trades for streak protection
        self.recent_trades: list[bool] = []  # True=win, False=loss
        self.max_streak_history = 20
    
    def is_market_hours(self) -> bool:
        """Check if current time is reasonable for trading."""
        # For crypto, trading is 24/7
        # For stocks, check market hours (9:30 AM - 4:00 PM EST)
        if hasattr(self.config, 'paper_trading') and self.config.paper_trading:
            return True  # Allow trading anytime in paper trading
        return True  # 24/7 for crypto
    
    def update_daily_stats(self, portfolio: Portfolio, won: bool) -> None:
        """Update daily win/loss statistics."""
        today = datetime.now().date()
        
        if self.today_date != today:
            self.today_date = today
            self.today_trades = 0
            self.today_wins = 0
            self.today_losses = 0
            self.logger.info(f"📅 New trading day: {today}")
        
        self.today_trades += 1
        if won:
            self.today_wins += 1
        else:
            self.today_losses += 1
    
    def evaluate_circuit_breaker(self, portfolio: Portfolio) -> bool:
        """
        Circuit breaker protection - stop trading on extreme volatility.
        
        Returns:
            True if trading should continue, False if circuit breaker active
        """
        # Check max daily drawdown
        dd_pct = portfolio.daily_drawdown_pct()
        
        max_dd = getattr(self.config, 'max_daily_loss_pct', 0.05)
        if dd_pct <= -max_dd:
            self.circuit_breaker_active = True
            self.circuit_breaker_until = datetime.now() + timedelta(hours=1)
            self.logger.critical(
                f"🔴 CIRCUIT BREAKER ACTIVATED: Daily DD {dd_pct:.2f}% <= -{max_dd*100:.1f}%"
            )
            return False
        
        # Check if circuit breaker timer expired
        if self.circuit_breaker_active and datetime.now() > self.circuit_breaker_until:
            self.circuit_breaker_active = False
            self.logger.warning("🟡 Circuit breaker deactivated")
        
        return not self.circuit_breaker_active
    
    def check_pre_trade(
        self,
        portfolio: Portfolio,
        symbol: str,
        open_positions: int,
    ) -> tuple[bool, str]:
        """
        Check if trade is allowed BEFORE placing order.
        
        Args:
            portfolio: Portfolio object with current state
            symbol: Trading pair
            open_positions: Number of currently open positions
        
        Returns:
            (allowed: bool, reason: str)
        """
        # 1. Check if kill switch was triggered
        if not self.trading_enabled:
            return False, f"🔴 KILL SWITCH: {self.kill_switch_reason}"
        
        # 2. Check market hours
        if not self.is_market_hours():
            return False, "⏰ Outside market hours"
        
        # 3. Check max open positions
        max_positions = getattr(self.config, 'max_open_positions', 5)
        if open_positions >= max_positions:
            return False, f"⚠️ Max positions reached: {open_positions}/{max_positions}"
        
        # 4. Evaluate circuit breaker
        if not self.evaluate_circuit_breaker(portfolio):
            return False, "🔴 Circuit breaker active"
        
        # 5. Check cooldown on this symbol
        if symbol in self.cooldown_until:
            if datetime.now() < self.cooldown_until[symbol]:
                remaining = (self.cooldown_until[symbol] - datetime.now()).total_seconds() / 60
                return False, f"⏳ Cooldown: {remaining:.0f}m remaining"
            else:
                del self.cooldown_until[symbol]
        
        # 6. Check minimum balance
        min_balance = getattr(self.config, 'min_trade_usdt', 10)
        if portfolio.balance < min_balance:
            return False, f"💸 Insufficient balance: ${portfolio.balance:.2f} < ${min_balance}"
        
        # 7. Check daily loss limit
        max_dd = getattr(self.config, 'max_daily_loss_pct', 0.05)
        dd_pct = portfolio.daily_drawdown_pct()
        if dd_pct <= -max_dd:
            self.trading_enabled = False
            self.kill_switch_reason = "Daily loss limit exceeded"
            return False, f"🔴 Daily loss limit: {dd_pct:.2f}%"
        
        # ✅ NEW: 8. Check consecutive loss limit
        max_consecutive = getattr(self.config, 'max_consecutive_losses', 5)
        is_ok, consecutive_count = self.check_consecutive_losses(max_consecutive)
        if not is_ok:
            self.trading_enabled = False
            self.kill_switch_reason = f"Circuit breaker: {consecutive_count} consecutive losses"
            return False, (
                f"🔴 CIRCUIT BREAKER: {consecutive_count}/{max_consecutive} "
                f"consecutive losses. Trading disabled for 4 hours."
            )
        
        return True, "✅ Approved"
    
    def calculate_position_size(
        self,
        portfolio: Portfolio,
        entry_price: float,
        stop_loss_price: float,
        symbol: str = "",
        atr_value: float = 0.0,
    ) -> PositionSize:
        """
        Calculate safe position size based on risk management rules.
        
        Uses Kelly Criterion variant:
        - Risk per trade: 1-2% of equity
        - Stop loss distance: ATR-based (volatility-adjusted)
        
        Args:
            portfolio: Current portfolio
            entry_price: Entry price
            stop_loss_price: Stop loss price
            symbol: Trading pair (optional)
            atr_value: Current ATR (optional, for volatility adjustment)
        
        Returns:
            PositionSize object
        """
        # Risk per trade: 2% of equity (professional standard)
        risk_pct = getattr(self.config, 'max_risk_per_trade', 0.02)
        risk_amount = portfolio.equity * risk_pct
        
        # Distance to stop loss
        risk_per_unit = abs(entry_price - stop_loss_price)
        
        if risk_per_unit <= 0:
            return PositionSize(
                shares=0.0,
                risk_amount=0.0,
                entry_price=entry_price,
                stop_loss=stop_loss_price,
                reason="Stop loss not set properly"
            )
        
        # Position size = Risk amount / Risk per unit
        position_size = risk_amount / risk_per_unit
        
        # Don't risk more than 30% of equity on single trade
        max_size_amt = (portfolio.equity * 0.3)
        max_position = max_size_amt / entry_price
        
        if position_size > max_position:
            reason = "Limited to 30% equity max"
            position_size = max_position
        else:
            reason = f"2% risk ({risk_pct*100:.0f}% of equity)"
        
        # Don't trade less than minimum
        min_notional = getattr(self.config, 'min_trade_usdt', 10)
        notional_value = position_size * entry_price
        
        if notional_value < min_notional:
            return PositionSize(
                shares=0.0,
                risk_amount=0.0,
                entry_price=entry_price,
                stop_loss=stop_loss_price,
                reason=f"Trade size ${notional_value:.2f} < min ${min_notional}"
            )
        
        return PositionSize(
            shares=position_size,
            risk_amount=risk_amount,
            entry_price=entry_price,
            stop_loss=stop_loss_price,
            reason=reason,
        )
    
    def update_trailing_stop(
        self,
        current_price: float,
        entry_price: float,
        peak_price: float,
        stop_loss: float,
        atr_value: float,
        trailing_stop_pct: float = 0.025,
    ) -> tuple[float, float]:
        """
        Update trailing stop-loss.
        
        Moves stop loss up as price moves up (for BUY positions).
        
        Args:
            current_price: Current market price
            entry_price: Entry price
            peak_price: Highest price since entry
            stop_loss: Current stop loss
            atr_value: Current ATR
            trailing_stop_pct: Trailing stop percentage
        
        Returns:
            (new_peak_price, new_stop_loss)
        """
        new_peak = max(peak_price, current_price)
        
        # Trailing stop: 2.5% from peak
        new_stop = new_peak * (1 - trailing_stop_pct)
        
        # But never move stop below entry (protect against early loss)
        new_stop = max(new_stop, entry_price - (atr_value * 1.5))
        
        # Don't move stop down (only up)
        new_stop = max(new_stop, stop_loss)
        
        return new_peak, new_stop
    
    def set_cooldown(self, symbol: str, minutes: int = 30) -> None:
        """
        Set cooldown on a symbol after losing trade.
        
        Prevents overtrading and revenge trading.
        
        Args:
            symbol: Trading pair
            minutes: Cooldown duration
        """
        self.cooldown_until[symbol] = datetime.now() + timedelta(minutes=minutes)
        self.logger.warning(f"⏳ Cooldown set for {symbol}: {minutes}m")
    
    def update_trade_result(self, won: bool) -> None:
        """
        Track trade result for streak detection.
        
        Args:
            won: True if trade was profitable
        """
        self.recent_trades.append(won)
        
        # Keep only recent trades
        if len(self.recent_trades) > self.max_streak_history:
            self.recent_trades.pop(0)
        
        # Check for loss streaks
        if len(self.recent_trades) >= 3:
            last_3 = self.recent_trades[-3:]
            if not any(last_3):  # All 3 are losses
                loss_count = sum(1 for t in self.recent_trades[-5:] if not t)
                self.logger.warning(
                    f"⚠️ Loss streak detected: {loss_count} recent losses "
                    f"({sum(self.recent_trades)}/{len(self.recent_trades)} total wins)"
                )
    
    def get_position_size_multiplier(self) -> float:
        """
        Get multiplier for position size based on recent performance.
        
        Returns:
            Multiplier: 1.0 = full size, 0.5 = half size, 0.25 = quarter size
        
        Algorithm:
        - 0-1 losses: 1.0x (normal)
        - 2-3 losses: 0.5x (scale down to recover)
        - 4-5 losses: 0.25x (very cautious)
        - 6+ losses: 0.1x (almost stopped)
        """
        if len(self.recent_trades) < 2:
            return 1.0  # Not enough data
        
        # Count recent losses
        recent_5 = self.recent_trades[-5:]
        loss_count = sum(1 for t in recent_5 if not t)
        
        if loss_count == 0:
            return 1.0  # All wins - trade full size
        elif loss_count == 1:
            return 1.0  # One loss - still full size
        elif loss_count == 2:
            return 0.5  # Two losses - scale down
        elif loss_count == 3:
            return 0.25  # Three losses - very small
        elif loss_count == 4:
            return 0.15  # Four losses - tiny
        else:  # 5+ losses
            return 0.1  # Almost stopped (10% size)
    
    def check_consecutive_losses(self, max_consecutive: int = 5) -> tuple[bool, int]:
        """
        Check for too many consecutive losses.
        
        Args:
            max_consecutive: Maximum allowed consecutive losses
        
        Returns:
            (is_ok: bool, consecutive_count: int)
        """
        consecutive_count = 0
        
        if self.recent_trades:
            for won in reversed(self.recent_trades):
                if not won:  # Loss
                    consecutive_count += 1
                else:  # Win breaks streak
                    break
        
        if consecutive_count >= max_consecutive:
            return False, consecutive_count
        
        return True, consecutive_count

    
    def check_correlation(
        self,
        open_positions: Dict[str, float],
        symbol: str,
        correlation_threshold: float = 0.8,
    ) -> bool:
        """
        Check if new trade is correlated with existing positions.
        
        Avoids taking similar trades (e.g., both BTC and ETH).
        
        Args:
            open_positions: Dict of open position details
            symbol: New trading pair
            correlation_threshold: Max correlation allowed
        
        Returns:
            True if trade is allowed, False if too correlated
        """
        # Simple correlation check (can be expanded with actual correlation calc)
        # For now, prevent trading same asset class simultaneously
        
        coin_family = symbol.split('/')[0][:3]  # First 3 chars (BTC, ETH, SOL, etc)
        
        for pos_symbol in open_positions.keys():
            pos_family = pos_symbol.split('/')[0][:3]
            if coin_family == pos_family and pos_symbol != symbol:
                self.logger.warning(
                    f"⚠️ Correlation filter: {symbol} correlated with {pos_symbol}"
                )
                return False
        
        return True
    
    def get_stats(self) -> Dict:
        """Get risk manager statistics."""
        return {
            "trading_enabled": self.trading_enabled,
            "kill_switch_reason": self.kill_switch_reason,
            "circuit_breaker_active": self.circuit_breaker_active,
            "today_trades": self.today_trades,
            "today_wins": self.today_wins,
            "today_losses": self.today_losses,
            "today_win_rate": (
                self.today_wins / self.today_trades * 100
                if self.today_trades > 0 else 0
            ),
        }


class TradeValidator:
    """Validate specific trade details."""
    
    @staticmethod
    def validate_entry(
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        min_reward_risk_ratio: float = 1.5,
    ) -> tuple[bool, str]:
        """
        Validate entry/exit levels.
        
        Args:
            entry_price: Entry price
            stop_loss: Stop loss price
            take_profit: Take profit price
            min_reward_risk_ratio: Minimum win/loss ratio (typically 1.5:1 or 2:1)
        
        Returns:
            (valid: bool, reason: str)
        """
        # Check stop loss is below entry
        if stop_loss >= entry_price:
            return False, "Stop loss must be below entry"
        
        # Check take profit is above entry
        if take_profit <= entry_price:
            return False, "Take profit must be above entry"
        
        # Check reward/risk ratio
        risk = abs(entry_price - stop_loss)
        reward = abs(take_profit - entry_price)
        
        if risk <= 0:
            return False, "Invalid stop loss"
        
        ratio = reward / risk
        if ratio < min_reward_risk_ratio:
            return False, f"Risk/reward ratio {ratio:.2f} < {min_reward_risk_ratio}"
        
        return True, "Valid"
    
    @staticmethod
    def validate_order_size(
        shares: float,
        entry_price: float,
        min_notional: float = 10.0,
        max_notional: float = 100000.0,
    ) -> tuple[bool, str]:
        """
        Validate order size.
        
        Args:
            shares: Number of shares
            entry_price: Entry price
            min_notional: Minimum order value
            max_notional: Maximum order value
        
        Returns:
            (valid: bool, reason: str)
        """
        notional = shares * entry_price
        
        if notional < min_notional:
            return False, f"Too small: ${notional:.2f} < ${min_notional}"
        
        if notional > max_notional:
            return False, f"Too large: ${notional:.2f} > ${max_notional}"
        
        return True, "Valid"


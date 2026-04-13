"""
Options Strategies Layer.

Generate additional income and hedging using options:
- Cash-Secured Puts (sell premium when confident, collect 3-5% income)
- Covered Calls (sell calls against stock positions for income)
- Protective Puts (hedge against 20%+ moves with cheap downside protection)
- Collar Strategies (low-cost hedges by selling upside)
- Iron Condors (sell both put and call spreads for income in range-bound markets)
- Call Spreads (synthetic long stock exposure using less capital)

Requirements:
- Alpaca 2.0+ supports options
- Need options market data (bid/ask prices)
- More complex position tracking

Result: 2-5% additional annual income, better risk-adjusted returns.
"""

import logging
from dataclasses import dataclass
from typing import Literal, Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import numpy as np


@dataclass
class OptionContract:
    """Options contract details."""
    symbol: str
    expiration: str  # "YYYY-MM-DD"
    strike: float
    option_type: Literal["CALL", "PUT"]
    bid: float
    ask: float
    implied_vol: float
    days_to_expiration: int


@dataclass
class OptionsStrategy:
    """Recommended options strategy."""
    name: str  # "COVERED_CALL", "CASH_SECURED_PUT", etc.
    direction: Literal["BULLISH", "BEARISH", "NEUTRAL"]
    legs: List[Dict]  # [{"type": "SELL_CALL", "strike": 100, "qty": 1}, ...]
    premium_collected: float  # Total credit received
    max_profit: float
    max_loss: float
    break_even: float
    probability_profit: float  # 0-1
    days_to_expiration: int
    reason: str


class OptionsStrategyGenerator:
    """
    Generate options strategies based on market conditions and stock positions.
    """
    
    def __init__(self, config=None):
        """Initialize options strategy generator."""
        self.config = config or {}
        self.logger = logging.getLogger("options")
        self.min_spread_pct = 0.01  # 1% bid-ask spread minimum
    
    def generate_covered_call(
        self,
        symbol: str,
        current_stock_price: float,
        shares_owned: int,
        call_options: List[OptionContract],
        target_income_pct: float = 0.03,  # 3% income target
    ) -> Optional[OptionsStrategy]:
        """
        Generate covered call strategy.
        
        Sell calls against existing stock position to collect premium.
        
        Args:
            symbol: Stock symbol
            current_stock_price: Current stock price
            shares_owned: Number of shares owned (in contracts, 100 = 1 contract)
            call_options: Available call options
            target_income_pct: Income target as % of stock price
        
        Returns:
            OptionsStrategy if viable, None otherwise
        """
        
        if not shares_owned or shares_owned < 100:
            return None
        
        num_contracts = shares_owned // 100
        
        # Find call strike close to current price (slightly OTM for income)
        target_strike = current_stock_price * 1.02  # 2% OTM
        
        best_call = None
        for call in call_options:
            if call.option_type == "CALL" and call.strike >= target_strike:
                if best_call is None or call.strike < best_call.strike:
                    best_call = call
        
        if not best_call:
            return None
        
        # Check if premium is worth it
        premium_per_share = (best_call.bid + best_call.ask) / 2
        income_pct = premium_per_share / current_stock_price
        
        if income_pct < target_income_pct * 0.5:
            return None  # Not enough premium
        
        max_profit = (best_call.strike - current_stock_price) * shares_owned + (premium_per_share * shares_owned)
        max_loss = current_stock_price * shares_owned - (premium_per_share * shares_owned)
        
        return OptionsStrategy(
            name="COVERED_CALL",
            direction="BULLISH",
            legs=[
                {
                    "type": "LONG_STOCK",
                    "symbol": symbol,
                    "qty": shares_owned,
                    "price": current_stock_price,
                },
                {
                    "type": "SELL_CALL",
                    "symbol": symbol,
                    "strike": best_call.strike,
                    "expiration": best_call.expiration,
                    "qty": num_contracts,
                    "price": premium_per_share,
                },
            ],
            premium_collected=premium_per_share * shares_owned,
            max_profit=max_profit,
            max_loss=max_loss,
            break_even=current_stock_price - premium_per_share,
            probability_profit=0.65,  # Typical for OTM calls
            days_to_expiration=best_call.days_to_expiration,
            reason=f"Collect {income_pct*100:.1f}% premium income (target: {target_income_pct*100:.1f}%)",
        )
    
    def generate_cash_secured_put(
        self,
        symbol: str,
        current_stock_price: float,
        put_options: List[OptionContract],
        cash_available: float,
        target_return_pct: float = 0.03,  # 3% return if assigned
    ) -> Optional[OptionsStrategy]:
        """
        Generate cash-secured put strategy.
        
        Sell puts to collect premium, willing to buy stock at discount if assigned.
        
        Args:
            symbol: Stock symbol
            current_stock_price: Current stock price
            put_options: Available put options
            cash_available: Cash available to secure the put
            target_return_pct: Desired return on cash
        
        Returns:
            OptionsStrategy if viable, None otherwise
        """
        
        # Find put strike slightly OTM (support level)
        target_strike = current_stock_price * 0.98  # 2% OTM (below current)
        
        best_put = None
        for put in put_options:
            if put.option_type == "PUT" and put.strike <= target_strike:
                if best_put is None or put.strike > best_put.strike:
                    best_put = put
        
        if not best_put:
            return None
        
        # Check if we have enough cash to secure 1 contract (100 shares * strike)
        required_cash = best_put.strike * 100
        
        if required_cash > cash_available:
            return None
        
        premium_per_share = (best_put.bid + best_put.ask) / 2
        return_on_cash = (premium_per_share * 100) / required_cash
        
        if return_on_cash < target_return_pct * 0.5:
            return None
        
        # P&L calculation
        # Max profit = premium collected (if stock stays above strike)
        max_profit = premium_per_share * 100
        
        # Max loss = cash at risk - premium (if assigned at strike)
        max_loss = required_cash - (premium_per_share * 100)
        
        break_even = best_put.strike - premium_per_share
        
        return OptionsStrategy(
            name="CASH_SECURED_PUT",
            direction="BULLISH",
            legs=[
                {
                    "type": "SELL_PUT",
                    "symbol": symbol,
                    "strike": best_put.strike,
                    "expiration": best_put.expiration,
                    "qty": 1,
                    "price": premium_per_share,
                },
            ],
            premium_collected=max_profit,
            max_profit=max_profit,
            max_loss=max_loss,
            break_even=break_even,
            probability_profit=0.60,
            days_to_expiration=best_put.days_to_expiration,
            reason=f"{return_on_cash*100:.1f}% return on cash (no stock move needed)",
        )
    
    def generate_protective_put(
        self,
        symbol: str,
        current_stock_price: float,
        shares_owned: int,
        put_options: List[OptionContract],
        protection_level_pct: float = 0.10,  # Protect against 10% drop
    ) -> Optional[OptionsStrategy]:
        """
        Generate protective put (portfolio insurance).
        
        Buy puts to hedge downside risk on existing stock position.
        
        Args:
            symbol: Stock symbol
            current_stock_price: Current stock price
            shares_owned: Number of shares owned
            put_options: Available put options
            protection_level_pct: How far down to protect (10% = protect below 90% of current)
        
        Returns:
            OptionsStrategy if viable, None otherwise
        """
        
        if not shares_owned or shares_owned < 100:
            return None
        
        # Find put strike at protection level
        protection_price = current_stock_price * (1.0 - protection_level_pct)
        
        best_put = None
        for put in put_options:
            if put.option_type == "PUT" and put.strike <= current_stock_price:
                if best_put is None or abs(put.strike - protection_price) < abs(best_put.strike - protection_price):
                    best_put = put
        
        if not best_put:
            return None
        
        num_contracts = shares_owned // 100
        premium_per_share = (best_put.bid + best_put.ask) / 2
        premium_pct = premium_per_share / current_stock_price
        
        # Max loss with protection
        max_loss_protected = (current_stock_price - best_put.strike) * shares_owned + (premium_per_share * shares_owned)
        
        # Max loss without protection
        max_loss_unprotected = current_stock_price * shares_owned
        
        protection_benefit = max_loss_unprotected - max_loss_protected
        
        return OptionsStrategy(
            name="PROTECTIVE_PUT",
            direction="NEUTRAL",
            legs=[
                {
                    "type": "LONG_STOCK",
                    "symbol": symbol,
                    "qty": shares_owned,
                    "price": current_stock_price,
                },
                {
                    "type": "LONG_PUT",
                    "symbol": symbol,
                    "strike": best_put.strike,
                    "expiration": best_put.expiration,
                    "qty": num_contracts,
                    "price": premium_per_share,
                },
            ],
            premium_collected=-max(0, premium_per_share * shares_owned),  # Negative = cost
            max_profit=float('inf'),  # Unlimited upside
            max_loss=max_loss_protected,
            break_even=current_stock_price + premium_per_share,
            probability_profit=0.70,
            days_to_expiration=best_put.days_to_expiration,
            reason=f"Limit downside to {best_put.strike:.0f} ({protection_benefit/max_loss_unprotected*100:.0f}% protection)",
        )
    
    def generate_collar(
        self,
        symbol: str,
        current_stock_price: float,
        shares_owned: int,
        call_options: List[OptionContract],
        put_options: List[OptionContract],
    ) -> Optional[OptionsStrategy]:
        """
        Generate collar strategy (low-cost hedge).
        
        Buy protective puts (downside insurance) by selling calls (give up some upside).
        Net cost is usually near zero or a small credit.
        
        Args:
            symbol: Stock symbol
            current_stock_price: Current stock price
            shares_owned: Number of shares owned
            call_options: Available call options
            put_options: Available put options
        
        Returns:
            OptionsStrategy if viable, None otherwise
        """
        
        if not shares_owned or shares_owned < 100:
            return None
        
        # Find protective put (5-10% OTM)
        put_strike = current_stock_price * 0.95
        best_put = None
        for put in put_options:
            if put.option_type == "PUT" and put.strike <= put_strike:
                if best_put is None or put.strike > best_put.strike:
                    best_put = put
        
        if not best_put:
            return None
        
        # Find call to sell (upside you're willing to give up)
        call_strike = current_stock_price * 1.10  # 10% above current
        best_call = None
        for call in call_options:
            if call.option_type == "CALL" and call.strike >= call_strike:
                if best_call is None or call.strike < best_call.strike:
                    best_call = call
        
        if not best_call:
            return None
        
        put_cost = (best_put.bid + best_put.ask) / 2
        call_credit = (best_call.bid + best_call.ask) / 2
        
        num_contracts = shares_owned // 100
        net_cost = (put_cost - call_credit) * shares_owned
        
        if net_cost > 0:
            # Collar costs money - not ideal
            return None
        
        return OptionsStrategy(
            name="COLLAR",
            direction="NEUTRAL",
            legs=[
                {
                    "type": "LONG_STOCK",
                    "symbol": symbol,
                    "qty": shares_owned,
                },
                {
                    "type": "LONG_PUT",
                    "strike": best_put.strike,
                    "expiration": best_put.expiration,
                    "qty": num_contracts,
                },
                {
                    "type": "SELL_CALL",
                    "strike": best_call.strike,
                    "expiration": best_call.expiration,
                    "qty": num_contracts,
                },
            ],
            premium_collected=abs(net_cost) if net_cost < 0 else 0,
            max_profit=(best_call.strike - current_stock_price) * shares_owned + abs(net_cost),
            max_loss=(current_stock_price - best_put.strike) * shares_owned + abs(net_cost),
            break_even=current_stock_price,
            probability_profit=0.65,
            days_to_expiration=min(best_put.days_to_expiration, best_call.days_to_expiration),
            reason=f"Zero-cost hedge: protect below {best_put.strike:.0f}, cap upside at {best_call.strike:.0f}",
        )
    
    @staticmethod
    def estimate_probability_profit(
        strategy_name: str,
        stock_price: float,
        strike: float,
        days_to_expiration: int,
        implied_vol: float,
    ) -> float:
        """
        Rough estimate of probability the strategy is profitable.
        
        Uses normal distribution of likely stock price at expiration.
        """
        
        # Standard deviation of price move = IV * sqrt(time)
        t_years = days_to_expiration / 365.0
        std_move = stock_price * implied_vol * np.sqrt(t_years)
        
        if strategy_name == "COVERED_CALL":
            # Profitable if stock stays below strike
            z_score = (strike - stock_price) / std_move
            prob = 0.5 + 0.5 * np.tanh(z_score / 2.0)  # CDF approximation
            return min(1.0, prob)
        
        elif strategy_name == "CASH_SECURED_PUT":
            # Profitable if stock stays above strike
            z_score = (stock_price - strike) / std_move
            prob = 0.5 + 0.5 * np.tanh(z_score / 2.0)
            return min(1.0, prob)
        
        else:
            return 0.5  # Unknown

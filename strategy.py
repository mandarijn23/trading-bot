"""
Professional Trading Strategies with Composable Architecture.

Base Strategy class allows:
- Multiple strategy implementations
- Filters (trend, volume, volatility)
- Regime detection switching
- Signal confirmation

Strategies included:
1. TrendFollowing - Follow main trend with pullback entries
2. MeanReversion - Buy oversold in uptrend, sell overbought in downtrend
3. Breakout - Trade breakouts of key levels

All strategies use professional indicators like:
- RSI (momentum)
- ATR (volatility, stops)
- EMA (trend)
- Volume confirmation
- Bollinger Bands (volatility)
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Literal, Optional, Dict
import pandas as pd
import numpy as np
from indicators import Indicators, MarketRegime


@dataclass
class StrategySignal:
    """Trading signal with confidence and details."""
    signal: Literal["BUY", "HOLD", "SELL"]
    confidence: float  # 0.0 to 1.0
    entry_price: float
    stop_loss: float
    take_profit: float
    reason: str  # Why this signal was generated
    rsi: float
    trend: str
    atr: float
    volume_confirm: bool


class StrategyFilter:
    """Filters for signal confirmation."""
    
    @staticmethod
    def trend_filter(
        df: pd.DataFrame,
        min_strength: float = 0.5
    ) -> bool:
        """
        Check if in strong trend (avoid sideways markets).
        
        Returns:
            True if in uptrend or downtrend
        """
        trend = MarketRegime.detect_trend(df)
        return trend != "RANGING"
    
    @staticmethod
    def volume_filter(df: pd.DataFrame, period: int = 20) -> bool:
        """
        Check if volume is above average (confirms trend).
        
        Returns:
            True if current volume > average
        """
        avg_vol = df["volume"].tail(period).mean()
        current_vol = df["volume"].iloc[-1]
        return current_vol > avg_vol
    
    @staticmethod
    def volatility_filter(
        df: pd.DataFrame,
        min_atr_pct: float = 0.5,
        max_atr_pct: float = 5.0
    ) -> bool:
        """
        Check if volatility is in acceptable range.
        
        Too low: Low profit potential
        Too high: Stop losses hit too easily
        
        Returns:
            True if volatility is acceptable
        """
        atr = Indicators.atr(df, 14).iloc[-1]
        atr_pct = (atr / df["close"].iloc[-1]) * 100
        return min_atr_pct <= atr_pct <= max_atr_pct
    
    @staticmethod
    def support_resistance_filter(df: pd.DataFrame, period: int = 20) -> bool:
        """
        Check if price is near support/resistance (potential bounce).
        
        Returns:
            True if near support or resistance
        """
        support, resistance = MarketRegime.support_resistance(df, period)
        current_price = df["close"].iloc[-1]
        price_range = resistance - support
        
        # Near support (within 10% of range)
        near_support = abs(current_price - support) < price_range * 0.1
        # Near resistance (within 10% of range)
        near_resistance = abs(current_price - resistance) < price_range * 0.1
        
        return near_support or near_resistance


class BaseStrategy(ABC):
    """
    Abstract base class for all strategies.
    
    Subclasses must implement:
    - get_signal(df) - Generate BUY/HOLD/SELL signal
    """
    
    def __init__(self, name: str):
        self.name = name
        self.filters: list = []
    
    def add_filter(self, filter_fn) -> None:
        """Add a filter that must pass for signal generation."""
        self.filters.append(filter_fn)
    
    def apply_filters(self, df: pd.DataFrame) -> bool:
        """Apply all filters - all must pass."""
        return all(f(df) for f in self.filters)
    
    @abstractmethod
    def generate_signal(self, df: pd.DataFrame) -> StrategySignal:
        """
        Generate trading signal.
        
        Args:
            df: OHLCV DataFrame
        
        Returns:
            StrategySignal object
        """
        pass
    
    def get_signal(self, df: pd.DataFrame) -> StrategySignal:
        """
        Get signal with filter confirmation.
        
        Args:
            df: OHLCV DataFrame
        
        Returns:
            StrategySignal (may suppress signal if filters fail)
        """
        if len(df) < 200:
            return StrategySignal(
                signal="HOLD",
                confidence=0.0,
                entry_price=0.0,
                stop_loss=0.0,
                take_profit=0.0,
                reason="Insufficient data",
                rsi=50.0,
                trend="RANGING",
                atr=0.0,
                volume_confirm=False,
            )
        
        # Generate signal
        signal = self.generate_signal(df)
        
        # If signal is not HOLD, check filters
        if signal.signal != "HOLD":
            if not self.apply_filters(df):
                return StrategySignal(
                    signal="HOLD",
                    confidence=0.0,
                    entry_price=signal.entry_price,
                    stop_loss=signal.stop_loss,
                    take_profit=signal.take_profit,
                    reason=f"Filters blocked: {self.name}",
                    rsi=signal.rsi,
                    trend=signal.trend,
                    atr=signal.atr,
                    volume_confirm=signal.volume_confirm,
                )
        
        return signal


class MeanReversionStrategy(BaseStrategy):
    """
    Mean Reversion Strategy.
    
    Logic:
    - In UPTREND: Buy when RSI oversold (pullback)
    - In DOWNTREND: Sell when RSI overbought (bounce)
    - In RANGING: Trade both sides
    
    Entries validated by:
    - RSI crossing oversold/overbought level
    - Volume confirmation
    - ATR-based position sizing
    """
    
    def __init__(
        self,
        rsi_period: int = 14,
        oversold: float = 30,
        overbought: float = 70,
    ):
        super().__init__("MeanReversion")
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought
    
    def generate_signal(self, df: pd.DataFrame) -> StrategySignal:
        """Generate mean reversion signal."""
        closes = df["close"]
        rsi = Indicators.rsi(closes, self.rsi_period).iloc[-1]
        prev_rsi = Indicators.rsi(closes, self.rsi_period).iloc[-2]
        
        atr = Indicators.atr(df, 14).iloc[-1]
        trend = MarketRegime.detect_trend(df)
        volume_confirm = StrategyFilter.volume_filter(df)
        
        entry_price = float(closes.iloc[-1])
        
        signal = "HOLD"
        confidence = 0.0
        reason = ""
        
        # Uptrend: Buy oversold pullbacks
        if trend == "UPTREND":
            if prev_rsi < self.oversold and rsi >= self.oversold:
                signal = "BUY"
                confidence = 0.7 if volume_confirm else 0.5
                reason = "Oversold bounce in uptrend"
        
        # Downtrend: Sell overbought bounces
        elif trend == "DOWNTREND":
            if prev_rsi > self.overbought and rsi <= self.overbought:
                signal = "SELL"
                confidence = 0.7 if volume_confirm else 0.5
                reason = "Overbought selling in downtrend"
        
        # Ranging: Trade extremes
        else:
            if rsi < self.oversold:
                signal = "BUY"
                confidence = 0.6
                reason = "Oversold in ranging market"
            elif rsi > self.overbought:
                signal = "SELL"
                confidence = 0.6
                reason = "Overbought in ranging market"
        
        # Calculate stops using ATR
        stop_loss = entry_price - (atr * 2.0) if signal == "BUY" else entry_price + (atr * 2.0)
        take_profit = entry_price + (atr * 3.0) if signal == "BUY" else entry_price - (atr * 3.0)
        
        return StrategySignal(
            signal=signal,
            confidence=confidence,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reason=reason,
            rsi=rsi,
            trend=trend,
            atr=atr,
            volume_confirm=volume_confirm,
        )


class TrendFollowingStrategy(BaseStrategy):
    """
    Trend Following Strategy.
    
    Logic:
    - Follow main uptrend/downtrend
    - Enter on pullbacks within trend
    - Exit on trend reversal
    
    Uses:
    - EMA crossover for trend
    - RSI for entry timing
    - ATR for stops
    """
    
    def __init__(
        self,
        ema_fast: int = 9,
        ema_slow: int = 21,
        rsi_period: int = 14,
    ):
        super().__init__("TrendFollowing")
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.rsi_period = rsi_period
    
    def generate_signal(self, df: pd.DataFrame) -> StrategySignal:
        """Generate trend following signal."""
        closes = df["close"]
        
        ema_f = Indicators.ema(closes, self.ema_fast).iloc[-1]
        ema_s = Indicators.ema(closes, self.ema_slow).iloc[-1]
        rsi = Indicators.rsi(closes, self.rsi_period).iloc[-1]
        atr = Indicators.atr(df, 14).iloc[-1]
        
        entry_price = float(closes.iloc[-1])
        trend = MarketRegime.detect_trend(df)
        
        signal = "HOLD"
        confidence = 0.0
        reason = ""
        
        # Uptrend: Price > EMA fast > EMA slow
        if ema_f > ema_s and entry_price > ema_f:
            # Strong uptrend - buy pullbacks to EMA
            distance_to_ema = abs(entry_price - ema_f)
            if distance_to_ema < (atr * 1.5):  # Near EMA
                signal = "BUY"
                confidence = 0.75
                reason = "Pullback in strong uptrend"
        
        # Downtrend: Price < EMA fast < EMA slow
        elif ema_f < ema_s and entry_price < ema_f:
            # Strong downtrend - sell bounces to EMA
            distance_to_ema = abs(entry_price - ema_f)
            if distance_to_ema < (atr * 1.5):  # Near EMA
                signal = "SELL"
                confidence = 0.75
                reason = "Bounce rejected in strong downtrend"
        
        # Calculate stops
        stop_loss = entry_price - (atr * 2.5) if signal == "BUY" else entry_price + (atr * 2.5)
        take_profit = entry_price + (atr * 4.0) if signal == "BUY" else entry_price - (atr * 4.0)
        
        return StrategySignal(
            signal=signal,
            confidence=confidence,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reason=reason,
            rsi=rsi,
            trend=trend,
            atr=atr,
            volume_confirm=StrategyFilter.volume_filter(df),
        )


class BreakoutStrategy(BaseStrategy):
    """
    Breakout Strategy.
    
    Logic:
    - Identify support/resistance levels
    - Buy breakouts above resistance
    - Sell breakouts below support
    - Use volume confirmation
    
    Uses Donchian channels and Keltner channels.
    """
    
    def __init__(self, period: int = 20):
        super().__init__("Breakout")
        self.period = period
    
    def generate_signal(self, df: pd.DataFrame) -> StrategySignal:
        """Generate breakout signal."""
        closes = df["close"]
        
        # Donchian channels
        upper_channel, lower_channel = Indicators.donchian_channel(df, self.period)
        
        # Keltner channels for confirmation
        _, kc_upper, kc_lower = Indicators.keltner_channel(df, self.period)
        
        entry_price = float(closes.iloc[-1])
        prev_close = float(closes.iloc[-2])
        
        atr = Indicators.atr(df, 14).iloc[-1]
        rsi = Indicators.rsi(closes, 14).iloc[-1]
        volume_confirm = StrategyFilter.volume_filter(df)
        
        signal = "HOLD"
        confidence = 0.0
        reason = ""
        
        # Breakout above resistance
        if prev_close <= upper_channel.iloc[-2] and entry_price > upper_channel.iloc[-1]:
            signal = "BUY"
            confidence = 0.8 if volume_confirm else 0.6
            reason = "Breakout above resistance"
        
        # Breakdown below support
        elif prev_close >= lower_channel.iloc[-2] and entry_price < lower_channel.iloc[-1]:
            signal = "SELL"
            confidence = 0.8 if volume_confirm else 0.6
            reason = "Breakdown below support"
        
        # Calculate stops
        stop_loss = lower_channel.iloc[-1] - atr if signal == "BUY" else upper_channel.iloc[-1] + atr
        take_profit = entry_price + (atr * 3.0) if signal == "BUY" else entry_price - (atr * 3.0)
        
        return StrategySignal(
            signal=signal,
            confidence=confidence,
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            reason=reason,
            rsi=rsi,
            trend=MarketRegime.detect_trend(df),
            atr=atr,
            volume_confirm=volume_confirm,
        )


class StrategyManager:
    """
    Manage and select between multiple strategies.
    
    Uses market regime to choose best strategy:
    - Trending market: TrendFollowing
    - Ranging market: MeanReversion
    - Volatile market: Breakout
    """
    
    def __init__(self):
        self.strategies: Dict[str, BaseStrategy] = {
            "mean_reversion": MeanReversionStrategy(),
            "trend_following": TrendFollowingStrategy(),
            "breakout": BreakoutStrategy(),
        }
        
        # Set default filters
        self.strategies["mean_reversion"].add_filter(StrategyFilter.volume_filter)
        self.strategies["trend_following"].add_filter(StrategyFilter.trend_filter)
        self.strategies["breakout"].add_filter(StrategyFilter.volume_filter)
    
    def select_strategy(self, df: pd.DataFrame) -> str:
        """
        Select best strategy based on market regime.
        
        Returns:
            Name of selected strategy
        """
        trend = MarketRegime.detect_trend(df)
        
        if trend == "UPTREND" or trend == "DOWNTREND":
            return "trend_following"
        elif trend == "RANGING":
            atr_pct = (Indicators.atr(df, 14).iloc[-1] / df["close"].iloc[-1]) * 100
            if atr_pct > 2.0:  # High volatility
                return "breakout"
            else:
                return "mean_reversion"
        
        return "mean_reversion"  # Default
    
    def get_signal(self, df: pd.DataFrame) -> StrategySignal:
        """
        Get signal from best strategy for current market regime.
        
        Returns:
            StrategySignal from selected strategy
        """
        selected = self.select_strategy(df)
        return self.strategies[selected].get_signal(df)


# ==== BACKWARD COMPATIBILITY ====
# Keep old function signatures for existing code

def get_signal(
    df: pd.DataFrame,
    rsi_period: int = 14,
    oversold: float = 30,
    **kwargs
) -> Literal["BUY", "HOLD"]:
    """
    Legacy function - returns simple BUY/HOLD signal.
    
    Uses mean reversion strategy by default.
    """
    strategy = MeanReversionStrategy(rsi_period=rsi_period, oversold=oversold)
    signal_obj = strategy.get_signal(df)
    return signal_obj.signal


def get_signal_enhanced(
    df: pd.DataFrame,
    rsi_period: int = 14,
    oversold: float = 30,
    overbought: float = 70,
) -> tuple[Literal["BUY", "HOLD"], StrategySignal]:
    """
    Legacy function - returns signal with details.
    
    Uses mean reversion strategy by default.
    """
    strategy = MeanReversionStrategy(
        rsi_period=rsi_period,
        oversold=oversold,
        overbought=overbought
    )
    signal_obj = strategy.get_signal(df)
    return signal_obj.signal, signal_obj



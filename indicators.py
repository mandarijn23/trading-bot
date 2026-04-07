"""
Professional Trading Indicators Module

Provides reusable technical analysis indicators:
- ATR (Average True Range) - volatility
- RSI (Relative Strength Index) - momentum
- EMA (Exponential Moving Average) - trend
- Bollinger Bands - volatility and reversal
- MACD - trend confirmation
- Volume Rate of Change - volume analysis
- Donchian Channels - breakout
"""

from typing import Tuple
import pandas as pd
import numpy as np


class Indicators:
    """Professional technical indicators for trading."""
    
    @staticmethod
    def atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        Average True Range - volatility measure.
        
        Higher ATR = higher volatility = wider stops needed.
        Used for dynamic position sizing and stop-loss placement.
        
        Args:
            df: DataFrame with 'high', 'low', 'close'
            period: ATR period (default 14)
        
        Returns:
            Series of ATR values
        """
        high = df["high"]
        low = df["low"]
        close = df["close"]
        
        # True Range = max(H-L, |H-Pc|, |L-Pc|)
        tr1 = high - low
        tr2 = (high - close.shift()).abs()
        tr3 = (low - close.shift()).abs()
        tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
        
        # Smoothed average
        atr = tr.rolling(window=period).mean()
        return atr
    
    @staticmethod
    def rsi(closes: pd.Series, period: int = 14) -> pd.Series:
        """
        Relative Strength Index - momentum oscillator.
        
        Values:
        - < 30: Oversold (potential bounce)
        - 30-70: Neutral
        - > 70: Overbought (potential reversal)
        
        Args:
            closes: Series of close prices
            period: RSI period (default 14)
        
        Returns:
            Series of RSI values (0-100)
        """
        delta = closes.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        
        avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
        avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
        
        rs = pd.Series(50.0, index=closes.index)
        mask = avg_loss > 0
        rs[mask] = avg_gain[mask] / avg_loss[mask]
        
        rsi = 100 - (100 / (1 + rs))
        rsi[(avg_loss == 0) & (avg_gain > 0)] = 100.0
        rsi[(avg_loss == 0) & (avg_gain == 0)] = 50.0
        
        return rsi
    
    @staticmethod
    def ema(closes: pd.Series, period: int = 20) -> pd.Series:
        """
        Exponential Moving Average - trend indicator.
        
        Reacts faster to recent prices than SMA.
        
        - Price above EMA: Uptrend
        - Price below EMA: Downtrend
        
        Args:
            closes: Series of close prices
            period: EMA period
        
        Returns:
            Series of EMA values
        """
        return closes.ewm(span=period, adjust=False).mean()
    
    @staticmethod
    def sma(closes: pd.Series, period: int = 20) -> pd.Series:
        """
        Simple Moving Average - trend indicator.
        
        Args:
            closes: Series of close prices
            period: SMA period
        
        Returns:
            Series of SMA values
        """
        return closes.rolling(window=period).mean()
    
    @staticmethod
    def bollinger_bands(closes: pd.Series, period: int = 20, std_dev: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Bollinger Bands - volatility bands around SMA.
        
        Usage:
        - Price near upper band: Potential overbought
        - Price near lower band: Potential oversold
        - Band width: Volatility measure
        
        Args:
            closes: Series of close prices
            period: SMA period
            std_dev: Number of standard deviations (typically 2)
        
        Returns:
            (middle_band, upper_band, lower_band)
        """
        sma = closes.rolling(window=period).mean()
        std = closes.rolling(window=period).std()
        upper = sma + (std * std_dev)
        lower = sma - (std * std_dev)
        
        return sma, upper, lower
    
    @staticmethod
    def macd(closes: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        MACD (Moving Average Convergence Divergence) - trend confirmation.
        
        Usage:
        - MACD > Signal: Bullish
        - MACD < Signal: Bearish
        - Histogram: Momentum (difference between MACD and signal)
        
        Args:
            closes: Series of close prices
            fast: Fast EMA period (default 12)
            slow: Slow EMA period (default 26)
            signal: Signal line period (default 9)
        
        Returns:
            (macd_line, signal_line, histogram)
        """
        ema_fast = closes.ewm(span=fast, adjust=False).mean()
        ema_slow = closes.ewm(span=slow, adjust=False).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line
        
        return macd_line, signal_line, histogram
    
    @staticmethod
    def volume_roc(volumes: pd.Series, period: int = 14) -> pd.Series:
        """
        Volume Rate of Change - momentum of volume.
        
        Positive ROC: Volume increasing (strong trend)
        Negative ROC: Volume decreasing (weak trend)
        
        Args:
            volumes: Series of volume values
            period: ROC period
        
        Returns:
            Series of volume ROC (%)
        """
        vol_roc = volumes.pct_change(periods=period) * 100
        return vol_roc
    
    @staticmethod
    def donchian_channel(df: pd.DataFrame, period: int = 20) -> Tuple[pd.Series, pd.Series]:
        """
        Donchian Channels - breakout levels.
        
        Highest high and lowest low over N periods.
        Useful for:
        - Breakout detection
        - Support/resistance
        - Stop-loss placement
        
        Args:
            df: DataFrame with 'high', 'low'
            period: Channel period
        
        Returns:
            (upper_channel, lower_channel)
        """
        upper = df["high"].rolling(window=period).max()
        lower = df["low"].rolling(window=period).min()
        
        return upper, lower
    
    @staticmethod
    def keltner_channel(df: pd.DataFrame, period: int = 20, atr_period: int = 10, multiplier: float = 2.0) -> Tuple[pd.Series, pd.Series, pd.Series]:
        """
        Keltner Channels - volatility bands using ATR.
        
        Better than Bollinger Bands in trending markets.
        
        Args:
            df: DataFrame with OHLCV
            period: EMA period for center line
            atr_period: ATR period
            multiplier: ATR multiplier for bands (typically 2)
        
        Returns:
            (middle_line, upper_band, lower_band)
        """
        middle = df["close"].ewm(span=period, adjust=False).mean()
        atr = Indicators.atr(df, atr_period)
        upper = middle + (atr * multiplier)
        lower = middle - (atr * multiplier)
        
        return middle, upper, lower
    
    @staticmethod
    def stochastic(df: pd.DataFrame, period: int = 14, smooth_k: int = 3, smooth_d: int = 3) -> Tuple[pd.Series, pd.Series]:
        """
        Stochastic Oscillator - momentum and overbought/oversold.
        
        Values:
        - < 20: Oversold
        - 20-80: Neutral
        - > 80: Overbought
        
        Args:
            df: DataFrame with 'high', 'low', 'close'
            period: Stochastic period
            smooth_k: K% smoothing period
            smooth_d: D% smoothing period
        
        Returns:
            (k_line, d_line) both 0-100
        """
        lowest_low = df["low"].rolling(window=period).min()
        highest_high = df["high"].rolling(window=period).max()
        
        k_raw = 100 * (df["close"] - lowest_low) / (highest_high - lowest_low + 1e-9)
        k_line = k_raw.rolling(window=smooth_k).mean()
        d_line = k_line.rolling(window=smooth_d).mean()
        
        return k_line, d_line
    
    @staticmethod
    def atr_percent(df: pd.DataFrame, period: int = 14) -> pd.Series:
        """
        ATR as percentage of close price.
        
        Useful for comparing volatility across different price levels.
        
        Args:
            df: DataFrame with OHLCV
            period: ATR period
        
        Returns:
            Series of ATR% values
        """
        atr = Indicators.atr(df, period)
        atr_pct = (atr / df["close"]) * 100
        return atr_pct


class MarketRegime:
    """Detect market regime (trending vs ranging)."""
    
    @staticmethod
    def detect_trend(df: pd.DataFrame, period: int = 20) -> str:
        """
        Detect if market is in uptrend or downtrend.
        
        Uses EMA positioning and ADX concept.
        
        Returns: "UPTREND", "DOWNTREND", or "RANGING"
        """
        ema_short = Indicators.ema(df["close"], 9)
        ema_long = Indicators.ema(df["close"], 21)
        
        # Check ADX-like concept (trend strength)
        high_recent = df["high"].tail(14).max()
        low_recent = df["low"].tail(14).min()
        
        close = df["close"].iloc[-1]
        ema_s = ema_short.iloc[-1]
        ema_l = ema_long.iloc[-1]
        
        # Price positioning
        if close > ema_s > ema_l:
            trend_strength = (close - ema_l) / (high_recent - low_recent + 1e-9)
            if trend_strength > 0.4:
                return "UPTREND"
        elif close < ema_s < ema_l:
            trend_strength = (ema_l - close) / (high_recent - low_recent + 1e-9)
            if trend_strength > 0.4:
                return "DOWNTREND"
        
        return "RANGING"
    
    @staticmethod
    def support_resistance(df: pd.DataFrame, period: int = 20) -> Tuple[float, float]:
        """
        Calculate dynamic support and resistance.
        
        Returns:
            (support_level, resistance_level)
        """
        resistance = df["high"].tail(period).max()
        support = df["low"].tail(period).min()
        
        return support, resistance

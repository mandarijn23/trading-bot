"""
RSI Mean Reversion Strategy — with 200 MA + Volume + ATR.

Strategy:
- Only BUYs when price is ABOVE the 200 MA (trend filter)
- RSI recovers ABOVE oversold level (mean reversion signal)
- Volume must be above average (confirms the move)
- Stop loss uses ATR (adapts to volatility, not fixed %)
- Trailing stop locks in profits
"""

from typing import Literal, NamedTuple
import pandas as pd
import numpy as np


class StrategySignal(NamedTuple):
    """Trading signal with details."""
    signal: Literal["BUY", "HOLD"]
    rsi: float
    volume_confirm: bool
    atr: float
    stop_loss_atr: float


def calculate_atr(df: pd.DataFrame, period: int = 14) -> pd.Series:
    """
    Calculate Average True Range for volatility-based stops.
    
    Args:
        df: DataFrame with high, low, close columns
        period: ATR period
    
    Returns:
        Series of ATR values
    """
    high = df["high"]
    low = df["low"]
    close = df["close"]
    
    # True range: max of (H-L, |H-Pc|, |L-Pc|)
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    
    # Average true range
    atr = tr.rolling(period).mean()
    return atr


def calculate_rsi(closes: pd.Series, period: int = 14) -> pd.Series:
    """
    Calculate Relative Strength Index (RSI).
    
    Args:
        closes: Series of close prices
        period: RSI period (default 14)
    
    Returns:
        Series of RSI values
    """
    delta: pd.Series = closes.diff()
    gain: pd.Series = delta.clip(lower=0)
    loss: pd.Series = -delta.clip(upper=0)
    avg_gain: pd.Series = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss: pd.Series = loss.ewm(com=period - 1, min_periods=period).mean()
    rs: pd.Series = avg_gain / avg_loss.replace(0, 1e-9)
    return 100 - (100 / (1 + rs))


def get_signal(
    df: pd.DataFrame,
    rsi_period: int = 14,
    oversold: float = 30,
    overbought: float = 70,
) -> Literal["BUY", "HOLD"]:
    """
    Generate trading signal based on RSI and 200-period moving average.
    
    Args:
        df: DataFrame with OHLCV data (must have 'close' column)
        rsi_period: RSI calculation period
        oversold: RSI oversold threshold for BUY signal
        overbought: RSI overbought threshold (not used in current strategy)
    
    Returns:
        Signal: "BUY" or "HOLD"
    """
    signal, _ = get_signal_enhanced(df, rsi_period, oversold, overbought)
    return signal


def get_signal_enhanced(
    df: pd.DataFrame,
    rsi_period: int = 14,
    oversold: float = 30,
    overbought: float = 70,
) -> tuple[Literal["BUY", "HOLD"], StrategySignal]:
    """
    Generate trading signal with volume confirmation and ATR stop loss.
    
    Args:
        df: DataFrame with OHLCV data (must have 'close', 'volume' columns)
        rsi_period: RSI calculation period
        oversold: RSI oversold threshold
        overbought: RSI overbought threshold (not used)
    
    Returns:
        Tuple of (signal, StrategySignal details)
    
    Raises:
        ValueError: If DataFrame is missing required columns or insufficient data
    """
    required = ["close", "high", "low", "volume"]
    if not all(col in df.columns for col in required):
        raise ValueError(f"DataFrame must contain {required} columns")
    
    if len(df) < 200:
        return "HOLD", StrategySignal("HOLD", 0, False, 0, 0)
    
    closes: pd.Series = df["close"]
    rsi: pd.Series = calculate_rsi(closes, rsi_period)
    ma200: pd.Series = closes.rolling(200).mean()
    atr: pd.Series = calculate_atr(df, period=14)
    
    # Volume confirmation
    avg_volume = df["volume"].rolling(20).mean()
    current_volume = df["volume"].iloc[-1]
    volume_confirm = current_volume > avg_volume.iloc[-1]
    
    # Price and trend
    price: float = float(closes.iloc[-1])
    trend_up: bool = price > float(ma200.iloc[-1])
    
    # RSI signal
    prev_rsi: float = float(rsi.iloc[-2])
    curr_rsi: float = float(rsi.iloc[-1])
    atr_value: float = float(atr.iloc[-1])
    
    # Buy signal: RSI recovers above oversold + volume confirms + price above MA
    signal = "HOLD"
    if trend_up and prev_rsi < oversold and curr_rsi >= oversold and volume_confirm:
        signal = "BUY"
    elif trend_up and prev_rsi < oversold and curr_rsi >= oversold:
        # Signal but no volume confirmation
        pass
    
    # ATR-based stop loss: typically 2x ATR below entry
    stop_loss_atr = price - (2.0 * atr_value)
    
    return signal, StrategySignal(signal, curr_rsi, volume_confirm, atr_value, stop_loss_atr)


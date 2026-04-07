"""
RSI Mean Reversion Strategy — with 200 MA Trend Filter + Trailing Stop.

- Only BUYs when price is ABOVE the 200 MA (no buying in downtrends)
- Uses trailing stop to lock in profits as price rises
- Removes RSI_SELL as exit — let TP and trailing stop do the work
"""

from typing import Literal
import pandas as pd
import numpy as np


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
    
    Raises:
        ValueError: If DataFrame is missing required columns or insufficient data
    """
    if "close" not in df.columns:
        raise ValueError("DataFrame must contain 'close' column")
    
    if len(df) < 200:
        return "HOLD"

    closes: pd.Series = df["close"]
    rsi: pd.Series = calculate_rsi(closes, rsi_period)
    ma200: pd.Series = closes.rolling(200).mean()

    prev_rsi: float = float(rsi.iloc[-2])
    curr_rsi: float = float(rsi.iloc[-1])
    price: float = float(closes.iloc[-1])
    trend_up: bool = price > float(ma200.iloc[-1])

    # Buy signal: RSI recovers ABOVE oversold level AND price above 200 MA
    # (Not RSI falling INTO oversold - that would be the start of further decline)
    if trend_up and prev_rsi < oversold and curr_rsi >= oversold:
        return "BUY"
    
    return "HOLD"


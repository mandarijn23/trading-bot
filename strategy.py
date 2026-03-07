"""
RSI Mean Reversion Strategy
----------------------------
Logic:
  - BUY  when RSI crosses BELOW the oversold threshold  (e.g. 30) → price likely to bounce up
  - SELL when RSI crosses ABOVE the overbought threshold (e.g. 70) → price likely to pull back

This exploits short-term overreactions in the market.
"""

import pandas as pd


def calculate_rsi(closes: pd.Series, period: int = 14) -> pd.Series:
    """Compute RSI from a series of closing prices."""
    delta = closes.diff()
    gain  = delta.clip(lower=0)
    loss  = -delta.clip(upper=0)

    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()

    rs  = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi


def get_signal(df: pd.DataFrame, rsi_period: int, oversold: float, overbought: float) -> str:
    """
    Analyse the latest candles and return a signal.

    Returns:
        "BUY"   – RSI just crossed below oversold level
        "SELL"  – RSI just crossed above overbought level
        "HOLD"  – no actionable signal
    """
    if len(df) < rsi_period + 2:
        return "HOLD"

    closes = df["close"]
    rsi    = calculate_rsi(closes, rsi_period)

    prev_rsi = rsi.iloc[-2]
    curr_rsi = rsi.iloc[-1]

    if prev_rsi >= oversold and curr_rsi < oversold:
        return "BUY"
    elif prev_rsi <= overbought and curr_rsi > overbought:
        return "SELL"
    return "HOLD"

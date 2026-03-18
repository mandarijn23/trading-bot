"""
RSI Mean Reversion Strategy — with 200 MA Trend Filter + Trailing Stop
------------------------------------------------------------------------
- Only BUYs when price is ABOVE the 200 MA (no buying in downtrends)
- Uses trailing stop to lock in profits as price rises
- Removes RSI_SELL as exit — let TP and trailing stop do the work
"""

import pandas as pd


def calculate_rsi(closes: pd.Series, period: int = 14) -> pd.Series:
    delta    = closes.diff()
    gain     = delta.clip(lower=0)
    loss     = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
    avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
    rs       = avg_gain / avg_loss.replace(0, 1e-9)
    return 100 - (100 / (1 + rs))


def get_signal(df: pd.DataFrame, rsi_period: int, oversold: float) -> str:
    if len(df) < 200:
        return "HOLD"

    closes   = df["close"]
    rsi      = calculate_rsi(closes, rsi_period)
    ma200    = closes.rolling(200).mean()

    prev_rsi = rsi.iloc[-2]
    curr_rsi = rsi.iloc[-1]
    price    = closes.iloc[-1]
    trend_up = price > ma200.iloc[-1]

    if trend_up and prev_rsi >= oversold and curr_rsi < oversold:
        return "BUY"
    return "HOLD"

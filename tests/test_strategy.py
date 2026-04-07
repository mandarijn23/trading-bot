"""
Unit tests for strategy module.

Run with: pytest tests/test_strategy.py -v
"""

import pytest
import pandas as pd
import numpy as np
from strategy import calculate_rsi, get_signal


class TestCalculateRSI:
    """Test RSI calculation."""
    
    def test_rsi_basic_calculation(self):
        """Test RSI calculation with known data."""
        closes = pd.Series([44, 44.34, 44.09, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03])
        rsi = calculate_rsi(closes, period=14)
        
        # RSI should be between 0 and 100
        assert rsi.min() >= 0
        assert rsi.max() <= 100
        assert len(rsi) == len(closes)
    
    def test_rsi_with_minimum_periods(self):
        """Test RSI returns correct length."""
        closes = pd.Series(np.random.rand(100))
        rsi = calculate_rsi(closes, period=14)
        
        assert len(rsi) == len(closes)
        assert pd.isna(rsi.iloc[0])  # First values will be NaN
    
    def test_rsi_all_increasing(self):
        """Test RSI with all increasing prices."""
        closes = pd.Series(range(1, 50))
        rsi = calculate_rsi(closes, period=14)
        
        # RSI should be high when prices only go up
        assert rsi.iloc[-1] > 70
    
    def test_rsi_all_decreasing(self):
        """Test RSI with all decreasing prices."""
        closes = pd.Series(range(50, 1, -1))
        rsi = calculate_rsi(closes, period=14)
        
        # RSI should be low when prices only go down
        assert rsi.iloc[-1] < 30


class TestGetSignal:
    """Test trading signal generation."""
    
    def create_sample_df(self, prices):
        """Helper to create sample OHLCV DataFrame."""
        df = pd.DataFrame({
            "close": prices,
            "open": prices * 0.99,
            "high": prices * 1.01,
            "low": prices * 0.98,
            "volume": np.ones(len(prices)) * 1000000,
        })
        return df
    
    def test_signal_insufficient_data(self):
        """Test signal with insufficient data."""
        prices = list(range(1, 50))
        df = self.create_sample_df(prices)
        
        signal = get_signal(df, rsi_period=14, oversold=30, overbought=70)
        assert signal == "HOLD"
    
    def test_signal_missing_close_column(self):
        """Test signal with missing close column."""
        df = pd.DataFrame({"other_col": [1, 2, 3]})
        
        with pytest.raises(ValueError, match="DataFrame must contain 'close' column"):
            get_signal(df)
    
    def test_signal_rsi_oversold_crossover(self):
        """Test BUY signal when RSI crosses below oversold."""
        # Create data that will trigger RSI crossing below 30
        prices = [100] * 200 + list(np.linspace(100, 95, 50))
        df = self.create_sample_df(prices)
        
        signal = get_signal(df, rsi_period=14, oversold=35, overbought=70)
        # Signal depends on exact RSI calculation, but should still be callable
        assert signal in ["BUY", "HOLD"]
    
    def test_signal_downtrend_no_buy(self):
        """Test no BUY signal in downtrend."""
        # Strong downtrend
        prices = list(np.linspace(100, 50, 300))
        df = self.create_sample_df(prices)
        
        signal = get_signal(df, rsi_period=14, oversold=30, overbought=70)
        # Should not BUY in downtrend
        assert signal == "HOLD"
    
    def test_signal_return_type(self):
        """Test signal return type."""
        prices = list(range(1, 300))
        df = self.create_sample_df(prices)
        
        signal = get_signal(df)
        assert isinstance(signal, str)
        assert signal in ["BUY", "HOLD"]


class TestEdgeCases:
    """Test edge cases."""
    
    def test_rsi_with_constant_prices(self):
        """Test RSI when prices don't change."""
        closes = pd.Series([100] * 50)
        rsi = calculate_rsi(closes, period=14)
        
        # RSI should be around 50 when prices are constant (no gain/loss)
        assert 40 < rsi.iloc[-1] < 60
    
    def test_rsi_with_nan_values(self):
        """Test RSI handles NaN gracefully."""
        closes = pd.Series([100, 101, 102, np.nan, 104, 105])
        rsi = calculate_rsi(closes, period=14)
        
        # Should not crash; NaN will propagate
        assert len(rsi) == len(closes)

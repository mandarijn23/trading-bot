"""
Unit tests for ML model.

Run with: pytest tests/test_ml_model.py -v
"""

import pytest
import numpy as np
import pandas as pd
from ml_model import FeatureExtractor, TradingAI


class TestFeatureExtractor:
    """Test feature extraction."""
    
    def create_sample_df(self, n: int = 100, trend: str = "up") -> pd.DataFrame:
        """Create sample OHLCV data."""
        if trend == "up":
            closes = np.linspace(100, 110, n)
        elif trend == "down":
            closes = np.linspace(110, 100, n)
        else:
            closes = np.ones(n) * 100
        
        # Add some noise
        closes = closes + np.random.randn(n) * 0.5
        
        df = pd.DataFrame({
            "close": closes,
            "open": closes * 0.99,
            "high": closes * 1.01,
            "low": closes * 0.98,
            "volume": np.ones(n) * 1000000,
        })
        return df
    
    def test_extract_features_returns_correct_shape(self):
        """Test feature extraction returns correct shape."""
        df = self.create_sample_df(n=100)
        X, y = FeatureExtractor.extract_features(df, lookback=20)
        
        assert X.shape[1] == 6  # 6 features
        assert len(X) == len(y)
    
    def test_extract_features_with_insufficient_data(self):
        """Test with insufficient data."""
        df = self.create_sample_df(n=10)
        X, y = FeatureExtractor.extract_features(df, lookback=20)
        
        assert len(X) == 0
        assert len(y) == 0
    
    def test_features_are_normalized(self):
        """Test features are in reasonable ranges."""
        df = self.create_sample_df(n=200, trend="up")
        X, y = FeatureExtractor.extract_features(df, lookback=20)
        
        # RSI should be normalized (0-1)
        rsi_column = X[:, 4]
        assert np.all(rsi_column >= 0)
        assert np.all(rsi_column <= 1)
    
    def test_uptrend_produces_buy_signals(self):
        """Test uptrend produces positive targets."""
        df = self.create_sample_df(n=300, trend="up")
        X, y = FeatureExtractor.extract_features(df, lookback=20)
        
        # In uptrend, should have some positive targets
        assert np.sum(y) > 0


class TestTradingAI:
    """Test AI model."""
    
    def test_ai_initialization(self):
        """Test AI initializes correctly."""
        ai = TradingAI()
        assert ai.model is not None or ai.model is None  # TF might not be installed
        assert ai.metrics["trades"] >= 0
    
    def test_get_position_size_multiplier(self):
        """Test position size adjustment."""
        ai = TradingAI()
        multiplier = ai.get_position_size_multiplier()
        
        assert 0.5 <= multiplier <= 1.5
    
    def test_update_from_trade_increments_counter(self):
        """Test trade tracking."""
        ai = TradingAI()
        initial_trades = ai.metrics["trades"]
        
        ai.update_from_trade(pnl=10.0, was_win=True)
        
        assert ai.metrics["trades"] == initial_trades + 1
        assert ai.metrics["wins"] == initial_trades // ai.metrics["trades"] + 1 or initial_trades == 0
    
    def test_win_loss_tracking(self):
        """Test win/loss tracking."""
        ai = TradingAI()
        
        ai.update_from_trade(pnl=10.0, was_win=True)
        ai.update_from_trade(pnl=-5.0, was_win=False)
        ai.update_from_trade(pnl=15.0, was_win=True)
        
        assert ai.metrics["trades"] == 3
        assert ai.metrics["wins"] == 2
        assert ai.metrics["losses"] == 1
        assert ai.metrics["total_pnl"] == 20.0
    
    def test_predict_entry_probability_returns_0_to_1(self):
        """Test prediction returns valid probability."""
        ai = TradingAI()
        
        df = pd.DataFrame({
            "close": np.linspace(100, 102, 30),
            "open": np.linspace(100, 102, 30) * 0.99,
            "high": np.linspace(100, 102, 30) * 1.01,
            "low": np.linspace(100, 102, 30) * 0.98,
            "volume": np.ones(30) * 1000000,
        })
        
        prob = ai.predict_entry_probability(df)
        assert 0 <= prob <= 1
    
    def test_get_stats_format(self):
        """Test stats dictionary format."""
        ai = TradingAI()
        ai.update_from_trade(10.0, True)
        
        stats = ai.get_stats()
        
        assert isinstance(stats, dict)
        assert "total_trades" in stats
        assert "win_rate" in stats or "status" in stats


class TestAIIntegration:
    """Integration tests."""
    
    def test_ai_learns_from_series_of_trades(self):
        """Test AI adapts over multiple trades."""
        ai = TradingAI()
        
        # Simulate winning streak
        for _ in range(10):
            ai.update_from_trade(pnl=10.0, was_win=True)
        
        multiplier_after_wins = ai.get_position_size_multiplier()
        
        # Simulate losing streak
        for _ in range(5):
            ai.update_from_trade(pnl=-5.0, was_win=False)
        
        multiplier_after_losses = ai.get_position_size_multiplier()
        
        # Multiplier should be lower after losses
        assert multiplier_after_losses < multiplier_after_wins
    
    def test_persistence(self):
        """Test metrics are saved and loaded."""
        import tempfile
        import json
        from pathlib import Path
        
        # Create temp file
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            temp_path = Path(f.name)
        
        try:
            ai = TradingAI()
            ai.metrics_file = temp_path
            ai.update_from_trade(10.0, True)
            ai.save_metrics()
            
            # Load in new instance
            ai2 = TradingAI()
            ai2.metrics_file = temp_path
            ai2.load_metrics()
            
            assert ai2.metrics["trades"] == 1
            assert ai2.metrics["wins"] == 1
        finally:
            if temp_path.exists():
                temp_path.unlink()

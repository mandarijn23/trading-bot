"""
Unit tests for configuration module.

Run with: pytest tests/test_config.py -v
"""

import pytest
import os
from pydantic import ValidationError
from stock_config import StockTradingConfig, load_stock_config


class TestTradingConfig:
    """Test configuration validation."""
    
    def test_config_defaults(self):
        """Test default configuration values."""
        config = StockTradingConfig(
            alpaca_api_key="test_key",
            alpaca_api_secret="test_secret"
        )
        
        assert config.rsi_period == 14
        assert config.rsi_oversold == 35
        assert config.paper_trading is True
        assert config.trade_amount_usd == 20.0
    
    def test_config_custom_values(self):
        """Test setting custom configuration values."""
        config = StockTradingConfig(
            alpaca_api_key="test_key",
            alpaca_api_secret="test_secret",
            rsi_period=15,
            trade_amount_usd=50.0,
        )
        
        assert config.rsi_period == 15
        assert config.trade_amount_usd == 50.0
    
    def test_config_symbol_parsing(self):
        """Test parsing symbols from string."""
        config = StockTradingConfig(
            alpaca_api_key="test_key",
            alpaca_api_secret="test_secret",
            symbols="BTC/USDT,ETH/USDT"
        )
        
        assert config.symbols == ["BTC/USDT", "ETH/USDT"]
    
    def test_config_rsi_oversold_validation(self):
        """Test RSI oversold must be less than overbought."""
        with pytest.raises(ValidationError):
            StockTradingConfig(
                alpaca_api_key="test_key",
                alpaca_api_secret="test_secret",
                rsi_oversold=80,  # Greater than overbought default 70
            )
    
    def test_config_rsi_period_bounds(self):
        """Test RSI period bounds."""
        # Too low
        with pytest.raises(ValidationError):
            StockTradingConfig(
                alpaca_api_key="test_key",
                alpaca_api_secret="test_secret",
                rsi_period=1,
            )
        
        # Too high
        with pytest.raises(ValidationError):
            StockTradingConfig(
                alpaca_api_key="test_key",
                alpaca_api_secret="test_secret",
                rsi_period=201,
            )
        
        # Valid
        config = StockTradingConfig(
            alpaca_api_key="test_key",
            alpaca_api_secret="test_secret",
            rsi_period=50,
        )
        assert config.rsi_period == 50
    
    def test_config_trade_amount_positive(self):
        """Test trade amount must be positive."""
        with pytest.raises(ValidationError):
            StockTradingConfig(
                alpaca_api_key="test_key",
                alpaca_api_secret="test_secret",
                trade_amount_usd=0,
            )
    
    def test_config_stop_loss_bounds(self):
        """Test stop loss percentage bounds."""
        with pytest.raises(ValidationError):
            StockTradingConfig(
                alpaca_api_key="test_key",
                alpaca_api_secret="test_secret",
                stop_loss_pct=1.5,  # Greater than 1 (100%)
            )
        
        config = StockTradingConfig(
            alpaca_api_key="test_key",
            alpaca_api_secret="test_secret",
            stop_loss_pct=0.05,
        )
        assert config.stop_loss_pct == 0.05
    
    def test_config_missing_required_fields(self):
        """Test missing required API keys."""
        os.environ.pop("ALPACA_API_KEY", None)
        os.environ.pop("ALPACA_API_SECRET", None)
        with pytest.raises(ValidationError):
            StockTradingConfig(_env_file=None)
    
    def test_config_check_interval_positive(self):
        """Test check interval must be positive."""
        with pytest.raises(ValidationError):
            StockTradingConfig(
                alpaca_api_key="test_key",
                alpaca_api_secret="test_secret",
                check_interval=0,
            )

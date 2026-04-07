"""
Configuration module with validation and type hints.
Load settings from .env file or environment variables.
"""

import os
from typing import List
from dotenv import load_dotenv
from pydantic import Field, field_validator, ConfigDict
from pydantic_settings import BaseSettings


load_dotenv()


class TradingConfig(BaseSettings):
    """Trading bot configuration with validation."""
    
    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore"  # Ignore extra fields from .env
    )
    
    # API Keys
    binance_api_key: str = Field(..., env="BINANCE_API_KEY")
    binance_api_secret: str = Field(..., env="BINANCE_API_SECRET")
    
    # Trading symbols
    symbols: List[str] = Field(default=["BTC/USDT", "ETH/USDT", "SOL/USDT"], env="SYMBOLS")
    timeframe: str = Field(default="1h", env="TIMEFRAME")
    
    # RSI Settings
    rsi_period: int = Field(default=10, ge=2, le=200, env="RSI_PERIOD")
    rsi_oversold: float = Field(default=35, ge=0, le=50, env="RSI_OVERSOLD")
    rsi_overbought: float = Field(default=70, ge=50, le=100, env="RSI_OVERBOUGHT")
    
    # Risk Management
    trade_amount_usdt: float = Field(default=20.0, gt=0, env="TRADE_AMOUNT_USDT")
    trailing_stop_pct: float = Field(default=0.025, gt=0, lt=1, env="TRAILING_STOP_PCT")
    cooldown_candles: int = Field(default=8, ge=0, env="COOLDOWN_CANDLES")
    stop_loss_pct: float = Field(default=0.03, gt=0, lt=1, env="STOP_LOSS_PCT")
    take_profit_pct: float = Field(default=0.08, gt=0, lt=1, env="TAKE_PROFIT_PCT")
    
    # Bot settings
    paper_trading: bool = Field(default=True, env="PAPER_TRADING")
    check_interval: int = Field(default=60, gt=0, env="CHECK_INTERVAL")
    log_level: str = Field(default="INFO", env="LOG_LEVEL")
    
    @field_validator("rsi_oversold", mode="before")
    @classmethod
    def validate_rsi_oversold(cls, v, info):
        if "rsi_overbought" in info.data and v >= info.data["rsi_overbought"]:
            raise ValueError("rsi_oversold must be less than rsi_overbought")
        return v
    
    @field_validator("symbols", mode="before")
    @classmethod
    def parse_symbols(cls, v):
        if isinstance(v, str):
            return [s.strip() for s in v.split(",")]
        return v


def load_config() -> TradingConfig:
    """Load and validate configuration."""
    try:
        config = TradingConfig()
        return config
    except Exception as e:
        raise ValueError(f"Configuration error: {e}")


# Convenience aliases for backward compatibility (if needed)
if os.getenv("BINANCE_API_KEY"):
    config = load_config()
    API_KEY = config.binance_api_key
    API_SECRET = config.binance_api_secret
    SYMBOLS = config.symbols
    TIMEFRAME = config.timeframe
    RSI_PERIOD = config.rsi_period
    RSI_OVERSOLD = config.rsi_oversold
    RSI_OVERBOUGHT = config.rsi_overbought
    TRADE_AMOUNT_USDT = config.trade_amount_usdt
    TRAILING_STOP_PCT = config.trailing_stop_pct
    COOLDOWN_CANDLES = config.cooldown_candles
    STOP_LOSS_PCT = config.stop_loss_pct
    TAKE_PROFIT_PCT = config.take_profit_pct
    PAPER_TRADING = config.paper_trading
    CHECK_INTERVAL = config.check_interval

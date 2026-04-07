"""
Stock Trading Configuration (Alpaca).

For paper trading on real US stock market.
Get API keys: https://app.alpaca.markets
"""

import os
from typing import List
from dotenv import load_dotenv
from pydantic import Field, ConfigDict
from pydantic_settings import BaseSettings


load_dotenv()


class StockTradingConfig(BaseSettings):
    """Stock trading configuration via Alpaca."""
    
    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore"  # Ignore extra fields from .env
    )
    
    # Alpaca API Keys
    alpaca_api_key: str = Field(..., env="ALPACA_API_KEY")
    alpaca_api_secret: str = Field(..., env="ALPACA_API_SECRET")
    
    # Alpaca base URL (paper trading by default)
    alpaca_base_url: str = Field(
        default="https://paper-api.alpaca.markets",
        env="ALPACA_BASE_URL"
    )
    
    # Trading symbols (stocks/ETFs)
    symbols: List[str] = Field(
        default=["SPY", "QQQ", "VOO"],
        env="STOCK_SYMBOLS"
    )
    
    # Timeframe for analysis (1min, 5min, 15min, 1h, 1d)
    timeframe: str = Field(default="15min", env="STOCK_TIMEFRAME")
    
    # RSI Settings (same as crypto but adjusted for stocks)
    rsi_period: int = Field(default=14, ge=2, le=200, env="STOCK_RSI_PERIOD")
    rsi_oversold: float = Field(default=35, ge=0, le=50, env="STOCK_RSI_OVERSOLD")
    rsi_overbought: float = Field(default=65, ge=50, le=100, env="STOCK_RSI_OVERBOUGHT")
    
    # Risk Management
    trade_amount_usd: float = Field(default=20.0, gt=0, env="STOCK_TRADE_AMOUNT")
    min_trade_usd: float = Field(default=10.0, gt=0, env="STOCK_MIN_TRADE_AMOUNT")
    trailing_stop_pct: float = Field(default=0.02, gt=0, lt=1, env="STOCK_TRAILING_STOP")
    stop_loss_pct: float = Field(default=0.03, gt=0, lt=1, env="STOCK_STOP_LOSS")
    take_profit_pct: float = Field(default=0.05, gt=0, lt=1, env="STOCK_TAKE_PROFIT")
    cooldown_candles: int = Field(default=4, ge=0, env="STOCK_COOLDOWN")
    max_daily_loss_pct: float = Field(default=0.05, gt=0, lt=1, env="STOCK_MAX_DAILY_LOSS")
    max_open_positions: int = Field(default=2, ge=1, env="STOCK_MAX_OPEN_POS")
    
    # Paper vs Live trading
    paper_trading: bool = Field(default=True, env="STOCK_PAPER_TRADING")
    
    # Bot settings
    check_interval: int = Field(default=60, gt=0, env="STOCK_CHECK_INTERVAL")
    log_level: str = Field(default="INFO", env="STOCK_LOG_LEVEL")
    
    # Use AI for entries?
    use_ai: bool = Field(default=True, env="STOCK_USE_AI")
    min_ai_confidence: float = Field(default=0.45, ge=0, le=1, env="STOCK_MIN_AI_CONFIDENCE")


def load_stock_config() -> StockTradingConfig:
    """Load and validate stock configuration."""
    try:
        config = StockTradingConfig()
        return config
    except Exception as e:
        raise ValueError(f"Stock configuration error: {e}")


# Convenience aliases
if os.getenv("ALPACA_API_KEY"):
    config = load_stock_config()
    ALPACA_API_KEY = config.alpaca_api_key
    ALPACA_API_SECRET = config.alpaca_api_secret
    ALPACA_BASE_URL = config.alpaca_base_url
    SYMBOLS = config.symbols
    TIMEFRAME = config.timeframe
    RSI_PERIOD = config.rsi_period
    RSI_OVERSOLD = config.rsi_oversold
    RSI_OVERBOUGHT = config.rsi_overbought
    TRADE_AMOUNT_USD = config.trade_amount_usd
    TRAILING_STOP_PCT = config.trailing_stop_pct
    STOP_LOSS_PCT = config.stop_loss_pct
    TAKE_PROFIT_PCT = config.take_profit_pct
    COOLDOWN_CANDLES = config.cooldown_candles
    PAPER_TRADING = config.paper_trading
    CHECK_INTERVAL = config.check_interval
    USE_AI = config.use_ai

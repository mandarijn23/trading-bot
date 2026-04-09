"""
Stock Trading Configuration (Alpaca).

For paper trading on real US stock market.
Get API keys: https://app.alpaca.markets
"""

import os
import json
from typing import List
from typing import Annotated
from dotenv import load_dotenv
from pydantic import Field, ConfigDict
from pydantic import field_validator
from pydantic_settings import BaseSettings, NoDecode


load_dotenv()


class StockTradingConfig(BaseSettings):
    """Stock trading configuration via Alpaca."""
    
    model_config = ConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore",  # Ignore extra fields from .env
        populate_by_name=True,
    )
    
    # Alpaca API Keys
    alpaca_api_key: str = Field(..., validation_alias="ALPACA_API_KEY")
    alpaca_api_secret: str = Field(..., validation_alias="ALPACA_API_SECRET")
    
    # Alpaca base URL (paper trading by default)
    alpaca_base_url: str = Field(
        default="https://paper-api.alpaca.markets",
        validation_alias="ALPACA_BASE_URL"
    )
    
    # Trading symbols (stocks/ETFs)
    symbols: Annotated[List[str], NoDecode] = Field(
        default=["SPY", "QQQ", "VOO"],
        validation_alias="STOCK_SYMBOLS"
    )

    # Optional broader universe used for dynamic symbol selection.
    universe_symbols: Annotated[List[str], NoDecode] = Field(
        default=[],
        validation_alias="STOCK_UNIVERSE_SYMBOLS"
    )

    # Dynamic symbol selection controls.
    dynamic_symbol_selection: bool = Field(default=False, validation_alias="STOCK_DYNAMIC_SELECTION")
    dynamic_symbol_count: int = Field(default=3, ge=1, le=30, validation_alias="STOCK_DYNAMIC_SYMBOL_COUNT")
    selection_refresh_cycles: int = Field(default=15, ge=1, le=300, validation_alias="STOCK_SELECTION_REFRESH_CYCLES")

    # Liquidity and volatility filters for dynamic selection.
    min_dollar_volume: float = Field(default=2_000_000.0, ge=0, validation_alias="STOCK_MIN_DOLLAR_VOLUME")
    min_atr_pct: float = Field(default=0.003, ge=0, le=1, validation_alias="STOCK_MIN_ATR_PCT")
    max_atr_pct: float = Field(default=0.08, ge=0, le=1, validation_alias="STOCK_MAX_ATR_PCT")
    
    # Timeframe for analysis (1min, 5min, 15min, 1h, 1d)
    timeframe: str = Field(default="15Min", validation_alias="STOCK_TIMEFRAME")
    
    # RSI Settings (same as crypto but adjusted for stocks)
    rsi_period: int = Field(default=14, ge=2, le=200, validation_alias="STOCK_RSI_PERIOD")
    rsi_oversold: float = Field(default=35, ge=0, le=50, validation_alias="STOCK_RSI_OVERSOLD")
    rsi_overbought: float = Field(default=65, ge=50, le=100, validation_alias="STOCK_RSI_OVERBOUGHT")
    
    # Risk Management
    trade_amount_usd: float = Field(default=20.0, gt=0, validation_alias="STOCK_TRADE_AMOUNT")
    min_trade_usd: float = Field(default=10.0, gt=0, validation_alias="STOCK_MIN_TRADE_AMOUNT")
    trailing_stop_pct: float = Field(default=0.02, gt=0, lt=1, validation_alias="STOCK_TRAILING_STOP")
    stop_loss_pct: float = Field(default=0.03, gt=0, lt=1, validation_alias="STOCK_STOP_LOSS")
    take_profit_pct: float = Field(default=0.05, gt=0, lt=1, validation_alias="STOCK_TAKE_PROFIT")
    cooldown_candles: int = Field(default=4, ge=0, validation_alias="STOCK_COOLDOWN")
    max_daily_loss_pct: float = Field(default=0.05, gt=0, lt=1, validation_alias="STOCK_MAX_DAILY_LOSS")
    max_open_positions: int = Field(default=2, ge=1, validation_alias="STOCK_MAX_OPEN_POS")
    max_risk_per_trade: float = Field(default=0.02, gt=0, lt=0.2, validation_alias="STOCK_MAX_RISK_PER_TRADE")
    profit_optimized_sizing: bool = Field(default=True, validation_alias="STOCK_PROFIT_OPTIMIZED_SIZING")
    min_conviction_risk_mult: float = Field(default=0.75, gt=0, le=1, validation_alias="STOCK_MIN_CONVICTION_RISK_MULT")
    max_conviction_risk_mult: float = Field(default=1.75, ge=1, le=3, validation_alias="STOCK_MAX_CONVICTION_RISK_MULT")
    high_confidence_threshold: float = Field(default=0.65, ge=0, le=1, validation_alias="STOCK_HIGH_CONFIDENCE_THRESHOLD")
    very_high_confidence_threshold: float = Field(default=0.75, ge=0, le=1, validation_alias="STOCK_VERY_HIGH_CONFIDENCE_THRESHOLD")
    
    # Paper vs Live trading
    paper_trading: bool = Field(default=True, validation_alias="STOCK_PAPER_TRADING")
    
    # Bot settings
    check_interval: int = Field(default=60, gt=0, validation_alias="STOCK_CHECK_INTERVAL")
    log_level: str = Field(default="INFO", validation_alias="STOCK_LOG_LEVEL")
    log_max_mb: int = Field(default=10, ge=1, le=200, validation_alias="STOCK_LOG_MAX_MB")
    log_backup_count: int = Field(default=7, ge=1, le=30, validation_alias="STOCK_LOG_BACKUP_COUNT")
    bars_limit: int = Field(default=250, ge=50, validation_alias="STOCK_BARS_LIMIT")
    min_bars: int = Field(default=30, ge=20, validation_alias="STOCK_MIN_BARS")
    insufficient_data_log_cooldown_sec: int = Field(
        default=900,
        ge=0,
        validation_alias="STOCK_INSUFFICIENT_DATA_LOG_COOLDOWN",
    )
    account_snapshot_log_cooldown_sec: int = Field(
        default=900,
        ge=0,
        validation_alias="STOCK_ACCOUNT_SNAPSHOT_LOG_COOLDOWN",
    )
    retrain_interval_trades: int = Field(
        default=20,
        ge=1,
        validation_alias="STOCK_RETRAIN_INTERVAL_TRADES",
    )
    max_position_value_pct: float = Field(
        default=0.25,
        gt=0,
        lt=1,
        validation_alias="STOCK_MAX_POSITION_VALUE_PCT",
    )
    max_gross_exposure_pct: float = Field(
        default=0.5,
        gt=0,
        lt=1,
        validation_alias="STOCK_MAX_GROSS_EXPOSURE_PCT",
    )
    
    # Use AI for entries?
    use_ai: bool = Field(default=True, validation_alias="STOCK_USE_AI")
    min_ai_confidence: float = Field(default=0.45, ge=0, le=1, validation_alias="STOCK_MIN_AI_CONFIDENCE")
    
    @field_validator("symbols", mode="before")
    @classmethod
    def parse_symbols(cls, v):
        if isinstance(v, str):
            text = v.strip()
            if not text:
                return ["SPY", "QQQ", "VOO"]

            # Accept JSON arrays and comma-separated values.
            if text.startswith("["):
                try:
                    parsed = json.loads(text)
                    if isinstance(parsed, list):
                        return [str(s).strip() for s in parsed if str(s).strip()]
                except Exception:
                    pass

                # Also support loose bracket form like [SPY,QQQ,VOO].
                text = text.strip("[]")

            parsed = []
            for s in text.split(","):
                clean = s.strip().strip('"').strip("'")
                if clean:
                    parsed.append(clean)
            return parsed
        return v

    @field_validator("universe_symbols", mode="before")
    @classmethod
    def parse_universe_symbols(cls, v):
        return cls.parse_symbols(v)


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

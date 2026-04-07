"""
Stock Trading Bot — RSI + 200 MA on Real US Stocks (via Alpaca).

Paper trading on real market with SPY, QQQ, VOO + AI learning.

Run:  python stock_bot.py
"""

import sys
import logging
import time
from typing import Dict, Literal
from datetime import datetime

import pandas as pd
import alpaca_trade_api as tradeapi

from stock_config import load_stock_config
from strategy import get_signal

try:
    from ml_model import TradingAI
    HAS_AI = True
except ImportError:
    HAS_AI = False


# Configure logging
def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Configure logging."""
    logger = logging.getLogger("stock-bot")
    logger.setLevel(log_level.upper())
    
    formatter = logging.Formatter(
        "%(asctime)s  %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    fh = logging.FileHandler("stock_bot.log")
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    
    return logger


class StockPosition:
    """Manages a stock position."""
    
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.active = False
        self.entry_price = 0.0
        self.peak_price = 0.0
        self.trailing_stop = 0.0
        self.take_profit = 0.0
        self.quantity = 0
        self.cooldown = 0
        self.entry_time = None
        self.ai_confidence = 0.5

    def open(self, price: float, quantity: int, stop_loss_pct: float, take_profit_pct: float, ai_confidence: float = 0.5) -> None:
        """Open position."""
        self.active = True
        self.entry_price = price
        self.peak_price = price
        self.quantity = quantity
        self.trailing_stop = price * (1 - stop_loss_pct)
        self.take_profit = price * (1 + take_profit_pct)
        self.entry_time = datetime.now()
        self.ai_confidence = ai_confidence

    def check_exit(self, price: float, trailing_stop_pct: float) -> Literal["HOLD", "TRAIL_STOP", "TAKE_PROFIT"]:
        """Check if should exit."""
        if not self.active:
            return "HOLD"
        
        if price > self.peak_price:
            self.peak_price = price
            self.trailing_stop = price * (1 - trailing_stop_pct)
        
        if price <= self.trailing_stop:
            return "TRAIL_STOP"
        if price >= self.take_profit:
            return "TAKE_PROFIT"
        
        return "HOLD"

    def close(self, was_loss: bool = False, cooldown_candles: int = 0) -> None:
        """Close position."""
        self.active = False
        if was_loss:
            self.cooldown = cooldown_candles

    def tick_cooldown(self) -> None:
        """Decrement cooldown."""
        if self.cooldown > 0:
            self.cooldown -= 1

    def ready(self) -> bool:
        """Ready for new entry?"""
        return not self.active and self.cooldown == 0


class StockTradingBot:
    """Stock trading bot using Alpaca API."""
    
    def __init__(self, config) -> None:
        self.config = config
        self.logger = setup_logging(config.log_level)
        self.api = None
        self.positions: Dict[str, StockPosition] = {}
        self.ai = TradingAI() if HAS_AI and config.use_ai else None
        
    def connect(self) -> None:
        """Connect to Alpaca."""
        try:
            # Use positional arguments for Alpaca REST API (3.0+)
            self.api = tradeapi.REST(
                key_id=self.config.alpaca_api_key,
                secret_key=self.config.alpaca_api_secret,
                base_url=self.config.alpaca_base_url,
            )
            
            # Check connection
            self.api.get_account()
            
            if self.config.paper_trading:
                self.logger.info("✅ Connected to Alpaca (PAPER TRADING)")
            else:
                self.logger.warning("⚠️  Connected to Alpaca (LIVE TRADING)")
            
            # Initialize positions
            self.positions = {s: StockPosition(s) for s in self.config.symbols}
            
        except Exception as e:
            self.logger.error(f"Failed to connect: {e}")
            raise

    def fetch_bars(self, symbol: str, limit: int = 250) -> pd.DataFrame:
        """Fetch historical bars from Alpaca."""
        try:
            bars = self.api.get_bars(
                symbol,
                self.config.timeframe,
                limit=limit
            ).df
            
            if bars.empty:
                return pd.DataFrame()
            
            # Reset index (index contains timestamp)
            bars.reset_index(inplace=True)
            
            # Select only the columns we need
            needed_cols = ["timestamp", "open", "high", "low", "close", "volume"]
            available_cols = [col for col in needed_cols if col in bars.columns]
            bars = bars[available_cols]
            
            # Ensure we have all needed columns
            for col in needed_cols:
                if col not in bars.columns:
                    self.logger.warning(f"Missing column {col} in Alpaca data")
                    return pd.DataFrame()
            
            bars["timestamp"] = pd.to_datetime(bars["timestamp"])
            
            return bars
        except Exception as e:
            self.logger.error(f"Failed to fetch bars for {symbol}: {e}")
            return pd.DataFrame()

    def place_order(self, side: Literal["buy", "sell"], symbol: str, qty: int, ai_confidence: float = 0.5) -> bool:
        """Place order on Alpaca."""
        try:
            if self.config.paper_trading or qty <= 0:
                confidence_str = f" (AI: {ai_confidence:.0%})" if side == "buy" else ""
                self.logger.info(f"[PAPER] {side.upper()} {qty} {symbol}{confidence_str}")
                return True
            
            self.api.submit_order(
                symbol=symbol,
                qty=qty,
                side=side,
                type="market",
                time_in_force="day",
            )
            self.logger.info(f"[LIVE] {side.upper()} {qty} {symbol}")
            return True
        except Exception as e:
            self.logger.error(f"Order failed for {symbol}: {e}")
            return False

    def process_symbol(self, symbol: str) -> None:
        """Process single stock."""
        try:
            df = self.fetch_bars(symbol)
            
            if df.empty or len(df) < 200:
                self.logger.warning(f"[{symbol}] Insufficient data")
                return
            
            price = float(df["close"].iloc[-1])
            pos = self.positions[symbol]
            pos.tick_cooldown()

            # Check for exit
            exit_reason = pos.check_exit(price, self.config.trailing_stop_pct)
            if exit_reason in ("TRAIL_STOP", "TAKE_PROFIT"):
                self.logger.info(f"[{symbol}] EXIT {exit_reason} @ ${price:.2f}")
                success = self.place_order("sell", symbol, pos.quantity)
                if success:
                    was_loss = price < pos.entry_price
                    pnl = (price - pos.entry_price) * pos.quantity
                    
                    if self.ai:
                        self.ai.update_from_trade(pnl, not was_loss)
                    
                    pos.close(was_loss=was_loss, cooldown_candles=self.config.cooldown_candles)
            
            # Check for entry
            elif pos.ready():
                signal = get_signal(df, self.config.rsi_period, self.config.rsi_oversold, self.config.rsi_overbought)
                
                ai_confidence = 0.5
                if self.ai and signal == "BUY":
                    ai_confidence = self.ai.predict_entry_probability(df)
                
                if signal == "BUY" and (not self.ai or ai_confidence > 0.45):
                    qty = int(self.config.trade_amount_usd / price)
                    if qty > 0:
                        self.logger.info(f"[{symbol}] BUY signal | AI: {ai_confidence:.0%}")
                        success = self.place_order("buy", symbol, qty, ai_confidence)
                        if success:
                            pos.open(price, qty, self.config.stop_loss_pct, self.config.take_profit_pct, ai_confidence)
            elif pos.active:
                self.logger.debug(f"[{symbol}] ${price:.2f} TP=${pos.take_profit:.2f} TS=${pos.trailing_stop:.2f}")
            else:
                self.logger.debug(f"[{symbol}] Cooldown: {pos.cooldown} bars")
                
        except Exception as e:
            self.logger.error(f"[{symbol}] Error: {e}")

    def run(self) -> None:
        """Main trading loop."""
        self.connect()
        self.logger.info(f"🤖 Stock Bot started | Symbols: {self.config.symbols} | {self.config.timeframe}")
        if self.ai:
            stats = self.ai.get_stats()
            self.logger.info(f"🧠 AI active | Trades: {stats.get('total_trades', 0)} | WR: {stats.get('win_rate', 0)}%")
        
        try:
            while True:
                for symbol in self.config.symbols:
                    self.process_symbol(symbol)
                
                time.sleep(self.config.check_interval)
                
        except KeyboardInterrupt:
            self.logger.info("Bot stopped by user")
            if self.ai:
                stats = self.ai.get_stats()
                self.logger.info(f"Final AI Stats: {stats}")
        except Exception as e:
            self.logger.error(f"Bot error: {e}")
            raise


def main() -> None:
    """Entry point."""
    try:
        config = load_stock_config()
        bot = StockTradingBot(config)
        bot.run()
    except Exception as e:
        logging.error(f"Failed to start bot: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()

"""
Multi-pair Trading Bot — RSI + 200 MA + Trailing Stop + AI Learning.

Async trading bot with machine learning capabilities:
- AI predicts entry probability
- Learns from trade outcomes
- Adapts position sizes dynamically

Run:  python bot.py
"""

import asyncio
import logging
import sys
from typing import Dict, Literal
from datetime import datetime
from collections import defaultdict

import ccxt.async_support as ccxt
import pandas as pd

from config import load_config
from strategy import get_signal
from ml_model import TradingAI
from portfolio import Portfolio
from risk import RiskManager
from discord_alerts import discord


# Configure logging
def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Configure logging with file and console output."""
    logger = logging.getLogger("trading-bot")
    logger.setLevel(log_level.upper())
    
    formatter = logging.Formatter(
        "%(asctime)s  %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    # File handler
    fh = logging.FileHandler("bot.log")
    fh.setFormatter(formatter)
    logger.addHandler(fh)
    
    # Console handler
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    
    return logger


class Position:
    """Manages an active trading position."""
    
    def __init__(self, symbol: str) -> None:
        self.symbol = symbol
        self.active = False
        self.entry_price = 0.0
        self.peak_price = 0.0
        self.trailing_stop = 0.0
        self.take_profit = 0.0
        self.cooldown = 0  # intervals to wait before next entry
        self.entry_time = None
        self.ai_confidence = 0.0  # AI entry probability

    def open(self, price: float, stop_loss_pct: float, take_profit_pct: float, ai_confidence: float = 0.5) -> None:
        """Open a new position."""
        self.active = True
        self.entry_price = price
        self.peak_price = price
        self.trailing_stop = price * (1 - stop_loss_pct)
        self.take_profit = price * (1 + take_profit_pct)
        self.entry_time = datetime.now()
        self.ai_confidence = ai_confidence

    def check_exit(self, price: float, trailing_stop_pct: float) -> Literal["HOLD", "TRAIL_STOP", "TAKE_PROFIT"]:
        """Check if position should be closed."""
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
        """Close the position."""
        self.active = False
        if was_loss:
            self.cooldown = cooldown_candles

    def tick_cooldown(self) -> None:
        """Decrement cooldown counter."""
        if self.cooldown > 0:
            self.cooldown -= 1

    def ready(self) -> bool:
        """Check if ready for new entry."""
        return not self.active and self.cooldown == 0


class AsyncTradingBot:
    """Async trading bot with AI learning capabilities."""
    
    def __init__(self, config) -> None:
        self.config = config
        self.logger = setup_logging(config.log_level)
        self.exchange: ccxt.binance | None = None
        self.positions: Dict[str, Position] = {}
        self.latest_prices: Dict[str, float] = {}
        self.ai = TradingAI()  # Initialize AI model
        self.trades_data: Dict[str, list] = defaultdict(list)  # Track data for retraining
        self.retrain_counter = 0
        
        # 🆕 Portfolio & Risk Management
        self.portfolio = Portfolio(starting_balance=self.config.starting_balance)
        self.risk = RiskManager(config)
        self.logger.info(f"Portfolio initialized: ${self.portfolio.equity:.2f}")
        
    async def connect(self) -> None:
        """Connect to exchange."""
        try:
            if self.config.paper_trading:
                self.exchange = ccxt.binance({"enableRateLimit": True})
                self.logger.info("[PAPER] Trading mode — no API key required")
            else:
                self.exchange = ccxt.binance({
                    "apiKey": self.config.binance_api_key,
                    "secret": self.config.binance_api_secret,
                    "enableRateLimit": True,
                    "options": {"defaultType": "spot"},
                })
                self.logger.warning("[LIVE] Trading mode — REAL MONEY AT RISK!")
            
            # Initialize positions
            self.positions = {symbol: Position(symbol) for symbol in self.config.symbols}
        except Exception as e:
            self.logger.error(f"Failed to connect to exchange: {e}")
            raise

    async def fetch_ohlcv(self, symbol: str, limit: int = 250) -> pd.DataFrame:
        """Fetch OHLCV data."""
        try:
            raw = await self.exchange.fetch_ohlcv(symbol, self.config.timeframe, limit=limit)
            df = pd.DataFrame(
                raw,
                columns=["timestamp", "open", "high", "low", "close", "volume"]
            )
            df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
            return df
        except Exception as e:
            self.logger.error(f"Failed to fetch OHLCV for {symbol}: {e}")
            raise

    async def place_order(
        self,
        side: Literal["buy", "sell"],
        symbol: str,
        price: float,
        ai_confidence: float = 0.5
    ) -> bool:
        """Place market order."""
        try:
            # Adjust position size based on AI win rate and trend
            base_amount = self.config.trade_amount_usdt
            position_multiplier = self.ai.get_position_size_multiplier()
            
            # Position size = base * win_rate_multiplier (not confidence)
            # AI confidence is used as FILTER only, not for sizing
            adjusted_amount = base_amount * position_multiplier
            
            qty = round(adjusted_amount / price, 6)
            
            if self.config.paper_trading:
                confidence_str = f" (AI confidence: {ai_confidence:.0%})" if side == "buy" else ""
                self.logger.info(f"[PAPER] {side.upper()} {qty} {symbol} @ {price:.2f}{confidence_str}")
                return True
            
            order = await self.exchange.create_market_order(symbol, side, qty)
            self.logger.info(f"[LIVE] Order placed: {side.upper()} {qty} {symbol} @ {price:.2f}")
            return True
        except Exception as e:
            self.logger.error(f"Order failed for {symbol}: {e}")
            return False

    async def process_symbol(self, symbol: str) -> None:
        """Process single symbol."""
        try:
            df = await self.fetch_ohlcv(symbol)
            price = float(df["close"].iloc[-1])
            self.latest_prices[symbol] = price
            pos = self.positions[symbol]
            
            pos.tick_cooldown()
            
            # Check for position exit
            exit_reason = pos.check_exit(price, self.config.trailing_stop_pct)
            if exit_reason in ("TRAIL_STOP", "TAKE_PROFIT"):
                self.logger.info(f"[{symbol}] EXIT {exit_reason} @ {price:.2f}")
                success = await self.place_order("sell", symbol, price)
                if success:
                    was_loss = price < pos.entry_price
                    position = self.portfolio.positions.get(symbol, {})
                    qty = float(position.get("size", self.config.trade_amount_usdt / pos.entry_price)) if pos.entry_price > 0 else 0.0
                    pnl = (price - pos.entry_price) * qty
                    notional = pos.entry_price * qty if pos.entry_price > 0 else 0.0
                    pnl_pct = (pnl / notional) * 100 if notional > 0 else 0
                    
                    # 📊 Update portfolio
                    self.portfolio.close_position(symbol, price, datetime.now())
                    
                    # AI learns from this trade
                    self.ai.update_from_trade(pnl, not was_loss)
                    
                    # 🔔 Discord notification
                    discord.notify_sell(symbol, pos.entry_price, price, int(round(qty)), pnl_pct, exit_reason)
                    
                    pos.close(was_loss=was_loss, cooldown_candles=self.config.cooldown_candles)
            
            # Check for entry signal
            elif pos.ready():
                signal = get_signal(
                    df,
                    self.config.rsi_period,
                    self.config.rsi_oversold,
                    self.config.rsi_overbought,
                )
                
                # Get AI confidence (0-1)
                ai_confidence = self.ai.predict_entry_probability(df)
                
                # Only enter if signal + AI is confident enough
                if signal == "BUY" and ai_confidence > self.config.min_ai_confidence:
                    # 🔴 RISK CHECK: Before placing any order
                    open_positions = sum(1 for p in self.positions.values() if p.active)
                    allowed, reason = self.risk.check_pre_trade(self.portfolio, symbol, open_positions)
                    if not allowed:
                        self.logger.warning(f"[{symbol}] Trade blocked by risk manager: {reason}")
                        return
                    
                    self.logger.info(f"[{symbol}] BUY signal | AI confidence: {ai_confidence:.0%}")
                    success = await self.place_order("buy", symbol, price, ai_confidence)
                    if success:
                        # 📊 Register in portfolio
                        qty = round(self.config.trade_amount_usdt / price, 6)
                        self.portfolio.open_position(symbol, price, qty, datetime.now())
                        pos.open(price, self.config.stop_loss_pct, self.config.take_profit_pct, ai_confidence)
                        
                        # 🔔 Discord notification
                        discord.notify_buy(symbol, price, int(qty), ai_confidence)
                elif signal == "BUY":
                    self.logger.debug(f"[{symbol}] BUY signal ignored (AI confidence too low: {ai_confidence:.0%})")
            
            elif pos.active:
                self.logger.debug(
                    f"[{symbol}] price={price:.2f}  "
                    f"trail={pos.trailing_stop:.2f}  TP={pos.take_profit:.2f}  "
                    f"AI-conf={pos.ai_confidence:.0%}"
                )
            else:
                self.logger.debug(f"[{symbol}] Cooldown: {pos.cooldown} intervals remaining")

            if self.latest_prices:
                self.portfolio.update_equity(self.latest_prices)
                
        except asyncio.CancelledError:
            self.logger.info(f"[{symbol}] Task cancelled")
            raise
        except Exception as e:
            self.logger.error(f"[{symbol}] Error: {e}")

    async def run(self) -> None:
        """Main bot loop."""
        await self.connect()
        self.logger.info(f"🤖 Bot started | pairs: {self.config.symbols} | {self.config.timeframe}")
        self.logger.info(f"🧠 AI Model active | Win rate: {self.ai.get_stats().get('win_rate', 'N/A')}%")
        
        # 🔔 Discord startup notification
        discord.send_message(
            "🚀 Bot Started",
            {
                "Pairs": ", ".join(self.config.symbols),
                "Timeframe": self.config.timeframe,
                "Mode": "PAPER TRADING" if self.config.paper_trading else "LIVE TRADING ⚠️",
                "Status": "Ready",
            },
            color=3066993  # Green
        )
        
        try:
            while True:
                # 📊 Update portfolio state
                today = datetime.utcnow().date()
                self.portfolio.new_day(today)
                
                # Process all symbols concurrently
                tasks = [self.process_symbol(symbol) for symbol in self.config.symbols]
                await asyncio.gather(*tasks, return_exceptions=True)

                # Mark portfolio to market after all symbols are processed.
                latest_prices = {}
                for symbol, position in self.positions.items():
                    if position.entry_price > 0:
                        latest_prices[symbol] = position.entry_price if not position.active else position.entry_price
                self.portfolio.update_equity(latest_prices)
                
                # Periodically log AI stats and portfolio status
                self.retrain_counter += 1
                if self.retrain_counter % 60 == 0:  # Every 60 iterations
                    stats = self.ai.get_stats()
                    portfolio_stats = self.portfolio.get_stats()
                    self.logger.info(f"🤖 AI Stats: {stats}")
                    self.logger.info(f"💰 Portfolio: Equity=${portfolio_stats['equity']:.2f}, Daily P&L: {portfolio_stats['daily_pnl_pct']:+.2f}%")
                
                await asyncio.sleep(self.config.check_interval)
        except KeyboardInterrupt:
            self.logger.info("Bot stopped by user")
            self._print_final_stats()
        except Exception as e:
            self.logger.error(f"Bot error: {e}")
            # 🔔 Send error notification to Discord
            discord.notify_error("Bot crashed!", {"Error": str(e)})
            raise
        finally:
            if self.exchange:
                try:
                    await self.exchange.close()
                except Exception:
                    pass  # Exchange already closed or doesn't support async close
    
    def _print_final_stats(self) -> None:
        """Print final AI statistics."""
        stats = self.ai.get_stats()
        if stats.get("total_trades", 0) > 0:
            self.logger.info("=" * 60)
            self.logger.info("🤖 FINAL AI STATISTICS")
            self.logger.info("=" * 60)
            for key, value in stats.items():
                self.logger.info(f"  {key}: {value}")
            self.logger.info("=" * 60)
            
            # 🔔 Send final summary to Discord
            discord.notify_daily_summary({
                "trades": stats.get("total_trades", 0),
                "wins": stats.get("wins", 0),
                "win_rate": f"{stats.get('win_rate', 0):.1f}%",
                "pnl": f"{stats.get('total_pnl_pct', 0):+.2f}%",
            })


async def main() -> None:
    """Entry point."""
    try:
        config = load_config()
        bot = AsyncTradingBot(config)
        await bot.run()
    except Exception as e:
        logging.error(f"Failed to start bot: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())

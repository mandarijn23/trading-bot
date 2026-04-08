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

try:
    import alpaca_trade_api as tradeapi
except ImportError:
    tradeapi = None

from stock_config import load_stock_config
from strategy import get_signal, get_signal_enhanced
from market_hours import USMarketSession

try:
    # Try Random Forest first (lightweight, better on small datasets)
    from ml_model_rf import TradingAI
    HAS_AI = True
except ImportError:
    # Fall back to TensorFlow
    try:
        from ml_model import TradingAI
        HAS_AI = True
    except ImportError:
        HAS_AI = False

try:
    from discord_alerts import discord
except ImportError:
    discord = None

try:
    from model_retrainer import ModelRetrainer
    HAS_RETRAINER = True
except ImportError:
    HAS_RETRAINER = False


# Configure logging
class SafeConsoleFilter(logging.Filter):
    """Normalize log messages for consoles that cannot encode Unicode."""

    def filter(self, record: logging.LogRecord) -> bool:
        try:
            msg = record.getMessage()
            safe = msg.encode("ascii", errors="replace").decode("ascii")
            record.msg = safe
            record.args = ()
        except Exception:
            pass
        return True


def setup_logging(log_level: str = "INFO") -> logging.Logger:
    """Configure logging."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    logger = logging.getLogger("stock-bot")
    logger.setLevel(log_level.upper())
    
    formatter = logging.Formatter(
        "%(asctime)s  %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    fh = logging.FileHandler("stock_bot.log")
    fh.setFormatter(formatter)
    fh.addFilter(SafeConsoleFilter())
    logger.addHandler(fh)
    
    ch = logging.StreamHandler(sys.stdout)
    ch.setFormatter(formatter)
    ch.addFilter(SafeConsoleFilter())
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

    def open(self, price: float, quantity: int, stop_loss_pct: float, take_profit_pct: float, ai_confidence: float = 0.5, atr_stop: float = None) -> None:
        """Open position. Use ATR stop if provided, otherwise fixed %."""
        self.active = True
        self.entry_price = price
        self.peak_price = price
        self.quantity = quantity
        
        # Use ATR-based stop if provided, otherwise fixed %
        if atr_stop is not None:
            self.trailing_stop = atr_stop
        else:
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
        self.retrainer = ModelRetrainer(retrain_interval=20) if HAS_RETRAINER and HAS_AI else None
        self.daily_pnl = 0.0  # Track daily P&L for max loss limit
        self.start_date = datetime.now().date()  # Reset daily loss at midnight
        self.market = USMarketSession()
        self.session_active = False
        
    def connect(self) -> None:
        """Connect to Alpaca."""
        try:
            if tradeapi is None:
                raise ImportError("alpaca_trade_api is required for live/paper trading")

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
                    pnl_pct = (pnl / (pos.entry_price * pos.quantity)) * 100 if pos.entry_price > 0 else 0
                    self.daily_pnl += pnl_pct
                    
                    self._log_trade(symbol, "sell", pos.entry_price, pos.quantity, pos.ai_confidence, 
                                   exit_reason=exit_reason, exit_price=price, pnl=pnl)
                    
                    if self.ai:
                        self.ai.update_from_trade(pnl, not was_loss)
                    
                    # Send Discord notification
                    if discord:
                        discord.notify_sell(symbol, pos.entry_price, price, pos.quantity, pnl_pct, exit_reason)
                    
                    pos.close(was_loss=was_loss, cooldown_candles=self.config.cooldown_candles)
            
            # Check for entry
            elif pos.ready():
                # Check daily loss limit and max open positions
                if not self._check_daily_loss():
                    return  # Stop trading for the day
                
                if self._count_open_positions() >= self.config.max_open_positions:
                    self.logger.debug(f"[{symbol}] Max open positions ({self.config.max_open_positions}) reached")
                    return
                
                signal, sig_details = get_signal_enhanced(df, self.config.rsi_period, self.config.rsi_oversold, self.config.rsi_overbought)
                
                # Log volume confirmation
                volume_status = "✓" if sig_details.volume_confirm else "✗"
                
                ai_confidence = 0.5
                if self.ai and signal == "BUY":
                    ai_confidence = self.ai.predict_entry_probability(df)
                
                if signal == "BUY" and (not self.ai or ai_confidence > self.config.min_ai_confidence):
                    qty = int(self.config.trade_amount_usd / price)
                    
                    # Validate trade size
                    trade_usd = qty * price
                    if not self._validate_trade_size(trade_usd):
                        self.logger.debug(f"[{symbol}] Trade size too small: ${trade_usd:.2f}")
                        return
                    
                    if qty > 0:
                        self.logger.info(f"[{symbol}] BUY signal | Vol:{volume_status} | ATR:{sig_details.atr:.2f} | AI:{ai_confidence:.0%}")
                        success = self.place_order("buy", symbol, qty, ai_confidence)
                        if success:
                            self._log_trade(symbol, "buy", price, qty, ai_confidence)
                            pos.open(price, qty, self.config.stop_loss_pct, self.config.take_profit_pct, ai_confidence, atr_stop=sig_details.stop_loss_atr)
                            # Send Discord notification
                            if discord:
                                discord.notify_buy(symbol, price, qty, ai_confidence)
            elif pos.active:
                self.logger.debug(f"[{symbol}] ${price:.2f} TP=${pos.take_profit:.2f} TS=${pos.trailing_stop:.2f}")
            else:
                self.logger.debug(f"[{symbol}] Cooldown: {pos.cooldown} bars")
                
        except Exception as e:
            self.logger.error(f"[{symbol}] Error: {e}")
    
    def _check_daily_loss(self) -> bool:
        """Check if daily loss exceeded. Resets at new day."""
        # Reset if new day
        today = datetime.now().date()
        if today > self.start_date:
            self.daily_pnl = 0.0
            self.start_date = today
        
        # Check limit
        max_loss = -abs(self.config.max_daily_loss_pct)  # Negative number
        if self.daily_pnl < max_loss:
            self.logger.warning(f"🛑 Daily loss limit exceeded: {self.daily_pnl:.2f}% | Max: {max_loss:.2f}%")
            return False  # Stop trading
        return True
    
    def _count_open_positions(self) -> int:
        """Count currently open positions."""
        return sum(1 for pos in self.positions.values() if pos.active)
    
    def _validate_trade_size(self, trade_amount: float) -> bool:
        """Check trade size is above minimum."""
        if trade_amount < self.config.min_trade_usd:
            self.logger.debug(f"Trade size ${trade_amount:.2f} below minimum ${self.config.min_trade_usd:.2f}")
            return False
        return True

    def _has_open_positions(self) -> bool:
        return any(pos.active for pos in self.positions.values())

    def _close_all_positions(self, reason: str = "MARKET_CLOSE") -> None:
        """Force close all open positions when the market session ends."""
        for symbol, pos in self.positions.items():
            if not pos.active:
                continue

            try:
                df = self.fetch_bars(symbol, limit=50)
                if df.empty:
                    price = pos.entry_price
                    self.logger.warning(f"[{symbol}] No fresh bars at session end; using entry price")
                else:
                    price = float(df["close"].iloc[-1])

                self.logger.info(f"[{symbol}] EXIT {reason} @ ${price:.2f}")
                success = self.place_order("sell", symbol, pos.quantity)
                if success:
                    was_loss = price < pos.entry_price
                    pnl = (price - pos.entry_price) * pos.quantity
                    pnl_pct = (pnl / (pos.entry_price * pos.quantity)) * 100 if pos.entry_price > 0 else 0
                    self.daily_pnl += pnl_pct

                    self._log_trade(
                        symbol,
                        "sell",
                        pos.entry_price,
                        pos.quantity,
                        pos.ai_confidence,
                        exit_reason=reason,
                        exit_price=price,
                        pnl=pnl,
                    )

                    if self.ai:
                        self.ai.update_from_trade(pnl, not was_loss)

                    if discord:
                        discord.notify_sell(symbol, pos.entry_price, price, pos.quantity, pnl_pct, reason)

                    pos.close(was_loss=was_loss, cooldown_candles=self.config.cooldown_candles)
            except Exception as e:
                self.logger.error(f"[{symbol}] Failed to close position at session end: {e}")

    def _wait_until_open(self) -> None:
        """Sleep until the next NYSE open."""
        while not self.market.is_open():
            seconds = self.market.seconds_until_open()
            minutes = seconds / 60.0
            self.logger.info(f"Market closed | opens in {minutes:.0f} minutes")
            sleep_seconds = 300 if seconds <= 0 else max(30, min(300, int(seconds)))
            time.sleep(sleep_seconds)

    def _finalize_session(self) -> None:
        """Run end-of-day learning and reporting."""
        if self.retrainer and self.ai:
            try:
                self.logger.info("🧠 End-of-day retraining...")
                retrained = self.retrainer.retrain_model(self.ai)
                if retrained:
                    self.logger.info("✅ End-of-day retraining complete")
            except Exception as e:
                self.logger.error(f"End-of-day retraining failed: {e}")

        if self.ai:
            stats = self.ai.get_stats()
            self.logger.info(f"Session AI Stats: {stats}")
            if discord and stats.get("total_trades", 0) > 0:
                discord.notify_daily_summary({
                    "trades": stats.get("total_trades", 0),
                    "wins": stats.get("wins", 0),
                    "win_rate": f"{stats.get('win_rate', 0):.1f}%",
                    "pnl": f"{stats.get('total_pnl_pct', 0):+.2f}%",
                })
    
    def _log_trade(self, symbol: str, side: str, price: float, qty: int, ai_confidence: float, exit_reason: str = None, exit_price: float = None, pnl: float = None) -> None:
        """Log trade to CSV for analysis."""
        try:
            import csv
            from pathlib import Path
            
            csv_file = "trades_history.csv"
            file_exists = Path(csv_file).exists()
            
            with open(csv_file, "a", newline="") as f:
                writer = csv.writer(f)
                
                # Write header if new file
                if not file_exists:
                    writer.writerow([
                        "timestamp", "symbol", "side", "entry_price", "qty", 
                        "ai_confidence", "exit_reason", "exit_price", "pnl_usd", "pnl_pct"
                    ])
                
                # Calculate P&L if available
                pnl_pct = None
                if exit_price and side == "buy":
                    pnl_pct = ((exit_price - price) / price) * 100
                
                writer.writerow([
                    datetime.now().isoformat(),
                    symbol,
                    side,
                    f"{price:.2f}",
                    qty,
                    f"{ai_confidence:.0%}",
                    exit_reason or "",
                    f"{exit_price:.2f}" if exit_price else "",
                    f"{pnl:.2f}" if pnl else "",
                    f"{pnl_pct:.2f}%" if pnl_pct else ""
                ])
        except Exception as e:
            self.logger.debug(f"Failed to log trade: {e}")

    def run(self) -> None:
        """Main trading loop."""
        self.connect()
        self.logger.info(f"🤖 Stock Bot started | Symbols: {self.config.symbols} | {self.config.timeframe}")
        if self.ai:
            stats = self.ai.get_stats()
            self.logger.info(f"🧠 AI active | Trades: {stats.get('total_trades', 0)} | WR: {stats.get('win_rate', 0)}%")

        self._wait_until_open()
        self.session_active = True
        
        # 🔔 Discord startup notification
        if discord:
            discord.send_message(
                "🚀 Stock Bot Started",
                {
                    "Symbols": ", ".join(self.config.symbols),
                    "Timeframe": self.config.timeframe,
                    "Mode": "PAPER TRADING" if self.config.paper_trading else "LIVE TRADING ⚠️",
                    "Status": "Ready",
                },
                color=3066993  # Green
            )
        
        try:
            while True:
                if not self.market.is_open():
                    self.logger.info("Market closed | ending session and closing positions")
                    if self._has_open_positions():
                        self._close_all_positions("MARKET_CLOSE")
                    self._finalize_session()
                    self.session_active = False
                    return

                for symbol in self.config.symbols:
                    self.process_symbol(symbol)
                
                # Check if model retraining is needed
                if self.retrainer and self.ai and self.retrainer.should_retrain():
                    self.logger.info("🧠 Triggering model retraining...")
                    try:
                        self.retrainer.retrain_model(self.ai)
                        self.logger.info("✅ Model retraining complete")
                        if discord:
                            discord.notify_warning("🧠 Model retraining complete")
                    except Exception as e:
                        self.logger.error(f"❌ Model retraining failed: {e}")
                        if discord:
                            discord.notify_error(f"Model retraining failed: {e}")

                if self.market.seconds_until_close() <= self.config.check_interval:
                    self.logger.info("Market close approaching | preparing to stop at close")
                
                time.sleep(self.config.check_interval)
                
        except KeyboardInterrupt:
            self.logger.info("Bot stopped by user")
            if self._has_open_positions():
                self._close_all_positions("MANUAL_STOP")
            if self.ai:
                stats = self.ai.get_stats()
                self.logger.info(f"Final AI Stats: {stats}")
                # 🔔 Send final summary to Discord
                if discord and stats.get("total_trades", 0) > 0:
                    discord.notify_daily_summary({
                        "trades": stats.get("total_trades", 0),
                        "wins": stats.get("wins", 0),
                        "win_rate": f"{stats.get('win_rate', 0):.1f}%",
                        "pnl": f"{stats.get('total_pnl_pct', 0):+.2f}%",
                    })
        except Exception as e:
            self.logger.error(f"Bot error: {e}")
            # 🔔 Send error notification to Discord
            if discord:
                discord.notify_error("Stock Bot crashed!", {"Error": str(e)})
            raise


def main() -> None:
    """Entry point."""
    try:
        config = load_stock_config()
        bot = StockTradingBot(config)
        bot.run()
    except Exception as e:
        logging.error(f"Failed to start bot: {e}")
        if discord:
            discord.notify_error("Stock Bot startup failed!", {"Error": str(e)})
        sys.exit(1)


if __name__ == "__main__":
    main()

"""
Stock Trading Bot — RSI + 200 MA on Real US Stocks (via Alpaca).

Paper trading on real market with SPY, QQQ, VOO + AI learning.

Run:  python stock_bot.py
"""

import sys
import logging
import time
from math import log10
from logging.handlers import RotatingFileHandler
from typing import Dict, List, Literal
from datetime import datetime

import pandas as pd

try:
    import alpaca_trade_api as tradeapi
except ImportError:
    tradeapi = None

from stock_config import load_stock_config
from strategy import get_signal, get_signal_enhanced
from market_hours import USMarketSession
from portfolio import Portfolio
from risk import RiskManager

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


def setup_logging(log_level: str = "INFO", log_max_mb: int = 10, log_backup_count: int = 7) -> logging.Logger:
    """Configure logging."""
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")

    logger = logging.getLogger("stock-bot")
    logger.handlers.clear()
    logger.setLevel(log_level.upper())
    
    formatter = logging.Formatter(
        "%(asctime)s  %(levelname)-8s %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S"
    )
    
    fh = RotatingFileHandler(
        "stock_bot.log",
        maxBytes=log_max_mb * 1024 * 1024,
        backupCount=log_backup_count,
    )
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
        logging.getLogger("stock-bot").info(
            f"[{self.symbol}] OPEN position: ${price:.2f} x {quantity} | "
            f"Stop: ${self.trailing_stop:.2f} | TP: ${self.take_profit:.2f} | AI: {ai_confidence:.0%}"
        )

    def check_exit(self, price: float, trailing_stop_pct: float) -> Literal["HOLD", "TRAIL_STOP", "TAKE_PROFIT"]:
        """Check if should exit."""
        if self.active:
            logger.debug(f"[{self.symbol}] Price: ${price:.2f} Trail: ${self.trailing_stop:.2f} TP: ${self.take_profit:.2f}")
        if not self.active:
            return "HOLD"
        
        if price > self.peak_price:
            self.peak_price = price
            self.trailing_stop = price * (1 - trailing_stop_pct)
        
        if price <= self.trailing_stop:
            logger.info(
                f"[{self.symbol}] EXIT TRAIL_STOP @ ${price:.2f} "
                f"(Entry: ${self.entry_price:.2f}, Loss: {(price/self.entry_price - 1)*100:.1f}%)"
            )
            return "TRAIL_STOP"
        if price >= self.take_profit:
            logger.info(
                f"[{self.symbol}] EXIT TAKE_PROFIT @ ${price:.2f} "
                f"(Entry: ${self.entry_price:.2f}, Gain: {(price/self.entry_price - 1)*100:.1f}%)"
            )
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
        self.logger = setup_logging(config.log_level, config.log_max_mb, config.log_backup_count)
        self.api = None
        self.positions: Dict[str, StockPosition] = {}
        self.ai = TradingAI() if HAS_AI and config.use_ai else None
        retrain_interval = getattr(self.config, "retrain_interval_trades", 20)
        self.retrainer = ModelRetrainer(retrain_interval=retrain_interval) if HAS_RETRAINER and self.ai else None
        self.portfolio = Portfolio(starting_balance=getattr(self.config, "starting_balance", 100000.0))
        self.risk = RiskManager(config)
        self.daily_pnl = 0.0  # Track daily P&L for max loss limit
        self.start_date = datetime.now().date()  # Reset daily loss at midnight
        self.market = USMarketSession()
        self.session_active = False
        self.loop_count = 0
        self.universe_symbols = self._build_universe()
        self.active_symbols = list(self.config.symbols)
        self._insufficient_data_last_log: Dict[str, datetime] = {}
        self._account_snapshot_last_log: datetime | None = None

    def _build_universe(self) -> List[str]:
        """Build a unique symbol universe while preserving order."""
        ordered: List[str] = []
        seen = set()
        for symbol in list(self.config.symbols) + list(self.config.universe_symbols):
            s = str(symbol).strip().upper()
            if not s or s in seen:
                continue
            seen.add(s)
            ordered.append(s)
        return ordered or ["SPY", "QQQ", "VOO"]

    def _ensure_position(self, symbol: str) -> StockPosition:
        """Create a position slot if this symbol has not been seen before."""
        if symbol not in self.positions:
            self.positions[symbol] = StockPosition(symbol)
        return self.positions[symbol]

    def _score_symbol(self, symbol: str) -> float:
        """Score a symbol for short-term opportunity quality."""
        df = self.fetch_bars(symbol, limit=120)
        if df.empty or len(df) < 60:
            return float("-inf")

        close = df["close"].astype(float)
        high = df["high"].astype(float)
        low = df["low"].astype(float)
        volume = df["volume"].astype(float)

        price = float(close.iloc[-1])
        ma20 = float(close.rolling(20).mean().iloc[-1])
        ma50 = float(close.rolling(50).mean().iloc[-1])
        ret20 = float((close.iloc[-1] / close.iloc[-21]) - 1.0)
        atr_pct = float((high - low).rolling(14).mean().iloc[-1] / max(price, 1e-9))
        dollar_vol = float((close * volume).tail(20).mean())

        if dollar_vol < self.config.min_dollar_volume:
            return float("-inf")
        if atr_pct < self.config.min_atr_pct or atr_pct > self.config.max_atr_pct:
            return float("-inf")

        trend_bonus = 0.02 if (price > ma20 > ma50) else -0.02
        liquidity_bonus = min(0.05, max(0.0, (log10(max(dollar_vol, 1.0)) - 6.0) * 0.01))
        volatility_bonus = max(0.0, 0.02 - abs(atr_pct - 0.015))
        return ret20 + trend_bonus + liquidity_bonus + volatility_bonus

    def _refresh_active_symbols(self) -> None:
        """Pick top-ranked symbols from the configured universe."""
        if not self.config.dynamic_symbol_selection:
            self.active_symbols = list(self.config.symbols)
            return

        ranked = []
        for symbol in self.universe_symbols:
            score = self._score_symbol(symbol)
            if score == float("-inf"):
                continue
            ranked.append((score, symbol))

        ranked.sort(reverse=True)
        keep = max(1, min(self.config.dynamic_symbol_count, len(self.universe_symbols)))
        selected = [symbol for _, symbol in ranked[:keep]]

        if not selected:
            selected = list(self.config.symbols)

        changed = selected != self.active_symbols
        self.active_symbols = selected
        for s in self.active_symbols:
            self._ensure_position(s)

        if changed:
            self.logger.info(
                f"Dynamic selection updated | Active symbols: {', '.join(self.active_symbols)}"
            )

    def _sync_from_account(self) -> None:
        """Sync live Alpaca account balances and positions into local state."""
        if not self.api:
            return

        try:
            account = self.api.get_account()
            self.portfolio.sync_from_account(account)
            self.portfolio.new_day(datetime.now().date())
            self.daily_pnl = self.portfolio.daily_pnl_pct()

            live_positions = {position.symbol: position for position in self.api.list_positions()}
            for symbol in list(self.positions.keys()):
                local_position = self.positions.get(symbol) or StockPosition(symbol)
                live_position = live_positions.get(symbol)

                if live_position is None:
                    local_position.active = False
                    local_position.quantity = 0
                    self.positions[symbol] = local_position
                    continue

                try:
                    entry_price = float(live_position.avg_entry_price)
                    quantity = int(float(live_position.qty))
                except (TypeError, ValueError):
                    continue

                local_position.active = True
                local_position.entry_price = entry_price
                local_position.peak_price = max(local_position.peak_price, entry_price)
                local_position.trailing_stop = entry_price * (1 - self.config.stop_loss_pct)
                local_position.take_profit = entry_price * (1 + self.config.take_profit_pct)
                local_position.quantity = quantity
                self.positions[symbol] = local_position

            self._log_account_snapshot(account)
        except Exception as e:
            self.logger.warning(f"Failed to sync Alpaca account state: {e}")

    def _current_gross_exposure_value(self) -> float:
        """Estimate current gross exposure from synced positions."""
        total = 0.0
        for position in self.positions.values():
            if position.active and position.quantity > 0 and position.entry_price > 0:
                total += position.quantity * position.entry_price
        return total

    def _log_account_snapshot(self, account) -> None:
        """Emit a throttled snapshot of live account and portfolio stats."""
        cooldown_sec = max(0, int(getattr(self.config, "account_snapshot_log_cooldown_sec", 900)))
        now = datetime.now()
        if self._account_snapshot_last_log and (now - self._account_snapshot_last_log).total_seconds() < cooldown_sec:
            return

        gross_exposure = self._current_gross_exposure_value()
        equity = self.portfolio.equity
        exposure_pct = (gross_exposure / equity * 100.0) if equity > 0 else 0.0
        stats = self.portfolio.get_stats()

        account_cash = getattr(account, "cash", None)
        account_buying_power = getattr(account, "buying_power", None)
        unrealized_plpc = getattr(account, "unrealized_plpc", None)
        realized_plpc = getattr(account, "realized_plpc", None)

        parts = [
            f"equity=${equity:.2f}",
            f"cash=${self.portfolio.balance:.2f}",
            f"buying_power=${self.portfolio.buying_power:.2f}",
            f"day_pnl=${stats['daily_pnl']:+.2f} ({stats['daily_pnl_pct']:+.2f}%)",
            f"total_return={stats['total_return_pct']:+.2f}%",
            f"gross_exposure=${gross_exposure:.2f} ({exposure_pct:.1f}%)",
        ]

        if account_cash is not None:
            parts.append(f"alpaca_cash=${float(account_cash):.2f}")
        if account_buying_power is not None:
            parts.append(f"alpaca_bp=${float(account_buying_power):.2f}")
        if unrealized_plpc is not None:
            parts.append(f"unrealized_plpc={float(unrealized_plpc)*100.0:+.2f}%")
        if realized_plpc is not None:
            parts.append(f"realized_plpc={float(realized_plpc)*100.0:+.2f}%")

        self.logger.info("Alpaca snapshot | " + " | ".join(parts))
        self._account_snapshot_last_log = now

    def _size_order(
        self,
        symbol: str,
        price: float,
        stop_loss_price: float,
        atr_value: float,
        conviction_multiplier: float = 1.0,
        conviction_reason: str = "neutral",
    ) -> tuple[int, str]:
        """Size an order from live equity and stop distance."""
        position_size = self.risk.calculate_position_size(
            self.portfolio,
            entry_price=price,
            stop_loss_price=stop_loss_price,
            symbol=symbol,
            atr_value=atr_value,
            conviction_multiplier=conviction_multiplier,
        )

        qty = int(position_size.shares)
        max_affordable_qty = int((self.portfolio.balance * 0.95) / price) if self.portfolio.balance > 0 else 0
        qty = min(qty, max_affordable_qty)

        max_gross_exposure_pct = getattr(self.config, "max_gross_exposure_pct", 0.5)
        gross_exposure = self._current_gross_exposure_value()
        exposure_budget = max(0.0, (self.portfolio.equity * max_gross_exposure_pct) - gross_exposure)
        max_exposure_qty = int(exposure_budget / price) if price > 0 else 0
        qty = min(qty, max_exposure_qty)

        if qty <= 0:
            if exposure_budget <= 0:
                exposure_pct = (gross_exposure / self.portfolio.equity * 100.0) if self.portfolio.equity > 0 else 0.0
                return 0, f"Gross exposure cap reached ({exposure_pct:.1f}%/{max_gross_exposure_pct*100:.1f}%)"
            return 0, position_size.reason

        reason = position_size.reason
        if qty < int(position_size.shares):
            reason = f"{reason} | exposure cap ${exposure_budget:.2f} left"

        reason = f"{reason} | conviction {conviction_multiplier:.2f} ({conviction_reason})"
        return qty, reason

    def _compute_conviction_multiplier(
        self,
        df: pd.DataFrame,
        price: float,
        ai_confidence: float,
        volume_confirm: bool,
    ) -> tuple[float, str]:
        """Higher-conviction setups are allowed to risk more capital."""
        if not getattr(self.config, "profit_optimized_sizing", True):
            return 1.0, "disabled"

        min_mult = float(getattr(self.config, "min_conviction_risk_mult", 0.75))
        max_mult = float(getattr(self.config, "max_conviction_risk_mult", 1.75))
        high_conf = float(getattr(self.config, "high_confidence_threshold", 0.65))
        very_high_conf = float(getattr(self.config, "very_high_confidence_threshold", 0.75))

        score = 1.0
        reasons: list[str] = []

        if ai_confidence >= very_high_conf:
            score += 0.35
            reasons.append("very_high_ai")
        elif ai_confidence >= high_conf:
            score += 0.20
            reasons.append("high_ai")
        elif ai_confidence >= self.config.min_ai_confidence:
            score += 0.05
            reasons.append("ok_ai")

        if volume_confirm:
            score += 0.10
            reasons.append("volume")

        ma20 = float(df["close"].rolling(20).mean().iloc[-1]) if len(df) >= 20 else price
        ma50 = float(df["close"].rolling(50).mean().iloc[-1]) if len(df) >= 50 else ma20
        if price > ma20 > ma50:
            score += 0.10
            reasons.append("trend")

        score = max(min_mult, min(max_mult, score))
        return score, "+".join(reasons) if reasons else "neutral"
        
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
            self.positions = {s: StockPosition(s) for s in self.universe_symbols}
            self._refresh_active_symbols()
            self._sync_from_account()
            
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
            bars_limit = getattr(self.config, "bars_limit", 250)
            min_bars = max(getattr(self.config, "min_bars", 45), self.config.rsi_period + 2)
            df = self.fetch_bars(symbol, limit=bars_limit)

            if df.empty or len(df) < min_bars:
                now = datetime.now()
                cooldown_sec = max(0, int(getattr(self.config, "insufficient_data_log_cooldown_sec", 900)))
                last_log = self._insufficient_data_last_log.get(symbol)
                if (last_log is None) or ((now - last_log).total_seconds() >= cooldown_sec):
                    self.logger.warning(
                        f"[{symbol}] Insufficient data: bars={len(df)} required={min_bars}"
                    )
                    self._insufficient_data_last_log[symbol] = now
                return

            if symbol in self._insufficient_data_last_log:
                del self._insufficient_data_last_log[symbol]
            
            price = float(df["close"].iloc[-1])
            pos = self._ensure_position(symbol)
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
                    if self.retrainer:
                        self.retrainer.record_closed_trade()
                    
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
                    stop_loss_price = sig_details.stop_loss_atr or (price * (1 - self.config.stop_loss_pct))
                    conviction_multiplier, conviction_reason = self._compute_conviction_multiplier(
                        df,
                        price,
                        ai_confidence,
                        sig_details.volume_confirm,
                    )
                    qty, size_reason = self._size_order(
                        symbol,
                        price,
                        stop_loss_price,
                        sig_details.atr,
                        conviction_multiplier=conviction_multiplier,
                        conviction_reason=conviction_reason,
                    )
                    
                    # Validate trade size
                    trade_usd = qty * price
                    if not self._validate_trade_size(trade_usd):
                        self.logger.debug(f"[{symbol}] Trade size too small: ${trade_usd:.2f} | {size_reason}")
                        return
                    
                    if qty > 0:
                        self.logger.info(
                            f"[{symbol}] BUY signal | Vol:{volume_status} | ATR:{sig_details.atr:.2f} | "
                            f"AI:{ai_confidence:.0%} | Qty:{qty} | {size_reason}"
                        )
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

        self.daily_pnl = self.portfolio.daily_pnl_pct()
        
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
                    if self.retrainer:
                        self.retrainer.record_closed_trade()

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
                total_trades = int(stats.get("total_trades", 0))
                wins = int(stats.get("wins", 0))
                win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0
                total_pnl_usd = float(stats.get("total_pnl", 0.0))
                discord.notify_daily_summary({
                    "trades": total_trades,
                    "wins": wins,
                    "win_rate": f"{win_rate:.1f}%",
                    "pnl": f"${total_pnl_usd:+.2f}",
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
                if exit_price and side == "sell" and price > 0:
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
        self.logger.info(
            f"🤖 Stock Bot started | Universe: {len(self.universe_symbols)} | "
            f"Active: {self.active_symbols} | {self.config.timeframe}"
        )
        if self.ai:
            stats = self.ai.get_stats()
            total_trades = int(stats.get("total_trades", 0))
            wins = int(stats.get("wins", 0))
            win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0
            self.logger.info(f"🧠 AI active | Trades: {total_trades} | WR: {win_rate:.1f}%")

        self._wait_until_open()
        self.session_active = True
        
        # 🔔 Discord startup notification
        if discord:
            discord.send_message(
                "🚀 Stock Bot Started",
                {
                    "Symbols": ", ".join(self.active_symbols),
                    "Timeframe": self.config.timeframe,
                    "Mode": "PAPER TRADING" if self.config.paper_trading else "LIVE TRADING ⚠️",
                    "Status": "Ready",
                },
                color=3066993  # Green
            )
        
        try:
            while True:
                self._sync_from_account()

                if not self.market.is_open():
                    self.logger.info("Market closed | ending session and closing positions")
                    if self._has_open_positions():
                        self._close_all_positions("MARKET_CLOSE")
                    self._finalize_session()
                    self.session_active = False
                    return

                self.loop_count += 1
                if self.loop_count == 1 or self.loop_count % self.config.selection_refresh_cycles == 0:
                    self._refresh_active_symbols()

                for symbol in self.active_symbols:
                    self.process_symbol(symbol)
                
                # Check if model retraining is needed
                if self.retrainer and self.ai and self.retrainer.should_retrain():
                    self.logger.info("🧠 Triggering model retraining...")
                    try:
                        retrained = self.retrainer.retrain_model(self.ai)
                        if retrained:
                            self.logger.info("✅ Model retraining complete")
                        else:
                            self.logger.info("🧠 Retraining skipped (not enough recent closed-trade data)")
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
                    total_trades = int(stats.get("total_trades", 0))
                    wins = int(stats.get("wins", 0))
                    win_rate = (wins / total_trades * 100.0) if total_trades > 0 else 0.0
                    total_pnl_usd = float(stats.get("total_pnl", 0.0))
                    discord.notify_daily_summary({
                        "trades": total_trades,
                        "wins": wins,
                        "win_rate": f"{win_rate:.1f}%",
                        "pnl": f"${total_pnl_usd:+.2f}",
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
        error_text = str(e)
        logging.error(f"Failed to start bot: {error_text}")

        lowered = error_text.lower()
        is_auth_error = any(token in lowered for token in ("unauthorized", "forbidden", "401"))

        if discord:
            discord.notify_error("Stock Bot startup failed!", {"Error": error_text})

        # Exit code 3 is treated as non-restartable by systemd for auth/config issues.
        if is_auth_error:
            sys.exit(3)
        sys.exit(1)


if __name__ == "__main__":
    main()

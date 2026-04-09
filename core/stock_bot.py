"""
Stock Trading Bot — RSI + 200 MA on Real US Stocks (via Alpaca).

Paper trading on real market with SPY, QQQ, VOO + AI learning.

Run:  python stock_bot.py
"""

import sys
import logging
import time
import json
from math import log10
from logging.handlers import RotatingFileHandler
from typing import Any, Dict, List, Literal, Optional
from datetime import datetime
from pathlib import Path

import pandas as pd

try:
    import alpaca_trade_api as tradeapi
except ImportError:
    tradeapi = None

from stock_config import load_stock_config
from strategy import get_signal, get_signal_enhanced
from market_hours import USMarketSession
from external_signals import ExternalSignalMonitor

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

try:
    from daily_performance_report import load_closed_trades, build_report, load_cycle_metrics
    HAS_DAILY_REPORT = True
except ImportError:
    HAS_DAILY_REPORT = False


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
        self.entry_context: Dict[str, Any] = {}

    def open(
        self,
        price: float,
        quantity: int,
        stop_loss_pct: float,
        take_profit_pct: float,
        ai_confidence: float = 0.5,
        atr_stop: float = None,
        entry_context: Optional[Dict[str, Any]] = None,
    ) -> None:
        """Open position. Use ATR stop if provided, otherwise fixed %."""
        log = logging.getLogger("stock-bot")
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
        self.entry_context = dict(entry_context or {})
        log.info(
            f"[{self.symbol}] OPEN position: ${price:.2f} x {quantity} | "
            f"Stop: ${self.trailing_stop:.2f} | TP: ${self.take_profit:.2f} | AI: {ai_confidence:.0%}"
        )

    def check_exit(self, price: float, trailing_stop_pct: float) -> Literal["HOLD", "TRAIL_STOP", "TAKE_PROFIT"]:
        """Check if should exit."""
        log = logging.getLogger("stock-bot")
        if self.active:
            log.debug(f"[{self.symbol}] Price: ${price:.2f} Trail: ${self.trailing_stop:.2f} TP: ${self.take_profit:.2f}")
        if not self.active:
            return "HOLD"
        
        if price > self.peak_price:
            self.peak_price = price
            self.trailing_stop = price * (1 - trailing_stop_pct)
        
        if price <= self.trailing_stop:
            log.info(
                f"[{self.symbol}] EXIT TRAIL_STOP @ ${price:.2f} "
                f"(Entry: ${self.entry_price:.2f}, Loss: {(price/self.entry_price - 1)*100:.1f}%)"
            )
            return "TRAIL_STOP"
        if price >= self.take_profit:
            log.info(
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
        self.retrainer = ModelRetrainer(retrain_interval=20) if HAS_RETRAINER and HAS_AI else None
        self.daily_pnl = 0.0  # Track daily P&L for max loss limit
        self.start_date = datetime.now().date()  # Reset daily loss at midnight
        self.market = USMarketSession()
        self.external_signals = ExternalSignalMonitor(config, self.logger)
        self.session_active = False
        self.trading_paused = False
        self.pause_reason = ""
        self.loop_count = 0
        self.universe_symbols = self._build_universe()
        self.active_symbols = list(self.config.symbols)
        self.symbol_tiers = self._build_symbol_tiers()
        self.decision_trace_enabled = bool(getattr(self.config, "decision_trace_enabled", True))
        self.decision_trace_to_console = bool(getattr(self.config, "decision_trace_to_console", False))
        self.decision_trace_file = str(getattr(self.config, "decision_trace_file", "logs/decision_trace.jsonl"))
        self.cycle_stats = {}
        self._reset_cycle_stats()

    @staticmethod
    def _to_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return float(value)
        except Exception:
            return default

    def _trace_decision(self, symbol: str, stage: str, decision: str, payload: Optional[Dict[str, Any]] = None) -> None:
        """Write structured decision traces for explainability and win-rate tuning."""
        if not self.decision_trace_enabled:
            return

        event: Dict[str, Any] = {
            "timestamp": datetime.now().isoformat(),
            "symbol": symbol,
            "stage": stage,
            "decision": decision,
            "loop": int(self.loop_count),
        }
        if payload:
            event.update(payload)

        try:
            path = Path(self.decision_trace_file)
            path.parent.mkdir(parents=True, exist_ok=True)
            with path.open("a", encoding="utf-8") as f:
                f.write(json.dumps(event, ensure_ascii=True) + "\n")
        except Exception as e:
            self.logger.debug(f"Decision trace write failed: {e}")

        if self.decision_trace_to_console:
            self.logger.info(
                "TRACE | %s | %s | %s | %s",
                symbol,
                stage,
                decision,
                json.dumps(payload or {}, ensure_ascii=True),
            )

    def _reset_cycle_stats(self) -> None:
        self.cycle_stats = {
            "bars_ok": 0,
            "bars_insufficient": 0,
            "signals_buy": 0,
            "entries_attempted": 0,
            "entries_blocked": 0,
            "entries_blocked_external": 0,
            "entries_filled": 0,
            "exits": 0,
            "errors": 0,
        }

    def _log_cycle_stats(self) -> None:
        if not self.cycle_stats:
            return
        self.logger.info(
            "Cycle stats | bars_ok=%d insufficient=%d buy_signals=%d entries=%d blocked=%d blocked_external=%d filled=%d exits=%d errors=%d",
            self.cycle_stats["bars_ok"],
            self.cycle_stats["bars_insufficient"],
            self.cycle_stats["signals_buy"],
            self.cycle_stats["entries_attempted"],
            self.cycle_stats["entries_blocked"],
            self.cycle_stats["entries_blocked_external"],
            self.cycle_stats["entries_filled"],
            self.cycle_stats["exits"],
            self.cycle_stats["errors"],
        )

    def _inc_stat(self, key: str, value: int = 1) -> None:
        self.cycle_stats[key] = int(self.cycle_stats.get(key, 0)) + value

    def _entry_risk_check(self, symbol: str, df: pd.DataFrame, price: float) -> tuple[bool, str]:
        """Additional entry filters for spread, volatility, and liquidity spikes."""
        try:
            max_bar_spread_pct = float(getattr(self.config, "max_bar_spread_pct", 0.02))
            max_entry_atr_pct = float(getattr(self.config, "max_entry_atr_pct", 0.08))
            min_entry_dollar_volume = float(getattr(self.config, "min_entry_dollar_volume", self.config.min_trade_usd * 50))

            high = float(df["high"].iloc[-1])
            low = float(df["low"].iloc[-1])
            spread_pct = (high - low) / max(price, 1e-9)
            if spread_pct > max_bar_spread_pct:
                return False, f"{symbol} spread too wide ({spread_pct:.2%} > {max_bar_spread_pct:.2%})"

            atr_pct = float((df["high"] - df["low"]).rolling(14).mean().iloc[-1] / max(price, 1e-9))
            if atr_pct > max_entry_atr_pct:
                return False, f"{symbol} volatility too high ({atr_pct:.2%} > {max_entry_atr_pct:.2%})"

            dollar_volume = float((df["close"] * df["volume"]).tail(20).mean())
            if dollar_volume < min_entry_dollar_volume:
                return False, f"{symbol} liquidity too low (${dollar_volume:,.0f} < ${min_entry_dollar_volume:,.0f})"

            return True, "ok"
        except Exception as e:
            return False, f"{symbol} risk check failed: {e}"

    def _maybe_retrain(self, trade_closed: bool = False) -> None:
        if not (self.retrainer and self.ai):
            return
        if not self.retrainer.should_retrain(trade_closed=trade_closed):
            return

        self.logger.info("🧠 Triggering model retraining after closed-trade threshold...")
        try:
            retrained = self.retrainer.retrain_model(self.ai)
            if retrained:
                self.logger.info("✅ Model retraining complete")
                if discord:
                    discord.notify_warning("🧠 Model retraining complete")
        except Exception as e:
            self.logger.error(f"❌ Model retraining failed: {e}")
            if discord:
                discord.notify_error(f"Model retraining failed: {e}")

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

    def _build_symbol_tiers(self) -> Dict[str, str]:
        tiers: Dict[str, str] = {}
        for s in getattr(self.config, "symbol_tier_a", []) or []:
            tiers[str(s).strip().upper()] = "A"
        for s in getattr(self.config, "symbol_tier_b", []) or []:
            tiers[str(s).strip().upper()] = "B"
        for s in getattr(self.config, "symbol_tier_c", []) or []:
            tiers[str(s).strip().upper()] = "C"
        return tiers

    def _symbol_tier(self, symbol: str) -> str:
        return str(self.symbol_tiers.get(str(symbol).upper(), "B")).upper()

    def _tier_weight(self, tier: str) -> float:
        t = str(tier).upper()
        if t == "A":
            return float(getattr(self.config, "tier_weight_a", 1.0))
        if t == "C":
            return float(getattr(self.config, "tier_weight_c", 0.0))
        return float(getattr(self.config, "tier_weight_b", 0.75))

    def _regime_weight(self, trend: str) -> float:
        t = str(trend or "").upper()
        if t == "UPTREND":
            return float(getattr(self.config, "regime_weight_uptrend", 1.0))
        if t == "DOWNTREND":
            return float(getattr(self.config, "regime_weight_downtrend", 0.5))
        return float(getattr(self.config, "regime_weight_ranging", 0.7))

    def _min_ai_for_trend(self, trend: str) -> float:
        t = str(trend or "").upper()
        base = float(getattr(self.config, "min_ai_confidence", 0.45))
        if t == "UPTREND":
            return float(getattr(self.config, "min_ai_confidence_uptrend", base))
        if t == "DOWNTREND":
            return float(getattr(self.config, "min_ai_confidence_downtrend", max(base, 0.60)))
        return float(getattr(self.config, "min_ai_confidence_ranging", max(base, 0.55)))

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

        base_score = ret20 + trend_bonus + liquidity_bonus + volatility_bonus
        weight = float(getattr(self.config, "external_symbol_weight", 0.0))
        if weight <= 0:
            return base_score

        ext = self.external_signals.get_snapshot(symbol)
        ext_component = (0.6 * ext.catalyst_score) + (0.3 * ((ext.sentiment_score + 1.0) / 2.0)) - (0.3 * ext.event_risk)
        return base_score + (weight * ext_component)

    def _startup_model_quality_gate(self) -> None:
        """Pause entries at startup when latest model report does not pass thresholds."""
        if not bool(getattr(self.config, "enforce_model_quality_gate", False)):
            return

        path = Path(getattr(self.config, "model_quality_report_path", "training_report.json"))
        if not path.exists():
            self.trading_paused = True
            self.pause_reason = f"model quality gate: missing report {path}"
            self.logger.warning("Entry pause enabled: %s", self.pause_reason)
            return

        try:
            payload = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
            auc = float(payload.get("overall_auc", 0.0))
            f1 = float(payload.get("overall_f1", 0.0))
            holdout = int(payload.get("total_test_samples", 0))
            min_auc = float(getattr(self.config, "model_min_auc", 0.53))
            min_f1 = float(getattr(self.config, "model_min_f1", 0.53))
            min_holdout = int(getattr(self.config, "model_min_holdout_samples", 60))

            if auc < min_auc or f1 < min_f1 or holdout < min_holdout:
                self.trading_paused = True
                self.pause_reason = (
                    "model quality gate: "
                    f"auc={auc:.3f} f1={f1:.3f} holdout={holdout} "
                    f"required auc>={min_auc:.3f} f1>={min_f1:.3f} holdout>={min_holdout}"
                )
                self.logger.warning("Entry pause enabled: %s", self.pause_reason)
                return

            self.logger.info("Model quality gate passed | auc=%.3f f1=%.3f holdout=%d", auc, f1, holdout)
        except Exception as e:
            self.trading_paused = True
            self.pause_reason = f"model quality gate: failed to parse report ({e})"
            self.logger.warning("Entry pause enabled: %s", self.pause_reason)

    def _refresh_decay_gate(self) -> None:
        """Pause or resume entries based on decay + drawdown multi-condition signal."""
        if not bool(getattr(self.config, "decay_gate_enabled", True)):
            return
        if not HAS_DAILY_REPORT:
            return

        try:
            df = load_closed_trades("trades_history.csv")
            report = build_report(df, cycle_metrics=load_cycle_metrics("stock_bot.log", lookback_days=1))
            level = str(report.get("decay_level", "STABLE")).upper()
            max_loss_pct = float(getattr(self.config, "max_daily_loss_pct", 0.05)) * 100.0
            trigger_frac = float(getattr(self.config, "decay_gate_daily_loss_fraction", 0.5))
            drawdown_trigger = -abs(max_loss_pct * trigger_frac)

            gate_payload = {
                "generated_at": datetime.now().isoformat(),
                "decay_level": level,
                "pause_recommended": level == "CRITICAL",
                "drawdown_trigger_pct": drawdown_trigger,
                "daily_pnl_pct": float(self.daily_pnl),
                "reason": report.get("decay_reason", ""),
            }
            gate_file = Path(getattr(self.config, "decay_gate_file", "logs/strategy_gate.json"))
            gate_file.parent.mkdir(parents=True, exist_ok=True)
            gate_file.write_text(json.dumps(gate_payload, indent=2), encoding="utf-8")

            should_pause = level == "CRITICAL" and self.daily_pnl <= drawdown_trigger
            if should_pause:
                self.trading_paused = True
                self.pause_reason = (
                    f"decay gate: level={level}, daily_pnl={self.daily_pnl:.2f}% "
                    f"<= trigger={drawdown_trigger:.2f}%"
                )
                self.logger.warning("Entry pause enabled: %s", self.pause_reason)
                return

            # Only auto-resume if no startup quality lock is active.
            if self.trading_paused and self.pause_reason.startswith("decay gate"):
                self.trading_paused = False
                self.pause_reason = ""
                self.logger.info("Decay gate resumed entries: conditions back within thresholds")
        except Exception as e:
            self.logger.debug(f"Decay gate refresh failed: {e}")

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
                self._inc_stat("bars_insufficient")
                self.logger.warning(f"[{symbol}] Insufficient data")
                self._trace_decision(symbol, "data", "skip", {"reason": "insufficient_data", "bars": int(len(df))})
                return
            self._inc_stat("bars_ok")
            
            price = float(df["close"].iloc[-1])
            pos = self._ensure_position(symbol)
            pos.tick_cooldown()

            # Check for exit
            exit_reason = pos.check_exit(price, self.config.trailing_stop_pct)
            if exit_reason in ("TRAIL_STOP", "TAKE_PROFIT"):
                self.logger.info(f"[{symbol}] EXIT {exit_reason} @ ${price:.2f}")
                success = self.place_order("sell", symbol, pos.quantity)
                if success:
                    self._inc_stat("exits")
                    was_loss = price < pos.entry_price
                    pnl = (price - pos.entry_price) * pos.quantity
                    pnl_pct = (pnl / (pos.entry_price * pos.quantity)) * 100 if pos.entry_price > 0 else 0
                    self.daily_pnl += pnl_pct

                    self._trace_decision(
                        symbol,
                        "exit",
                        "filled",
                        {
                            "exit_reason": exit_reason,
                            "entry_price": round(float(pos.entry_price), 4),
                            "exit_price": round(price, 4),
                            "qty": int(pos.quantity),
                            "pnl_usd": round(float(pnl), 4),
                            "pnl_pct": round(float(pnl_pct), 4),
                            "was_right": bool(pnl > 0),
                            "entry_context": dict(pos.entry_context or {}),
                        },
                    )
                    
                    self._log_trade(symbol, "sell", pos.entry_price, pos.quantity, pos.ai_confidence, 
                                   exit_reason=exit_reason, exit_price=price, pnl=pnl)
                    
                    if self.ai:
                        self.ai.update_from_trade(pnl, not was_loss)
                    
                    # Send Discord notification
                    if discord:
                        discord.notify_sell(symbol, pos.entry_price, price, pos.quantity, pnl_pct, exit_reason)
                    
                    pos.close(was_loss=was_loss, cooldown_candles=self.config.cooldown_candles)
                    self._maybe_retrain(trade_closed=True)
            
            # Check for entry
            elif pos.ready():
                if self.trading_paused:
                    self.logger.debug(f"[{symbol}] Entry paused: {self.pause_reason}")
                    self._trace_decision(symbol, "pre_entry", "blocked", {"reason": "trading_paused", "pause_reason": self.pause_reason})
                    return

                # Check daily loss limit and max open positions
                if not self._check_daily_loss():
                    self._trace_decision(symbol, "pre_entry", "blocked", {"reason": "daily_loss_limit"})
                    return  # Stop trading for the day
                
                if self._count_open_positions() >= self.config.max_open_positions:
                    self.logger.debug(f"[{symbol}] Max open positions ({self.config.max_open_positions}) reached")
                    self._trace_decision(
                        symbol,
                        "pre_entry",
                        "blocked",
                        {"reason": "max_open_positions", "max_open_positions": int(self.config.max_open_positions)},
                    )
                    return
                
                signal, sig_details = get_signal_enhanced(df, self.config.rsi_period, self.config.rsi_oversold, self.config.rsi_overbought)
                if signal == "BUY":
                    self._inc_stat("signals_buy")

                signal_context = {
                    "signal": signal,
                    "reason": str(getattr(sig_details, "reason", "")),
                    "trade_grade": str(getattr(sig_details, "trade_grade", "")),
                    "quality_score": round(self._to_float(getattr(sig_details, "quality_score", 0.0)), 4),
                    "rsi": round(self._to_float(getattr(sig_details, "rsi", 0.0)), 4),
                    "trend": str(getattr(sig_details, "trend", "")),
                    "atr": round(self._to_float(getattr(sig_details, "atr", 0.0)), 6),
                    "volume_confirm": bool(getattr(sig_details, "volume_confirm", False)),
                    "no_trade_zone": bool(getattr(sig_details, "no_trade_zone", False)),
                    "no_trade_reason": str(getattr(sig_details, "no_trade_reason", "")),
                    "price": round(price, 4),
                }
                self._trace_decision(symbol, "signal", signal.lower(), signal_context)

                tier = self._symbol_tier(symbol)
                if tier == "C":
                    self._inc_stat("entries_blocked")
                    self._trace_decision(symbol, "tier_gate", "blocked", {"reason": "tier_c_block", "tier": tier})
                    return
                
                # Log volume confirmation
                volume_status = "✓" if sig_details.volume_confirm else "✗"
                
                ai_confidence = 0.5
                ext_snapshot = self.external_signals.get_snapshot(symbol)
                if self.ai and signal == "BUY":
                    model_df = df.copy()
                    model_df["external_sentiment"] = float(ext_snapshot.sentiment_score)
                    model_df["external_catalyst"] = float(ext_snapshot.catalyst_score)
                    model_df["external_event_risk"] = float(ext_snapshot.event_risk)
                    model_df["external_confidence"] = float(ext_snapshot.confidence)
                    ai_confidence = self.ai.predict_entry_probability(model_df)

                self._trace_decision(
                    symbol,
                    "ai_gate",
                    "evaluated",
                    {
                        "ai_enabled": bool(self.ai is not None),
                        "ai_confidence": round(float(ai_confidence), 6),
                        "min_ai_confidence": round(float(self._min_ai_for_trend(getattr(sig_details, "trend", ""))), 6),
                        "passed": bool((not self.ai) or (signal != "BUY") or (ai_confidence > float(self._min_ai_for_trend(getattr(sig_details, "trend", ""))))),
                        "external_sentiment": round(float(ext_snapshot.sentiment_score), 6),
                        "external_catalyst": round(float(ext_snapshot.catalyst_score), 6),
                        "external_event_risk": round(float(ext_snapshot.event_risk), 6),
                        "external_confidence": round(float(ext_snapshot.confidence), 6),
                        "tier": tier,
                    },
                )
                
                if signal == "BUY" and (not self.ai or ai_confidence > float(self._min_ai_for_trend(getattr(sig_details, "trend", "")))):
                    self._inc_stat("entries_attempted")

                    ext_allowed, ext_reason = self.external_signals.allow_entry(ext_snapshot)
                    if not ext_allowed:
                        self._inc_stat("entries_blocked")
                        self._inc_stat("entries_blocked_external")
                        self.logger.info(
                            "[%s] Entry blocked by external gate: %s | sentiment=%.2f catalyst=%.2f event_risk=%.2f confidence=%.2f",
                            symbol,
                            ext_reason,
                            ext_snapshot.sentiment_score,
                            ext_snapshot.catalyst_score,
                            ext_snapshot.event_risk,
                            ext_snapshot.confidence,
                        )
                        self._trace_decision(
                            symbol,
                            "external_gate",
                            "blocked",
                            {
                                "reason": ext_reason,
                                "sentiment": round(float(ext_snapshot.sentiment_score), 6),
                                "catalyst": round(float(ext_snapshot.catalyst_score), 6),
                                "event_risk": round(float(ext_snapshot.event_risk), 6),
                                "confidence": round(float(ext_snapshot.confidence), 6),
                            },
                        )
                        return
                    self._trace_decision(symbol, "external_gate", "passed", {"reason": ext_reason})

                    allowed, reason = self._entry_risk_check(symbol, df, price)
                    if not allowed:
                        self._inc_stat("entries_blocked")
                        self.logger.info(f"[{symbol}] Entry blocked: {reason}")
                        self._trace_decision(symbol, "risk_gate", "blocked", {"reason": reason})
                        return
                    self._trace_decision(symbol, "risk_gate", "passed", {"reason": reason})

                    regime_weight = self._regime_weight(getattr(sig_details, "trend", ""))
                    tier_weight = self._tier_weight(tier)
                    effective_trade_usd = float(self.config.trade_amount_usd) * tier_weight * regime_weight
                    qty = int(effective_trade_usd / price)
                    
                    # Validate trade size
                    trade_usd = qty * price
                    if not self._validate_trade_size(trade_usd):
                        self._inc_stat("entries_blocked")
                        self.logger.debug(f"[{symbol}] Trade size too small: ${trade_usd:.2f}")
                        self._trace_decision(
                            symbol,
                            "size_gate",
                            "blocked",
                            {
                                "trade_usd": round(float(trade_usd), 4),
                                "min_trade_usd": round(float(self.config.min_trade_usd), 4),
                                "effective_trade_usd": round(float(effective_trade_usd), 4),
                                "tier": tier,
                                "tier_weight": round(float(tier_weight), 4),
                                "regime_weight": round(float(regime_weight), 4),
                            },
                        )
                        return
                    self._trace_decision(
                        symbol,
                        "size_gate",
                        "passed",
                        {
                            "trade_usd": round(float(trade_usd), 4),
                            "qty": int(qty),
                            "effective_trade_usd": round(float(effective_trade_usd), 4),
                            "tier": tier,
                            "tier_weight": round(float(tier_weight), 4),
                            "regime_weight": round(float(regime_weight), 4),
                        },
                    )
                    
                    if qty > 0:
                        self.logger.info(f"[{symbol}] BUY signal | Vol:{volume_status} | ATR:{sig_details.atr:.2f} | AI:{ai_confidence:.0%}")
                        success = self.place_order("buy", symbol, qty, ai_confidence)
                        if success:
                            self._inc_stat("entries_filled")
                            self._log_trade(symbol, "buy", price, qty, ai_confidence)
                            entry_context = {
                                "signal_reason": str(getattr(sig_details, "reason", "")),
                                "trade_grade": str(getattr(sig_details, "trade_grade", "")),
                                "quality_score": round(self._to_float(getattr(sig_details, "quality_score", 0.0)), 4),
                                "rsi": round(self._to_float(getattr(sig_details, "rsi", 0.0)), 4),
                                "trend": str(getattr(sig_details, "trend", "")),
                                "atr": round(self._to_float(getattr(sig_details, "atr", 0.0)), 6),
                                "volume_confirm": bool(getattr(sig_details, "volume_confirm", False)),
                                "ai_confidence": round(float(ai_confidence), 6),
                                "external_sentiment": round(float(ext_snapshot.sentiment_score), 6),
                                "external_catalyst": round(float(ext_snapshot.catalyst_score), 6),
                                "external_event_risk": round(float(ext_snapshot.event_risk), 6),
                                "external_confidence": round(float(ext_snapshot.confidence), 6),
                                "tier": tier,
                                "tier_weight": round(float(tier_weight), 4),
                                "regime_weight": round(float(regime_weight), 4),
                                "effective_trade_usd": round(float(effective_trade_usd), 4),
                            }
                            self._trace_decision(symbol, "entry", "filled", {"qty": int(qty), "price": round(price, 4), **entry_context})
                            pos.open(
                                price,
                                qty,
                                self.config.stop_loss_pct,
                                self.config.take_profit_pct,
                                ai_confidence,
                                atr_stop=getattr(sig_details, "stop_loss_atr", None),
                                entry_context=entry_context,
                            )
                            # Send Discord notification
                            if discord:
                                discord.notify_buy(symbol, price, qty, ai_confidence)
                elif signal == "BUY":
                    self._inc_stat("entries_blocked")
                    self._trace_decision(
                        symbol,
                        "ai_gate",
                        "blocked",
                        {
                            "reason": "ai_confidence_below_min",
                            "ai_confidence": round(float(ai_confidence), 6),
                            "min_ai_confidence": round(float(self._min_ai_for_trend(getattr(sig_details, "trend", ""))), 6),
                            "tier": tier,
                        },
                    )
            elif pos.active:
                self.logger.debug(f"[{symbol}] ${price:.2f} TP=${pos.take_profit:.2f} TS=${pos.trailing_stop:.2f}")
            else:
                self.logger.debug(f"[{symbol}] Cooldown: {pos.cooldown} bars")
                
        except Exception as e:
            self._inc_stat("errors")
            self._trace_decision(symbol, "error", "exception", {"error": str(e)})
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
                    self._inc_stat("exits")
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
                    self._maybe_retrain(trade_closed=True)
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
        self._startup_model_quality_gate()
        self.logger.info(
            f"🤖 Stock Bot started | Universe: {len(self.universe_symbols)} | "
            f"Active: {self.active_symbols} | {self.config.timeframe}"
        )
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
                    "Symbols": ", ".join(self.active_symbols),
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

                self.loop_count += 1
                self._reset_cycle_stats()
                if self.loop_count == 1 or self.loop_count % self.config.selection_refresh_cycles == 0:
                    self._refresh_active_symbols()
                if self.loop_count == 1 or self.loop_count % int(getattr(self.config, "decay_gate_check_cycles", 10)) == 0:
                    self._refresh_decay_gate()

                for symbol in self.active_symbols:
                    self.process_symbol(symbol)
                self._log_cycle_stats()

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

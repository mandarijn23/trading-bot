"""
Stock Trading Bot — RSI + 200 MA on Real US Stocks (via Alpaca).

Paper trading on real market with SPY, QQQ, VOO + AI learning.

Run:  python stock_bot.py
"""

import sys
import logging
import time
from math import log10
from pathlib import Path
from logging.handlers import RotatingFileHandler
from typing import Dict, List, Literal
from datetime import datetime, timezone

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

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

try:
    from model_drift import ModelDriftMonitor
except ImportError:
    ModelDriftMonitor = None

try:
    from concentration import PortfolioConcentrationMonitor
except ImportError:
    PortfolioConcentrationMonitor = None

try:
    from portfolio_analytics import PortfolioRiskAnalyzer
except ImportError:
    PortfolioRiskAnalyzer = None

try:
    from sector_exposure import SectorExposureAnalyzer
except ImportError:
    SectorExposureAnalyzer = None

try:
    from health_monitor import HealthMonitor
except ImportError:
    HealthMonitor = None

# NEW: Professional trading features
try:
    from multi_timeframe import MultiTimeframeAnalyzer, TimeframeDataManager
    HAS_MULTIFRAME = True
except ImportError:
    HAS_MULTIFRAME = False

try:
    from execution_optimizer import ExecutionOptimizer
    HAS_EXECUTION = True
except ImportError:
    HAS_EXECUTION = False

try:
    from kalman_filter import AdaptiveConfidenceFilter, BayesianEdgeDetector
    HAS_KALMAN = True
except ImportError:
    HAS_KALMAN = False

try:
    from capital_allocation import MultiStrategyAllocator, KellyCriterion
    HAS_CAPITAL_ALLOC = True
except ImportError:
    HAS_CAPITAL_ALLOC = False

try:
    from macro_regime import MacroRegimeDetector, LatencyTracker
    HAS_MACRO_REGIME = True
except ImportError:
    HAS_MACRO_REGIME = False

try:
    from order_flow import OrderFlowDetector, VolumeProfileAnalyzer
    HAS_ORDER_FLOW = True
except ImportError:
    HAS_ORDER_FLOW = False

try:
    from multi_strategy_engine import MultiStrategyEngine
    HAS_MULTI_STRATEGY = True
except ImportError:
    HAS_MULTI_STRATEGY = False

try:
    from options_strategies import OptionsStrategyGenerator
    HAS_OPTIONS = True
except ImportError:
    HAS_OPTIONS = False

try:
    from order_executor import ReliableOrderExecutor, OrderExecutionError, OrderRejectedError
except ImportError:
    ReliableOrderExecutor = None
    OrderExecutionError = RuntimeError
    OrderRejectedError = RuntimeError

try:
    from order_watchdog import OrderWatchdog
except ImportError:
    OrderWatchdog = None

try:
    from observability.json_logger import JsonEventLogger
    from observability.trade_logger import TradeLogger
except ImportError:
    JsonEventLogger = None
    TradeLogger = None


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
        logger = logging.getLogger("stock-bot")
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
        self.drift_monitor = (
            ModelDriftMonitor(
                window_trades=getattr(self.config, "drift_detection_window_trades", 20),
                threshold=getattr(self.config, "drift_detection_threshold", 0.20),
                min_trades=getattr(self.config, "drift_detection_min_trades", 10),
                confidence_floor=getattr(self.config, "drift_confidence_floor", 0.65),
                risk_scale=getattr(self.config, "drift_risk_scale", 0.75),
            )
            if ModelDriftMonitor is not None
            else None
        )
        self.concentration_monitor = (
            PortfolioConcentrationMonitor(
                max_symbol_exposure_pct=getattr(self.config, "max_symbol_exposure_pct", 0.20),
                max_group_exposure_pct=getattr(self.config, "max_group_exposure_pct", 0.45),
            )
            if PortfolioConcentrationMonitor is not None
            else None
        )
        self.portfolio_risk_analyzer = (
            PortfolioRiskAnalyzer(
                correlation_threshold=float(getattr(self.config, "correlation_threshold", 0.85)),
                max_portfolio_heat_pct=float(getattr(self.config, "max_portfolio_heat_pct", 0.15)),
                min_periods=int(getattr(self.config, "correlation_min_periods", 30)),
                lookback_bars=int(getattr(self.config, "correlation_lookback_bars", 120)),
                fallback_stop_pct=float(getattr(self.config, "stop_loss_pct", 0.03)),
            )
            if PortfolioRiskAnalyzer is not None
            else None
        )
        self.sector_exposure_analyzer = (
            SectorExposureAnalyzer(
                max_sector_exposure_pct=float(getattr(self.config, "max_sector_exposure_pct", 0.40)),
                imbalance_alert_pct=float(getattr(self.config, "sector_imbalance_alert_pct", 0.30)),
            )
            if SectorExposureAnalyzer is not None
            else None
        )
        self.health_monitor = (
            HealthMonitor(
                cpu_load_warn_pct=float(getattr(self.config, "health_cpu_load_warn_pct", 90.0)),
                memory_warn_pct=float(getattr(self.config, "health_memory_warn_pct", 90.0)),
                disk_warn_pct=float(getattr(self.config, "health_disk_warn_pct", 90.0)),
                api_stale_sec=int(getattr(self.config, "health_api_stale_sec", 180)),
            )
            if HealthMonitor is not None
            else None
        )
        
        # NEW: Pro features initialization
        self.multiframe_analyzer = MultiTimeframeAnalyzer() if HAS_MULTIFRAME else None
        self.execution_optimizer = ExecutionOptimizer(config) if HAS_EXECUTION else None
        self.kalman_filter = AdaptiveConfidenceFilter(prior_win_rate=0.55, initial_confidence=0.3) if HAS_KALMAN else None
        self.capital_allocator = MultiStrategyAllocator() if HAS_CAPITAL_ALLOC else None
        self.macro_regime_detector = MacroRegimeDetector() if HAS_MACRO_REGIME else None
        self.latency_tracker = LatencyTracker(backtest_latency_ms=50) if HAS_MACRO_REGIME else None
        self.order_flow_detector = OrderFlowDetector() if HAS_ORDER_FLOW else None
        self.multi_strategy_engine = MultiStrategyEngine(symbols=getattr(self.config, "symbols", [])) if HAS_MULTI_STRATEGY else None
        self.options_generator = OptionsStrategyGenerator(config) if HAS_OPTIONS else None
        self.order_executor = None
        self.order_watchdog = None
        self._json_event_log_path = str(getattr(self.config, "json_event_log_path", "logs/events.jsonl"))
        self._trades_db_path = str(getattr(self.config, "trades_db_path", "data/trades.db"))
        self.event_logger = None
        self.trade_logger = None
        self._last_execution_by_symbol: Dict[str, dict] = {}
        
        self.daily_pnl = 0.0  # Track daily P&L for max loss limit
        self.start_date = datetime.now().date()  # Reset daily loss at midnight
        self.market = USMarketSession()
        self.session_active = False
        self.loop_count = 0
        self.universe_symbols = self._build_universe()
        self.active_symbols = list(self.config.symbols)
        self._insufficient_data_last_log: Dict[str, datetime] = {}
        self._account_snapshot_last_log: datetime | None = None
        self.ai_confidence_floor_override = float(getattr(self.config, "min_ai_confidence", 0.45))
        self.drift_risk_scale = 1.0
        self._max_positions_notified_today = False  # Track if we've alerted about max positions
        self.benchmark_symbols = self._normalize_benchmark_symbols(
            getattr(self.config, "benchmark_symbols", ["SPY", "VTI"])
        )
        self.benchmark_record_every_loops = max(1, int(getattr(self.config, "benchmark_record_every_loops", 1)))
        self.health_check_every_loops = max(1, int(getattr(self.config, "health_check_every_loops", 1)))
        self.health_alert_cooldown_sec = max(0, int(getattr(self.config, "health_alert_cooldown_sec", 300)))
        self._last_health_alert_at: datetime | None = None
        self._last_api_heartbeat_at: datetime | None = None

    @staticmethod
    def _normalize_benchmark_symbols(symbols: List[str]) -> List[str]:
        """Normalize and de-duplicate benchmark symbols while preserving order."""
        ordered: List[str] = []
        seen = set()
        for symbol in symbols:
            normalized = str(symbol).strip().upper()
            if not normalized or normalized in seen:
                continue
            seen.add(normalized)
            ordered.append(normalized)
        return ordered

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
        # Reset max positions notification flag on new day
        today = datetime.now().date()
        if today > self.start_date:
            self._max_positions_notified_today = False
            self.start_date = today
        
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
            self._last_api_heartbeat_at = datetime.now(timezone.utc)

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

    def _run_health_checks(self) -> None:
        """Run periodic health checks and alert on critical failures."""
        if self.health_monitor is None:
            return

        report = self.health_monitor.evaluate(
            last_api_heartbeat_at=self._last_api_heartbeat_at,
            now=datetime.now(timezone.utc),
            api_required=bool(self.api is not None),
        )
        issues = report.get("issues", [])

        self._emit_event(
            {
                "event": "health_check",
                "metrics": report.get("metrics", {}),
                "heartbeat_age_sec": report.get("heartbeat_age_sec"),
                "issue_count": len(issues),
                "issues": issues,
            },
            level="INFO" if not issues else "WARNING",
            component="HealthMonitor",
        )

        if not issues:
            return

        for issue in issues:
            level = str(issue.get("level", "warning")).lower()
            component = str(issue.get("component", "unknown"))
            message = str(issue.get("message", "health issue"))
            value = issue.get("value")
            threshold = issue.get("threshold")
            suffix = ""
            if value is not None and threshold is not None:
                suffix = f" | value={value:.2f} threshold={float(threshold):.2f}"
            if level == "critical":
                self.logger.error(f"Health critical [{component}] {message}{suffix}")
            else:
                self.logger.warning(f"Health warning [{component}] {message}{suffix}")

        has_critical = bool(report.get("has_critical", False))
        if not has_critical or not discord:
            return

        now = datetime.now(timezone.utc)
        if self._last_health_alert_at is not None:
            elapsed = (now - self._last_health_alert_at).total_seconds()
            if elapsed < self.health_alert_cooldown_sec:
                return

        self._last_health_alert_at = now
        critical = [issue for issue in issues if str(issue.get("level", "")).lower() == "critical"]
        details = {
            "critical_issues": len(critical),
            "issues": "; ".join(
                f"{issue.get('component')}: {issue.get('message')}"
                for issue in critical[:3]
            ) or "none",
            "heartbeat_age_sec": report.get("heartbeat_age_sec"),
        }
        discord.notify_error("Health monitor critical state", details)

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

    def _record_benchmark_prices(self) -> None:
        """Persist latest benchmark closes for portfolio-relative performance tracking."""
        if not self.benchmark_symbols:
            return

        self._init_observability()
        if self.trade_logger is None:
            return

        captured: list[dict] = []
        for symbol in self.benchmark_symbols:
            try:
                bars = self.fetch_bars(symbol, limit=2)
                if bars.empty or "close" not in bars:
                    continue

                close_price = float(bars["close"].iloc[-1])
                ts_value = bars["timestamp"].iloc[-1] if "timestamp" in bars else datetime.now(timezone.utc)
                price_time = ts_value.isoformat() if hasattr(ts_value, "isoformat") else str(ts_value)

                row = self.trade_logger.record_benchmark_price(
                    symbol=symbol,
                    close_price=close_price,
                    price_time=price_time,
                    source="alpaca",
                )
                captured.append(
                    {
                        "symbol": row["symbol"],
                        "price_time": row["price_time"],
                        "close": row["close"],
                    }
                )
            except Exception as e:
                self.logger.debug(f"Benchmark capture skipped for {symbol}: {e}")

        if captured:
            self._emit_event(
                {
                    "event": "benchmark_prices_recorded",
                    "count": len(captured),
                    "rows": captured,
                },
                level="INFO",
                component="BenchmarkTracking",
            )

    def _init_observability(self) -> None:
        """Initialize optional persistence and structured event logger lazily."""
        if self.event_logger is None and JsonEventLogger is not None:
            try:
                self.event_logger = JsonEventLogger(file_path=self._json_event_log_path)
            except Exception as e:
                self.logger.warning(f"Failed to initialize JsonEventLogger: {e}")

        if self.trade_logger is None and TradeLogger is not None:
            try:
                self.trade_logger = TradeLogger(
                    db_path=self._trades_db_path,
                    event_logger=self.event_logger,
                )
            except Exception as e:
                self.logger.warning(f"Failed to initialize TradeLogger: {e}")

    def _emit_event(self, event: dict, level: str = "INFO", component: str = "StockBot") -> None:
        """Emit structured JSON event when logger is configured."""
        self._init_observability()
        if self.event_logger is None:
            return
        try:
            self.event_logger.log_event(event=event, level=level, component=component)
        except Exception as e:
            self.logger.debug(f"Structured event logging failed: {e}")

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

        if self.concentration_monitor:
            concentration = self.concentration_monitor.limit_order(
                symbol=symbol,
                desired_quantity=qty,
                price=price,
                positions=self.positions,
                equity=self.portfolio.equity,
            )
            adjusted_qty = int(concentration.get("adjusted_quantity", qty))
            reason = f"{reason} | {concentration.get('reason', 'concentration check')}"

            # Notify if concentration limit was applied
            if adjusted_qty < qty and discord:
                discord.notify_concentration_limit_hit(
                    symbol,
                    qty,
                    adjusted_qty,
                    concentration.get('reason', 'concentration limit')
                )

            qty = adjusted_qty

            if qty <= 0:
                return 0, reason

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
        score *= self.drift_risk_scale
        score = max(min_mult, min(max_mult, score))
        return score, "+".join(reasons) if reasons else "neutral"

    def _refresh_adaptive_controls(self) -> None:
        """Refresh drift-based confidence and risk controls."""
        if not self.drift_monitor:
            self.ai_confidence_floor_override = float(getattr(self.config, "min_ai_confidence", 0.45))
            self.drift_risk_scale = 1.0
            return

        try:
            drift = self.drift_monitor.evaluate()
            if drift.get("drift_detected"):
                self.ai_confidence_floor_override = float(drift.get("recommended_min_ai_confidence", self.config.min_ai_confidence))
                self.drift_risk_scale = float(drift.get("risk_scale", 0.75))
                recent_wr = float(drift.get("recent_win_rate", 0.0))
                baseline_wr = float(drift.get("baseline_win_rate", 0.0))
                self.logger.warning(
                    "Model drift detected | recent WR %.1f%% vs baseline %.1f%% | confidence floor %.2f | risk scale %.2f",
                    recent_wr * 100,
                    baseline_wr * 100,
                    self.ai_confidence_floor_override,
                    self.drift_risk_scale,
                )
                # Notify Discord
                if discord:
                    discord.notify_drift_detected(
                        "Stock Bot",
                        recent_wr,
                        baseline_wr,
                        self.ai_confidence_floor_override
                    )
            else:
                self.ai_confidence_floor_override = float(getattr(self.config, "min_ai_confidence", 0.45))
                self.drift_risk_scale = 1.0
        except Exception as e:
            self.logger.debug(f"Drift monitor unavailable: {e}")
            self.ai_confidence_floor_override = float(getattr(self.config, "min_ai_confidence", 0.45))
            self.drift_risk_scale = 1.0
    
    def _enrich_signal_with_pro_features(
        self,
        symbol: str,
        base_signal: Literal["BUY", "HOLD", "SELL"],
        df: pd.DataFrame,
    ) -> tuple[Literal["BUY", "HOLD", "SELL"], float, str]:
        """
        Enrich trading signal with pro features:
        - Multi-timeframe confluence
        - Macro regime detection
        - Order flow analysis
        - Kalman filter confidence
        - Execution optimization
        
        Returns:
            (adjusted_signal, final_confidence, notes)
        """
        
        ai_confidence = 0.5
        if self.ai and base_signal == "BUY":
            ai_confidence = self.ai.predict_entry_probability(df)
        
        notes = ""
        signal_multiplier = 1.0
        
        # Multi-timeframe analysis
        if self.multiframe_analyzer and len(df) >= 50:
            try:
                df_hourly = TimeframeDataManager.resample_to_hourly(df)
                df_daily = TimeframeDataManager.resample_to_daily(df)
                
                if len(df_hourly) >= 20 and len(df_daily) >= 5:
                    mtf = self.multiframe_analyzer.analyze(df, df_hourly, df_daily, base_signal)
                    signal_multiplier *= mtf["confidence_multiplier"]
                    
                    if mtf["signal_quality"] == "POOR":
                        base_signal = "HOLD"  # Reject poor confluence
                    
                    notes += f"MTF:{mtf['signal_quality']} "
            except Exception as e:
                self.logger.debug(f"Multi-timeframe error: {e}")
        
        # Macro regime detection
        if self.macro_regime_detector:
            try:
                regime = self.macro_regime_detector.detect_regime(
                    df,
                    current_time=datetime.now(),
                )
                
                signal_multiplier *= regime.trade_aggressiveness
                
                if not regime.should_trade:
                    base_signal = "HOLD"
                    notes += f"REGIME:{regime.regime} "
                else:
                    notes += f"Regime:{regime.regime} "
            except Exception as e:
                self.logger.debug(f"Macro regime error: {e}")
        
        # Order flow detection
        if self.order_flow_detector:
            try:
                flow = self.order_flow_detector.detect_flow(df, symbol)
                
                if flow.institutional_probability > 0.6:
                    signal_multiplier *= 1.1  # Boost when institutional presence detected
                    notes += f"OF:{flow.pattern} "
            except Exception as e:
                self.logger.debug(f"Order flow error: {e}")
        
        # Kalman filter updates
        if self.kalman_filter:
            try:
                can_trade, reason = self.kalman_filter.get_trading_allowed()
                
                if not can_trade:
                    base_signal = "HOLD"
                    notes += f"Kalman:BLOCKED({reason}) "
                
                kalman_mult = self.kalman_filter.get_confidence_multiplier()
                signal_multiplier *= kalman_mult
                notes += f"Kalman:{kalman_mult:.2f} "
            except Exception as e:
                self.logger.debug(f"Kalman error: {e}")
        
        # Apply final multiplier to confidence
        final_confidence = min(1.0, ai_confidence * signal_multiplier)
        
        return base_signal, final_confidence, notes
        
    def connect(self) -> None:
        """Connect to Alpaca."""
        try:
            self._init_observability()
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

            self._emit_event(
                {
                    "event": "broker_connected",
                    "paper_trading": bool(self.config.paper_trading),
                    "symbols": self.active_symbols,
                },
                level="INFO",
                component="Connection",
            )
            
            # Initialize positions
            self.positions = {s: StockPosition(s) for s in self.universe_symbols}
            self._refresh_active_symbols()
            self._sync_from_account()

            if ReliableOrderExecutor is not None:
                self.order_executor = ReliableOrderExecutor(
                    self.api,
                    logger=self.logger,
                    max_retries=int(getattr(self.config, "order_max_retries", 3)),
                    initial_backoff_sec=float(getattr(self.config, "order_retry_backoff_sec", 1.0)),
                    verify_fill_timeout_sec=float(getattr(self.config, "order_fill_timeout_sec", 30.0)),
                    poll_interval_sec=float(getattr(self.config, "order_poll_interval_sec", 1.0)),
                )

            if OrderWatchdog is not None:
                self.order_watchdog = OrderWatchdog(
                    self.api,
                    logger=self.logger,
                    max_open_seconds=int(getattr(self.config, "stuck_order_seconds", 30)),
                    auto_cancel=bool(getattr(self.config, "cancel_stuck_orders", True)),
                    on_alert=self._on_stuck_order_alert,
                )
            
        except Exception as e:
            self.logger.error(f"Failed to connect: {e}")
            self._emit_event(
                {
                    "event": "broker_connect_failed",
                    "error": str(e),
                },
                level="ERROR",
                component="Connection",
            )
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

    def place_order(
        self,
        side: Literal["buy", "sell"],
        symbol: str,
        qty: int,
        ai_confidence: float = 0.5,
        expected_price: float | None = None,
    ) -> bool:
        """Place order on Alpaca."""
        try:
            side_norm = str(side).lower()
            if self.config.paper_trading or qty <= 0:
                confidence_str = f" (AI: {ai_confidence:.0%})" if side_norm == "buy" else ""
                self.logger.info(f"[PAPER] {side.upper()} {qty} {symbol}{confidence_str}")
                self._last_execution_by_symbol[symbol] = {
                    "side": side_norm,
                    "status": "paper",
                    "filled_qty": int(qty),
                    "avg_fill_price": expected_price,
                    "latency_ms": 0,
                }
                self._emit_event(
                    {
                        "event": "order_submitted",
                        "mode": "paper",
                        "symbol": symbol,
                        "side": side_norm,
                        "qty": int(qty),
                        "expected_price": expected_price,
                    },
                    level="INFO",
                    component="OrderExecution",
                )
                return True

            if self.order_executor is not None:
                result = self.order_executor.place_market_order(
                    symbol=symbol,
                    side=side,
                    qty=qty,
                )
                self.logger.info(
                    "[LIVE] %s %s %s | status=%s filled=%s avg_price=%.4f attempts=%s latency_ms=%s",
                    side.upper(),
                    qty,
                    symbol,
                    result.status,
                    result.filled_qty,
                    result.avg_fill_price,
                    result.attempts,
                    result.latency_ms,
                )
                if result.partial_fill:
                    self.logger.warning(
                        "Partial fill detected | symbol=%s requested=%s filled=%s",
                        symbol,
                        qty,
                        result.filled_qty,
                    )
                self._last_execution_by_symbol[symbol] = {
                    "side": side_norm,
                    "status": result.status,
                    "filled_qty": int(result.filled_qty),
                    "avg_fill_price": float(result.avg_fill_price) if result.avg_fill_price else None,
                    "latency_ms": int(result.latency_ms),
                    "attempts": int(result.attempts),
                }
                self._emit_event(
                    {
                        "event": "order_submitted",
                        "mode": "live",
                        "symbol": symbol,
                        "side": side_norm,
                        "qty": int(qty),
                        "filled_qty": int(result.filled_qty),
                        "status": result.status,
                        "avg_fill_price": float(result.avg_fill_price) if result.avg_fill_price else None,
                        "latency_ms": int(result.latency_ms),
                        "attempts": int(result.attempts),
                        "expected_price": expected_price,
                    },
                    level="INFO",
                    component="OrderExecution",
                )
                return result.filled_qty > 0

            self.api.submit_order(symbol=symbol, qty=qty, side=side, type="market", time_in_force="day")
            self.logger.info(f"[LIVE] {side.upper()} {qty} {symbol}")
            self._last_execution_by_symbol[symbol] = {
                "side": side_norm,
                "status": "submitted",
                "filled_qty": int(qty),
                "avg_fill_price": None,
                "latency_ms": None,
            }
            self._emit_event(
                {
                    "event": "order_submitted",
                    "mode": "live",
                    "symbol": symbol,
                    "side": side_norm,
                    "qty": int(qty),
                    "status": "submitted",
                    "expected_price": expected_price,
                },
                level="INFO",
                component="OrderExecution",
            )
            return True
        except OrderRejectedError as e:
            self.logger.error(f"Order rejected for {symbol}: {e}")
            self._emit_event(
                {
                    "event": "order_rejected",
                    "symbol": symbol,
                    "side": str(side).lower(),
                    "qty": int(qty),
                    "error": str(e),
                },
                level="ERROR",
                component="OrderExecution",
            )
            return False
        except OrderExecutionError as e:
            self.logger.error(f"Order execution failed for {symbol}: {e}")
            self._emit_event(
                {
                    "event": "order_execution_failed",
                    "symbol": symbol,
                    "side": str(side).lower(),
                    "qty": int(qty),
                    "error": str(e),
                },
                level="ERROR",
                component="OrderExecution",
            )
            return False
        except Exception as e:
            self.logger.error(f"Order failed for {symbol}: {e}")
            self._emit_event(
                {
                    "event": "order_failed",
                    "symbol": symbol,
                    "side": str(side).lower(),
                    "qty": int(qty),
                    "error": str(e),
                },
                level="ERROR",
                component="OrderExecution",
            )
            return False

    def _on_stuck_order_alert(self, alert) -> None:
        """Handle stale open-order alerts from watchdog."""
        self.logger.warning(
            "Order watchdog alert | symbol=%s side=%s status=%s age=%.1fs order_id=%s",
            alert.symbol,
            alert.side,
            alert.status,
            alert.age_seconds,
            alert.order_id,
        )
        self._emit_event(
            {
                "event": "stuck_order_alert",
                "symbol": alert.symbol,
                "side": alert.side,
                "status": alert.status,
                "age_seconds": float(alert.age_seconds),
                "order_id": alert.order_id,
            },
            level="WARNING",
            component="OrderWatchdog",
        )
        if discord:
            try:
                discord.notify_error(
                    "Stuck order detected",
                    {
                        "symbol": alert.symbol,
                        "side": alert.side,
                        "status": alert.status,
                        "age_seconds": f"{alert.age_seconds:.1f}",
                        "order_id": alert.order_id,
                    },
                )
            except Exception as e:
                self.logger.debug(f"Failed to send stuck-order alert: {e}")

    def _actual_slippage_for(self, symbol: str, side: str, expected_price: float) -> float | None:
        """Compute signed execution slippage from the last order metadata."""
        exec_meta = self._last_execution_by_symbol.get(symbol)
        if not exec_meta:
            return None

        fill_price = exec_meta.get("avg_fill_price")
        if fill_price is None or expected_price <= 0:
            return None

        side_norm = str(side).lower()
        if side_norm == "buy":
            return float(fill_price) - float(expected_price)
        return float(expected_price) - float(fill_price)

    def _record_entry_trade(
        self,
        symbol: str,
        entry_price: float,
        entry_size: int,
        signal_regime: str | None = None,
    ) -> None:
        """Persist entry records for post-trade analytics."""
        if self.api is None:
            return
        self._init_observability()
        if self.trade_logger is None:
            return

        strategy_name = str(getattr(self.config, "strategy_name", "RSI_2MA"))
        expected_slippage = float(getattr(self.config, "backtest_slippage_assumption", 0.0))
        trade_id = self.trade_logger.record_entry(
            symbol=symbol,
            entry_price=entry_price,
            entry_size=entry_size,
            entry_side="BUY",
            strategy_name=strategy_name,
            signal_regime=signal_regime,
            entry_time=datetime.now(timezone.utc),
            backtest_expected_pnl=None,
            backtest_slippage_assumption=expected_slippage,
        )
        self._emit_event(
            {
                "event": "trade_entry_persisted",
                "trade_id": int(trade_id),
                "symbol": symbol,
                "entry_price": float(entry_price),
                "entry_size": int(entry_size),
                "strategy_name": strategy_name,
                "signal_regime": signal_regime,
            },
            level="INFO",
            component="TradePersistence",
        )

    def _record_exit_trade(
        self,
        symbol: str,
        exit_price: float,
        exit_size: int,
        exit_reason: str,
        fees: float = 0.0,
    ) -> None:
        """Persist exit records and attach slippage observations."""
        if self.api is None:
            return
        self._init_observability()
        if self.trade_logger is None:
            return

        actual_slippage = self._actual_slippage_for(symbol, side="sell", expected_price=exit_price)
        row = self.trade_logger.record_exit_for_symbol(
            symbol=symbol,
            exit_price=exit_price,
            exit_size=exit_size,
            exit_reason=exit_reason,
            fees=fees,
            exit_time=datetime.now(timezone.utc),
            actual_slippage=actual_slippage,
        )
        self._emit_event(
            {
                "event": "trade_exit_persisted",
                "symbol": symbol,
                "exit_price": float(exit_price),
                "exit_size": int(exit_size),
                "exit_reason": exit_reason,
                "pnl": float(row.get("pnl") or 0.0) if row else None,
                "actual_slippage": actual_slippage,
            },
            level="INFO",
            component="TradePersistence",
        )

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
                success = self.place_order("sell", symbol, pos.quantity, expected_price=price)
                if success:
                    was_loss = price < pos.entry_price
                    pnl = (price - pos.entry_price) * pos.quantity
                    pnl_pct = (pnl / (pos.entry_price * pos.quantity)) * 100 if pos.entry_price > 0 else 0
                    self.daily_pnl += pnl_pct
                    
                    self._log_trade(symbol, "sell", pos.entry_price, pos.quantity, pos.ai_confidence, 
                                   exit_reason=exit_reason, exit_price=price, pnl=pnl)
                    self._record_exit_trade(
                        symbol=symbol,
                        exit_price=price,
                        exit_size=pos.quantity,
                        exit_reason=exit_reason,
                        fees=0.0,
                    )
                    
                    if self.ai:
                        self.ai.update_from_trade(pnl, not was_loss)
                    if self.retrainer:
                        self.retrainer.record_closed_trade()
                    self.risk.update_trade_result(not was_loss)
                    
                    # Send Discord notification
                    if discord:
                        discord.notify_sell(symbol, pos.entry_price, price, pos.quantity, pnl_pct, exit_reason)
                    
                    pos.close(was_loss=was_loss, cooldown_candles=self.config.cooldown_candles)
            
            # Check for entry
            elif pos.ready():
                # Check daily loss limit and max open positions
                if not self._check_daily_loss():
                    return  # Stop trading for the day
                
                current_positions = self._count_open_positions()
                if current_positions >= self.config.max_open_positions:
                    # Only notify once per day to avoid spam
                    if not self._max_positions_notified_today:
                        self.logger.info(f"Max open positions ({self.config.max_open_positions}) reached")
                        if discord:
                            discord.notify_max_positions_reached(current_positions, self.config.max_open_positions)
                        self._max_positions_notified_today = True
                    return

                heat_blocked, heat_pct, max_heat_pct = self._portfolio_heat_gate()
                if heat_blocked:
                    self.logger.warning(
                        f"[{symbol}] Trade blocked by portfolio heat: "
                        f"{heat_pct*100:.2f}% >= {max_heat_pct*100:.2f}%"
                    )
                    self._emit_event(
                        {
                            "event": "trade_blocked_portfolio_heat",
                            "symbol": symbol,
                            "heat_pct": heat_pct,
                            "max_heat_pct": max_heat_pct,
                        },
                        level="WARNING",
                        component="PortfolioRisk",
                    )
                    return

                allowed, reason = self.risk.check_pre_trade(
                    self.portfolio,
                    symbol,
                    current_positions,
                )
                if not allowed:
                    self.logger.warning(f"[{symbol}] Trade blocked by risk manager: {reason}")
                    return
                
                signal, sig_details = get_signal_enhanced(df, self.config.rsi_period, self.config.rsi_oversold, self.config.rsi_overbought)
                
                # Apply pro features: multi-timeframe, regime, order flow, Kalman
                signal, ai_confidence, multiframe_notes = self._enrich_signal_with_pro_features(
                    symbol, signal, df
                )
                
                # Log volume confirmation
                volume_status = "✓" if sig_details.volume_confirm else "✗"

                effective_min_ai_confidence = max(
                    float(getattr(self.config, "min_ai_confidence", 0.45)),
                    float(self.ai_confidence_floor_override),
                )
                
                if signal == "BUY" and (not self.ai or ai_confidence > effective_min_ai_confidence):
                    corr_allowed, corr_reason, max_corr = self._correlation_gate(symbol)
                    if not corr_allowed:
                        self.logger.warning(
                            f"[{symbol}] Trade blocked by correlation gate: "
                            f"{corr_reason} (max={max_corr:.2f})"
                        )
                        self._emit_event(
                            {
                                "event": "trade_blocked_correlation",
                                "symbol": symbol,
                                "reason": corr_reason,
                                "max_correlation": max_corr,
                            },
                            level="WARNING",
                            component="PortfolioRisk",
                        )
                        return

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
                        sector_allowed, sector_decision = self._sector_exposure_gate(symbol, qty, price)
                        imbalance = sector_decision.get("imbalance_sectors", {})
                        if imbalance:
                            imbalance_text = ", ".join(
                                f"{sector_name}={sector_pct*100:.1f}%"
                                for sector_name, sector_pct in sorted(imbalance.items())
                            )
                            self.logger.warning(f"Sector imbalance alert | {imbalance_text}")
                            self._emit_event(
                                {
                                    "event": "sector_imbalance_alert",
                                    "symbol": symbol,
                                    "imbalance_sectors": imbalance,
                                },
                                level="WARNING",
                                component="PortfolioRisk",
                            )

                        if not sector_allowed:
                            projected_pct = float(sector_decision.get("projected_sector_pct", 0.0))
                            max_pct = float(sector_decision.get("max_sector_exposure_pct", 0.0))
                            sector_name = str(sector_decision.get("sector", "UNKNOWN"))
                            reason = str(sector_decision.get("reason", "sector_cap_exceeded"))
                            self.logger.warning(
                                f"[{symbol}] Trade blocked by sector gate: {reason} "
                                f"({sector_name} {projected_pct*100:.2f}% > {max_pct*100:.2f}%)"
                            )
                            self._emit_event(
                                {
                                    "event": "trade_blocked_sector_exposure",
                                    "symbol": symbol,
                                    "sector": sector_name,
                                    "reason": reason,
                                    "projected_sector_pct": projected_pct,
                                    "max_sector_exposure_pct": max_pct,
                                    "imbalance_sectors": imbalance,
                                },
                                level="WARNING",
                                component="PortfolioRisk",
                            )
                            return

                        self.logger.info(
                            f"[{symbol}] BUY signal | Vol:{volume_status} | ATR:{sig_details.atr:.2f} | "
                            f"AI:{ai_confidence:.0%} | Qty:{qty} | {size_reason}"
                        )
                        success = self.place_order("buy", symbol, qty, ai_confidence, expected_price=price)
                        if success:
                            self._log_trade(symbol, "buy", price, qty, ai_confidence)
                            self._record_entry_trade(
                                symbol=symbol,
                                entry_price=price,
                                entry_size=qty,
                                signal_regime=multiframe_notes.strip() or None,
                            )
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

    def _count_open_positions(self) -> int:
        """Count open positions currently tracked in memory."""
        return sum(1 for pos in self.positions.values() if pos.active)

    def _check_daily_loss(self) -> bool:
        """Stop new entries when daily drawdown breaches configured limit."""
        max_dd = float(getattr(self.config, "max_daily_loss_pct", 0.05))
        dd_pct = float(self.portfolio.daily_drawdown_pct())
        if dd_pct <= -max_dd:
            self.logger.warning(
                f"Daily drawdown limit reached ({dd_pct:.2f}% <= -{max_dd*100:.2f}%). New entries paused."
            )
            return False
        return True

    def _portfolio_heat_gate(self) -> tuple[bool, float, float]:
        """Evaluate portfolio heat breaker before opening new positions."""
        max_heat = float(getattr(self.config, "max_portfolio_heat_pct", 0.15))
        if self.portfolio_risk_analyzer is None:
            return False, 0.0, max_heat

        blocked, heat = self.portfolio_risk_analyzer.should_block_for_heat(
            positions=self.positions,
            equity=self.portfolio.equity,
        )
        return bool(blocked), float(heat), max_heat

    def _correlation_gate(self, candidate_symbol: str) -> tuple[bool, str, float]:
        """Block entries when candidate is too correlated to open positions."""
        if self.portfolio_risk_analyzer is None:
            return True, "disabled", 0.0

        open_symbols = [
            symbol
            for symbol, pos in self.positions.items()
            if getattr(pos, "active", False) and symbol != candidate_symbol
        ]
        if not open_symbols:
            return True, "no_open_positions", 0.0

        lookback = int(getattr(self.config, "correlation_lookback_bars", 120))
        frames: dict[str, pd.DataFrame] = {}
        for symbol in [candidate_symbol] + open_symbols:
            bars = self.fetch_bars(symbol, limit=lookback)
            if isinstance(bars, pd.DataFrame) and not bars.empty:
                frames[symbol] = bars

        decision = self.portfolio_risk_analyzer.check_entry_correlation(
            candidate_symbol=candidate_symbol,
            open_symbols=open_symbols,
            price_frames=frames,
        )
        return bool(decision.allowed), str(decision.reason), float(decision.max_correlation)

    def _sector_exposure_gate(self, candidate_symbol: str, qty: int, price: float) -> tuple[bool, dict]:
        """Block entries that would push one sector beyond concentration limits."""
        max_sector = float(getattr(self.config, "max_sector_exposure_pct", 0.40))
        if self.sector_exposure_analyzer is None:
            return True, {
                "allowed": True,
                "sector": "UNKNOWN",
                "current_sector_pct": 0.0,
                "projected_sector_pct": 0.0,
                "max_sector_exposure_pct": max_sector,
                "reason": "disabled",
                "imbalance_sectors": {},
            }

        decision = self.sector_exposure_analyzer.check_entry_limit(
            candidate_symbol=candidate_symbol,
            desired_quantity=qty,
            price=price,
            positions=self.positions,
            equity=self.portfolio.equity,
        )
        return bool(decision.allowed), decision.to_dict()

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
                success = self.place_order("sell", symbol, pos.quantity, expected_price=price)
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
                    self._record_exit_trade(
                        symbol=symbol,
                        exit_price=price,
                        exit_size=pos.quantity,
                        exit_reason=reason,
                        fees=0.0,
                    )

                    if self.ai:
                        self.ai.update_from_trade(pnl, not was_loss)
                    if self.retrainer:
                        self.retrainer.record_closed_trade()
                    self.risk.update_trade_result(not was_loss)

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

            self._emit_event(
                {
                    "event": "trade_csv_logged",
                    "symbol": symbol,
                    "side": side,
                    "entry_price": float(price),
                    "qty": int(qty),
                    "ai_confidence": float(ai_confidence),
                    "exit_reason": exit_reason,
                    "exit_price": float(exit_price) if exit_price else None,
                    "pnl": float(pnl) if pnl is not None else None,
                },
                level="INFO",
                component="TradeLogging",
            )
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
                    self._refresh_adaptive_controls()

                if self.loop_count == 1 or self.loop_count % self.benchmark_record_every_loops == 0:
                    self._record_benchmark_prices()

                if self.loop_count == 1 or self.loop_count % self.health_check_every_loops == 0:
                    self._run_health_checks()

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

                if self.order_watchdog is not None:
                    self.order_watchdog.check_once()
                
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

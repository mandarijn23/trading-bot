"""Trade logging wrapper for persistence + structured events."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from observability.json_logger import JsonEventLogger
from persistence.trade_record import TradeRecordRepository
from persistence.trade_store import TradeStore


class TradeLogger:
    """Coordinates trade DB writes and JSON event emission."""

    def __init__(
        self,
        db_path: str = "data/trades.db",
        event_logger: JsonEventLogger | None = None,
    ) -> None:
        self.repo = TradeRecordRepository(TradeStore(db_path))
        self.event_logger = event_logger or JsonEventLogger()
        self._active_trade_ids: dict[str, int] = {}

    def record_entry(
        self,
        symbol: str,
        entry_price: float,
        entry_size: int,
        entry_side: str,
        strategy_name: str,
        signal_regime: str | None = None,
        entry_time: datetime | str | None = None,
        backtest_expected_pnl: float | None = None,
        backtest_slippage_assumption: float | None = None,
    ) -> int:
        trade_id = self.repo.record_entry(
            symbol=symbol,
            entry_price=entry_price,
            entry_size=entry_size,
            entry_side=entry_side,
            strategy_name=strategy_name,
            signal_regime=signal_regime,
            entry_time=entry_time,
            backtest_expected_pnl=backtest_expected_pnl,
            backtest_slippage_assumption=backtest_slippage_assumption,
        )
        self._active_trade_ids[str(symbol).upper()] = trade_id

        self.event_logger.info(
            {
                "component": "TradeLogger",
                "event": "trade_entry_recorded",
                "trade_id": trade_id,
                "symbol": str(symbol).upper(),
                "entry_price": float(entry_price),
                "entry_size": int(entry_size),
                "entry_side": str(entry_side).upper(),
                "strategy_name": strategy_name,
                "signal_regime": signal_regime,
            }
        )
        return trade_id

    def record_exit(
        self,
        trade_id: int,
        exit_price: float,
        exit_size: int,
        exit_reason: str,
        fees: float = 0.0,
        exit_time: datetime | str | None = None,
        actual_slippage: float | None = None,
    ) -> dict[str, Any] | None:
        row = self.repo.record_exit(
            trade_id=trade_id,
            exit_price=exit_price,
            exit_size=exit_size,
            exit_reason=exit_reason,
            fees=fees,
            exit_time=exit_time,
            actual_slippage=actual_slippage,
        )

        if row is None:
            self.event_logger.warning(
                {
                    "component": "TradeLogger",
                    "event": "trade_exit_missing_trade_id",
                    "trade_id": int(trade_id),
                }
            )
            return None

        symbol = str(row.get("symbol", "")).upper()
        if symbol and self._active_trade_ids.get(symbol) == int(trade_id):
            del self._active_trade_ids[symbol]

        self.event_logger.info(
            {
                "component": "TradeLogger",
                "event": "trade_exit_recorded",
                "trade_id": int(trade_id),
                "symbol": symbol,
                "exit_reason": str(exit_reason),
                "pnl": float(row.get("pnl") or 0.0),
                "pnl_pct": float(row.get("pnl_pct") or 0.0),
                "fees": float(row.get("fees") or 0.0),
            }
        )
        return row

    def record_exit_for_symbol(
        self,
        symbol: str,
        exit_price: float,
        exit_size: int,
        exit_reason: str,
        fees: float = 0.0,
        exit_time: datetime | str | None = None,
        actual_slippage: float | None = None,
    ) -> dict[str, Any] | None:
        symbol_key = str(symbol).upper()
        trade_id = self._active_trade_ids.get(symbol_key)
        if trade_id is None:
            self.event_logger.warning(
                {
                    "component": "TradeLogger",
                    "event": "trade_exit_without_active_entry",
                    "symbol": symbol_key,
                    "exit_reason": str(exit_reason),
                }
            )
            return None

        return self.record_exit(
            trade_id=trade_id,
            exit_price=exit_price,
            exit_size=exit_size,
            exit_reason=exit_reason,
            fees=fees,
            exit_time=exit_time,
            actual_slippage=actual_slippage,
        )

    def get_active_trade_id(self, symbol: str) -> int | None:
        return self._active_trade_ids.get(str(symbol).upper())

    def record_benchmark_price(
        self,
        symbol: str,
        close_price: float,
        price_time: datetime | str | None = None,
        source: str = "alpaca",
    ) -> dict[str, Any]:
        """Persist one benchmark price observation and emit an event."""
        row = self.repo.record_benchmark_price(
            symbol=symbol,
            close_price=close_price,
            price_time=price_time,
            source=source,
        )

        self.event_logger.info(
            {
                "component": "TradeLogger",
                "event": "benchmark_price_recorded",
                "symbol": row["symbol"],
                "price_time": row["price_time"],
                "close": row["close"],
                "source": row["source"],
            }
        )
        return row

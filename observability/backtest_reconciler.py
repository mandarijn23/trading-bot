"""Backtest vs live performance reconciliation utilities."""

from __future__ import annotations

from datetime import date
from typing import Mapping, Any, Iterable

from observability.json_logger import JsonEventLogger
from persistence.trade_record import TradeRecordRepository
from persistence.trade_store import TradeStore


class BacktestLiveReconciler:
    """Compares live outcomes with backtest assumptions."""

    def __init__(
        self,
        db_path: str = "data/trades.db",
        event_logger: JsonEventLogger | None = None,
    ) -> None:
        self.repo = TradeRecordRepository(TradeStore(db_path))
        self.event_logger = event_logger or JsonEventLogger()

    def reconcile_rows(self, expected_rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        summary = self.repo.reconcile_vs_backtest(expected_rows)
        self.event_logger.info(
            {
                "component": "BacktestReconciler",
                "event": "reconciliation_completed",
                **summary,
            }
        )
        return summary

    def daily_report(self, day: date) -> dict[str, Any]:
        rows = self.repo.get_trades_by_date(day.isoformat(), day.isoformat())
        closed = [r for r in rows if r.get("pnl") is not None]

        total_pnl = sum(float(r.get("pnl") or 0.0) for r in closed)
        total_expected = sum(float(r.get("backtest_expected_pnl") or 0.0) for r in closed)
        total_actual_slippage = sum(float(r.get("actual_slippage") or 0.0) for r in closed)
        total_assumed_slippage = sum(float(r.get("backtest_slippage_assumption") or 0.0) for r in closed)

        report = {
            "day": day.isoformat(),
            "closed_trades": len(closed),
            "total_pnl": total_pnl,
            "total_expected_pnl": total_expected,
            "pnl_variance": total_pnl - total_expected,
            "total_actual_slippage": total_actual_slippage,
            "total_assumed_slippage": total_assumed_slippage,
            "slippage_variance": total_actual_slippage - total_assumed_slippage,
        }

        self.event_logger.info(
            {
                "component": "BacktestReconciler",
                "event": "daily_reconciliation_report",
                **report,
            }
        )
        return report

    @staticmethod
    def should_alert_slippage(
        total_actual_slippage: float,
        total_assumed_slippage: float,
        factor_threshold: float = 1.5,
    ) -> bool:
        if total_assumed_slippage <= 0:
            return total_actual_slippage > 0
        return total_actual_slippage > (total_assumed_slippage * factor_threshold)

"""Tests for backtest vs live reconciliation utilities."""

from __future__ import annotations

from datetime import date

from observability.backtest_reconciler import BacktestLiveReconciler
from observability.json_logger import JsonEventLogger
from persistence.trade_record import TradeRecordRepository
from persistence.trade_store import TradeStore


def test_reconciliation_summary_and_daily_report(tmp_path):
    db_path = tmp_path / "trades.db"

    repo = TradeRecordRepository(TradeStore(str(db_path)))
    t1 = repo.record_entry(
        symbol="SPY",
        entry_price=100.0,
        entry_size=10,
        entry_side="BUY",
        strategy_name="RSI_2MA",
        backtest_expected_pnl=20.0,
        backtest_slippage_assumption=0.02,
    )
    repo.record_exit(
        trade_id=t1,
        exit_price=101.5,
        exit_size=10,
        exit_reason="TP",
        fees=0.0,
        actual_slippage=0.03,
    )

    reconciler = BacktestLiveReconciler(
        db_path=str(db_path),
        event_logger=JsonEventLogger(str(tmp_path / "events.jsonl")),
    )
    summary = reconciler.reconcile_rows(
        [
            {
                "trade_id": t1,
                "expected_pnl": 20.0,
                "expected_slippage": 0.02,
            }
        ]
    )

    assert summary["compared_trades"] == 1
    assert round(float(summary["total_pnl_variance"]), 2) == -5.0
    assert round(float(summary["total_slippage_variance"]), 4) == 0.01

    report = reconciler.daily_report(day=date.today())
    assert report["closed_trades"] >= 1
    assert "pnl_variance" in report
    assert "slippage_variance" in report


def test_slippage_alert_threshold():
    assert BacktestLiveReconciler.should_alert_slippage(3.1, 2.0, factor_threshold=1.5) is True
    assert BacktestLiveReconciler.should_alert_slippage(2.9, 2.0, factor_threshold=1.5) is False

"""Tests for SQLite trade persistence repository."""

from __future__ import annotations

from persistence.trade_record import TradeRecordRepository
from persistence.trade_store import TradeStore


def test_trade_entry_and_exit_persistence(tmp_path):
    db_path = tmp_path / "trades.db"
    repo = TradeRecordRepository(TradeStore(str(db_path)))

    trade_id = repo.record_entry(
        symbol="SPY",
        entry_price=100.0,
        entry_size=10,
        entry_side="BUY",
        strategy_name="RSI_2MA",
        signal_regime="BULL",
        backtest_expected_pnl=12.0,
        backtest_slippage_assumption=0.02,
    )

    closed = repo.record_exit(
        trade_id=trade_id,
        exit_price=102.0,
        exit_size=10,
        exit_reason="TAKE_PROFIT",
        fees=1.0,
        actual_slippage=0.03,
    )

    assert closed is not None
    assert closed["trade_id"] == trade_id
    assert round(float(closed["pnl"]), 2) == 19.0
    assert round(float(closed["pnl_pct"]), 4) == 1.9


def test_strategy_stats_and_daily_pnl(tmp_path):
    db_path = tmp_path / "trades.db"
    repo = TradeRecordRepository(TradeStore(str(db_path)))

    t1 = repo.record_entry("SPY", 100.0, 10, "BUY", "RSI_2MA")
    repo.record_exit(t1, 102.0, 10, "TP", fees=0.0)

    t2 = repo.record_entry("SPY", 100.0, 10, "BUY", "RSI_2MA")
    repo.record_exit(t2, 98.0, 10, "SL", fees=0.0)

    stats = repo.get_strategy_stats("RSI_2MA")
    assert stats["total_trades"] == 2
    assert stats["winning_trades"] == 1
    assert stats["losing_trades"] == 1
    assert stats["win_rate"] == 50.0

    daily = repo.get_daily_pnl()
    assert len(daily) >= 1
    assert any("pnl" in row for row in daily)

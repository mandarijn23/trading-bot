"""Tests for monthly tear sheet generation."""

from __future__ import annotations

import json
from datetime import datetime, timezone

from persistence.trade_record import TradeRecordRepository
from persistence.trade_store import TradeStore
from tools.monthly_tearsheet import build_monthly_tearsheet, main, render_monthly_tearsheet, write_monthly_tearsheet


def _seed_month(repo: TradeRecordRepository) -> None:
    april_5 = datetime(2026, 4, 5, 14, 30, tzinfo=timezone.utc)
    april_10 = datetime(2026, 4, 10, 14, 30, tzinfo=timezone.utc)
    april_30 = datetime(2026, 4, 30, 20, 0, tzinfo=timezone.utc)
    may_2 = datetime(2026, 5, 2, 14, 30, tzinfo=timezone.utc)

    t1 = repo.record_entry(
        symbol="SPY",
        entry_price=100.0,
        entry_size=10,
        entry_side="BUY",
        strategy_name="RSI_2MA",
        entry_time=april_5,
        backtest_expected_pnl=15.0,
        backtest_slippage_assumption=0.02,
    )
    repo.record_exit(
        trade_id=t1,
        exit_price=103.0,
        exit_size=10,
        exit_reason="TP",
        fees=0.5,
        exit_time=april_10,
        actual_slippage=0.03,
    )

    t2 = repo.record_entry(
        symbol="QQQ",
        entry_price=200.0,
        entry_size=5,
        entry_side="BUY",
        strategy_name="RSI_2MA",
        entry_time=april_10,
        backtest_expected_pnl=-5.0,
        backtest_slippage_assumption=0.01,
    )
    repo.record_exit(
        trade_id=t2,
        exit_price=198.0,
        exit_size=5,
        exit_reason="SL",
        fees=0.25,
        exit_time=april_30,
        actual_slippage=0.01,
    )

    t3 = repo.record_entry(
        symbol="SPY",
        entry_price=104.0,
        entry_size=4,
        entry_side="BUY",
        strategy_name="RSI_2MA",
        entry_time=may_2,
    )
    repo.record_exit(
        trade_id=t3,
        exit_price=105.0,
        exit_size=4,
        exit_reason="TP",
        fees=0.0,
        exit_time=may_2,
        actual_slippage=0.0,
    )

    repo.record_benchmark_price("SPY", 100.0, price_time="2026-04-01T14:30:00+00:00")
    repo.record_benchmark_price("SPY", 104.0, price_time="2026-04-30T20:00:00+00:00")
    repo.record_benchmark_price("VTI", 200.0, price_time="2026-04-01T14:30:00+00:00")
    repo.record_benchmark_price("VTI", 208.0, price_time="2026-04-30T20:00:00+00:00")


def test_build_monthly_tearsheet_and_render(tmp_path):
    repo = TradeRecordRepository(TradeStore(str(tmp_path / "trades.db")))
    _seed_month(repo)

    report = build_monthly_tearsheet(repo, month="2026-04", benchmark_symbols=["SPY", "VTI"])

    assert report.month == "2026-04"
    assert report.closed_trades == 2
    assert report.wins == 1
    assert report.losses == 1
    assert report.benchmark["month"]["month"] == "2026-04"
    assert report.benchmark["benchmark_symbols"] == ["SPY", "VTI"]

    markdown = render_monthly_tearsheet(report)
    assert "# Monthly Tear Sheet - 2026-04" in markdown
    assert "## Benchmark Comparison" in markdown
    assert "SPY return %" in markdown
    assert "## Symbol Breakdown" in markdown

    output_path = write_monthly_tearsheet(report, tmp_path / "tearsheet.md")
    assert output_path.exists()
    assert output_path.read_text(encoding="utf-8").startswith("# Monthly Tear Sheet - 2026-04")


def test_monthly_tearsheet_main_json_output(tmp_path, capsys):
    db_path = tmp_path / "trades.db"
    repo = TradeRecordRepository(TradeStore(str(db_path)))
    _seed_month(repo)

    rc = main(["--db", str(db_path), "--month", "2026-04", "--json", "--symbols", "SPY,VTI"])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["month"] == "2026-04"
    assert payload["closed_trades"] == 2
    assert payload["benchmark"]["month"]["month"] == "2026-04"
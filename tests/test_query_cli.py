"""Tests for observability query CLI commands and argument handling."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

import pytest

from observability.query_cli import (
    cmd_benchmark,
    cmd_daily,
    cmd_reconcile,
    cmd_slippage,
    cmd_strategy,
    cmd_trades,
    main,
)
from persistence.trade_record import TradeRecordRepository
from persistence.trade_store import TradeStore


def _seed_repo(repo: TradeRecordRepository) -> None:
    now = datetime.now(timezone.utc)

    t1 = repo.record_entry(
        symbol="SPY",
        entry_price=100.0,
        entry_size=10,
        entry_side="BUY",
        strategy_name="RSI_2MA",
        entry_time=now - timedelta(days=2),
        backtest_expected_pnl=20.0,
        backtest_slippage_assumption=0.02,
    )
    repo.record_exit(
        trade_id=t1,
        exit_price=102.0,
        exit_size=10,
        exit_reason="TAKE_PROFIT",
        fees=0.5,
        exit_time=now - timedelta(days=2, hours=-1),
        actual_slippage=0.03,
    )

    t2 = repo.record_entry(
        symbol="SPY",
        entry_price=100.0,
        entry_size=5,
        entry_side="BUY",
        strategy_name="RSI_2MA",
        entry_time=now - timedelta(hours=12),
        backtest_expected_pnl=10.0,
        backtest_slippage_assumption=0.01,
    )
    repo.record_exit(
        trade_id=t2,
        exit_price=98.0,
        exit_size=5,
        exit_reason="STOP_LOSS",
        fees=0.25,
        exit_time=now - timedelta(hours=11),
        actual_slippage=0.02,
    )

    t3 = repo.record_entry(
        symbol="QQQ",
        entry_price=200.0,
        entry_size=2,
        entry_side="BUY",
        strategy_name="TREND",
        entry_time=now - timedelta(hours=2),
        backtest_expected_pnl=5.0,
        backtest_slippage_assumption=0.01,
    )
    repo.record_exit(
        trade_id=t3,
        exit_price=201.0,
        exit_size=2,
        exit_reason="TAKE_PROFIT",
        fees=0.1,
        exit_time=now - timedelta(hours=1),
        actual_slippage=-0.01,
    )

    repo.record_benchmark_price(
        symbol="SPY",
        close_price=100.0,
        price_time=(now - timedelta(days=8)).isoformat(),
    )
    repo.record_benchmark_price(
        symbol="SPY",
        close_price=103.0,
        price_time=(now - timedelta(days=1)).isoformat(),
    )
    repo.record_benchmark_price(
        symbol="VTI",
        close_price=200.0,
        price_time=(now - timedelta(days=8)).isoformat(),
    )
    repo.record_benchmark_price(
        symbol="VTI",
        close_price=206.0,
        price_time=(now - timedelta(days=1)).isoformat(),
    )


def test_query_commands_return_expected_shapes(tmp_path):
    db_path = tmp_path / "trades.db"
    repo = TradeRecordRepository(TradeStore(str(db_path)))
    _seed_repo(repo)

    daily = cmd_daily(repo, limit=10)
    assert len(daily) >= 1
    assert {"day", "trades", "pnl"}.issubset(daily[-1].keys())

    strategy = cmd_strategy(repo, "RSI_2MA")
    assert strategy["strategy_name"] == "RSI_2MA"
    assert strategy["total_trades"] == 2

    slippage = cmd_slippage(repo)
    assert slippage["sample_count"] == 3
    assert "avg_slippage_bps" in slippage

    trades = cmd_trades(repo, symbol="SPY", limit=10)
    assert len(trades) == 2
    assert all(t["symbol"] == "SPY" for t in trades)

    reconcile = cmd_reconcile(repo)
    assert reconcile["compared_trades"] == 3
    assert "total_pnl_variance" in reconcile

    benchmark = cmd_benchmark(repo, benchmark_symbols=["SPY", "VTI"])
    assert benchmark["summary"]["months_compared"] >= 1
    assert len(benchmark["monthly"]) >= 1
    assert "SPY_return_pct" in benchmark["monthly"][0]
    assert "excess_vs_SPY_pct" in benchmark["monthly"][0]


def test_cmd_trades_since_filter(tmp_path):
    db_path = tmp_path / "trades.db"
    repo = TradeRecordRepository(TradeStore(str(db_path)))
    _seed_repo(repo)

    since = (datetime.now(timezone.utc) - timedelta(hours=24)).isoformat()
    rows = cmd_trades(repo, symbol="SPY", since=since, limit=10)

    assert len(rows) == 1
    assert rows[0]["symbol"] == "SPY"


def test_main_json_output_and_since_validation(tmp_path, capsys):
    db_path = tmp_path / "trades.db"
    repo = TradeRecordRepository(TradeStore(str(db_path)))
    _seed_repo(repo)

    rc = main(["--db", str(db_path), "--json", "strategy", "RSI_2MA"])
    assert rc == 0

    payload = json.loads(capsys.readouterr().out)
    assert payload["strategy_name"] == "RSI_2MA"

    rc = main(["--db", str(db_path), "--json", "benchmark", "--symbols", "SPY,VTI"])
    assert rc == 0
    benchmark_payload = json.loads(capsys.readouterr().out)
    assert "monthly" in benchmark_payload
    assert "summary" in benchmark_payload

    with pytest.raises(ValueError):
        main(["--db", str(db_path), "trades", "SPY", "--since", "not-a-date"])

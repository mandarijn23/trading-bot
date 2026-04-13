from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd

import tools.backtest as backtest_module
from concentration import PortfolioConcentrationMonitor
from model_drift import ModelDriftMonitor


def _make_trade_history() -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for idx in range(20):
        rows.append({"side": "sell", "pnl_pct": "1.0%", "ai_confidence": "70%"})
    for idx in range(10):
        rows.append({"side": "sell", "pnl_pct": "-1.0%", "ai_confidence": "40%"})
    return rows


def test_model_drift_monitor_detects_recent_decay():
    monitor = ModelDriftMonitor(window_trades=10, threshold=0.15, min_trades=10)

    result = monitor.evaluate(_make_trade_history())

    assert result["drift_detected"] is True
    assert result["recent_win_rate"] < result["baseline_win_rate"]
    assert result["risk_scale"] < 1.0


def test_concentration_monitor_trims_group_exposure():
    monitor = PortfolioConcentrationMonitor(
        max_symbol_exposure_pct=0.20,
        max_group_exposure_pct=0.30,
        correlated_groups=(("SPY", "QQQ", "VOO"),),
    )

    positions = {
        "SPY": SimpleNamespace(active=True, quantity=10, entry_price=100.0),
        "QQQ": SimpleNamespace(active=True, quantity=10, entry_price=100.0),
    }

    result = monitor.limit_order(
        symbol="VOO",
        desired_quantity=20,
        price=100.0,
        positions=positions,
        equity=10_000.0,
    )

    assert result["allowed"] is True
    assert result["adjusted_quantity"] == 10
    assert "cap" in result["reason"]


def test_walk_forward_validation_returns_summary(monkeypatch):
    monkeypatch.setattr(backtest_module, "get_signal", lambda *_args, **_kwargs: "BUY")

    rows = 120
    close = np.linspace(100.0, 112.0, rows)
    df = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=rows, freq="h"),
            "open": close * 0.999,
            "high": close * 1.01,
            "low": close * 0.99,
            "close": close,
            "volume": np.ones(rows) * 1_000_000,
        }
    )

    config = backtest_module.BacktestConfig(
        walkforward_train_size=60,
        walkforward_test_size=20,
        walkforward_step=20,
    )
    engine = backtest_module.ProfessionalBacktester(config)

    summary = engine.walk_forward_validation(df, "SPY")

    assert summary["period_count"] > 0
    assert summary["avg_train_sharpe"] == summary["avg_train_sharpe"]
    assert summary["avg_test_sharpe"] == summary["avg_test_sharpe"]
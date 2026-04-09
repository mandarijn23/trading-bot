"""Test hourly performance reporting."""

import sys
from pathlib import Path

import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
for rel in ("utils", "config", "core", "models", "strategies", "tools"):
    p = str(ROOT_DIR / rel)
    if p not in sys.path:
        sys.path.insert(0, p)

import pandas as pd


def test_hourly_performance_report_imports():
    """Test that the reporting script imports correctly."""
    try:
        from tools.hourly_performance_report import (  # noqa: F401
            calculate_metrics,
            generate_quickchart_win_pct,
            load_closed_trades,
            send_performance_report_to_discord,
        )
    except ImportError as e:
        pytest.fail(f"Failed to import: {e}")


def test_calculate_metrics():
    """Test metrics calculation."""
    from tools.hourly_performance_report import calculate_metrics
    
    # Empty dataframe
    metrics = calculate_metrics(pd.DataFrame())
    assert metrics["total_trades"] == 0
    assert metrics["win_pct"] == 0
    
    # Sample trades
    trades = pd.DataFrame({
        "side": ["buy", "sell", "buy", "sell"],
        "pnl_pct_num": [None, 1.5, None, -0.5],
    })
    
    metrics = calculate_metrics(trades)
    assert metrics["total_trades"] == 4
    assert metrics["win_count"] == 1
    assert metrics["loss_count"] == 1


def test_quickchart_urls():
    """Test QuickChart URL generation."""
    from tools.hourly_performance_report import (
        generate_quickchart_cumulative_pnl,
        generate_quickchart_daily_trades,
        generate_quickchart_win_pct,
    )
    
    trades = pd.DataFrame({
        "timestamp": pd.date_range("2024-01-01", periods=10, freq="1D"),
        "side": ["buy", "sell"] * 5,
        "pnl_pct_num": [None, 1.0, None, -0.5, None, 2.0, None, 0.5, None, -1.0],
    })
    
    # Test win % chart
    url = generate_quickchart_win_pct(trades)
    assert url.startswith("https://quickchart.io/chart?c=")
    
    # Test daily trades chart
    url = generate_quickchart_daily_trades(trades)
    assert url.startswith("https://quickchart.io/chart?c=")
    
    # Test cumulative PnL chart
    url = generate_quickchart_cumulative_pnl(trades)
    assert url.startswith("https://quickchart.io/chart?c=")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])

"""Tests for local-dashboard hourly performance reporting."""

import sys
from pathlib import Path

import pandas as pd
import pytest

ROOT_DIR = Path(__file__).resolve().parents[1]
for rel in ("utils", "config", "core", "models", "strategies", "tools"):
    p = str(ROOT_DIR / rel)
    if p not in sys.path:
        sys.path.insert(0, p)


def test_hourly_performance_report_imports():
    """Test that reporting module imports with new local dashboard API."""
    try:
        from tools.hourly_performance_report import (  # noqa: F401
            calculate_metrics,
            load_closed_trades,
            send_performance_report_to_discord,
        )
    except ImportError as e:
        pytest.fail(f"Failed to import: {e}")


def test_calculate_metrics():
    """Test metrics calculation for empty and populated input."""
    from tools.hourly_performance_report import calculate_metrics

    empty_metrics = calculate_metrics(pd.DataFrame())
    assert empty_metrics["total_trades"] == 0
    assert empty_metrics["win_pct"] == 0

    trades = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=4, freq="1D"),
            "side": ["buy", "sell", "buy", "sell"],
            "pnl_pct_num": [None, 1.5, None, -0.5],
        }
    )
    metrics = calculate_metrics(trades)
    assert metrics["total_trades"] == 4
    assert metrics["win_count"] == 1
    assert metrics["loss_count"] == 1


def test_send_performance_report_uses_dashboard_panels():
    """Ensure dashboard send path works with local chart panels."""
    from tools.hourly_performance_report import calculate_metrics, send_performance_report_to_discord

    class FakeDiscord:
        def __init__(self):
            self.graph_mention = ""
            self.called = False
            self.payload = None

        def send_dashboard(self, **kwargs):
            self.called = True
            self.payload = kwargs
            return True

    trades = pd.DataFrame(
        {
            "timestamp": pd.date_range("2024-01-01", periods=6, freq="1D"),
            "side": ["buy", "sell", "buy", "sell", "buy", "sell"],
            "pnl_pct_num": [None, 0.8, None, -0.4, None, 1.2],
        }
    )
    metrics = calculate_metrics(trades)
    fake = FakeDiscord()

    ok = send_performance_report_to_discord(fake, metrics, trades)
    assert ok is True
    assert fake.called is True
    assert "chart_panels" in fake.payload
    assert len(fake.payload["chart_panels"]) == 4


if __name__ == "__main__":
    pytest.main([__file__, "-q"])

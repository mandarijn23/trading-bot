"""Tests for portfolio heat and correlation analytics."""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np
import pandas as pd

from portfolio_analytics import PortfolioRiskAnalyzer


def _frame_from_close(close: np.ndarray) -> pd.DataFrame:
    return pd.DataFrame({"close": close.astype(float)})


def test_portfolio_heat_calculation():
    analyzer = PortfolioRiskAnalyzer(max_portfolio_heat_pct=0.15)

    positions = {
        "SPY": SimpleNamespace(active=True, quantity=10, entry_price=100.0, trailing_stop=95.0),
        "QQQ": SimpleNamespace(active=False, quantity=5, entry_price=200.0, trailing_stop=190.0),
    }

    heat = analyzer.portfolio_heat_pct(positions, equity=10_000.0)
    assert round(heat, 5) == 0.005

    blocked, current_heat = analyzer.should_block_for_heat(positions, equity=10_000.0)
    assert blocked is False
    assert round(current_heat, 5) == 0.005


def test_correlation_gate_blocks_high_correlation():
    analyzer = PortfolioRiskAnalyzer(correlation_threshold=0.85, min_periods=30, lookback_bars=120)

    base = np.linspace(100.0, 160.0, 140)
    frames = {
        "SPY": _frame_from_close(base),
        "QQQ": _frame_from_close(base * 1.01),
    }

    decision = analyzer.check_entry_correlation(
        candidate_symbol="QQQ",
        open_symbols=["SPY"],
        price_frames=frames,
    )

    assert decision.allowed is False
    assert decision.max_correlation > 0.99
    assert decision.reason == "correlation_threshold_exceeded"


def test_correlation_gate_allows_low_correlation():
    analyzer = PortfolioRiskAnalyzer(correlation_threshold=0.85, min_periods=30, lookback_bars=120)

    rng = np.random.default_rng(42)
    trend = np.linspace(100.0, 160.0, 140)
    noisy = 100.0 + np.cumsum(rng.normal(0.0, 1.0, size=140))
    frames = {
        "SPY": _frame_from_close(trend),
        "XLE": _frame_from_close(noisy),
    }

    decision = analyzer.check_entry_correlation(
        candidate_symbol="XLE",
        open_symbols=["SPY"],
        price_frames=frames,
    )

    assert decision.allowed is True
    assert decision.max_correlation < 0.85

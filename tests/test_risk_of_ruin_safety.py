from __future__ import annotations

import pytest

from risk_of_ruin import check_strategy_safety


def test_check_strategy_safety_respects_starting_capital_argument():
    # Same edge profile should be treated consistently across account sizes.
    is_safe_10k = check_strategy_safety(
        win_rate=0.55,
        avg_win=200.0,
        avg_loss=200.0,
        starting_capital=10000.0,
        verbose=False,
    )
    is_safe_20k = check_strategy_safety(
        win_rate=0.55,
        avg_win=400.0,
        avg_loss=400.0,
        starting_capital=20000.0,
        verbose=False,
    )

    assert is_safe_10k == is_safe_20k


def test_check_strategy_safety_rejects_non_positive_starting_capital():
    with pytest.raises(ValueError, match="starting_capital must be > 0"):
        check_strategy_safety(
            win_rate=0.55,
            avg_win=200.0,
            avg_loss=200.0,
            starting_capital=0.0,
            verbose=False,
        )

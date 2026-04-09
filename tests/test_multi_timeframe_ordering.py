from __future__ import annotations

import multi_timeframe as mtf


class _Signal:
    def __init__(self, trend: str, signal: str):
        self.trend = trend
        self.signal = signal


def test_timeframe_order_uses_duration_not_hardcoded_sequence():
    analyzer = mtf.MultiTimeframeAnalyzer(primary_timeframes=["1d", "4h", "1h"])
    analyzer.signals = {
        "4h": _Signal("UPTREND", "BUY"),
        "1d": _Signal("DOWNTREND", "HOLD"),
        "1h": _Signal("UPTREND", "BUY"),
    }

    # If ordering is correct (1d > 4h > 1h), macro trend is DOWNTREND,
    # so lower-timeframe BUY should not be approved.
    assert analyzer.get_combined_signal() == "HOLD"


def test_timeframe_minutes_parser_handles_common_units():
    to_min = mtf.MultiTimeframeAnalyzer._timeframe_to_minutes
    assert to_min("5m") == 5
    assert to_min("1h") == 60
    assert to_min("1d") == 1440
    assert to_min("1w") == 10080
    assert to_min("unknown") == -1

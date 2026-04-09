"""Tests for daily_performance_report utilities."""

from __future__ import annotations

import pandas as pd

from daily_performance_report import build_gate_state, build_report, evaluate_decay


def test_evaluate_decay_critical_on_large_drop():
    recent = {"trades": 8, "win_rate": 35.0, "pnl_total": -2.0, "pnl_per_trade": -0.4}
    baseline = {"trades": 30, "win_rate": 60.0, "pnl_total": 8.0, "pnl_per_trade": 0.4}
    level, _ = evaluate_decay(recent, baseline)
    assert level == "CRITICAL"


def test_build_report_returns_symbol_sections():
    rows = [
        {"timestamp": "2026-03-01 10:00:00", "side": "sell", "symbol": "BTC/USDT", "pnl_pct": "1.5%"},
        {"timestamp": "2026-03-03 10:00:00", "side": "sell", "symbol": "BTC/USDT", "pnl_pct": "-0.8%"},
        {"timestamp": "2026-03-10 10:00:00", "side": "sell", "symbol": "ETH/USDT", "pnl_pct": "0.6%"},
        {"timestamp": "2026-03-20 10:00:00", "side": "sell", "symbol": "ETH/USDT", "pnl_pct": "0.2%"},
        {"timestamp": "2026-04-05 10:00:00", "side": "sell", "symbol": "BTC/USDT", "pnl_pct": "-0.5%"},
    ]
    df = pd.DataFrame(rows)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    df["pnl_pct_num"] = df["pnl_pct"].str.replace("%", "", regex=False).astype(float)
    df["date"] = df["timestamp"].dt.date

    report = build_report(df)
    assert "overall" in report
    assert "symbols" in report
    assert "BTC/USDT" in report["symbols"]


def test_build_gate_state_critical_recommends_pause():
    report = {
        "decay_level": "CRITICAL",
        "decay_reason": "edge drop",
    }
    gate = build_gate_state(report, max_daily_loss_pct=0.05, trigger_fraction=0.5)
    assert gate["pause_recommended"] is True
    assert gate["drawdown_trigger_pct"] == -2.5

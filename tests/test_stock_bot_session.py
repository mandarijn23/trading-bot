"""Tests for stock bot session closeout logic."""

from __future__ import annotations

from types import SimpleNamespace
import json

import pandas as pd

import stock_bot
import core.stock_bot as core_stock_bot


class _FakeLogger:
    def info(self, *_args, **_kwargs):
        pass

    def warning(self, *_args, **_kwargs):
        pass

    def error(self, *_args, **_kwargs):
        pass

    def debug(self, *_args, **_kwargs):
        pass


class _FakeAI:
    def __init__(self):
        self.updates = []

    def get_stats(self):
        return {"total_trades": 0, "win_rate": 0.0}

    def update_from_trade(self, pnl, won):
        self.updates.append((pnl, won))


class _FakeDiscord:
    def notify_sell(self, *_args, **_kwargs):
        return True

    def notify_daily_summary(self, *_args, **_kwargs):
        return True


def _make_config():
    return SimpleNamespace(
        log_level="INFO",
        log_max_mb=10,
        log_backup_count=7,
        alpaca_api_key="key",
        alpaca_api_secret="secret",
        alpaca_base_url="https://paper-api.alpaca.markets",
        symbols=["SPY"],
        universe_symbols=[],
        dynamic_symbol_selection=False,
        dynamic_symbol_count=1,
        selection_refresh_cycles=15,
        min_dollar_volume=1,
        min_atr_pct=0.0,
        max_atr_pct=1.0,
        timeframe="15Min",
        rsi_period=14,
        rsi_oversold=35,
        rsi_overbought=65,
        use_ai=False,
        paper_trading=True,
        trade_amount_usd=20.0,
        min_trade_usd=10.0,
        trailing_stop_pct=0.02,
        stop_loss_pct=0.03,
        take_profit_pct=0.05,
        cooldown_candles=4,
        check_interval=1,
        max_daily_loss_pct=0.05,
        max_open_positions=2,
        enforce_model_quality_gate=False,
        model_quality_report_path="training_report.json",
        model_min_auc=0.53,
        model_min_f1=0.53,
        model_min_holdout_samples=60,
    )


def test_close_all_positions_marks_position_closed(monkeypatch):
    monkeypatch.setattr(stock_bot, "setup_logging", lambda *_args, **_kwargs: _FakeLogger())
    monkeypatch.setattr(stock_bot, "discord", _FakeDiscord())
    monkeypatch.setattr(stock_bot, "ModelRetrainer", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(stock_bot, "HAS_RETRAINER", False)

    bot = stock_bot.StockTradingBot(_make_config())
    bot.positions = {"SPY": stock_bot.StockPosition("SPY")}
    bot.positions["SPY"].open(price=100.0, quantity=1, stop_loss_pct=0.03, take_profit_pct=0.05)
    bot.ai = _FakeAI()

    sample = pd.DataFrame({"close": [101.0], "open": [101.0], "high": [101.0], "low": [101.0], "volume": [1000]})
    bot.fetch_bars = lambda *_args, **_kwargs: sample
    bot.place_order = lambda *_args, **_kwargs: True
    bot._log_trade = lambda *_args, **_kwargs: None

    bot._close_all_positions("MARKET_CLOSE")

    assert bot.positions["SPY"].active is False
    assert len(bot.ai.updates) == 1


def test_process_symbol_external_gate_blocks_buy(monkeypatch):
    monkeypatch.setattr(stock_bot, "setup_logging", lambda *_args, **_kwargs: _FakeLogger())
    monkeypatch.setattr(core_stock_bot, "setup_logging", lambda *_args, **_kwargs: _FakeLogger())
    monkeypatch.setattr(stock_bot, "discord", _FakeDiscord())
    monkeypatch.setattr(core_stock_bot, "discord", _FakeDiscord())
    monkeypatch.setattr(stock_bot, "ModelRetrainer", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(core_stock_bot, "ModelRetrainer", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(stock_bot, "HAS_RETRAINER", False)
    monkeypatch.setattr(core_stock_bot, "HAS_RETRAINER", False)

    bot = stock_bot.StockTradingBot(_make_config())

    bars = pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=250, freq="15min"),
            "open": [100.0] * 250,
            "high": [101.0] * 250,
            "low": [99.0] * 250,
            "close": [100.0 + (i * 0.02) for i in range(250)],
            "volume": [1_500_000.0] * 250,
        }
    )
    bot.fetch_bars = lambda *_args, **_kwargs: bars

    monkeypatch.setattr(
        core_stock_bot,
        "get_signal_enhanced",
        lambda *_args, **_kwargs: (
            "BUY",
            SimpleNamespace(volume_confirm=True, atr=1.0, stop_loss_atr=None),
        ),
    )

    bot._entry_risk_check = lambda *_args, **_kwargs: (True, "ok")

    order_calls = []
    bot.place_order = lambda *_args, **_kwargs: order_calls.append("called") or True

    class _ExternalGate:
        def get_snapshot(self, _symbol):
            return SimpleNamespace(
                sentiment_score=-0.8,
                catalyst_score=0.0,
                event_risk=0.9,
                confidence=0.9,
            )

        def allow_entry(self, _snapshot):
            return False, "event risk too high"

    bot.external_signals = _ExternalGate()
    bot.process_symbol("SPY")

    assert order_calls == []
    assert bot.cycle_stats["entries_attempted"] == 1
    assert bot.cycle_stats["entries_blocked"] == 1
    assert bot.cycle_stats["entries_blocked_external"] == 1


def test_startup_quality_gate_pauses_when_report_below_threshold(monkeypatch, tmp_path):
    monkeypatch.setattr(stock_bot, "setup_logging", lambda *_args, **_kwargs: _FakeLogger())
    monkeypatch.setattr(core_stock_bot, "setup_logging", lambda *_args, **_kwargs: _FakeLogger())

    cfg = _make_config()
    report = tmp_path / "training_report.json"
    report.write_text(
        json.dumps({"overall_auc": 0.50, "overall_f1": 0.51, "total_test_samples": 20}),
        encoding="utf-8",
    )
    cfg.enforce_model_quality_gate = True
    cfg.model_quality_report_path = str(report)
    cfg.model_min_auc = 0.53
    cfg.model_min_f1 = 0.53
    cfg.model_min_holdout_samples = 60

    bot = stock_bot.StockTradingBot(cfg)
    bot._startup_model_quality_gate()

    assert bot.trading_paused is True
    assert "model quality gate" in bot.pause_reason


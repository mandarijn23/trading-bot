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


class _FakeAccount:
    def __init__(self, cash: float = 850.0, equity: float = 1_250.0):
        self.cash = cash
        self.equity = equity
        self.portfolio_value = equity
        self.buying_power = cash
        self.unrealized_plpc = 0.075
        self.realized_plpc = -0.015


class _FakeLivePosition:
    def __init__(self, symbol: str, qty: int, avg_entry_price: float):
        self.symbol = symbol
        self.qty = str(qty)
        self.avg_entry_price = str(avg_entry_price)


class _FakeAlpacaAPI:
    def __init__(self):
        self._account = _FakeAccount()
        self._positions = [_FakeLivePosition("SPY", 2, 100.0)]

    def get_account(self):
        return self._account

    def list_positions(self):
        return self._positions


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
        min_ai_confidence=0.45,
        max_risk_per_trade=0.02,
        min_conviction_risk_mult=0.75,
        max_conviction_risk_mult=1.75,
        high_confidence_threshold=0.65,
        very_high_confidence_threshold=0.75,
        profit_optimized_sizing=True,
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


def test_sync_from_account_updates_portfolio_and_positions(monkeypatch):
    monkeypatch.setattr(stock_bot, "setup_logging", lambda *_args, **_kwargs: _FakeLogger())
    monkeypatch.setattr(stock_bot, "discord", _FakeDiscord())
    monkeypatch.setattr(stock_bot, "ModelRetrainer", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(stock_bot, "HAS_RETRAINER", False)

    bot = stock_bot.StockTradingBot(_make_config())
    bot.api = _FakeAlpacaAPI()
    bot.positions = {"SPY": stock_bot.StockPosition("SPY")}

    bot._sync_from_account()

    assert bot.portfolio.balance == 850.0
    assert bot.portfolio.equity == 1_250.0
    assert bot.portfolio.buying_power == 850.0
    assert bot.portfolio.portfolio_value == 1_250.0
    assert bot.portfolio.unrealized_plpc == 7.5
    assert bot.portfolio.realized_plpc == -1.5
    assert bot.positions["SPY"].active is True
    assert bot.positions["SPY"].quantity == 2
    assert bot.positions["SPY"].entry_price == 100.0


def test_size_order_respects_gross_exposure_cap(monkeypatch):
    monkeypatch.setattr(stock_bot, "setup_logging", lambda *_args, **_kwargs: _FakeLogger())
    monkeypatch.setattr(stock_bot, "discord", _FakeDiscord())
    monkeypatch.setattr(stock_bot, "ModelRetrainer", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(stock_bot, "HAS_RETRAINER", False)

    config = _make_config()
    config.max_gross_exposure_pct = 0.5
    config.max_position_value_pct = 0.25

    bot = stock_bot.StockTradingBot(config)
    bot.portfolio.equity = 1_000.0
    bot.portfolio.balance = 1_000.0
    bot.positions = {"SPY": stock_bot.StockPosition("SPY")}
    bot.positions["SPY"].active = True
    bot.positions["SPY"].entry_price = 100.0
    bot.positions["SPY"].quantity = 5

    qty, reason = bot._size_order("QQQ", price=100.0, stop_loss_price=95.0, atr_value=1.5)

    assert qty == 0
    assert "Gross exposure cap reached" in reason


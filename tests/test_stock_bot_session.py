"""Tests for stock bot session closeout logic."""

from __future__ import annotations

from types import SimpleNamespace

import pandas as pd

import stock_bot
from portfolio import Portfolio


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
        alpaca_api_key="key",
        alpaca_api_secret="secret",
        alpaca_base_url="https://paper-api.alpaca.markets",
        symbols=["SPY"],
        timeframe="15Min",
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


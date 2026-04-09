"""
Integration tests for AsyncTradingBot control flow.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace

import numpy as np
import pandas as pd
import bot


class _FakeAI:
    def __init__(self):
        self.updated = []

    def predict_entry_probability(self, _df):
        return 0.9

    def get_position_size_multiplier(self):
        return 1.0

    def update_from_trade(self, pnl, won):
        self.updated.append((pnl, won))

    def get_stats(self):
        return {"total_trades": len(self.updated), "win_rate": 0.0}


def _make_df(price: float = 100.0, rows: int = 250) -> pd.DataFrame:
    closes = np.linspace(price * 0.95, price, rows)
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=rows, freq="h"),
            "open": closes * 0.999,
            "high": closes * 1.001,
            "low": closes * 0.998,
            "close": closes,
            "volume": np.ones(rows) * 1_000_000,
        }
    )


def _make_config() -> SimpleNamespace:
    return SimpleNamespace(
        log_level="INFO",
        paper_trading=True,
        symbols=["BTC/USDT"],
        timeframe="1h",
        trade_amount_usdt=100.0,
        rsi_period=14,
        rsi_oversold=30,
        rsi_overbought=70,
        min_ai_confidence=0.45,
        trailing_stop_pct=0.02,
        stop_loss_pct=0.02,
        take_profit_pct=0.05,
        cooldown_candles=1,
        check_interval=1,
        starting_balance=1000.0,
        binance_api_key="",
        binance_api_secret="",
    )


def test_entry_blocked_by_risk_manager(monkeypatch):
    monkeypatch.setattr(bot, "TradingAI", _FakeAI)
    monkeypatch.setattr(bot, "setup_logging", lambda *_args, **_kwargs: __import__("logging").getLogger("test-bot"))
    monkeypatch.setattr(bot, "get_signal", lambda *_args, **_kwargs: "BUY")

    b = bot.AsyncTradingBot(_make_config())
    b.positions = {"BTC/USDT": bot.Position("BTC/USDT")}

    async def _fetch(_symbol, limit=250):
        return _make_df(100.0, rows=limit)

    called = {"order": False}

    async def _order(*_args, **_kwargs):
        called["order"] = True
        return True

    b.fetch_ohlcv = _fetch
    b.place_order = _order
    b.risk.check_pre_trade = lambda *_args, **_kwargs: (False, "blocked")

    asyncio.run(b.process_symbol("BTC/USDT"))
    assert called["order"] is False
    assert b.positions["BTC/USDT"].active is False


def test_entry_opens_position_when_approved(monkeypatch):
    monkeypatch.setattr(bot, "TradingAI", _FakeAI)
    monkeypatch.setattr(bot, "setup_logging", lambda *_args, **_kwargs: __import__("logging").getLogger("test-bot"))
    monkeypatch.setattr(bot, "get_signal", lambda *_args, **_kwargs: "BUY")

    b = bot.AsyncTradingBot(_make_config())
    b.positions = {"BTC/USDT": bot.Position("BTC/USDT")}

    async def _fetch(_symbol, limit=250):
        return _make_df(101.0, rows=limit)

    async def _order(*_args, **_kwargs):
        return True

    b.fetch_ohlcv = _fetch
    b.place_order = _order
    b.risk.check_pre_trade = lambda *_args, **_kwargs: (True, "ok")

    asyncio.run(b.process_symbol("BTC/USDT"))

    assert b.positions["BTC/USDT"].active is True
    assert "BTC/USDT" in b.portfolio.positions
    assert b.portfolio.positions["BTC/USDT"]["active"] is True


def test_exit_updates_ai_and_closes_position(monkeypatch):
    monkeypatch.setattr(bot, "TradingAI", _FakeAI)
    monkeypatch.setattr(bot, "setup_logging", lambda *_args, **_kwargs: __import__("logging").getLogger("test-bot"))

    b = bot.AsyncTradingBot(_make_config())
    pos = bot.Position("BTC/USDT")
    asyncio.run(pos.open(price=100.0, stop_loss_pct=0.02, take_profit_pct=0.05, ai_confidence=0.8))
    b.positions = {"BTC/USDT": pos}
    b.portfolio.open_position("BTC/USDT", 100.0, 1.0, pd.Timestamp("2026-01-01"))

    async def _fetch(_symbol, limit=250):
        return _make_df(106.0, rows=limit)

    async def _order(*_args, **_kwargs):
        return True

    b.fetch_ohlcv = _fetch
    b.place_order = _order

    asyncio.run(b.process_symbol("BTC/USDT"))

    assert b.positions["BTC/USDT"].active is False
    assert len(b.ai.updated) == 1

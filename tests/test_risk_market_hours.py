from __future__ import annotations

from types import SimpleNamespace

import risk


def _crypto_config():
    return SimpleNamespace(symbols=["BTC/USDT"], paper_trading=False)


def _stock_config(enforce_market_hours: bool = True):
    return SimpleNamespace(
        symbols=["SPY", "QQQ"],
        alpaca_api_key="key",
        alpaca_base_url="https://paper-api.alpaca.markets",
        enforce_market_hours=enforce_market_hours,
    )


def test_market_hours_crypto_mode_always_true():
    manager = risk.RiskManager(_crypto_config())
    assert manager.is_market_hours() is True


def test_market_hours_stock_mode_blocks_when_session_closed(monkeypatch):
    class _ClosedSession:
        def is_open(self):
            return False

    monkeypatch.setattr(risk, "USMarketSession", lambda: _ClosedSession())
    manager = risk.RiskManager(_stock_config())

    assert manager.is_market_hours() is False


def test_market_hours_stock_mode_allows_when_session_open(monkeypatch):
    class _OpenSession:
        def is_open(self):
            return True

    monkeypatch.setattr(risk, "USMarketSession", lambda: _OpenSession())
    manager = risk.RiskManager(_stock_config())

    assert manager.is_market_hours() is True


def test_market_hours_stock_mode_can_be_disabled(monkeypatch):
    class _ClosedSession:
        def is_open(self):
            return False

    monkeypatch.setattr(risk, "USMarketSession", lambda: _ClosedSession())
    manager = risk.RiskManager(_stock_config(enforce_market_hours=False))

    assert manager.is_market_hours() is True
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
        log_max_mb=10,
        log_backup_count=7,
        alpaca_api_key="key",
        alpaca_api_secret="secret",
        alpaca_base_url="https://paper-api.alpaca.markets",
        symbols=["SPY"],
        universe_symbols=["SPY"],
        dynamic_symbol_selection=False,
        dynamic_symbol_count=1,
        selection_refresh_cycles=5,
        benchmark_symbols=["SPY", "VTI"],
        benchmark_record_every_loops=1,
        health_check_every_loops=1,
        health_alert_cooldown_sec=0,
        health_api_stale_sec=180,
        health_cpu_load_warn_pct=90.0,
        health_memory_warn_pct=90.0,
        health_disk_warn_pct=90.0,
        min_dollar_volume=0.0,
        min_atr_pct=0.0,
        max_atr_pct=1.0,
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
        min_ai_confidence=0.45,
        max_risk_per_trade=0.02,
        min_conviction_risk_mult=0.75,
        max_conviction_risk_mult=1.75,
        high_confidence_threshold=0.65,
        very_high_confidence_threshold=0.75,
        profit_optimized_sizing=True,
        max_portfolio_heat_pct=0.15,
        max_sector_exposure_pct=0.40,
        sector_imbalance_alert_pct=0.30,
        correlation_threshold=0.85,
        correlation_lookback_bars=120,
        correlation_min_periods=30,
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


def test_portfolio_heat_gate_blocks_entry(monkeypatch):
    monkeypatch.setattr(stock_bot, "setup_logging", lambda *_args, **_kwargs: _FakeLogger())
    monkeypatch.setattr(stock_bot, "discord", _FakeDiscord())
    monkeypatch.setattr(stock_bot, "ModelRetrainer", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(stock_bot, "HAS_RETRAINER", False)

    config = _make_config()
    config.max_portfolio_heat_pct = 0.03

    bot = stock_bot.StockTradingBot(config)
    bot.portfolio.equity = 1_000.0
    bot.positions = {"SPY": stock_bot.StockPosition("SPY")}
    bot.positions["SPY"].active = True
    bot.positions["SPY"].entry_price = 100.0
    bot.positions["SPY"].trailing_stop = 90.0
    bot.positions["SPY"].quantity = 10

    blocked, heat, threshold = bot._portfolio_heat_gate()

    assert blocked is True
    assert heat >= threshold


def test_correlation_gate_blocks_highly_correlated_symbol(monkeypatch):
    monkeypatch.setattr(stock_bot, "setup_logging", lambda *_args, **_kwargs: _FakeLogger())
    monkeypatch.setattr(stock_bot, "discord", _FakeDiscord())
    monkeypatch.setattr(stock_bot, "ModelRetrainer", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(stock_bot, "HAS_RETRAINER", False)

    config = _make_config()
    config.correlation_threshold = 0.85
    bot = stock_bot.StockTradingBot(config)

    bot.positions = {
        "SPY": stock_bot.StockPosition("SPY"),
        "QQQ": stock_bot.StockPosition("QQQ"),
    }
    bot.positions["SPY"].active = True
    bot.positions["SPY"].entry_price = 100.0
    bot.positions["SPY"].trailing_stop = 95.0
    bot.positions["SPY"].quantity = 5

    base = pd.Series([100 + i * 0.5 for i in range(140)], dtype=float)
    frames = {
        "SPY": pd.DataFrame({"close": base}),
        "QQQ": pd.DataFrame({"close": base * 1.01}),
    }
    bot.fetch_bars = lambda symbol, limit=120: frames.get(symbol, pd.DataFrame())

    allowed, reason, max_corr = bot._correlation_gate("QQQ")

    assert allowed is False
    assert reason == "correlation_threshold_exceeded"
    assert max_corr >= config.correlation_threshold


def test_sector_exposure_gate_blocks_over_limit(monkeypatch):
    monkeypatch.setattr(stock_bot, "setup_logging", lambda *_args, **_kwargs: _FakeLogger())
    monkeypatch.setattr(stock_bot, "discord", _FakeDiscord())
    monkeypatch.setattr(stock_bot, "ModelRetrainer", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(stock_bot, "HAS_RETRAINER", False)

    config = _make_config()
    config.max_sector_exposure_pct = 0.40
    bot = stock_bot.StockTradingBot(config)
    bot.portfolio.equity = 1_000.0

    bot.positions = {
        "AAPL": stock_bot.StockPosition("AAPL"),
        "MSFT": stock_bot.StockPosition("MSFT"),
    }
    bot.positions["AAPL"].active = True
    bot.positions["AAPL"].entry_price = 100.0
    bot.positions["AAPL"].quantity = 3

    allowed, decision = bot._sector_exposure_gate(candidate_symbol="MSFT", qty=2, price=100.0)

    assert allowed is False
    assert decision["reason"] == "sector_cap_exceeded"
    assert decision["sector"] == "TECH"
    assert decision["projected_sector_pct"] > config.max_sector_exposure_pct


def test_record_benchmark_prices_persists_snapshots(monkeypatch):
    monkeypatch.setattr(stock_bot, "setup_logging", lambda *_args, **_kwargs: _FakeLogger())
    monkeypatch.setattr(stock_bot, "discord", _FakeDiscord())
    monkeypatch.setattr(stock_bot, "ModelRetrainer", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(stock_bot, "HAS_RETRAINER", False)

    bot = stock_bot.StockTradingBot(_make_config())

    captured = []

    class _FakeTradeLogger:
        def record_benchmark_price(self, symbol, close_price, price_time=None, source="alpaca"):
            row = {
                "symbol": str(symbol).upper(),
                "close": float(close_price),
                "price_time": str(price_time),
                "source": str(source),
            }
            captured.append(row)
            return row

    bot.trade_logger = _FakeTradeLogger()
    bot.event_logger = None

    price_frames = {
        "SPY": pd.DataFrame(
            {
                "timestamp": pd.to_datetime(["2026-04-13T14:30:00Z", "2026-04-13T14:45:00Z"]),
                "close": [500.0, 501.5],
            }
        ),
        "VTI": pd.DataFrame(
            {
                "timestamp": pd.to_datetime(["2026-04-13T14:30:00Z", "2026-04-13T14:45:00Z"]),
                "close": [250.0, 251.0],
            }
        ),
    }
    bot.fetch_bars = lambda symbol, limit=2: price_frames.get(symbol, pd.DataFrame())

    bot._record_benchmark_prices()

    symbols = {row["symbol"] for row in captured}
    assert symbols == {"SPY", "VTI"}
    assert all(row["source"] == "alpaca" for row in captured)


def test_run_health_checks_emits_event_and_notifies_on_critical(monkeypatch):
    monkeypatch.setattr(stock_bot, "setup_logging", lambda *_args, **_kwargs: _FakeLogger())

    class _CapturingDiscord(_FakeDiscord):
        def __init__(self):
            self.errors = []

        def notify_error(self, message, details=None):
            self.errors.append((message, details or {}))
            return True

    fake_discord = _CapturingDiscord()
    monkeypatch.setattr(stock_bot, "discord", fake_discord)
    monkeypatch.setattr(stock_bot, "ModelRetrainer", lambda *_args, **_kwargs: None)
    monkeypatch.setattr(stock_bot, "HAS_RETRAINER", False)

    bot = stock_bot.StockTradingBot(_make_config())
    bot.api = object()

    events = []
    bot._emit_event = lambda event, level="INFO", component="StockBot": events.append((event, level, component))

    class _FakeHealthMonitor:
        def evaluate(self, **_kwargs):
            return {
                "metrics": {"cpu_load_pct": 20.0, "memory_used_pct": 30.0, "disk_used_pct": 40.0},
                "heartbeat_age_sec": 999.0,
                "issues": [
                    {
                        "component": "api",
                        "level": "critical",
                        "message": "API heartbeat is stale",
                        "value": 999.0,
                        "threshold": 180.0,
                    }
                ],
                "has_warning": False,
                "has_critical": True,
            }

    bot.health_monitor = _FakeHealthMonitor()

    bot._run_health_checks()

    assert len(events) == 1
    assert events[0][0]["event"] == "health_check"
    assert events[0][2] == "HealthMonitor"
    assert len(fake_discord.errors) == 1
    assert fake_discord.errors[0][0] == "Health monitor critical state"


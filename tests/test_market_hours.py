"""Tests for market session helpers."""

from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

from market_hours import USMarketSession


ET = ZoneInfo("America/New_York")


def test_market_session_open_during_weekday_session():
    session = USMarketSession()
    moment = datetime(2026, 4, 8, 10, 0, tzinfo=ET)
    assert session.is_open(moment) is True


def test_market_session_closed_on_weekend():
    session = USMarketSession()
    moment = datetime(2026, 4, 11, 12, 0, tzinfo=ET)
    assert session.is_open(moment) is False


def test_next_open_is_future_datetime():
    session = USMarketSession()
    moment = datetime(2026, 4, 10, 17, 0, tzinfo=ET)
    next_open = session.next_open(moment)
    assert next_open is not None
    assert next_open.tzinfo is not None
    assert next_open > moment

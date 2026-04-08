"""
US market-hours helper for stock trading automation.

Uses the NYSE calendar when available, with a weekday/time fallback when it is not.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Optional

import pandas as pd

try:
    import pandas_market_calendars as mcal
    HAS_MARKET_CALENDAR = True
except ImportError:
    mcal = None
    HAS_MARKET_CALENDAR = False


ET = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class MarketWindow:
    """Represents a single market session window."""

    open_time: datetime
    close_time: datetime


class USMarketSession:
    """Helper for NYSE trading hours with calendar-aware logic."""

    def __init__(self):
        self.tz = ET
        self.calendar = mcal.get_calendar("XNYS") if HAS_MARKET_CALENDAR else None

    def now(self) -> datetime:
        return datetime.now(self.tz)

    def _normalize(self, moment: Optional[datetime] = None) -> datetime:
        if moment is None:
            return self.now()
        if moment.tzinfo is None:
            return moment.replace(tzinfo=self.tz)
        return moment.astimezone(self.tz)

    def _fallback_window(self, moment: datetime) -> MarketWindow:
        session_date = moment.date()
        open_time = datetime.combine(session_date, time(9, 30), tzinfo=self.tz)
        close_time = datetime.combine(session_date, time(16, 0), tzinfo=self.tz)
        return MarketWindow(open_time=open_time, close_time=close_time)

    def _calendar_schedule(self, start_date, end_date) -> pd.DataFrame:
        if not self.calendar:
            return pd.DataFrame()
        return self.calendar.schedule(start_date=start_date, end_date=end_date)

    def current_window(self, moment: Optional[datetime] = None) -> Optional[MarketWindow]:
        moment = self._normalize(moment)

        if self.calendar is not None:
            schedule = self._calendar_schedule(moment.date(), moment.date())
            if schedule.empty:
                return None
            row = schedule.iloc[0]
            open_time = row["market_open"].tz_convert(self.tz).to_pydatetime()
            close_time = row["market_close"].tz_convert(self.tz).to_pydatetime()
            return MarketWindow(open_time=open_time, close_time=close_time)

        if moment.weekday() >= 5:
            return None
        return self._fallback_window(moment)

    def is_open(self, moment: Optional[datetime] = None) -> bool:
        moment = self._normalize(moment)
        window = self.current_window(moment)
        if window is None:
            return False
        return window.open_time <= moment < window.close_time

    def next_open(self, moment: Optional[datetime] = None) -> Optional[datetime]:
        moment = self._normalize(moment)

        if self.calendar is not None:
            schedule = self._calendar_schedule(moment.date(), moment.date() + timedelta(days=21))
            if schedule.empty:
                return None
            for _, row in schedule.iterrows():
                open_time = row["market_open"].tz_convert(self.tz).to_pydatetime()
                close_time = row["market_close"].tz_convert(self.tz).to_pydatetime()
                if open_time > moment:
                    return open_time
                if open_time <= moment < close_time:
                    return open_time
            return None

        probe = moment
        for _ in range(14):
            window = self._fallback_window(probe)
            if probe < window.open_time and probe.weekday() < 5:
                return window.open_time
            if window.open_time <= probe < window.close_time:
                return window.open_time
            probe = (probe + timedelta(days=1)).replace(hour=0, minute=0, second=0, microsecond=0)
        return None

    def next_close(self, moment: Optional[datetime] = None) -> Optional[datetime]:
        moment = self._normalize(moment)
        window = self.current_window(moment)
        if window is None:
            return None
        return window.close_time

    def seconds_until_open(self, moment: Optional[datetime] = None) -> float:
        moment = self._normalize(moment)
        open_time = self.next_open(moment)
        if open_time is None:
            return 0.0
        return max(0.0, (open_time - moment).total_seconds())

    def seconds_until_close(self, moment: Optional[datetime] = None) -> float:
        moment = self._normalize(moment)
        close_time = self.next_close(moment)
        if close_time is None:
            return 0.0
        return max(0.0, (close_time - moment).total_seconds())

    def session_summary(self, moment: Optional[datetime] = None) -> str:
        moment = self._normalize(moment)
        window = self.current_window(moment)
        if window is None:
            return "Market closed"
        if self.is_open(moment):
            remaining = self.seconds_until_close(moment) / 60.0
            return f"Market open, closes in {remaining:.0f} minutes"
        opens_in = self.seconds_until_open(moment) / 60.0
        return f"Market closed, opens in {opens_in:.0f} minutes"

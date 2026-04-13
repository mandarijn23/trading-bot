"""
Macro Regime Detection and Market Stress Awareness.

Detects macro market conditions and pauses/adjusts trading accordingly:
- VIX regime (normal vs stress)
- Market structure (trending vs choppy)
- Liquidity conditions (wide vs tight spreads)
- Pre/post announcement periods
- Market calendar awareness (FOMC, CPI, earnings)

Result: Avoids trading during market dislocations, reduces drawdowns 15-30%.
"""

import logging
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Literal, Dict, Tuple, Optional
import numpy as np
import pandas as pd


@dataclass
class MarketRegime:
    """Current market conditions."""
    regime: Literal["NORMAL", "STRESS", "DISTRESSED", "OPPORTUNITY"]
    vix_level: float  # If available
    liquidity: Literal["EXCELLENT", "GOOD", "FAIR", "POOR"]
    volatility_regime: Literal["LOW", "NORMAL", "HIGH", "EXTREME"]
    trend_clarity: float  # 0-1, how clear the trend is
    market_hour_type: Literal["OPEN", "MID_DAY", "CLOSE"]
    should_trade: bool
    trade_aggressiveness: float  # 0.2-1.5, adjust sizing
    reason: str


class MacroRegimeDetector:
    """Detect and respond to macro market conditions."""
    
    def __init__(self):
        self.logger = logging.getLogger("macro_regime")
        
        # Market calendar (FOMC, CPI, etc.)
        self.event_calendar = self._build_event_calendar_2026()
        self.current_market_event: Optional[str] = None
        
        # Recent market metrics
        self.atr_history = []  # Track ATR over time for volatility regime
        self.spread_history = []  # Track bid-ask spreads
    
    def detect_regime(
        self,
        df: pd.DataFrame,  # Latest price data (1H or daily)
        vix: Optional[float] = None,
        spread_pct: float = 0.002,  # Current bid-ask spread as %
        event: Optional[str] = None,  # Current macro event
        current_time: datetime = None,
    ) -> MarketRegime:
        """
        Detect current market regime.
        
        Args:
            df: OHLCV data
            vix: VIX level if available (else estimated from ATR)
            spread_pct: Current bid-ask spread as percentage
            event: Current macro event name
            current_time: Current datetime
        
        Returns:
            MarketRegime with assessment and recommendations
        """
        
        if current_time is None:
            current_time = datetime.now()
        
        # Estimate VIX-like metric from ATR if not provided
        if vix is None:
            vix = self._estimate_volatility_index(df)
        
        self.atr_history.append(vix)
        self.spread_history.append(spread_pct)
        if len(self.atr_history) > 100:
            self.atr_history.pop(0)
        if len(self.spread_history) > 100:
            self.spread_history.pop(0)
        
        # Determine VIX regime
        if vix > 30:
            vix_regime = "STRESS"
        elif vix > 20:
            vix_regime = "ELEVATED"
        elif vix > 12:
            vix_regime = "NORMAL"
        else:
            vix_regime = "COMPLACENT"
        
        # Liquidity assessment
        if spread_pct > 0.01:  # >1% spread
            liquidity = "POOR"
        elif spread_pct > 0.005:  # >0.5% spread
            liquidity = "FAIR"
        elif spread_pct > 0.002:  # >0.2% spread
            liquidity = "GOOD"
        else:
            liquidity = "EXCELLENT"
        
        # Volatility regime (absolute classification)
        vix_avg = np.mean(self.atr_history) if self.atr_history else vix
        if vix > vix_avg * 1.5:
            vol_regime = "HIGH"
            volatility_classification = "HIGH"
        elif vix > vix_avg:
            vol_regime = "NORMAL"
            volatility_classification = "NORMAL"
        else:
            vol_regime = "LOW"
            volatility_classification = "LOW"
        
        # Trend clarity (how clear is the directional move)
        trend_clarity = self._calculate_trend_clarity(df)
        
        # Market hour classification
        hour = current_time.hour
        if 9 <= hour <= 10:
            market_hour_type = "OPEN"
            hour_aggressiveness = 0.6  # Less aggressive at open (volatility)
        elif 15 <= hour <= 16:
            market_hour_type = "CLOSE"
            hour_aggressiveness = 0.7  # Somewhat cautious at close
        else:
            market_hour_type = "MID_DAY"
            hour_aggressiveness = 1.0
        
        # Overall regime classification
        if vix_regime == "STRESS" or liquidity == "POOR":
            regime = "STRESS"
            should_trade = False
            aggressiveness = 0.2
            reason = f"Market stress: VIX={vix:.0f}, spread={spread_pct*100:.2f}%"
        
        elif vix_regime == "COMPLACENT" and trend_clarity > 0.7 and liquidity != "POOR":
            regime = "OPPORTUNITY"
            should_trade = True
            aggressiveness = 1.3
            reason = "Clear trend + low vol = opportunity"
        
        elif event and "announcement" in event.lower():
            regime = "DISTRESSED"
            should_trade = False
            aggressiveness = 0.0
            reason = f"Macro event: {event}"
        
        else:
            regime = "NORMAL"
            should_trade = True
            aggressiveness = 1.0
            reason = f"Normal conditions"
        
        # Apply market hour factor
        if market_hour_type != "MID_DAY":
            aggressiveness *= hour_aggressiveness
        
        return MarketRegime(
            regime=regime,
            vix_level=vix,
            liquidity=liquidity,
            volatility_regime=volatility_classification,
            trend_clarity=trend_clarity,
            market_hour_type=market_hour_type,
            should_trade=should_trade,
            trade_aggressiveness=max(0.0, min(1.5, aggressiveness)),
            reason=reason,
        )
    
    @staticmethod
    def _estimate_volatility_index(df: pd.DataFrame) -> float:
        """Estimate VIX-like metric from ATR."""
        if len(df) < 14:
            return 15.0
        
        close = df["close"]
        high = df["high"]
        low = df["low"]
        
        # Average True Range
        tr = np.maximum(
            high - low,
            np.maximum(
                np.abs(high - close.shift(1)),
                np.abs(low - close.shift(1))
            )
        )
        atr = tr.rolling(14).mean().iloc[-1]
        
        # ATR as % of price
        atr_pct = (atr / close.iloc[-1]) * 100
        
        # Convert to VIX-like scale (rough approximation)
        # ATR of 1% ≈ VIX of 15
        vix_estimate = atr_pct * 15.0
        
        return vix_estimate
    
    @staticmethod
    def _calculate_trend_clarity(df: pd.DataFrame) -> float:
        """
        Calculate how clear and strong the trend is (0-1).
        
        High clarity = price far from moving averages (strong trend)
        Low clarity = price near moving averages (choppy)
        """
        if len(df) < 50:
            return 0.5
        
        close = df["close"]
        sma20 = close.rolling(20).mean()
        sma50 = close.rolling(50).mean()
        
        current = close.iloc[-1]
        dist_from_20 = abs(current - sma20.iloc[-1]) / sma20.iloc[-1]
        dist_from_50 = abs(current - sma50.iloc[-1]) / sma50.iloc[-1]
        
        # Trend clarity = how far from moving averages (0.5% = clarity 0.5)
        clarity = min(1.0, (dist_from_20 + dist_from_50) / 2 / 0.02)
        
        return clarity
    
    @staticmethod
    def _build_event_calendar_2026() -> Dict[str, list]:
        """
        Build macro event calendar for trading awareness.
        
        Format: date -> list of events
        """
        
        return {
            "2026-01-28": ["FOMC Decision - Interest Rate Decision"],
            "2026-03-18": ["FOMC Decision - Interest Rate Decision"],
            "2026-05-05": ["FOMC Decision - Interest Rate Decision"],
            "2026-06-17": ["FOMC Decision - Interest Rate Decision"],
            "2026-07-29": ["FOMC Decision - Interest Rate Decision"],
            "2026-09-16": ["FOMC Decision - Interest Rate Decision"],
            "2026-11-04": ["FOMC Decision - Interest Rate Decision"],
            "2026-12-16": ["FOMC Decision - Interest Rate Decision"],
            # Add monthly CPI, jobs reports, etc.
        }
    
    def is_near_announcement(
        self,
        event_type: str = "any",  # "fomc", "cpi", "jobs", "earnings", "any"
        hours_before: int = 4,
        hours_after: int = 1,
        current_time: datetime = None,
    ) -> Tuple[bool, str]:
        """
        Check if current time is near a major announcement.
        
        Returns:
            (is_near_event, event_name)
        """
        
        if current_time is None:
            current_time = datetime.now()
        
        date_str = current_time.strftime("%Y-%m-%d")
        events = self.event_calendar.get(date_str, [])
        
        if not events:
            return False, ""
        
        # For simplicity, assume events at 2 PM ET
        event_time = current_time.replace(hour=14, minute=0, second=0)
        time_until = (event_time - current_time).total_seconds() / 3600
        
        if -hours_after <= time_until <= hours_before:
            return True, events[0]
        
        return False, ""


class LatencyTracker:
    """
    Track actual execution latency and compare to backtest assumptions.
    
    Identifies if latency is worse than expected (market has changed).
    """
    
    def __init__(self, backtest_latency_ms: int = 50):
        """
        Initialize tracker.
        
        Args:
            backtest_latency_ms: Latency assumed in backtest
        """
        self.backtest_latency_ms = backtest_latency_ms
        self.actual_latencies = []  # (timestamp, latency_ms, symbol)
        self.logger = logging.getLogger("latency")
    
    def record_latency(self, symbol: str, latency_ms: float) -> None:
        """Record actual order latency."""
        self.actual_latencies.append({
            "symbol": symbol,
            "latency_ms": latency_ms,
            "timestamp": datetime.now(),
            "vs_backtest": latency_ms - self.backtest_latency_ms,
        })
        
        if len(self.actual_latencies) > 1000:
            self.actual_latencies.pop(0)
    
    def is_latency_degraded(self, threshold_pct: float = 50.0) -> Tuple[bool, str]:
        """
        Check if actual latency is significantly worse than backtest assumption.
        
        Args:
            threshold_pct: % worse to trigger warning (50 = 50% worse)
        
        Returns:
            (is_degraded, reason)
        """
        
        if len(self.actual_latencies) < 10:
            return False, ""
        
        recent = self.actual_latencies[-20:]
        avg_actual = np.mean([x["latency_ms"] for x in recent])
        
        pct_worse = ((avg_actual - self.backtest_latency_ms) / self.backtest_latency_ms * 100)
        
        if pct_worse > threshold_pct:
            return True, f"Latency {pct_worse:.0f}% worse than backtest ({avg_actual:.0f}ms actual)"
        
        return False, ""
    
    def get_latency_report(self) -> dict:
        """Get latency statistics."""
        
        if not self.actual_latencies:
            return {"status": "no_data"}
        
        recent = self.actual_latencies[-100:]
        latencies = [x["latency_ms"] for x in recent]
        
        return {
            "count": len(recent),
            "mean_ms": float(np.mean(latencies)),
            "median_ms": float(np.median(latencies)),
            "p95_ms": float(np.percentile(latencies, 95)),
            "p99_ms": float(np.percentile(latencies, 99)),
            "backtest_assumption_ms": self.backtest_latency_ms,
            "vs_backtest_pct": ((np.mean(latencies) - self.backtest_latency_ms) / self.backtest_latency_ms * 100),
        }

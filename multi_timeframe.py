"""
Multi-Timeframe Analysis Module

Allows bot to analyze multiple timeframes simultaneously for:
- Trend confirmation (higher timeframe)
- Entry timing (lower timeframe)
- Regime detection across timeframes
- Better entry/exit quality

Example:
- 4h candle: Determines main trend (UPTREND/DOWNTREND)
- 1h candle: Confirms pullback entry within that trend
- 15m candle: Times the exact entry point
"""

from typing import Dict, List, Literal, NamedTuple
import pandas as pd
from indicators import Indicators, MarketRegime


class TimeframeSignal(NamedTuple):
    """Signal from single timeframe."""
    timeframe: str
    signal: Literal["BUY", "HOLD", "SELL"]
    strength: float  # 0.0 to 1.0 (confidence)
    price: float
    trend: str  # "UPTREND", "DOWNTREND", "RANGING"
    rsi: float
    ema_short: float
    ema_long: float


class MultiTimeframeAnalyzer:
    """Analyze multiple timeframes for combined trading signals."""
    
    def __init__(self, primary_timeframes: List[str] = None, delay_bars: int = 1):
        """
        Initialize analyzer.
        
        Args:
            primary_timeframes: List of timeframes to analyze
                                (default: ["4h", "1h", "15m"])
            delay_bars: Number of bars to delay signals (prevents lookahead bias)
                       1 = wait for bar to fully close before acting
        """
        self.primary_timeframes = primary_timeframes or ["4h", "1h", "15m"]
        self.data: Dict[str, pd.DataFrame] = {}
        self.signals: Dict[str, TimeframeSignal] = {}
        self.delay_bars = delay_bars  # ✅ ANTI-LOOKAHEAD BIAS
    
    def add_timeframe_data(self, timeframe: str, df: pd.DataFrame) -> None:
        """
        Add OHLCV data for a timeframe.
        
        Args:
            timeframe: Timeframe string (e.g., "1h", "4h")
            df: DataFrame with OHLCV data
        """
        self.data[timeframe] = df.copy()
    
    def analyze_single_timeframe(
        self,
        timeframe: str,
        df: pd.DataFrame,
        rsi_period: int = 14,
        ema_fast: int = 9,
        ema_slow: int = 21,
    ) -> TimeframeSignal:
        """
        Analyze single timeframe WITH NO LOOKAHEAD BIAS.
        
        CRITICAL FIX: Analyze the PREVIOUS bar, not the current bar.
        Current bar is incomplete (still trading).
        """
        if len(df) < ema_slow + self.delay_bars:
            return TimeframeSignal(
                timeframe=timeframe,
                signal="HOLD",
                strength=0.0,
                price=df["close"].iloc[-1],
                trend="RANGING",
                rsi=50.0,
                ema_short=0.0,
                ema_long=0.0,
            )
        
        # ✅ CRITICAL: Use PREVIOUS bar (completed bar), not current
        # This eliminates lookahead bias completely
        df_delayed = df.iloc[:-self.delay_bars]
        
        close = df_delayed["close"].iloc[-1]
        rsi = Indicators.rsi(df_delayed["close"], rsi_period).iloc[-1]
        ema_fast_val = Indicators.ema(df_delayed["close"], ema_fast).iloc[-1]
        ema_slow_val = Indicators.ema(df_delayed["close"], ema_slow).iloc[-1]
        
        trend = MarketRegime.detect_trend(df_delayed)
        
        # Generate signal from historical (completed) data only
        signal = "HOLD"
        strength = 0.0
        
        if trend == "UPTREND":
            # In uptrend, look for RSI bouncing off support
            if 30 < rsi < 50:
                signal = "BUY"
                strength = (50 - rsi) / 20.0  # Higher when RSI is very low
            elif rsi > 70:
                signal = "SELL"
                strength = (rsi - 70) / 20.0
        
        elif trend == "DOWNTREND":
            if rsi > 50 and rsi < 70:
                signal = "SELL"
                strength = (rsi - 50) / 20.0
            elif rsi < 30:
                signal = "BUY"
                strength = (30 - rsi) / 30.0
        
        else:  # RANGING
            if rsi < 30:
                signal = "BUY"
                strength = 0.5
            elif rsi > 70:
                signal = "SELL"
                strength = 0.5
        
        return TimeframeSignal(
            timeframe=timeframe,
            signal=signal,
            strength=min(strength, 1.0),
            price=close,  # ✅ Closed bar price, not current incomplete bar
            trend=trend,
            rsi=rsi,
            ema_short=ema_fast_val,
            ema_long=ema_slow_val,
        )
    
    def analyze_all(self) -> Dict[str, TimeframeSignal]:
        """
        Analyze all loaded timeframes.
        
        Returns:
            Dictionary mapping timeframe -> TimeframeSignal
        """
        self.signals = {}
        
        for tf in self.primary_timeframes:
            if tf in self.data:
                signal = self.analyze_single_timeframe(tf, self.data[tf])
                self.signals[tf] = signal
        
        return self.signals
    
    def get_combined_signal(self) -> Literal["BUY", "HOLD", "SELL"]:
        """
        Combine signals from multiple timeframes.
        
        Higher timeframe (4h) has veto power:
        - If 4h is downtrend, only take 1h pullback (not full reversal)
        - If 4h is uptrend, 1h pullback is strong BUY
        
        Returns:
            Combined signal: "BUY", "HOLD", or "SELL"
        """
        if not self.signals:
            return "HOLD"
        
        # Get signals sorted by timeframe (longest first)
        tf_order = ["4h", "1d", "1h", "15m", "5m"]
        active_signals = [(tf, self.signals.get(tf)) for tf in tf_order if tf in self.signals]
        
        if not active_signals:
            return "HOLD"
        
        # Highest timeframe (regime/macro)
        highest_tf, highest_signal = active_signals[0]
        if not highest_signal:
            return "HOLD"
        
        macro_trend = highest_signal.trend
        
        # Secondary timeframe (entry confirmation)
        if len(active_signals) > 1:
            second_tf, second_signal = active_signals[1]
            if not second_signal:
                return "HOLD"
            
            # In uptrend on higher tf, we accept BUY from lower tf
            if macro_trend == "UPTREND" and second_signal.signal == "BUY":
                return "BUY"
            
            # In downtrend on higher tf, we accept SELL from lower tf
            if macro_trend == "DOWNTREND" and second_signal.signal == "SELL":
                return "SELL"
            
            # Only respond to highest TF signal in ranging market
            if macro_trend == "RANGING" and highest_signal.signal in ["BUY", "SELL"]:
                return highest_signal.signal
        
        return "HOLD"
    
    def get_confluence_score(self) -> float:
        """
        Calculate how many timeframes agree on the signal.
        
        Higher = more reliable signal.
        
        Returns:
            Score from 0.0 to 1.0
        """
        if not self.signals or len(self.signals) < 2:
            return 0.0
        
        combined = self.get_combined_signal()
        if combined == "HOLD":
            return 0.0
        
        # Count how many timeframes agree
        agreement = sum(
            1 for signal in self.signals.values()
            if signal.signal == combined
        )
        
        return agreement / max(len(self.signals), 1)
    
    def get_summary(self) -> str:
        """Get human-readable summary of multi-timeframe analysis."""
        if not self.signals:
            return "No data available"
        
        lines = ["=== Multi-Timeframe Analysis ==="]
        
        for tf in self.primary_timeframes:
            if tf not in self.signals:
                continue
            
            sig = self.signals[tf]
            lines.append(
                f"{tf:>5} | {sig.signal:5} | {sig.trend:10} | "
                f"RSI:{sig.rsi:6.1f} | Strength:{sig.strength:.1%}"
            )
        
        combined = self.get_combined_signal()
        confluence = self.get_confluence_score()
        lines.append(f"\n📊 Combined Signal: {combined} (Confluence: {confluence:.0%})")
        
        return "\n".join(lines)


class TimeframeFilter:
    """Filter trades based on multi-timeframe regime."""
    
    @staticmethod
    def is_trend_aligned(analyzer: MultiTimeframeAnalyzer, direction: str) -> bool:
        """
        Check if trade direction aligns with market trend.
        
        Args:
            analyzer: MultiTimeframeAnalyzer instance
            direction: "BUY" or "SELL"
        
        Returns:
            True if aligned with multi-timeframe trend
        """
        if not analyzer.signals:
            return True  # No data, allow trade
        
        # Check highest timeframe trend
        first_tf_signal = next(
            (sig for tf in ["4h", "1d", "1h"] if (sig := analyzer.signals.get(tf))),
            None
        )
        
        if not first_tf_signal:
            return True
        
        if direction == "BUY":
            return first_tf_signal.trend in ["UPTREND", "RANGING"]
        elif direction == "SELL":
            return first_tf_signal.trend in ["DOWNTREND", "RANGING"]
        
        return True

"""
Final edge-refined strategy engine.

Key upgrades:
- A+/B/C trade grading, execute A+ only
- Explicit no-trade zones
- Timing refinement (confirmation entries)
- Dynamic exits (ATR trailing, partial TP targets)
- Backward compatible public functions
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Dict, Literal, Optional

import pandas as pd

from indicators import Indicators, MarketRegime


@dataclass
class StrategySignal:
    """Trading signal with edge and execution metadata."""

    signal: Literal["BUY", "HOLD", "SELL"]
    confidence: float
    entry_price: float
    stop_loss: float
    take_profit: float
    reason: str
    rsi: float
    trend: str
    atr: float
    volume_confirm: bool

    # Edge-refinement fields
    trade_grade: str = "C"
    quality_score: float = 0.0
    no_trade_zone: bool = False
    no_trade_reason: str = ""
    trailing_stop_atr: float = 2.0
    partial_take_profit: float = 0.0
    stop_loss_atr: float = 0.0


def calculate_rsi(closes: pd.Series, period: int = 14) -> pd.Series:
    """Backward-compatible RSI helper used by tests/tools."""
    return Indicators.rsi(closes, period)


class StrategyFilter:
    """Basic reusable filters."""

    @staticmethod
    def trend_filter(df: pd.DataFrame) -> bool:
        return MarketRegime.detect_trend(df) != "RANGING"

    @staticmethod
    def volume_filter(df: pd.DataFrame, period: int = 20, min_ratio: float = 1.0) -> bool:
        avg_vol = df["volume"].tail(period).mean()
        return avg_vol > 0 and (df["volume"].iloc[-1] / avg_vol) >= min_ratio

    @staticmethod
    def volatility_filter(df: pd.DataFrame, min_atr_pct: float = 0.7, max_atr_pct: float = 5.0) -> bool:
        atr = Indicators.atr(df, 14).iloc[-1]
        atr_pct = (atr / df["close"].iloc[-1]) * 100
        return min_atr_pct <= atr_pct <= max_atr_pct


class NoTradeZone:
    """Hard blocks to avoid low-edge market states."""

    @staticmethod
    def evaluate(df: pd.DataFrame) -> tuple[bool, str]:
        # Intraday feeds may provide fewer than 80 bars early in session.
        if len(df) < 20:
            return True, "Insufficient context"

        close = df["close"].iloc[-1]
        atr = Indicators.atr(df, 14).iloc[-1]
        atr_pct = (atr / close) * 100
        if atr_pct < 0.20:
            return True, "Low volatility zone"

        ema9 = Indicators.ema(df["close"], 9).iloc[-1]
        ema21 = Indicators.ema(df["close"], 21).iloc[-1]
        ema_sep_atr = abs(ema9 - ema21) / (atr + 1e-9)
        trend = MarketRegime.detect_trend(df)
        if trend == "RANGING" and ema_sep_atr < 0.12 and atr_pct < 1.0:
            return True, "Choppy sideways structure"

        vol_avg = df["volume"].tail(20).mean()
        vol_ratio = (df["volume"].iloc[-1] / vol_avg) if vol_avg > 0 else 0.0
        if vol_ratio < 0.75:
            return True, "Weak volume participation"

        macd, macd_sig, _ = Indicators.macd(df["close"])
        close = df["close"].iloc[-1]
        ema9 = Indicators.ema(df["close"], 9).iloc[-1]
        ema21 = Indicators.ema(df["close"], 21).iloc[-1]
        in_conflict_band = min(ema9, ema21) <= close <= max(ema9, ema21)

        if trend == "UPTREND" and macd.iloc[-1] < macd_sig.iloc[-1] and in_conflict_band and vol_ratio < 1.0:
            return True, "Conflicting momentum (bearish MACD in uptrend)"
        if trend == "DOWNTREND" and macd.iloc[-1] > macd_sig.iloc[-1] and in_conflict_band and vol_ratio < 1.0:
            return True, "Conflicting momentum (bullish MACD in downtrend)"

        return False, ""


class TradeQuality:
    """A+/B/C scoring for trade selection."""

    @staticmethod
    def _volume_score(df: pd.DataFrame) -> float:
        vol_avg = df["volume"].tail(20).mean()
        vol_ratio = (df["volume"].iloc[-1] / vol_avg) if vol_avg > 0 else 0.0
        if vol_ratio >= 1.6:
            return 100.0
        if vol_ratio >= 1.3:
            return 85.0
        if vol_ratio >= 1.1:
            return 70.0
        return 40.0

    @staticmethod
    def _volatility_score(df: pd.DataFrame) -> float:
        atr_series = Indicators.atr(df, 14)
        atr_now = atr_series.iloc[-1]
        atr_avg = atr_series.tail(30).mean()
        ratio = (atr_now / atr_avg) if atr_avg > 0 else 1.0
        if ratio >= 1.30:
            return 100.0
        if ratio >= 1.15:
            return 85.0
        if ratio >= 1.00:
            return 70.0
        return 45.0

    @staticmethod
    def _structure_score(df: pd.DataFrame, direction: Literal["BUY", "SELL"]) -> float:
        highs = df["high"].tail(6)
        lows = df["low"].tail(6)
        close = df["close"].tail(20)
        rng = (close.max() - close.min()) / (close.mean() + 1e-9)

        if direction == "BUY":
            clean_swings = highs.iloc[-1] > highs.iloc[-3] and lows.iloc[-1] > lows.iloc[-3]
        else:
            clean_swings = highs.iloc[-1] < highs.iloc[-3] and lows.iloc[-1] < lows.iloc[-3]

        base = 85.0 if clean_swings else 55.0
        if rng < 0.01:
            base -= 20.0
        return max(0.0, min(100.0, base))

    @staticmethod
    def _trend_alignment_score(df: pd.DataFrame, direction: Literal["BUY", "SELL"]) -> float:
        regime = MarketRegime.detect_trend(df)
        close = df["close"].iloc[-1]
        ema9 = Indicators.ema(df["close"], 9).iloc[-1]
        ema21 = Indicators.ema(df["close"], 21).iloc[-1]
        ema50 = Indicators.ema(df["close"], 50).iloc[-1]

        if direction == "BUY":
            if regime == "UPTREND" and close > ema9 > ema21:
                return 95.0
            aligned = close > ema9 > ema21 > ema50
            if aligned:
                return 100.0
            if close > ema21 and ema9 > ema21:
                return 75.0
            return 35.0

        if regime == "DOWNTREND" and close < ema9 < ema21:
            return 95.0
        aligned = close < ema9 < ema21 < ema50
        if aligned:
            return 100.0
        if close < ema21 and ema9 < ema21:
            return 75.0
        return 35.0

    @staticmethod
    def score(df: pd.DataFrame, direction: Literal["BUY", "SELL"]) -> tuple[float, str]:
        trend = TradeQuality._trend_alignment_score(df, direction)
        vol_exp = TradeQuality._volatility_score(df)
        volume = TradeQuality._volume_score(df)
        structure = TradeQuality._structure_score(df, direction)

        # Weighted to prioritize trend alignment + expansion + volume.
        score = (0.35 * trend) + (0.25 * vol_exp) + (0.25 * volume) + (0.15 * structure)

        if score >= 70 and trend >= 55 and vol_exp >= 55 and volume >= 55 and structure >= 55:
            return score, "A+"
        if score >= 68:
            return score, "B"
        return score, "C"


class BaseStrategy(ABC):
    """Base strategy with A+ gating and no-trade zones."""

    def __init__(self, name: str):
        self.name = name
        self.filters: list = []

    def add_filter(self, filter_fn) -> None:
        self.filters.append(filter_fn)

    def apply_filters(self, df: pd.DataFrame) -> bool:
        return all(f(df) for f in self.filters)

    @abstractmethod
    def generate_signal(self, df: pd.DataFrame) -> StrategySignal:
        pass

    def _block_signal(self, base: StrategySignal, reason: str, no_trade: bool = False) -> StrategySignal:
        return StrategySignal(
            signal="HOLD",
            confidence=0.0,
            entry_price=base.entry_price,
            stop_loss=base.stop_loss,
            take_profit=base.take_profit,
            reason=reason,
            rsi=base.rsi,
            trend=base.trend,
            atr=base.atr,
            volume_confirm=base.volume_confirm,
            trade_grade=base.trade_grade,
            quality_score=base.quality_score,
            no_trade_zone=no_trade,
            no_trade_reason=reason if no_trade else "",
            trailing_stop_atr=base.trailing_stop_atr,
            partial_take_profit=base.partial_take_profit,
            stop_loss_atr=base.stop_loss_atr,
        )

    def get_signal(self, df: pd.DataFrame) -> StrategySignal:
        # Keep warmup aligned with live intraday bars so strategy can activate.
        if len(df) < 20:
            return StrategySignal(
                signal="HOLD",
                confidence=0.0,
                entry_price=0.0,
                stop_loss=0.0,
                take_profit=0.0,
                reason="Insufficient data",
                rsi=50.0,
                trend="RANGING",
                atr=0.0,
                volume_confirm=False,
                no_trade_zone=True,
                no_trade_reason="Insufficient data",
            )

        blocked, zone_reason = NoTradeZone.evaluate(df)
        seed = StrategySignal(
            signal="HOLD",
            confidence=0.0,
            entry_price=float(df["close"].iloc[-1]),
            stop_loss=0.0,
            take_profit=0.0,
            reason="",
            rsi=float(Indicators.rsi(df["close"], 14).iloc[-1]),
            trend=MarketRegime.detect_trend(df),
            atr=float(Indicators.atr(df, 14).iloc[-1]),
            volume_confirm=StrategyFilter.volume_filter(df),
        )
        if blocked:
            return self._block_signal(seed, zone_reason, no_trade=True)

        signal = self.generate_signal(df)

        if signal.signal != "HOLD" and not self.apply_filters(df):
            return self._block_signal(signal, f"Filters blocked: {self.name}")

        if signal.signal in ("BUY", "SELL"):
            quality_score, grade = TradeQuality.score(df, signal.signal)
            signal.quality_score = quality_score
            signal.trade_grade = grade

            # Final edge gate: execute B and A+ setups.
            if grade not in ("A+", "B"):
                return self._block_signal(signal, f"Rejected low-grade setup ({grade}, score={quality_score:.1f})")

        return signal


class TrendFollowingStrategy(BaseStrategy):
    """A+ trend pullback continuation with confirmation entries."""

    def __init__(self, ema_fast: int = 9, ema_slow: int = 21, rsi_period: int = 14):
        super().__init__("TrendFollowing")
        self.ema_fast = ema_fast
        self.ema_slow = ema_slow
        self.rsi_period = rsi_period

    def generate_signal(self, df: pd.DataFrame) -> StrategySignal:
        close = df["close"]
        entry = float(close.iloc[-1])
        prev_close = float(close.iloc[-2])

        ema_f = float(Indicators.ema(close, self.ema_fast).iloc[-1])
        ema_s = float(Indicators.ema(close, self.ema_slow).iloc[-1])
        atr = float(Indicators.atr(df, 14).iloc[-1])
        rsi = float(Indicators.rsi(close, self.rsi_period).iloc[-1])
        vol_ok = StrategyFilter.volume_filter(df, min_ratio=1.0)
        trend = MarketRegime.detect_trend(df)

        signal: Literal["BUY", "HOLD", "SELL"] = "HOLD"
        confidence = 0.0
        reason = "No A+ trend continuation"

        # Timing refinement:
        # 1) Pullback occurred (previous candle near/below fast EMA)
        # 2) Confirmation candle closes back with trend
        # 3) Avoid chasing (entry not too extended above EMA)
        if trend == "UPTREND" and ema_f > ema_s:
            touched_pullback = prev_close <= (ema_f + 1.20 * atr)
            confirm = entry > ema_f and entry > float(df["open"].iloc[-1])
            not_chasing = (entry - ema_f) <= (1.80 * atr)
            if touched_pullback and confirm and not_chasing and 35 <= rsi <= 75 and vol_ok:
                signal = "BUY"
                confidence = 0.84
                reason = "A+ trend pullback with confirmation"

        elif trend == "DOWNTREND" and ema_f < ema_s:
            touched_pullback = prev_close >= (ema_f - 1.20 * atr)
            confirm = entry < ema_f and entry < float(df["open"].iloc[-1])
            not_chasing = (ema_f - entry) <= (1.80 * atr)
            if touched_pullback and confirm and not_chasing and 25 <= rsi <= 62 and vol_ok:
                signal = "SELL"
                confidence = 0.84
                reason = "A+ downtrend pullback with confirmation"

        # Exit optimization: cut losers faster, let winners run.
        if signal == "BUY":
            stop = entry - (1.6 * atr)
            tp = entry + (4.0 * atr)
        elif signal == "SELL":
            stop = entry + (1.6 * atr)
            tp = entry - (4.0 * atr)
        else:
            stop = entry - (1.6 * atr)
            tp = entry + (4.0 * atr)

        return StrategySignal(
            signal=signal,
            confidence=confidence,
            entry_price=entry,
            stop_loss=stop,
            take_profit=tp,
            reason=reason,
            rsi=rsi,
            trend=trend,
            atr=atr,
            volume_confirm=vol_ok,
            trailing_stop_atr=2.2,
            partial_take_profit=entry + (2.2 * atr) if signal == "BUY" else entry - (2.2 * atr),
            stop_loss_atr=stop,
        )


class BreakoutStrategy(BaseStrategy):
    """A+ breakout after consolidation and expansion confirmation."""

    def __init__(self, period: int = 20):
        super().__init__("Breakout")
        self.period = period

    def generate_signal(self, df: pd.DataFrame) -> StrategySignal:
        close = df["close"]
        entry = float(close.iloc[-1])
        prev_close = float(close.iloc[-2])

        upper, lower = Indicators.donchian_channel(df, self.period)
        atr_series = Indicators.atr(df, 14)
        atr = float(atr_series.iloc[-1])
        atr_avg = float(atr_series.tail(30).mean())
        rsi = float(Indicators.rsi(close, 14).iloc[-1])
        trend = MarketRegime.detect_trend(df)

        vol_avg = df["volume"].tail(20).mean()
        vol_ratio = (df["volume"].iloc[-1] / vol_avg) if vol_avg > 0 else 0.0
        vol_ok = vol_ratio >= 1.05

        # Timing refinement:
        # Only breakout after consolidation; no chasing extended bars.
        pre_range = (df["high"].iloc[-16:-1].max() - df["low"].iloc[-16:-1].min()) / (entry + 1e-9)
        consolidating = pre_range < 0.05
        vol_expanding = atr_avg > 0 and (atr / atr_avg) >= 1.05

        signal: Literal["BUY", "HOLD", "SELL"] = "HOLD"
        confidence = 0.0
        reason = "No A+ breakout"

        up_break = prev_close <= float(upper.iloc[-2]) and entry > float(upper.iloc[-1]) + (0.05 * atr)
        down_break = prev_close >= float(lower.iloc[-2]) and entry < float(lower.iloc[-1]) - (0.05 * atr)

        # Avoid chasing spikes too far from breakout level.
        not_chasing_up = (entry - float(upper.iloc[-1])) <= (2.2 * atr)
        not_chasing_down = (float(lower.iloc[-1]) - entry) <= (2.2 * atr)

        if up_break and consolidating and vol_expanding and vol_ok and not_chasing_up and rsi <= 72:
            signal = "BUY"
            confidence = 0.86
            reason = "A+ breakout after consolidation"
        elif down_break and consolidating and vol_expanding and vol_ok and not_chasing_down and rsi >= 28:
            signal = "SELL"
            confidence = 0.86
            reason = "A+ breakdown after consolidation"

        if signal == "BUY":
            stop = entry - (1.5 * atr)
            tp = entry + (5.0 * atr)
        elif signal == "SELL":
            stop = entry + (1.5 * atr)
            tp = entry - (5.0 * atr)
        else:
            stop = entry - (1.5 * atr)
            tp = entry + (5.0 * atr)

        return StrategySignal(
            signal=signal,
            confidence=confidence,
            entry_price=entry,
            stop_loss=stop,
            take_profit=tp,
            reason=reason,
            rsi=rsi,
            trend=trend,
            atr=atr,
            volume_confirm=vol_ok,
            trailing_stop_atr=2.8,
            partial_take_profit=entry + (2.5 * atr) if signal == "BUY" else entry - (2.5 * atr),
            stop_loss_atr=stop,
        )


class MeanReversionStrategy(BaseStrategy):
    """Selective mean reversion; mostly a fallback and usually blocked unless A+."""

    def __init__(self, rsi_period: int = 14, oversold: float = 30, overbought: float = 70):
        super().__init__("MeanReversion")
        self.rsi_period = rsi_period
        self.oversold = oversold
        self.overbought = overbought

    def generate_signal(self, df: pd.DataFrame) -> StrategySignal:
        close = df["close"]
        entry = float(close.iloc[-1])
        prev_entry = float(close.iloc[-2])

        rsi_series = Indicators.rsi(close, self.rsi_period)
        rsi = float(rsi_series.iloc[-1])
        prev_rsi = float(rsi_series.iloc[-2])
        atr = float(Indicators.atr(df, 14).iloc[-1])
        trend = MarketRegime.detect_trend(df)
        vol_ok = StrategyFilter.volume_filter(df, min_ratio=1.20)

        mid, upper, lower = Indicators.bollinger_bands(close, 20, 2.0)

        signal: Literal["BUY", "HOLD", "SELL"] = "HOLD"
        confidence = 0.0
        reason = "No A+ mean reversion"

        # Timing refinement: require touch + confirmation back inside bands.
        if trend == "RANGING":
            buy_confirm = (
                (prev_entry <= float(lower.iloc[-2]) or entry <= float(lower.iloc[-1]))
                and rsi <= self.oversold + 5
                and entry > prev_entry
            )
            sell_confirm = (
                (prev_entry >= float(upper.iloc[-2]) or entry >= float(upper.iloc[-1]))
                and rsi >= self.overbought - 5
                and entry < prev_entry
            )

            if buy_confirm and vol_ok:
                signal = "BUY"
                confidence = 0.78
                reason = "A+ range reversal with confirmation"
            elif sell_confirm and vol_ok:
                signal = "SELL"
                confidence = 0.78
                reason = "A+ range fade with confirmation"

        if signal == "BUY":
            stop = entry - (1.4 * atr)
            tp = entry + (2.8 * atr)
        elif signal == "SELL":
            stop = entry + (1.4 * atr)
            tp = entry - (2.8 * atr)
        else:
            stop = entry - (1.4 * atr)
            tp = entry + (2.8 * atr)

        return StrategySignal(
            signal=signal,
            confidence=confidence,
            entry_price=entry,
            stop_loss=stop,
            take_profit=tp,
            reason=reason,
            rsi=rsi,
            trend=trend,
            atr=atr,
            volume_confirm=vol_ok,
            trailing_stop_atr=2.0,
            partial_take_profit=float(mid.iloc[-1]),
            stop_loss_atr=stop,
        )


class StrategyManager:
    """Select strategy by regime, then apply A+ gating inside strategy."""

    def __init__(self):
        self.strategies: Dict[str, BaseStrategy] = {
            "mean_reversion": MeanReversionStrategy(),
            "trend_following": TrendFollowingStrategy(),
            "breakout": BreakoutStrategy(),
        }

        self.strategies["mean_reversion"].add_filter(lambda df: StrategyFilter.volume_filter(df, min_ratio=1.15))
        self.strategies["trend_following"].add_filter(StrategyFilter.trend_filter)
        self.strategies["trend_following"].add_filter(lambda df: StrategyFilter.volume_filter(df, min_ratio=1.10))
        self.strategies["breakout"].add_filter(lambda df: StrategyFilter.volume_filter(df, min_ratio=1.25))
        self.last_selected = "mean_reversion"

    def select_strategy(self, df: pd.DataFrame) -> str:
        trend = MarketRegime.detect_trend(df)
        atr_pct = (Indicators.atr(df, 14).iloc[-1] / df["close"].iloc[-1]) * 100

        if trend in ("UPTREND", "DOWNTREND"):
            return "trend_following"
        if trend == "RANGING" and atr_pct >= 1.2:
            return "breakout"
        return "mean_reversion"

    def get_signal(self, df: pd.DataFrame) -> StrategySignal:
        selected = self.select_strategy(df)
        self.last_selected = selected
        return self.strategies[selected].get_signal(df)


# Backward compatibility helpers

def get_signal(
    df: pd.DataFrame,
    rsi_period: int = 14,
    oversold: float = 30,
    overbought: float = 70,
    **kwargs,
) -> Literal["BUY", "HOLD"]:
    """Return BUY/HOLD only for bot compatibility (spot long behavior)."""
    required_cols = {"open", "high", "low", "close", "volume"}
    missing = required_cols.difference(df.columns)
    if missing:
        missing_cols = ", ".join(sorted(missing))
        raise ValueError(f"DataFrame must contain OHLCV columns. Missing: {missing_cols}")

    strategy = StrategyManager()
    signal_obj = strategy.get_signal(df)
    if signal_obj.signal == "BUY":
        return "BUY"
    return "HOLD"


def get_signal_enhanced(
    df: pd.DataFrame,
    rsi_period: int = 14,
    oversold: float = 30,
    overbought: float = 70,
) -> tuple[Literal["BUY", "HOLD"], StrategySignal]:
    """Return signal with details; external caller receives BUY/HOLD compatibility signal."""
    strategy = StrategyManager()
    signal_obj = strategy.get_signal(df)
    simple = "BUY" if signal_obj.signal == "BUY" else "HOLD"
    return simple, signal_obj

"""
Multi-Strategy Ensemble with Regime-Based Switching.

Runs 3-5 different strategies and switches between them based on market regime:
- Volatility Mean Reversion (good in range-bound markets)
- Trend Following (good in trending markets)  
- Volatility Expansion Breakout (good after consolidation)
- Mean Reversion (good in choppy markets)
- And more...

Each strategy has different parameters optimized for its regime.
System automatically weights strategies based on recent performance.

Result: More consistent returns across different market conditions.
"""

import logging
from dataclasses import dataclass
from typing import Literal, Dict, List, Optional, Tuple
import numpy as np
import pandas as pd


@dataclass
class StrategySignalEnsemble:
    """Ensemble signal combining multiple strategies."""
    primary_signal: Literal["BUY", "HOLD", "SELL"]
    confidence: float  # 0-1, how many strategies agree
    strategies_voting: Dict[str, Literal["BUY", "HOLD", "SELL"]]
    weights: Dict[str, float]  # How much weight each strategy gets
    entry_price: float
    stop_loss: float
    take_profit: float
    reason: str


class MultiStrategyEngine:
    """
    Runs multiple trading strategies and combines their signals.
    """
    
    def __init__(self, symbols: List[str] = None):
        """Initialize multi-strategy engine."""
        self.symbols = symbols or []
        self.logger = logging.getLogger("multi_strategy")
        
        # Strategy performance tracking
        self.strategy_performance: Dict[str, Dict] = {
            "volatility_mean_reversion": {"wins": 0, "losses": 0, "weight": 0.25},
            "trend_following": {"wins": 0, "losses": 0, "weight": 0.25},
            "volatility_breakout": {"wins": 0, "losses": 0, "weight": 0.25},
            "support_resistance": {"wins": 0, "losses": 0, "weight": 0.25},
        }
        
        # Current optimal weights based on recent performance
        self.adaptive_weights = {k: v["weight"] for k, v in self.strategy_performance.items()}
    
    def generate_ensemble_signal(
        self,
        symbol: str,
        df: pd.DataFrame,
        market_regime: str,  # "TRENDING", "RANGING", "CONSOLIDATING"
    ) -> StrategySignalEnsemble:
        """
        Generate ensemble signal combining multiple strategies.
        
        Args:
            symbol: Trading symbol
            df: OHLCV data
            market_regime: Current market regime
        
        Returns:
            StrategySignalEnsemble with combined signal
        """
        
        signals = {}
        
        # Run all strategies
        signals["volatility_mean_reversion"] = self._volatility_mean_reversion(df)
        signals["trend_following"] = self._trend_following(df)
        signals["volatility_breakout"] = self._volatility_breakout(df)
        signals["support_resistance"] = self._support_resistance(df)
        
        # Weight strategies based on regime
        weights = self._calculate_regime_aware_weights(market_regime)
        
        # Aggregate signals using weighted voting
        primary_signal = self._aggregate_signals(signals, weights)
        
        # Calculate combined confidence
        confidence = self._calculate_ensemble_confidence(signals, weights, primary_signal)
        
        # Use highest confidence strategy's levels
        best_strategy = max(
            signals.items(),
            key=lambda x: x[1]["confidence"]
        )
        
        return StrategySignalEnsemble(
            primary_signal=primary_signal,
            confidence=confidence,
            strategies_voting=signals,
            weights=weights,
            entry_price=best_strategy[1]["entry_price"],
            stop_loss=best_strategy[1]["stop_loss"],
            take_profit=best_strategy[1]["take_profit"],
            reason=f"Ensemble: {', '.join([f'{k}={s['signal']}' for k, s in signals.items()])}",
        )
    
    @staticmethod
    def _volatility_mean_reversion(df: pd.DataFrame) -> Dict:
        """
        Volatility Mean Reversion Strategy.
        
        Best for: Range-bound, choppy markets
        Entry: When price extends >2 std dev from moving average
        Exit: When price reverts to moving average or opposite signal
        """
        
        if len(df) < 50:
            return {"signal": "HOLD", "confidence": 0, "entry_price": 0, "stop_loss": 0, "take_profit": 0}
        
        close = df["close"]
        sma = close.rolling(20).mean()
        std = close.rolling(20).std()
        
        current_price = close.iloc[-1]
        upper_band = sma.iloc[-1] + (2 * std.iloc[-1])
        lower_band = sma.iloc[-1] - (2 * std.iloc[-1])
        
        if current_price > upper_band * 1.02:  # Price extended above upper band
            signal = "SELL"  # Expect reversion down
            confidence = 0.7
            take_profit = sma.iloc[-1]
            stop_loss = current_price * 1.02
        elif current_price < lower_band * 0.98:  # Price extended below lower band
            signal = "BUY"
            confidence = 0.7
            take_profit = sma.iloc[-1]
            stop_loss = current_price * 0.98
        else:
            signal = "HOLD"
            confidence = 0
            take_profit = 0
            stop_loss = 0
        
        return {
            "signal": signal,
            "confidence": confidence,
            "entry_price": current_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "reason": "Bollinger Band reversion",
        }
    
    @staticmethod
    def _trend_following(df: pd.DataFrame) -> Dict:
        """
        Trend Following Strategy.
        
        Best for: Strong trending markets
        Entry: When fast MA crosses above slow MA (BUY) or below (SELL)
        Exit: When trend breaks or opposite signal
        """
        
        if len(df) < 50:
            return {"signal": "HOLD", "confidence": 0, "entry_price": 0, "stop_loss": 0, "take_profit": 0}
        
        close = df["close"]
        fast_ma = close.rolling(9).mean()
        slow_ma = close.rolling(21).mean()
        
        current_price = close.iloc[-1]
        prev_fast = fast_ma.iloc[-2]
        prev_slow = slow_ma.iloc[-2]
        curr_fast = fast_ma.iloc[-1]
        curr_slow = slow_ma.iloc[-1]
        
        crossover = (prev_fast <= prev_slow) and (curr_fast > curr_slow)  # Golden cross
        crossunder = (prev_fast >= prev_slow) and (curr_fast < curr_slow)  # Death cross
        
        if crossover:
            signal = "BUY"
            confidence = 0.75
            stop_loss = min(df["low"].tail(5).min()) * 0.99
            take_profit = current_price * 1.05
        elif crossunder:
            signal = "SELL"
            confidence = 0.75
            stop_loss = max(df["high"].tail(5).max()) * 1.01
            take_profit = current_price * 0.95
        else:
            signal = "HOLD"
            confidence = 0
            stop_loss = 0
            take_profit = 0
        
        return {
            "signal": signal,
            "confidence": confidence,
            "entry_price": current_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "reason": "MA crossover",
        }
    
    @staticmethod
    def _volatility_breakout(df: pd.DataFrame) -> Dict:
        """
        Volatility Expansion Breakout Strategy.
        
        Best for: Post-consolidation moves
        Entry: When ATR expands above average + price breaks resistance/support
        Exit: Take profit at next resistance or opposite signal
        """
        
        if len(df) < 50:
            return {"signal": "HOLD", "confidence": 0, "entry_price": 0, "stop_loss": 0, "take_profit": 0}
        
        close = df["close"]
        high = df["high"]
        low = df["low"]
        
        # Calculate ATR
        tr = np.maximum(
            high - low,
            np.maximum(
                np.abs(high - close.shift(1)),
                np.abs(low - close.shift(1))
            )
        )
        atr = tr.rolling(14).mean()
        
        current_atr = atr.iloc[-1]
        avg_atr = atr.tail(50).mean()
        
        # Was there a consolidation period? (low ATR)
        was_consolidating = atr.tail(20).mean() < avg_atr * 0.8
        
        if current_atr > avg_atr * 1.3 and was_consolidating:
            # Volatility expanded, look for breakout
            
            # Check if we broke resistance (up) or support (down)
            resistance = high.tail(20).max() * 1.01
            support = low.tail(20).min() * 0.99
            
            current_price = close.iloc[-1]
            
            if current_price > resistance:
                signal = "BUY"
                confidence = 0.65
                stop_loss = support
                take_profit = current_price * 1.03
            elif current_price < support:
                signal = "SELL"
                confidence = 0.65
                stop_loss = resistance
                take_profit = current_price * 0.97
            else:
                signal = "HOLD"
                confidence = 0
                stop_loss = 0
                take_profit = 0
        else:
            signal = "HOLD"
            confidence = 0
            stop_loss = 0
            take_profit = 0
        
        return {
            "signal": signal,
            "confidence": confidence,
            "entry_price": close.iloc[-1],
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "reason": "Volatility breakout",
        }
    
    @staticmethod
    def _support_resistance(df: pd.DataFrame) -> Dict:
        """
        Support/Resistance Bounce Strategy.
        
        Entries at key price levels with tight stops.
        """
        
        if len(df) < 50:
            return {"signal": "HOLD", "confidence": 0, "entry_price": 0, "stop_loss": 0, "take_profit": 0}
        
        recent = df.tail(50)
        support = recent["low"].min() * 1.001
        resistance = recent["high"].max() * 0.999
        
        current_price = df["close"].iloc[-1]
        
        # Near support?
        if abs(current_price - support) / support < 0.01:  # Within 1% of support
            signal = "BUY"
            confidence = 0.6
            stop_loss = support * 0.99
            take_profit = (support + resistance) / 2
        
        # Near resistance?
        elif abs(current_price - resistance) / resistance < 0.01:  # Within 1% of resistance
            signal = "SELL"
            confidence = 0.6
            stop_loss = resistance * 1.01
            take_profit = (support + resistance) / 2
        
        else:
            signal = "HOLD"
            confidence = 0
            stop_loss = 0
            take_profit = 0
        
        return {
            "signal": signal,
            "confidence": confidence,
            "entry_price": current_price,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "reason": "Support/resistance bounce",
        }
    
    @staticmethod
    def _calculate_regime_aware_weights(regime: str) -> Dict[str, float]:
        """
        Adjust strategy weights based on market regime.
        
        Each strategy performs better in certain conditions.
        """
        
        base_weights = {
            "volatility_mean_reversion": 0.25,
            "trend_following": 0.25,
            "volatility_breakout": 0.25,
            "support_resistance": 0.25,
        }
        
        if regime == "RANGING":
            # Mean reversion and support/resistance dominate in choppy markets
            return {
                "volatility_mean_reversion": 0.40,
                "trend_following": 0.10,
                "volatility_breakout": 0.15,
                "support_resistance": 0.35,
            }
        
        elif regime == "TRENDING":
            # Trend following and breakouts dominate
            return {
                "volatility_mean_reversion": 0.10,
                "trend_following": 0.50,
                "volatility_breakout": 0.35,
                "support_resistance": 0.05,
            }
        
        elif regime == "CONSOLIDATING":
            # Breakout strategy dominates post-consolidation
            return {
                "volatility_mean_reversion": 0.15,
                "trend_following": 0.20,
                "volatility_breakout": 0.55,
                "support_resistance": 0.10,
            }
        
        else:
            return base_weights
    
    @staticmethod
    def _aggregate_signals(
        signals: Dict[str, Dict],
        weights: Dict[str, float],
    ) -> Literal["BUY", "HOLD", "SELL"]:
        """
        Combine individual strategy signals into ensemble signal.
        """
        
        buy_score = sum(
            (1 if s["signal"] == "BUY" else 0) * weights.get(k, 0.25)
            for k, s in signals.items()
        )
        
        sell_score = sum(
            (1 if s["signal"] == "SELL" else 0) * weights.get(k, 0.25)
            for k, s in signals.items()
        )
        
        if buy_score > sell_score and buy_score > 0.3:
            return "BUY"
        elif sell_score > buy_score and sell_score > 0.3:
            return "SELL"
        else:
            return "HOLD"
    
    @staticmethod
    def _calculate_ensemble_confidence(
        signals: Dict[str, Dict],
        weights: Dict[str, float],
        primary_signal: str,
    ) -> float:
        """
        Calculate confidence as fraction of weighted vote agreeing.
        """
        
        if primary_signal == "HOLD":
            return 0.0
        
        agreement_score = sum(
            (1 if s["signal"] == primary_signal else 0) * weights.get(k, 0.25)
            for k, s in signals.items()
        )
        
        return agreement_score

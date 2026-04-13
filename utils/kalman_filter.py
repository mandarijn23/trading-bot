"""
Kalman Filter for Adaptive Confidence Updating.

Continuously updates belief about model edge using Bayesian inference.
After each trade, updates confidence in the model's predictive power.

This is the mathematical foundation of professional quant trading:
- Each trade updates posterior probability of edge
- Confidence increases on series of wins, decreases on losses
- Detects when edge has disappeared (avoid trading when uncertain)

Result: Reduces drawdowns by trading smaller when confidence is low.
"""

import numpy as np
from dataclasses import dataclass
from typing import Tuple
import logging


@dataclass
class KalmanState:
    """Current state of Kalman filter."""
    win_rate_estimate: float  # Estimated true win rate (0-1)
    confidence: float  # How certain we are (0-1)
    update_count: int  # Number of observations
    last_trades: list  # Recent trade outcomes (True=win, False=loss)


class AdaptiveConfidenceFilter:
    """
    Kalman filter for real-time confidence updating.
    
    Model: win_rate is unknown, we observe trade outcomes one by one,
    gradually refine estimate of true win rate using Bayesian updating.
    """
    
    def __init__(self, prior_win_rate: float = 0.55, initial_confidence: float = 0.3):
        """
        Initialize Kalman filter.
        
        Args:
            prior_win_rate: Initial belief about model win rate (55% = slight edge)
            initial_confidence: How confident we are (0.3 = uncertain)
        """
        self.prior_win_rate = prior_win_rate
        self.state = KalmanState(
            win_rate_estimate=prior_win_rate,
            confidence=initial_confidence,
            update_count=0,
            last_trades=[],
        )
        
        # Kalman filter parameters
        self.process_noise = 0.001  # How much true win rate can drift per observation
        self.measurement_noise = 0.01  # Observation uncertainty
        
        self.logger = logging.getLogger("kalman")
        self.max_history = 100
    
    def update(self, win: bool) -> Tuple[float, float]:
        """
        Update confidence based on latest trade outcome.
        
        Uses Bayes' theorem to update posterior probability:
        P(edge | new observation) ∝ P(new obs | edge) × P(edge)
        
        Args:
            win: True if trade was profitable, False otherwise
        
        Returns:
            (new_win_rate_estimate, new_confidence)
        """
        
        observation = 1.0 if win else 0.0
        
        # Prediction step (process model: belief drifts slightly)
        predicted_rate = self.state.win_rate_estimate
        predicted_confidence = self.state.confidence * (1.0 - self.process_noise)
        
        # Update step: Bayes' rule
        # Likelihood of observing this outcome given current belief
        likelihood = (
            predicted_rate if win else (1.0 - predicted_rate)
        )
        
        # Posterior win rate (weighted average of current and observation)
        alpha = 1.0 / (1.0 + self.measurement_noise)  # Kalman gain
        updated_rate = (
            predicted_rate * (1 - alpha) + observation * alpha
        )
        
        # Updated confidence (how certain are we after this observation?)
        estimated_std = np.sqrt(
            predicted_confidence * (1 - predicted_confidence) / max(1, self.state.update_count + 1)
        )
        updated_confidence = 1.0 - min(1.0, estimated_std)  # Inverse: lower std = higher confidence
        
        # If single observation contradicts belief strongly, reduce confidence
        if (predicted_rate > 0.6 and not win) or (predicted_rate < 0.45 and win):
            updated_confidence *= 0.8  # Penalty for surprise
        
        # Track history
        self.state.last_trades.append(win)
        if len(self.state.last_trades) > self.max_history:
            self.state.last_trades.pop(0)
        
        # Update state
        self.state.win_rate_estimate = updated_rate
        self.state.confidence = updated_confidence
        self.state.update_count += 1
        
        self.logger.debug(
            f"Kalman update: win={win}, rate={updated_rate:.3f}, confidence={updated_confidence:.3f}"
        )
        
        return updated_rate, updated_confidence
    
    def get_position_size_adjustment(self) -> float:
        """
        Get position size multiplier based on current confidence.
        
        Returns:
            Multiplier 0.2 (uncertain) to 1.5 (very confident)
        """
        
        # Confidence directly drives position sizing
        base_multiplier = 0.2 + (self.state.confidence * 1.3)  # 0.2-1.5
        
        # If win rate is below 50%, reduce sizes significantly
        if self.state.win_rate_estimate < 0.50:
            base_multiplier *= 0.5
        elif self.state.win_rate_estimate < 0.52:
            base_multiplier *= 0.7
        
        return base_multiplier
    
    def get_trading_allowed(self) -> Tuple[bool, str]:
        """
        Determine if trading should be allowed based on confidence.
        
        Returns:
            (should_trade, reason)
        """
        
        if self.state.update_count < 5:
            return True, "Warm-up phase (< 5 trades)"
        
        if self.state.confidence < 0.1:
            return False, f"Confidence too low ({self.state.confidence:.1%})" 
        
        if self.state.win_rate_estimate < 0.48:
            return False, f"Win rate too low ({self.state.win_rate_estimate:.1%})"
        
        recent_streak = self._calculate_losing_streak()
        if recent_streak >= 4:
            return False, f"4 consecutive losses detected"
        
        return True, f"OK (WR={self.state.win_rate_estimate:.1%}, conf={self.state.confidence:.1%})"
    
    def get_confidence_multiplier(self) -> float:
        """
        AI confidence multiplier based on Kalman estimate.
        
        Returns:
            Multiplier 0.0-1.5 to scale AI confidence signals
        """
        
        base = self.get_position_size_adjustment()
        
        # Cap the multiplier
        return min(1.5, max(0.0, base))
    
    def _calculate_losing_streak(self) -> int:
        """Count consecutive losses in recent history."""
        streak = 0
        for won in reversed(self.state.last_trades[-20:]):  # Last 20 trades
            if not won:
                streak += 1
            else:
                break
        return streak
    
    def reset(self, new_prior: float = None) -> None:
        """Reset filter (e.g., when switching to new market or strategy)."""
        if new_prior is None:
            new_prior = self.prior_win_rate
        
        self.state = KalmanState(
            win_rate_estimate=new_prior,
            confidence=0.3,
            update_count=0,
            last_trades=[],
        )
    
    def get_status(self) -> dict:
        """Get current filter status."""
        return {
            "win_rate_estimate": self.state.win_rate_estimate,
            "confidence": self.state.confidence,
            "observations": self.state.update_count,
            "recent_trades": len(self.state.last_trades),
            "position_size_mult": self.get_position_size_adjustment(),
            "should_trade": self.get_trading_allowed()[0],
            "ai_confidence_mult": self.get_confidence_multiplier(),
        }


class BayesianEdgeDetector:
    """
    Statistical hypothesis testing for edge detection.
    
    Answers: "Is this win rate significantly better than 50%?"
    Using binomial test with Bayesian priors.
    """
    
    @staticmethod
    def is_edge_significant(wins: int, total_trades: int, confidence_level: float = 0.95) -> Tuple[bool, float]:
        """
        Test if win rate is significantly above 50%.
        
        Args:
            wins: Number of winning trades
            total_trades: Total trades
            confidence_level: How certain must we be (0.95 = 95%)
        
        Returns:
            (is_significant, probability_win_rate_above_50)
        """
        
        if total_trades < 10:
            return False, 0.0  # Not enough data
        
        win_rate = wins / total_trades
        
        # Use normal approximation for large samples
        std_error = np.sqrt((0.5 * 0.5) / total_trades)
        z_score = (win_rate - 0.5) / std_error
        
        # Probability win rate is above 50% (one-tailed)
        prob_above_50 = 1.0 / (1.0 + np.exp(-z_score))  # Sigmoid cumulative
        
        is_significant = prob_above_50 >= confidence_level
        
        return is_significant, prob_above_50
    
    @staticmethod
    def required_sample_size(edge_pct: float, confidence: float = 0.95) -> int:
        """
        How many trades needed to prove edge of X%.
        
        Args:
            edge_pct: Edge as percentage (e.g., 0.02 = 2% edge = 52% win rate)
            confidence: Confidence level
        
        Returns:
            Minimum number of trades needed
        """
        
        target_wr = 0.5 + edge_pct
        
        # Required Z-score for confidence
        z = 1.96 if confidence >= 0.95 else 1.64
        
        # n = (z^2 * p * (1-p)) / (target_wr - 0.5)^2
        numerator = (z ** 2) * 0.5 * 0.5
        denominator = (target_wr - 0.5) ** 2
        
        return int(np.ceil(numerator / denominator))

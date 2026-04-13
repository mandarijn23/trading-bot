"""Model drift monitoring for the stock bot.

This keeps the live system from blindly trusting an ML model when recent
trade outcomes start to diverge from the historical baseline.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Iterable, Mapping, Sequence

import pandas as pd


@dataclass
class DriftStatus:
    """Result of a drift evaluation run."""

    drift_detected: bool
    recent_trades: int
    baseline_trades: int
    recent_win_rate: float
    baseline_win_rate: float
    win_rate_delta: float
    recent_avg_confidence: float
    baseline_avg_confidence: float
    recommended_min_ai_confidence: float
    risk_scale: float
    reason: str


class ModelDriftMonitor:
    """Monitor recent closed-trade performance for model decay."""

    def __init__(
        self,
        window_trades: int = 20,
        threshold: float = 0.20,
        min_trades: int = 10,
        confidence_floor: float = 0.65,
        risk_scale: float = 0.75,
    ) -> None:
        self.window_trades = max(1, int(window_trades))
        self.threshold = max(0.0, float(threshold))
        self.min_trades = max(1, int(min_trades))
        self.confidence_floor = min(0.95, max(0.0, float(confidence_floor)))
        self.risk_scale = min(1.0, max(0.1, float(risk_scale)))

    def _load_frame(
        self,
        trades: pd.DataFrame | Sequence[Mapping[str, object]] | None = None,
        csv_path: str = "trades_history.csv",
    ) -> pd.DataFrame:
        if trades is None:
            path = Path(csv_path)
            if not path.exists():
                return pd.DataFrame()
            try:
                return pd.read_csv(path)
            except Exception:
                return pd.DataFrame()

        if isinstance(trades, pd.DataFrame):
            return trades.copy()

        return pd.DataFrame(list(trades))

    @staticmethod
    def _to_float_series(series: pd.Series) -> pd.Series:
        values = pd.to_numeric(series.astype(str).str.replace("%", "", regex=False), errors="coerce")
        return values.astype(float)

    def evaluate(
        self,
        trades: pd.DataFrame | Sequence[Mapping[str, object]] | None = None,
        csv_path: str = "trades_history.csv",
    ) -> dict[str, object]:
        """Evaluate recent trade history and return a drift summary."""
        frame = self._load_frame(trades, csv_path=csv_path)
        if frame.empty or "side" not in frame.columns:
            status = DriftStatus(
                drift_detected=False,
                recent_trades=0,
                baseline_trades=0,
                recent_win_rate=0.0,
                baseline_win_rate=0.0,
                win_rate_delta=0.0,
                recent_avg_confidence=0.0,
                baseline_avg_confidence=0.0,
                recommended_min_ai_confidence=self.confidence_floor,
                risk_scale=1.0,
                reason="insufficient_data",
            )
            return asdict(status)

        closed = frame[frame["side"].astype(str).str.lower() == "sell"].copy()
        if closed.empty:
            status = DriftStatus(
                drift_detected=False,
                recent_trades=0,
                baseline_trades=0,
                recent_win_rate=0.0,
                baseline_win_rate=0.0,
                win_rate_delta=0.0,
                recent_avg_confidence=0.0,
                baseline_avg_confidence=0.0,
                recommended_min_ai_confidence=self.confidence_floor,
                risk_scale=1.0,
                reason="no_closed_trades",
            )
            return asdict(status)

        if "pnl_pct" not in closed.columns:
            closed["pnl_pct"] = 0.0

        closed["pnl_pct_num"] = self._to_float_series(closed["pnl_pct"]).fillna(0.0)

        if "ai_confidence" in closed.columns:
            closed["ai_confidence_num"] = self._to_float_series(closed["ai_confidence"]).fillna(0.0)
        else:
            closed["ai_confidence_num"] = 0.0

        if len(closed) < self.min_trades:
            status = DriftStatus(
                drift_detected=False,
                recent_trades=len(closed),
                baseline_trades=0,
                recent_win_rate=float((closed["pnl_pct_num"] > 0).mean() * 100.0),
                baseline_win_rate=0.0,
                win_rate_delta=0.0,
                recent_avg_confidence=float(closed["ai_confidence_num"].mean() if len(closed) else 0.0),
                baseline_avg_confidence=0.0,
                recommended_min_ai_confidence=self.confidence_floor,
                risk_scale=1.0,
                reason="insufficient_closed_trades",
            )
            return asdict(status)

        recent = closed.tail(self.window_trades)
        baseline = closed.iloc[:-len(recent)] if len(closed) > len(recent) else closed

        recent_win_rate = float((recent["pnl_pct_num"] > 0).mean())
        baseline_win_rate = float((baseline["pnl_pct_num"] > 0).mean()) if len(baseline) else recent_win_rate
        recent_avg_conf = float(recent["ai_confidence_num"].mean()) if len(recent) else 0.0
        baseline_avg_conf = float(baseline["ai_confidence_num"].mean()) if len(baseline) else recent_avg_conf

        win_rate_delta = baseline_win_rate - recent_win_rate
        confidence_delta = baseline_avg_conf - recent_avg_conf
        drift_detected = (
            len(recent) >= self.min_trades
            and win_rate_delta >= self.threshold
        ) or (
            len(recent) >= self.min_trades
            and confidence_delta >= self.threshold
        )

        if drift_detected:
            reason = "recent performance and confidence are below baseline"
            recommended_min_ai_confidence = min(0.95, max(self.confidence_floor, baseline_avg_conf + 0.05))
            risk_scale = self.risk_scale
        else:
            reason = "stable"
            recommended_min_ai_confidence = self.confidence_floor
            risk_scale = 1.0

        status = DriftStatus(
            drift_detected=drift_detected,
            recent_trades=len(recent),
            baseline_trades=len(baseline),
            recent_win_rate=recent_win_rate * 100.0,
            baseline_win_rate=baseline_win_rate * 100.0,
            win_rate_delta=win_rate_delta * 100.0,
            recent_avg_confidence=recent_avg_conf * 100.0,
            baseline_avg_confidence=baseline_avg_conf * 100.0,
            recommended_min_ai_confidence=recommended_min_ai_confidence,
            risk_scale=risk_scale,
            reason=reason,
        )
        return asdict(status)
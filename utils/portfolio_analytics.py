"""Portfolio-level correlation and heat analytics for risk gating."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import isfinite
from typing import Mapping, Sequence

import pandas as pd


@dataclass
class CorrelationGateDecision:
    """Correlation gate result for a candidate entry."""

    allowed: bool
    max_correlation: float
    correlated_symbol: str | None
    reason: str

    def to_dict(self) -> dict:
        return asdict(self)


class PortfolioRiskAnalyzer:
    """Compute portfolio heat and pairwise return correlation checks."""

    def __init__(
        self,
        correlation_threshold: float = 0.85,
        max_portfolio_heat_pct: float = 0.15,
        min_periods: int = 30,
        lookback_bars: int = 120,
        fallback_stop_pct: float = 0.03,
    ) -> None:
        self.correlation_threshold = max(0.0, min(1.0, float(correlation_threshold)))
        self.max_portfolio_heat_pct = max(0.0, float(max_portfolio_heat_pct))
        self.min_periods = max(5, int(min_periods))
        self.lookback_bars = max(self.min_periods, int(lookback_bars))
        self.fallback_stop_pct = max(0.001, min(0.5, float(fallback_stop_pct)))

    @staticmethod
    def _iter_positions(positions: Mapping[str, object] | Sequence[object]):
        if isinstance(positions, Mapping):
            return positions.items()
        return ((getattr(pos, "symbol", ""), pos) for pos in positions)

    @staticmethod
    def _position_active(position: object) -> bool:
        if isinstance(position, Mapping):
            return bool(position.get("active", False))
        return bool(getattr(position, "active", False))

    @staticmethod
    def _position_qty(position: object) -> float:
        if isinstance(position, Mapping):
            return float(position.get("quantity", position.get("size", 0.0)) or 0.0)
        return float(getattr(position, "quantity", getattr(position, "size", 0.0)) or 0.0)

    @staticmethod
    def _position_entry(position: object) -> float:
        if isinstance(position, Mapping):
            return float(position.get("entry_price", 0.0) or 0.0)
        return float(getattr(position, "entry_price", 0.0) or 0.0)

    @staticmethod
    def _position_stop(position: object) -> float:
        if isinstance(position, Mapping):
            if "trailing_stop" in position:
                return float(position.get("trailing_stop") or 0.0)
            return float(position.get("stop_loss", 0.0) or 0.0)
        trailing = getattr(position, "trailing_stop", None)
        if trailing is not None:
            return float(trailing or 0.0)
        return float(getattr(position, "stop_loss", 0.0) or 0.0)

    def position_risk_usd(self, position: object) -> float:
        """Estimate risk-at-stop in USD for one open long position."""
        if not self._position_active(position):
            return 0.0

        qty = self._position_qty(position)
        entry = self._position_entry(position)
        stop = self._position_stop(position)

        if qty <= 0 or entry <= 0 or not isfinite(entry):
            return 0.0

        if stop <= 0 or stop >= entry:
            stop = entry * (1.0 - self.fallback_stop_pct)

        risk_per_share = max(0.0, entry - stop)
        return risk_per_share * qty

    def portfolio_heat_pct(self, positions: Mapping[str, object] | Sequence[object], equity: float) -> float:
        """Return portfolio heat as fraction of equity (0.10 = 10%)."""
        eq = float(equity)
        if eq <= 0:
            return 0.0

        total_risk = 0.0
        for _, position in self._iter_positions(positions):
            total_risk += self.position_risk_usd(position)

        return max(0.0, total_risk / eq)

    def should_block_for_heat(self, positions: Mapping[str, object] | Sequence[object], equity: float) -> tuple[bool, float]:
        """Return whether heat limit is breached and current heat."""
        heat = self.portfolio_heat_pct(positions, equity)
        return heat >= self.max_portfolio_heat_pct, heat

    def correlation_matrix(self, price_frames: Mapping[str, pd.DataFrame]) -> pd.DataFrame:
        """Build return-correlation matrix from symbol -> bars DataFrames."""
        returns_map: dict[str, pd.Series] = {}

        for symbol, frame in price_frames.items():
            if frame is None or frame.empty or "close" not in frame:
                continue

            close = frame["close"].astype(float)
            returns = close.pct_change().dropna().tail(self.lookback_bars)
            if len(returns) < self.min_periods:
                continue
            returns_map[str(symbol).upper()] = returns

        if len(returns_map) < 2:
            return pd.DataFrame()

        returns_df = pd.DataFrame(returns_map).dropna(how="any")
        if len(returns_df) < self.min_periods:
            return pd.DataFrame()

        return returns_df.corr()

    def check_entry_correlation(
        self,
        candidate_symbol: str,
        open_symbols: Sequence[str],
        price_frames: Mapping[str, pd.DataFrame],
    ) -> CorrelationGateDecision:
        """Check candidate symbol against currently open symbols."""
        candidate = str(candidate_symbol).upper()
        active = [str(s).upper() for s in open_symbols if str(s).strip() and str(s).upper() != candidate]
        if not active:
            return CorrelationGateDecision(True, 0.0, None, "no_open_positions")

        matrix = self.correlation_matrix(price_frames)
        if matrix.empty or candidate not in matrix.index:
            return CorrelationGateDecision(True, 0.0, None, "insufficient_data")

        max_corr = 0.0
        worst_symbol = None
        for symbol in active:
            if symbol not in matrix.columns:
                continue
            corr = abs(float(matrix.loc[candidate, symbol]))
            if corr > max_corr:
                max_corr = corr
                worst_symbol = symbol

        if max_corr >= self.correlation_threshold:
            return CorrelationGateDecision(
                allowed=False,
                max_correlation=max_corr,
                correlated_symbol=worst_symbol,
                reason="correlation_threshold_exceeded",
            )

        return CorrelationGateDecision(
            allowed=True,
            max_correlation=max_corr,
            correlated_symbol=worst_symbol,
            reason="ok",
        )

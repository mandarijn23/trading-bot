"""Portfolio concentration monitoring for the stock bot."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from math import floor
from typing import Iterable, Mapping, Sequence


@dataclass
class ConcentrationStatus:
    """Result of a concentration check."""

    allowed: bool
    adjusted_quantity: int
    symbol_exposure_pct: float
    group_exposure_pct: float
    reason: str


class PortfolioConcentrationMonitor:
    """Cap exposure in a single symbol and in correlated symbol groups."""

    def __init__(
        self,
        max_symbol_exposure_pct: float = 0.20,
        max_group_exposure_pct: float = 0.45,
        correlated_groups: Sequence[Sequence[str]] | None = None,
    ) -> None:
        self.max_symbol_exposure_pct = max(0.0, float(max_symbol_exposure_pct))
        self.max_group_exposure_pct = max(0.0, float(max_group_exposure_pct))
        groups = correlated_groups or (("SPY", "QQQ", "VOO"),)
        self.correlated_groups = [tuple(sorted({str(symbol).upper() for symbol in group if str(symbol).strip()})) for group in groups]

    @staticmethod
    def _iter_positions(positions: Mapping[str, object] | Sequence[object]) -> Iterable[tuple[str, object]]:
        if isinstance(positions, Mapping):
            return positions.items()
        return ((getattr(position, "symbol", ""), position) for position in positions)

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
    def _position_price(position: object) -> float:
        if isinstance(position, Mapping):
            return float(position.get("entry_price", 0.0) or 0.0)
        return float(getattr(position, "entry_price", 0.0) or 0.0)

    def _open_position_value(self, position: object) -> float:
        if not self._position_active(position):
            return 0.0
        return self._position_qty(position) * self._position_price(position)

    def _current_exposure(self, positions: Mapping[str, object] | Sequence[object]) -> dict[str, float]:
        exposures: dict[str, float] = {}
        for symbol, position in self._iter_positions(positions):
            symbol_key = str(symbol).upper().strip()
            if not symbol_key:
                continue
            exposures[symbol_key] = exposures.get(symbol_key, 0.0) + self._open_position_value(position)
        return exposures

    def _group_for_symbol(self, symbol: str) -> tuple[str, ...] | None:
        symbol_key = str(symbol).upper().strip()
        for group in self.correlated_groups:
            if symbol_key in group:
                return group
        return None

    def limit_order(
        self,
        symbol: str,
        desired_quantity: int,
        price: float,
        positions: Mapping[str, object] | Sequence[object],
        equity: float,
    ) -> dict[str, object]:
        """Apply concentration caps and return an adjusted order size."""
        desired_quantity = max(0, int(desired_quantity))
        price = float(price)
        equity = float(equity)

        if desired_quantity <= 0 or price <= 0 or equity <= 0:
            status = ConcentrationStatus(
                allowed=False,
                adjusted_quantity=0,
                symbol_exposure_pct=0.0,
                group_exposure_pct=0.0,
                reason="invalid sizing inputs",
            )
            return asdict(status)

        exposures = self._current_exposure(positions)
        symbol_key = str(symbol).upper().strip()
        symbol_value = exposures.get(symbol_key, 0.0)
        symbol_budget = equity * self.max_symbol_exposure_pct
        symbol_remaining = max(0.0, symbol_budget - symbol_value)
        symbol_limit_qty = floor(symbol_remaining / price)

        group = self._group_for_symbol(symbol_key)
        group_value = 0.0
        group_limit_qty = desired_quantity
        if group is not None:
            group_value = sum(exposures.get(group_symbol, 0.0) for group_symbol in group)
            group_budget = equity * self.max_group_exposure_pct
            group_remaining = max(0.0, group_budget - group_value)
            group_limit_qty = floor(group_remaining / price)

        adjusted_quantity = min(desired_quantity, symbol_limit_qty, group_limit_qty)
        allowed = adjusted_quantity > 0

        if not allowed:
            if group is not None and group_value >= equity * self.max_group_exposure_pct:
                reason = f"group concentration cap reached for {','.join(group)}"
            elif symbol_value >= equity * self.max_symbol_exposure_pct:
                reason = f"symbol concentration cap reached for {symbol_key}"
            else:
                reason = "concentration limits blocked order"
        elif adjusted_quantity < desired_quantity:
            if group is not None and adjusted_quantity <= group_limit_qty < desired_quantity:
                reason = f"group cap trimmed order for {symbol_key}"
            else:
                reason = f"symbol cap trimmed order for {symbol_key}"
        else:
            reason = "within concentration limits"

        status = ConcentrationStatus(
            allowed=allowed,
            adjusted_quantity=int(adjusted_quantity),
            symbol_exposure_pct=(symbol_value / equity * 100.0) if equity > 0 else 0.0,
            group_exposure_pct=(group_value / equity * 100.0) if equity > 0 else 0.0,
            reason=reason,
        )
        return asdict(status)
"""Sector exposure analytics and entry-limit decisions."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Mapping, Sequence


DEFAULT_SYMBOL_TO_SECTOR: dict[str, str] = {
    # Broad indexes and sector ETFs.
    "SPY": "BROAD_MARKET",
    "VOO": "BROAD_MARKET",
    "VTI": "BROAD_MARKET",
    "QQQ": "TECH",
    "DIA": "INDUSTRIALS",
    "IWM": "SMALL_CAP",
    "XLK": "TECH",
    "XLC": "COMMUNICATION",
    "XLY": "CONSUMER_DISCRETIONARY",
    "XLP": "CONSUMER_STAPLES",
    "XLF": "FINANCIALS",
    "XLV": "HEALTHCARE",
    "XLI": "INDUSTRIALS",
    "XLE": "ENERGY",
    "XLRE": "REAL_ESTATE",
    "XLU": "UTILITIES",
    "XLB": "MATERIALS",
    "SMH": "TECH",
    "SOXX": "TECH",
    # Common large-cap names.
    "AAPL": "TECH",
    "MSFT": "TECH",
    "NVDA": "TECH",
    "AMD": "TECH",
    "AMZN": "CONSUMER_DISCRETIONARY",
    "TSLA": "CONSUMER_DISCRETIONARY",
    "GOOGL": "COMMUNICATION",
    "META": "COMMUNICATION",
    "JPM": "FINANCIALS",
    "BAC": "FINANCIALS",
    "XOM": "ENERGY",
    "CVX": "ENERGY",
    "JNJ": "HEALTHCARE",
    "UNH": "HEALTHCARE",
}


@dataclass
class SectorGateDecision:
    """Decision payload for a sector concentration check."""

    allowed: bool
    sector: str
    current_sector_pct: float
    projected_sector_pct: float
    max_sector_exposure_pct: float
    reason: str
    imbalance_sectors: dict[str, float] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


class SectorExposureAnalyzer:
    """Track sector allocations and block entries that breach caps."""

    def __init__(
        self,
        max_sector_exposure_pct: float = 0.40,
        imbalance_alert_pct: float = 0.30,
        symbol_to_sector: Mapping[str, str] | None = None,
    ) -> None:
        self.max_sector_exposure_pct = max(0.0, min(1.0, float(max_sector_exposure_pct)))
        self.imbalance_alert_pct = max(0.0, min(1.0, float(imbalance_alert_pct)))

        merged = dict(DEFAULT_SYMBOL_TO_SECTOR)
        if symbol_to_sector:
            merged.update({str(k).upper(): str(v).upper() for k, v in symbol_to_sector.items()})
        self.symbol_to_sector = merged

    @staticmethod
    def _iter_positions(positions: Mapping[str, object] | Sequence[object]):
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
    def _position_entry(position: object) -> float:
        if isinstance(position, Mapping):
            return float(position.get("entry_price", 0.0) or 0.0)
        return float(getattr(position, "entry_price", 0.0) or 0.0)

    def get_sector(self, symbol: str) -> str:
        """Return normalized sector label for a symbol."""
        key = str(symbol).strip().upper()
        if not key:
            return "UNKNOWN"
        return self.symbol_to_sector.get(key, "UNKNOWN")

    def sector_exposure_values(self, positions: Mapping[str, object] | Sequence[object]) -> dict[str, float]:
        """Aggregate open position notional values by sector."""
        exposure: dict[str, float] = {}
        for symbol, position in self._iter_positions(positions):
            if not self._position_active(position):
                continue

            qty = self._position_qty(position)
            entry = self._position_entry(position)
            if qty <= 0 or entry <= 0:
                continue

            sector = self.get_sector(str(symbol))
            exposure[sector] = exposure.get(sector, 0.0) + (qty * entry)

        return exposure

    def sector_exposure_pct(self, positions: Mapping[str, object] | Sequence[object], equity: float) -> dict[str, float]:
        """Return per-sector exposure as a fraction of equity."""
        eq = float(equity)
        if eq <= 0:
            return {}

        values = self.sector_exposure_values(positions)
        return {sector: (value / eq) for sector, value in values.items()}

    def sector_imbalance_alerts(self, positions: Mapping[str, object] | Sequence[object], equity: float) -> dict[str, float]:
        """Return sectors above configured imbalance alert threshold."""
        exposures = self.sector_exposure_pct(positions, equity)
        return {sector: pct for sector, pct in exposures.items() if pct >= self.imbalance_alert_pct}

    def check_entry_limit(
        self,
        candidate_symbol: str,
        desired_quantity: int,
        price: float,
        positions: Mapping[str, object] | Sequence[object],
        equity: float,
    ) -> SectorGateDecision:
        """Evaluate whether a candidate trade breaches sector concentration limits."""
        eq = float(equity)
        qty = max(0, int(desired_quantity))
        px = float(price)

        if eq <= 0:
            return SectorGateDecision(
                allowed=False,
                sector="UNKNOWN",
                current_sector_pct=0.0,
                projected_sector_pct=0.0,
                max_sector_exposure_pct=self.max_sector_exposure_pct,
                reason="invalid_equity",
                imbalance_sectors={},
            )

        if qty <= 0 or px <= 0:
            return SectorGateDecision(
                allowed=False,
                sector=self.get_sector(candidate_symbol),
                current_sector_pct=0.0,
                projected_sector_pct=0.0,
                max_sector_exposure_pct=self.max_sector_exposure_pct,
                reason="invalid_order_input",
                imbalance_sectors=self.sector_imbalance_alerts(positions, eq),
            )

        sector = self.get_sector(candidate_symbol)
        sector_values = self.sector_exposure_values(positions)
        current_value = float(sector_values.get(sector, 0.0))
        projected_value = current_value + (qty * px)

        current_pct = current_value / eq
        projected_pct = projected_value / eq

        simulated_values = dict(sector_values)
        simulated_values[sector] = projected_value
        imbalance = {
            name: (value / eq)
            for name, value in simulated_values.items()
            if (value / eq) >= self.imbalance_alert_pct
        }

        if projected_pct > self.max_sector_exposure_pct:
            reason = "sector_cap_exceeded"
            allowed = False
        else:
            reason = "ok"
            allowed = True

        return SectorGateDecision(
            allowed=allowed,
            sector=sector,
            current_sector_pct=current_pct,
            projected_sector_pct=projected_pct,
            max_sector_exposure_pct=self.max_sector_exposure_pct,
            reason=reason,
            imbalance_sectors=imbalance,
        )
"""Tests for sector exposure analytics and entry gate decisions."""

from __future__ import annotations

from types import SimpleNamespace

from sector_exposure import SectorExposureAnalyzer


def _position(qty: int, entry_price: float, active: bool = True):
    return SimpleNamespace(active=active, quantity=qty, entry_price=entry_price)


def test_sector_mapping_defaults_to_unknown_for_unmapped_symbol():
    analyzer = SectorExposureAnalyzer()

    assert analyzer.get_sector("AAPL") == "TECH"
    assert analyzer.get_sector("ZZZZ") == "UNKNOWN"


def test_sector_exposure_pct_aggregates_open_position_notional():
    analyzer = SectorExposureAnalyzer()
    positions = {
        "AAPL": _position(qty=2, entry_price=100.0),
        "XLE": _position(qty=1, entry_price=200.0),
        "MSFT": _position(qty=1, entry_price=100.0, active=False),
    }

    exposure = analyzer.sector_exposure_pct(positions, equity=1_000.0)

    assert exposure["TECH"] == 0.2
    assert exposure["ENERGY"] == 0.2
    assert "UNKNOWN" not in exposure


def test_check_entry_limit_blocks_when_projected_sector_exceeds_cap():
    analyzer = SectorExposureAnalyzer(max_sector_exposure_pct=0.40, imbalance_alert_pct=0.30)
    positions = {
        "AAPL": _position(qty=3, entry_price=100.0),
    }

    decision = analyzer.check_entry_limit(
        candidate_symbol="MSFT",
        desired_quantity=2,
        price=100.0,
        positions=positions,
        equity=1_000.0,
    )

    assert decision.allowed is False
    assert decision.reason == "sector_cap_exceeded"
    assert decision.sector == "TECH"
    assert decision.projected_sector_pct == 0.5


def test_check_entry_limit_reports_sector_imbalance_alerts():
    analyzer = SectorExposureAnalyzer(max_sector_exposure_pct=0.60, imbalance_alert_pct=0.30)
    positions = {
        "AAPL": _position(qty=4, entry_price=100.0),
    }

    decision = analyzer.check_entry_limit(
        candidate_symbol="XLE",
        desired_quantity=1,
        price=100.0,
        positions=positions,
        equity=1_000.0,
    )

    assert decision.allowed is True
    assert "TECH" in decision.imbalance_sectors
    assert decision.imbalance_sectors["TECH"] >= 0.30
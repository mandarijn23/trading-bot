"""Tests for external signal monitor behavior."""

from types import SimpleNamespace

from utils.external_signals import ExternalSignalMonitor, ExternalSignalSnapshot


def _config(**overrides):
    data = {
        "external_signals_enabled": True,
        "external_signal_cache_ttl": 300,
        "external_signal_timeout_sec": 1.0,
        "external_signal_min_confidence": 0.35,
        "external_sentiment_min": -0.35,
        "external_catalyst_min": 0.2,
        "external_event_risk_max": 0.85,
        "news_api_key": "",
        "twitter_bearer_token": "",
        "economic_calendar_api_key": "",
        "external_signal_file": "logs/does-not-exist.json",
    }
    data.update(overrides)
    return SimpleNamespace(**data)


def test_external_gate_disabled_allows():
    mon = ExternalSignalMonitor(_config(external_signals_enabled=False))
    snap = ExternalSignalSnapshot(symbol="SPY")
    allowed, reason = mon.allow_entry(snap)
    assert allowed is True
    assert "disabled" in reason


def test_external_gate_requires_confidence_to_block():
    mon = ExternalSignalMonitor(_config(external_signal_min_confidence=0.7))
    snap = ExternalSignalSnapshot(symbol="SPY", sentiment_score=-1.0, catalyst_score=0.0, event_risk=1.0, confidence=0.4)
    allowed, reason = mon.allow_entry(snap)
    assert allowed is True
    assert "confidence" in reason


def test_external_gate_blocks_high_event_risk():
    mon = ExternalSignalMonitor(_config())
    snap = ExternalSignalSnapshot(symbol="SPY", sentiment_score=0.0, catalyst_score=0.0, event_risk=0.95, confidence=0.9)
    allowed, reason = mon.allow_entry(snap)
    assert allowed is False
    assert "event risk" in reason


def test_external_gate_blocks_negative_sentiment_and_low_catalyst():
    mon = ExternalSignalMonitor(_config())
    snap = ExternalSignalSnapshot(symbol="SPY", sentiment_score=-0.8, catalyst_score=0.0, event_risk=0.2, confidence=0.9)
    allowed, reason = mon.allow_entry(snap)
    assert allowed is False
    assert "sentiment" in reason

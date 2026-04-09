"""Tests for RF feature extractor external-signal columns."""

import numpy as np
import pandas as pd

from models.ml_model_rf import FeatureExtractor


def _sample_df(n=260):
    closes = np.linspace(100, 110, n)
    return pd.DataFrame(
        {
            "timestamp": pd.date_range("2026-01-01", periods=n, freq="15min"),
            "open": closes * 0.99,
            "high": closes * 1.01,
            "low": closes * 0.98,
            "close": closes,
            "volume": np.ones(n) * 1_000_000,
        }
    )


def test_extract_features_includes_external_columns_when_present():
    df = _sample_df()
    df["external_sentiment"] = -0.2
    df["external_catalyst"] = 0.7
    df["external_event_risk"] = 0.4
    df["external_confidence"] = 0.9

    x = FeatureExtractor.extract_features(df)
    assert x is not None
    assert x.shape == (1, 16)
    assert abs(x[0, 12] - (-0.2)) < 1e-9
    assert abs(x[0, 13] - 0.7) < 1e-9
    assert abs(x[0, 14] - 0.4) < 1e-9
    assert abs(x[0, 15] - 0.9) < 1e-9


def test_extract_features_defaults_external_columns_to_neutral():
    df = _sample_df()
    x = FeatureExtractor.extract_features(df)
    assert x is not None
    assert x.shape == (1, 16)
    assert abs(x[0, 12]) < 1e-9
    assert abs(x[0, 13]) < 1e-9
    assert abs(x[0, 14]) < 1e-9
    assert abs(x[0, 15]) < 1e-9

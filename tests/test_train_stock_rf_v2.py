from __future__ import annotations

import numpy as np

from train_stock_rf_v2 import deduplicate_samples, split_dataset, train_test_overlap_ratio


def test_deduplicate_samples_removes_exact_duplicates():
    X = np.array([[1.0, 2.0], [1.0, 2.0], [3.0, 4.0]])
    y = np.array([1, 1, 0])

    X2, y2, dropped = deduplicate_samples(X, y)

    assert dropped == 1
    assert len(X2) == 2
    assert len(y2) == 2


def test_split_dataset_with_purge_gap_reduces_train_tail():
    X = np.arange(40).reshape(20, 2).astype(float)
    y = np.array([0, 1] * 10)

    X_train, X_test, y_train, y_test = split_dataset(X, y, holdout_ratio=0.2, purge_gap=3)

    # Split index is 16, train_end becomes 13 due to purge gap.
    assert len(X_train) == 13
    assert len(X_test) == 4
    assert len(y_train) == 13
    assert len(y_test) == 4


def test_train_test_overlap_ratio_detects_overlap():
    X_train = np.array([[1.0, 1.0], [2.0, 2.0]])
    X_test = np.array([[2.0, 2.0], [3.0, 3.0]])

    ratio = train_test_overlap_ratio(X_train, X_test)

    assert ratio == 0.5

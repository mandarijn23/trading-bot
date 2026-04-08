#!/usr/bin/env python3
"""Analyze training_history.jsonl for stability and trend quality."""

from __future__ import annotations

import json
from pathlib import Path


def main() -> int:
    path = Path("training_history.jsonl")
    if not path.exists():
        print("training_history.jsonl not found")
        return 1

    rows = []
    for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:
            continue

    if not rows:
        print("No valid rows in training_history.jsonl")
        return 1

    recent = rows[-8:]  # roughly last 8 hourly runs

    def avg(key: str) -> float:
        vals = [float(r.get(key, 0.0)) for r in recent]
        return sum(vals) / len(vals) if vals else 0.0

    avg_auc = avg("overall_auc")
    avg_f1 = avg("overall_f1")
    avg_acc = avg("overall_accuracy")
    avg_holdout = sum(int(r.get("total_test_samples", 0)) for r in recent) / len(recent)

    print("=== TRAINING HISTORY ANALYSIS ===")
    print(f"Total runs: {len(rows)}")
    print(f"Recent window size: {len(recent)}")
    print(f"Recent avg AUC: {avg_auc:.3f}")
    print(f"Recent avg F1: {avg_f1:.3f}")
    print(f"Recent avg Accuracy: {avg_acc:.3f}")
    print(f"Recent avg Holdout n: {avg_holdout:.1f}")

    if avg_holdout < 60:
        print("Status: LOW CONFIDENCE (need more holdout depth)")
    elif avg_auc >= 0.55 and avg_f1 >= 0.55:
        print("Status: IMPROVING EDGE")
    else:
        print("Status: NO CLEAR EDGE YET")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

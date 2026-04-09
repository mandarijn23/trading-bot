#!/usr/bin/env python3
"""One-command release validation for the stock trading bot.

Runs setup checks, config validation, focused tests, and optionally the
comparative backtest harness.
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path
from typing import List, Sequence, Tuple


ROOT = Path(__file__).resolve().parent.parent


def run_step(name: str, command: Sequence[str]) -> Tuple[str, bool]:
    print(f"\n=== {name} ===")
    print("$", " ".join(command))
    result = subprocess.run(command, cwd=ROOT)
    ok = result.returncode == 0
    print(f"[{ 'PASS' if ok else 'FAIL' }] {name}")
    return name, ok


def main() -> int:
    parser = argparse.ArgumentParser(description="Run release validation checks")
    parser.add_argument("--include-backtest", action="store_true", help="Run the comparative A/B/C backtest harness")
    parser.add_argument("--period", default="3mo", help="History period for the comparative backtest")
    parser.add_argument("--interval", default="1h", help="History interval for the comparative backtest")
    args = parser.parse_args()

    steps: List[Tuple[str, Sequence[str]]] = [
        ("Setup validation", [sys.executable, "tools/validate_setup.py"]),
        ("Config validation", [sys.executable, "cli.py", "validate-config"]),
        ("Preflight", [sys.executable, "cli.py", "preflight"]),
        (
            "Focused tests",
            [
                sys.executable,
                "-m",
                "pytest",
                "-q",
                "tests/test_external_signals.py",
                "tests/test_ml_model_rf_external.py",
                "tests/test_daily_performance_report.py",
                "tests/test_stock_bot_session.py",
                "tests/test_train_stock_rf_v2.py",
                "tests/test_strategy.py",
            ],
        ),
    ]

    if args.include_backtest:
        steps.append(
            (
                "Comparative backtest",
                [
                    sys.executable,
                    "tools/backtest_ab_tracks.py",
                    "--period",
                    args.period,
                    "--interval",
                    args.interval,
                ],
            )
        )

    results = [run_step(name, command) for name, command in steps]

    print("\n=== Validation Summary ===")
    for name, ok in results:
        print(f"{name}: {'PASS' if ok else 'FAIL'}")

    all_ok = all(ok for _, ok in results)
    if all_ok:
        print("\nRelease gate passed.")
        return 0

    print("\nRelease gate failed. Fix the failing step(s) before promoting.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

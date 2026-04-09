#!/usr/bin/env python3
"""
Paper Trading Preflight Checklist.

Validates environment, dependencies, configuration, and basic runtime smoke checks
before starting a paper-trading session.

Usage:
  python paper_launch_check.py
  python paper_launch_check.py --mode stocks
"""

from __future__ import annotations

import argparse
import importlib.util
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, List

import numpy as np
import pandas as pd


ROOT_DIR = Path(__file__).resolve().parent
for rel in ("core", "models", "strategies", "utils", "config"):
    p = str(ROOT_DIR / rel)
    if p not in sys.path:
        sys.path.insert(0, p)


@dataclass
class CheckResult:
    name: str
    ok: bool
    details: str


def _module_exists(module_name: str) -> bool:
    return importlib.util.find_spec(module_name) is not None


def _mode_from_env(requested: str) -> str:
    return "stocks"


def check_env_file(mode: str) -> CheckResult:
    env_path = Path(".env")
    if not env_path.exists():
        return CheckResult(".env file", False, "Missing .env file")

    content = env_path.read_text(encoding="utf-8", errors="ignore")
    required = ["ALPACA_API_KEY", "ALPACA_API_SECRET"]

    missing = [k for k in required if k not in content]
    if missing:
        return CheckResult(".env keys", False, f"Missing keys: {', '.join(missing)}")
    return CheckResult(".env keys", True, f"Found required keys for {mode}")


def check_dependencies(mode: str) -> CheckResult:
    common = ["pandas", "numpy", "pydantic", "pydantic_settings"]
    mode_deps = ["alpaca_trade_api"]
    missing = [m for m in common + mode_deps if not _module_exists(m)]
    if missing:
        return CheckResult("Dependencies", False, f"Missing: {', '.join(missing)}")
    return CheckResult("Dependencies", True, "All required packages installed")


def check_files(mode: str) -> CheckResult:
    files = ["strategies/strategy.py", "utils/risk.py", "utils/portfolio.py"]
    files.append("core/stock_bot.py")
    files.append("config/stock_config.py")
    missing = [f for f in files if not Path(f).exists()]
    if missing:
        return CheckResult("Required files", False, f"Missing: {', '.join(missing)}")
    return CheckResult("Required files", True, "Core files present")


def check_writable_outputs() -> CheckResult:
    try:
        p = Path("preflight_write_test.tmp")
        p.write_text("ok", encoding="utf-8")
        p.unlink(missing_ok=True)
        return CheckResult("Writable workspace", True, "Can write local files")
    except Exception as exc:
        return CheckResult("Writable workspace", False, f"Write failed: {exc}")


def check_strategy_smoke() -> CheckResult:
    try:
        from strategy import get_signal

        prices = np.linspace(100, 120, 260)
        df = pd.DataFrame(
            {
                "open": prices * 0.999,
                "high": prices * 1.002,
                "low": prices * 0.998,
                "close": prices,
                "volume": np.ones(len(prices)) * 1_000_000,
            }
        )
        sig = get_signal(df)
        if sig not in {"BUY", "HOLD"}:
            return CheckResult("Strategy smoke", False, f"Unexpected signal: {sig}")
        return CheckResult("Strategy smoke", True, f"Signal path OK ({sig})")
    except Exception as exc:
        return CheckResult("Strategy smoke", False, f"Failed: {exc}")


def check_config_load(mode: str) -> CheckResult:
    try:
        from stock_config import load_stock_config

        cfg = load_stock_config()
        details = f"symbols={len(cfg.symbols)}, paper={cfg.paper_trading}"
        return CheckResult("Config load", True, details)
    except Exception as exc:
        return CheckResult("Config load", False, f"Failed: {exc}")


def run_checks(mode: str) -> List[CheckResult]:
    checks: List[Callable[[], CheckResult]] = [
        lambda: check_env_file(mode),
        lambda: check_dependencies(mode),
        lambda: check_files(mode),
        check_writable_outputs,
        check_strategy_smoke,
        lambda: check_config_load(mode),
    ]
    return [fn() for fn in checks]


def main() -> int:
    parser = argparse.ArgumentParser(description="Paper-trading preflight checklist")
    parser.add_argument("--mode", choices=["stocks", "auto"], default="stocks")
    args = parser.parse_args()

    mode = _mode_from_env(args.mode)
    results = run_checks(mode)

    print("\n" + "=" * 64)
    print(f"  PAPER TRADING PREFLIGHT ({mode.upper()})")
    print("=" * 64)
    for r in results:
        status = "PASS" if r.ok else "FAIL"
        print(f"[{status}] {r.name}: {r.details}")

    failed = [r for r in results if not r.ok]
    print("-" * 64)
    if failed:
        print(f"Result: NOT READY ({len(failed)} failed checks)")
        print("Action: Fix failed items, then rerun preflight.")
        return 1

    print("Result: READY FOR PAPER TRADING")
    print("Action: Start bot in paper mode and monitor daily report.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

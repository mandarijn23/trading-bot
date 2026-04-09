#!/usr/bin/env python3
"""Backtest entrypoint (stock-only repository).

The legacy crypto backtester has been removed.
"""

import sys


def main() -> int:
    print("The legacy crypto backtester has been removed.")
    print("This repository is stock-only. Use paper trading with stock_bot.py and daily reports.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Compatibility wrapper for launching the stock bot from the repository root."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent
for rel in ("core", "models", "strategies", "utils", "config"):
    path = str(ROOT / rel)
    if path not in sys.path:
        sys.path.insert(0, path)

from core.stock_bot import *  # noqa: F401,F403
from core.stock_bot import main


if __name__ == "__main__":
    main()

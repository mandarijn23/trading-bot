"""Pytest path bootstrap for the repository's multi-folder module layout."""

from __future__ import annotations

import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

# Keep explicit order so test imports resolve to project modules consistently.
for rel in ("", "core", "config", "utils", "models", "strategies", "tools"):
    p = str(ROOT / rel) if rel else str(ROOT)
    if p not in sys.path:
        sys.path.insert(0, p)
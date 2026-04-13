"""SQLite store bootstrap for trade persistence."""

from __future__ import annotations

import sqlite3
from pathlib import Path


class TradeStore:
    """Manage SQLite connection lifecycle for trade records."""

    def __init__(self, db_path: str = "data/trades.db") -> None:
        self.db_path = Path(db_path)
        self.db_path.parent.mkdir(parents=True, exist_ok=True)

    def connect(self) -> sqlite3.Connection:
        """Create a configured SQLite connection."""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL;")
        conn.execute("PRAGMA synchronous=NORMAL;")
        return conn

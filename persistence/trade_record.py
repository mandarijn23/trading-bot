"""Trade persistence repository with query helpers and reconciliation."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Iterable, Mapping, Any

from persistence.trade_store import TradeStore


class TradeRecordRepository:
    """Repository for creating, updating, and querying trade records."""

    def __init__(self, store: TradeStore | None = None) -> None:
        self.store = store or TradeStore()
        self._ensure_schema()

    def _ensure_schema(self) -> None:
        schema = """
        CREATE TABLE IF NOT EXISTS trades (
            trade_id INTEGER PRIMARY KEY AUTOINCREMENT,
            symbol TEXT NOT NULL,
            entry_time TEXT NOT NULL,
            entry_price REAL NOT NULL,
            entry_size INTEGER NOT NULL,
            entry_side TEXT NOT NULL,
            strategy_name TEXT NOT NULL,
            signal_regime TEXT,
            exit_time TEXT,
            exit_price REAL,
            exit_size INTEGER,
            pnl REAL,
            pnl_pct REAL,
            fees REAL,
            exit_reason TEXT,
            days_held REAL,
            backtest_expected_pnl REAL,
            backtest_slippage_assumption REAL,
            actual_slippage REAL,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        );
        """

        indexes = [
            "CREATE INDEX IF NOT EXISTS idx_trades_symbol ON trades(symbol);",
            "CREATE INDEX IF NOT EXISTS idx_trades_strategy ON trades(strategy_name);",
            "CREATE INDEX IF NOT EXISTS idx_trades_entry_date ON trades(date(entry_time));",
            "CREATE INDEX IF NOT EXISTS idx_trades_regime ON trades(signal_regime);",
        ]

        with self.store.connect() as conn:
            conn.execute(schema)
            for stmt in indexes:
                conn.execute(stmt)
            conn.commit()

    @staticmethod
    def _to_iso(dt: datetime | str | None) -> str:
        if dt is None:
            return datetime.now(timezone.utc).isoformat()
        if isinstance(dt, datetime):
            return dt.isoformat()
        return str(dt)

    @staticmethod
    def _parse_iso(dt: str | None) -> datetime | None:
        if not dt:
            return None
        text = str(dt).replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            return None

    def record_entry(
        self,
        symbol: str,
        entry_price: float,
        entry_size: int,
        entry_side: str,
        strategy_name: str,
        signal_regime: str | None = None,
        entry_time: datetime | str | None = None,
        backtest_expected_pnl: float | None = None,
        backtest_slippage_assumption: float | None = None,
    ) -> int:
        """Insert a new entry leg and return its trade_id."""
        sql = """
        INSERT INTO trades (
            symbol, entry_time, entry_price, entry_size, entry_side,
            strategy_name, signal_regime, backtest_expected_pnl, backtest_slippage_assumption
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """

        with self.store.connect() as conn:
            cur = conn.execute(
                sql,
                (
                    str(symbol).upper(),
                    self._to_iso(entry_time),
                    float(entry_price),
                    int(entry_size),
                    str(entry_side).upper(),
                    str(strategy_name),
                    signal_regime,
                    backtest_expected_pnl,
                    backtest_slippage_assumption,
                ),
            )
            conn.commit()
            return int(cur.lastrowid)

    def record_exit(
        self,
        trade_id: int,
        exit_price: float,
        exit_size: int,
        exit_reason: str,
        fees: float = 0.0,
        exit_time: datetime | str | None = None,
        actual_slippage: float | None = None,
    ) -> dict[str, Any] | None:
        """Finalize a trade and compute pnl, pnl_pct and days held."""
        with self.store.connect() as conn:
            row = conn.execute(
                "SELECT entry_price, entry_size, entry_side, entry_time FROM trades WHERE trade_id = ?",
                (int(trade_id),),
            ).fetchone()
            if row is None:
                return None

            entry_price = float(row["entry_price"])
            entry_size = int(row["entry_size"])
            entry_side = str(row["entry_side"]).upper()
            entry_time_raw = str(row["entry_time"])
            exit_iso = self._to_iso(exit_time)
            size = max(0, int(exit_size))

            gross = (float(exit_price) - entry_price) * size
            if entry_side == "SELL":
                gross = -gross
            pnl = gross - float(fees)

            notional = entry_price * size if entry_price > 0 else 0.0
            pnl_pct = (pnl / notional * 100.0) if notional > 0 else 0.0

            days_held = None
            entry_dt = self._parse_iso(entry_time_raw)
            exit_dt = self._parse_iso(exit_iso)
            if entry_dt and exit_dt:
                days_held = (exit_dt - entry_dt).total_seconds() / 86400.0

            conn.execute(
                """
                UPDATE trades
                SET exit_time = ?, exit_price = ?, exit_size = ?, pnl = ?, pnl_pct = ?,
                    fees = ?, exit_reason = ?, days_held = ?, actual_slippage = ?
                WHERE trade_id = ?
                """,
                (
                    exit_iso,
                    float(exit_price),
                    size,
                    float(pnl),
                    float(pnl_pct),
                    float(fees),
                    str(exit_reason),
                    days_held,
                    actual_slippage,
                    int(trade_id),
                ),
            )
            conn.commit()

        return self.get_trade(int(trade_id))

    def get_trade(self, trade_id: int) -> dict[str, Any] | None:
        with self.store.connect() as conn:
            row = conn.execute("SELECT * FROM trades WHERE trade_id = ?", (int(trade_id),)).fetchone()
        return dict(row) if row else None

    def get_trades_by_symbol(
        self,
        symbol: str,
        since: str | None = None,
        limit: int = 1000,
    ) -> list[dict[str, Any]]:
        with self.store.connect() as conn:
            if since:
                rows = conn.execute(
                    """
                    SELECT * FROM trades
                    WHERE symbol = ? AND datetime(entry_time) >= datetime(?)
                    ORDER BY entry_time DESC
                    LIMIT ?
                    """,
                    (str(symbol).upper(), str(since), int(limit)),
                ).fetchall()
            else:
                rows = conn.execute(
                    "SELECT * FROM trades WHERE symbol = ? ORDER BY entry_time DESC LIMIT ?",
                    (str(symbol).upper(), int(limit)),
                ).fetchall()
        return [dict(r) for r in rows]

    def get_slippage_analysis(self, since: str | None = None) -> dict[str, Any]:
        """Aggregate slippage cost metrics from closed trades."""
        with self.store.connect() as conn:
            if since:
                rows = conn.execute(
                    """
                    SELECT entry_price, actual_slippage, backtest_slippage_assumption
                    FROM trades
                    WHERE actual_slippage IS NOT NULL
                      AND datetime(entry_time) >= datetime(?)
                    """,
                    (str(since),),
                ).fetchall()
            else:
                rows = conn.execute(
                    """
                    SELECT entry_price, actual_slippage, backtest_slippage_assumption
                    FROM trades
                    WHERE actual_slippage IS NOT NULL
                    """
                ).fetchall()

        if not rows:
            return {
                "sample_count": 0,
                "avg_slippage": 0.0,
                "avg_slippage_bps": 0.0,
                "total_slippage": 0.0,
                "total_adverse_slippage": 0.0,
                "total_favorable_slippage": 0.0,
                "assumed_total_slippage": 0.0,
                "slippage_variance": 0.0,
            }

        slippages = [float(r["actual_slippage"] or 0.0) for r in rows]
        entry_prices = [max(float(r["entry_price"] or 0.0), 1e-9) for r in rows]
        assumed = [float(r["backtest_slippage_assumption"] or 0.0) for r in rows]

        bps_values = [(s / p) * 10000.0 for s, p in zip(slippages, entry_prices)]
        total_slippage = sum(slippages)
        assumed_total = sum(assumed)

        return {
            "sample_count": len(rows),
            "avg_slippage": total_slippage / len(rows),
            "avg_slippage_bps": sum(bps_values) / len(rows),
            "total_slippage": total_slippage,
            "total_adverse_slippage": sum(s for s in slippages if s > 0),
            "total_favorable_slippage": sum(s for s in slippages if s < 0),
            "assumed_total_slippage": assumed_total,
            "slippage_variance": total_slippage - assumed_total,
        }

    def get_trades_by_date(self, start_date: str, end_date: str) -> list[dict[str, Any]]:
        with self.store.connect() as conn:
            rows = conn.execute(
                """
                SELECT * FROM trades
                WHERE date(entry_time) BETWEEN date(?) AND date(?)
                ORDER BY entry_time ASC
                """,
                (start_date, end_date),
            ).fetchall()
        return [dict(r) for r in rows]

    def get_daily_pnl(self) -> list[dict[str, Any]]:
        with self.store.connect() as conn:
            rows = conn.execute(
                """
                SELECT date(entry_time) AS day,
                       COUNT(*) AS trades,
                       SUM(COALESCE(pnl, 0)) AS pnl
                FROM trades
                GROUP BY date(entry_time)
                ORDER BY day ASC
                """
            ).fetchall()
        return [dict(r) for r in rows]

    def get_strategy_stats(self, strategy_name: str) -> dict[str, Any]:
        with self.store.connect() as conn:
            rows = conn.execute(
                """
                SELECT pnl
                FROM trades
                WHERE strategy_name = ? AND pnl IS NOT NULL
                """,
                (strategy_name,),
            ).fetchall()

        pnl_values = [float(r["pnl"]) for r in rows]
        total = len(pnl_values)
        wins = [p for p in pnl_values if p > 0]
        losses = [p for p in pnl_values if p <= 0]

        total_wins = sum(wins)
        total_losses_abs = abs(sum(losses))
        profit_factor = (total_wins / total_losses_abs) if total_losses_abs > 0 else (float("inf") if total_wins > 0 else 0.0)

        return {
            "strategy_name": strategy_name,
            "total_trades": total,
            "winning_trades": len(wins),
            "losing_trades": len(losses),
            "win_rate": (len(wins) / total * 100.0) if total > 0 else 0.0,
            "avg_win": (total_wins / len(wins)) if wins else 0.0,
            "avg_loss": (sum(losses) / len(losses)) if losses else 0.0,
            "profit_factor": profit_factor,
            "net_pnl": sum(pnl_values),
        }

    def reconcile_vs_backtest(self, expected_rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
        """Compare expected backtest outcomes to realized closed trades."""
        expected_by_trade_id: dict[int, dict[str, Any]] = {}
        for item in expected_rows:
            if "trade_id" not in item:
                continue
            expected_by_trade_id[int(item["trade_id"])] = {
                "expected_pnl": float(item.get("expected_pnl", item.get("backtest_expected_pnl", 0.0))),
                "expected_slippage": float(item.get("expected_slippage", item.get("backtest_slippage_assumption", 0.0))),
            }

        with self.store.connect() as conn:
            rows = conn.execute(
                "SELECT trade_id, pnl, actual_slippage FROM trades WHERE pnl IS NOT NULL"
            ).fetchall()

        total_variance = 0.0
        total_expected = 0.0
        slippage_variance = 0.0
        compared = 0

        for row in rows:
            trade_id = int(row["trade_id"])
            expected = expected_by_trade_id.get(trade_id)
            if expected is None:
                continue

            pnl = float(row["pnl"])
            actual_slippage = float(row["actual_slippage"] or 0.0)

            total_variance += (pnl - expected["expected_pnl"])
            total_expected += expected["expected_pnl"]
            slippage_variance += (actual_slippage - expected["expected_slippage"])
            compared += 1

        return {
            "compared_trades": compared,
            "total_expected_pnl": total_expected,
            "total_pnl_variance": total_variance,
            "avg_pnl_variance": (total_variance / compared) if compared > 0 else 0.0,
            "total_slippage_variance": slippage_variance,
            "avg_slippage_variance": (slippage_variance / compared) if compared > 0 else 0.0,
        }

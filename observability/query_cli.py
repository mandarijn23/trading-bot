"""Query CLI for trade persistence and observability analytics."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.append(str(ROOT_DIR))

from persistence.trade_record import TradeRecordRepository
from persistence.trade_store import TradeStore


def build_repo(db_path: str) -> TradeRecordRepository:
    return TradeRecordRepository(TradeStore(db_path))


def cmd_daily(repo: TradeRecordRepository, since: str | None = None, limit: int = 30) -> list[dict[str, Any]]:
    rows = repo.get_daily_pnl()
    if since:
        rows = [r for r in rows if str(r.get("day", "")) >= since]
    return rows[-max(1, int(limit)) :]


def cmd_strategy(repo: TradeRecordRepository, name: str) -> dict[str, Any]:
    return repo.get_strategy_stats(name)


def cmd_slippage(repo: TradeRecordRepository, since: str | None = None) -> dict[str, Any]:
    return repo.get_slippage_analysis(since=since)


def cmd_trades(
    repo: TradeRecordRepository,
    symbol: str,
    since: str | None = None,
    limit: int = 50,
) -> list[dict[str, Any]]:
    return repo.get_trades_by_symbol(symbol=symbol, since=since, limit=limit)


def _expected_rows_for_reconcile(repo: TradeRecordRepository, since: str | None = None) -> list[dict[str, Any]]:
    with repo.store.connect() as conn:
        if since:
            rows = conn.execute(
                """
                SELECT trade_id,
                       COALESCE(backtest_expected_pnl, 0) AS expected_pnl,
                       COALESCE(backtest_slippage_assumption, 0) AS expected_slippage
                FROM trades
                WHERE pnl IS NOT NULL AND datetime(entry_time) >= datetime(?)
                """,
                (str(since),),
            ).fetchall()
        else:
            rows = conn.execute(
                """
                SELECT trade_id,
                       COALESCE(backtest_expected_pnl, 0) AS expected_pnl,
                       COALESCE(backtest_slippage_assumption, 0) AS expected_slippage
                FROM trades
                WHERE pnl IS NOT NULL
                """
            ).fetchall()
    return [dict(r) for r in rows]


def cmd_reconcile(repo: TradeRecordRepository, since: str | None = None) -> dict[str, Any]:
    expected_rows = _expected_rows_for_reconcile(repo, since=since)
    summary = repo.reconcile_vs_backtest(expected_rows)
    summary["since"] = since
    return summary


def cmd_benchmark(
    repo: TradeRecordRepository,
    since: str | None = None,
    benchmark_symbols: list[str] | None = None,
) -> dict[str, Any]:
    symbols = [str(s).upper().strip() for s in (benchmark_symbols or ["SPY", "VTI"]) if str(s).strip()]
    if not symbols:
        symbols = ["SPY", "VTI"]
    return repo.get_monthly_benchmark_comparison(benchmark_symbols=symbols, since=since)


def _print_json(data: Any) -> None:
    print(json.dumps(data, indent=2, ensure_ascii=True))


def _print_rows(title: str, rows: list[dict[str, Any]], columns: list[str]) -> None:
    print(title)
    if not rows:
        print("(no rows)")
        return

    col_widths = {col: len(col) for col in columns}
    for row in rows:
        for col in columns:
            col_widths[col] = max(col_widths[col], len(str(row.get(col, ""))))

    header = " | ".join(col.ljust(col_widths[col]) for col in columns)
    separator = "-+-".join("-" * col_widths[col] for col in columns)
    print(header)
    print(separator)
    for row in rows:
        print(" | ".join(str(row.get(col, "")).ljust(col_widths[col]) for col in columns))


def _print_dict(title: str, data: dict[str, Any]) -> None:
    print(title)
    if not data:
        print("(empty)")
        return
    width = max(len(k) for k in data.keys())
    for key, value in data.items():
        print(f"{key.ljust(width)} : {value}")


def _validate_since(since: str | None) -> str | None:
    if since is None:
        return None
    text = str(since).strip()
    if not text:
        return None
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(f"Invalid ISO date/time for --since: {since}") from exc
    return text


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Query trade persistence and reconciliation metrics")
    parser.add_argument("--db", default="data/trades.db", help="Path to SQLite trades database")
    parser.add_argument("--json", action="store_true", help="Emit JSON output")

    sub = parser.add_subparsers(dest="command", required=True)

    p_daily = sub.add_parser("daily", help="Daily PnL summary")
    p_daily.add_argument("--since", default=None, help="ISO datetime/date lower bound")
    p_daily.add_argument("--limit", type=int, default=30, help="Max number of days")

    p_strategy = sub.add_parser("strategy", help="Strategy performance stats")
    p_strategy.add_argument("name", help="Strategy name")

    p_slippage = sub.add_parser("slippage", help="Slippage analysis")
    p_slippage.add_argument("--since", default=None, help="ISO datetime/date lower bound")

    p_trades = sub.add_parser("trades", help="Trades by symbol")
    p_trades.add_argument("symbol", help="Symbol (e.g. SPY)")
    p_trades.add_argument("--since", default=None, help="ISO datetime/date lower bound")
    p_trades.add_argument("--limit", type=int, default=50, help="Max rows")

    p_reconcile = sub.add_parser("reconcile", help="Backtest vs live variance summary")
    p_reconcile.add_argument("--since", default=None, help="ISO datetime/date lower bound")

    p_benchmark = sub.add_parser("benchmark", help="Monthly strategy returns vs benchmark symbols")
    p_benchmark.add_argument("--since", default=None, help="ISO datetime/date lower bound")
    p_benchmark.add_argument(
        "--symbols",
        default="SPY,VTI",
        help="Comma-separated benchmark symbols (default: SPY,VTI)",
    )

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    since = _validate_since(getattr(args, "since", None))
    repo = build_repo(args.db)

    if args.command == "daily":
        rows = cmd_daily(repo, since=since, limit=args.limit)
        if args.json:
            _print_json(rows)
        else:
            _print_rows("Daily PnL", rows, ["day", "trades", "pnl"])
        return 0

    if args.command == "strategy":
        data = cmd_strategy(repo, name=args.name)
        if args.json:
            _print_json(data)
        else:
            _print_dict(f"Strategy Stats: {args.name}", data)
        return 0

    if args.command == "slippage":
        data = cmd_slippage(repo, since=since)
        if args.json:
            _print_json(data)
        else:
            _print_dict("Slippage Summary", data)
        return 0

    if args.command == "trades":
        rows = cmd_trades(repo, symbol=args.symbol, since=since, limit=args.limit)
        if args.json:
            _print_json(rows)
        else:
            _print_rows(
                f"Trades: {args.symbol.upper()}",
                rows,
                ["trade_id", "symbol", "entry_time", "entry_price", "exit_price", "pnl", "exit_reason"],
            )
        return 0

    if args.command == "reconcile":
        data = cmd_reconcile(repo, since=since)
        if args.json:
            _print_json(data)
        else:
            _print_dict("Backtest vs Live Reconciliation", data)
        return 0

    if args.command == "benchmark":
        symbols = [s.strip().upper() for s in str(args.symbols).split(",") if s.strip()]
        data = cmd_benchmark(repo, since=since, benchmark_symbols=symbols)
        if args.json:
            _print_json(data)
        else:
            print("Benchmark Comparison")
            _print_dict("Summary", data.get("summary", {}))
            columns = ["month", "trades", "net_pnl", "strategy_return_pct"]
            for symbol in data.get("benchmark_symbols", symbols):
                columns.append(f"{symbol}_return_pct")
                columns.append(f"excess_vs_{symbol}_pct")
            _print_rows("Monthly Comparison", data.get("monthly", []), columns)
        return 0

    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

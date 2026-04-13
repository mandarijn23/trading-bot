#!/usr/bin/env python3
"""Generate a monthly tear sheet from persisted trades and benchmark data."""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

ROOT_DIR = Path(__file__).resolve().parents[1]
for rel in ("utils", "config", "core", "models", "strategies"):
    p = str(ROOT_DIR / rel)
    if p not in sys.path:
        sys.path.insert(0, p)

from persistence.trade_record import TradeRecordRepository
from persistence.trade_store import TradeStore


@dataclass
class MonthlyTearsheet:
    """Structured tear sheet payload for one calendar month."""

    month: str
    start_date: str
    end_date: str
    total_trades: int
    closed_trades: int
    wins: int
    losses: int
    win_rate: float
    net_pnl: float
    avg_pnl: float
    avg_win: float
    avg_loss: float
    profit_factor: float
    pnl_pct_on_notional: float
    max_drawdown: float
    best_trade: dict[str, Any] | None
    worst_trade: dict[str, Any] | None
    symbols: dict[str, dict[str, Any]]
    benchmark: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_month(month_text: str | None) -> tuple[date, date, str]:
    """Parse YYYY-MM into inclusive date bounds."""
    text = str(month_text or "").strip()
    if not text:
        today = datetime.now(timezone.utc).date()
        text = today.strftime("%Y-%m")

    try:
        year_text, month_value = text.split("-", 1)
        year = int(year_text)
        month = int(month_value)
        start = date(year, month, 1)
    except Exception as exc:
        raise ValueError(f"Invalid month value: {month_text!r}. Expected YYYY-MM.") from exc

    if month == 12:
        end = date(year + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(year, month + 1, 1) - timedelta(days=1)
    return start, end, text


def _pick_trade_timestamp(row: dict[str, Any]) -> datetime | None:
    for key in ("exit_time", "entry_time", "created_at"):
        raw = row.get(key)
        if not raw:
            continue
        text = str(raw).replace("Z", "+00:00")
        try:
            return datetime.fromisoformat(text)
        except ValueError:
            continue
    return None


def _compute_max_drawdown(pnl_values: Sequence[float]) -> float:
    """Return max drawdown in PnL units from a cumulative PnL curve."""
    peak = 0.0
    equity = 0.0
    max_dd = 0.0
    for pnl in pnl_values:
        equity += float(pnl)
        if equity > peak:
            peak = equity
        drawdown = equity - peak
        if drawdown < max_dd:
            max_dd = drawdown
    return max_dd


def _closed_trades_for_month(repo: TradeRecordRepository, start: date, end: date) -> list[dict[str, Any]]:
    rows = repo.get_trades_by_date(start.isoformat(), end.isoformat())
    closed = [row for row in rows if row.get("pnl") is not None]
    closed.sort(key=lambda row: _pick_trade_timestamp(row) or datetime.min.replace(tzinfo=timezone.utc))
    return closed


def _symbol_summary(trades: Iterable[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for row in trades:
        symbol = str(row.get("symbol", "UNKNOWN")).upper()
        grouped.setdefault(symbol, []).append(row)

    summary: dict[str, dict[str, Any]] = {}
    for symbol, rows in sorted(grouped.items()):
        pnls = [float(row.get("pnl") or 0.0) for row in rows]
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]
        notional = sum(float(row.get("entry_price") or 0.0) * float(row.get("entry_size") or 0.0) for row in rows)
        summary[symbol] = {
            "trades": len(rows),
            "wins": len(wins),
            "losses": len(losses),
            "win_rate": (len(wins) / len(rows) * 100.0) if rows else 0.0,
            "net_pnl": sum(pnls),
            "avg_pnl": (sum(pnls) / len(pnls)) if pnls else 0.0,
            "pnl_pct_on_notional": (sum(pnls) / notional * 100.0) if notional > 0 else 0.0,
        }
    return summary


def build_monthly_tearsheet(
    repo: TradeRecordRepository,
    month: str | None = None,
    benchmark_symbols: Sequence[str] = ("SPY", "VTI"),
) -> MonthlyTearsheet:
    """Build a structured tearsheet for one month."""
    start, end, month_text = parse_month(month)
    closed = _closed_trades_for_month(repo, start, end)

    pnls = [float(row.get("pnl") or 0.0) for row in closed]
    wins = [p for p in pnls if p > 0]
    losses = [p for p in pnls if p < 0]
    gross_wins = sum(wins)
    gross_losses = abs(sum(losses))
    notional = sum(float(row.get("entry_price") or 0.0) * float(row.get("entry_size") or 0.0) for row in closed)

    benchmark = repo.get_monthly_benchmark_comparison(benchmark_symbols=benchmark_symbols, since=start.isoformat())
    benchmark_month = None
    for row in benchmark.get("monthly", []):
        if row.get("month") == month_text:
            benchmark_month = row
            break

    sorted_by_pnl = sorted(closed, key=lambda row: float(row.get("pnl") or 0.0))
    worst_trade = sorted_by_pnl[0] if sorted_by_pnl else None
    best_trade = sorted_by_pnl[-1] if sorted_by_pnl else None

    benchmark_summary = {
        "benchmark_symbols": list(benchmark.get("benchmark_symbols", benchmark_symbols)),
        "summary": benchmark.get("summary", {}),
        "month": benchmark_month,
        "comparison": benchmark.get("monthly", []),
    }

    return MonthlyTearsheet(
        month=month_text,
        start_date=start.isoformat(),
        end_date=end.isoformat(),
        total_trades=len(rows := repo.get_trades_by_date(start.isoformat(), end.isoformat())),
        closed_trades=len(closed),
        wins=len(wins),
        losses=len(losses),
        win_rate=(len(wins) / len(closed) * 100.0) if closed else 0.0,
        net_pnl=sum(pnls),
        avg_pnl=(sum(pnls) / len(pnls)) if pnls else 0.0,
        avg_win=(gross_wins / len(wins)) if wins else 0.0,
        avg_loss=(-gross_losses / len(losses)) if losses else 0.0,
        profit_factor=(gross_wins / gross_losses) if gross_losses > 0 else (float("inf") if gross_wins > 0 else 0.0),
        pnl_pct_on_notional=(sum(pnls) / notional * 100.0) if notional > 0 else 0.0,
        max_drawdown=_compute_max_drawdown(pnls),
        best_trade=best_trade,
        worst_trade=worst_trade,
        symbols=_symbol_summary(closed),
        benchmark=benchmark_summary,
    )


def render_monthly_tearsheet(report: MonthlyTearsheet) -> str:
    """Render a markdown tear sheet."""
    lines: list[str] = []
    lines.append(f"# Monthly Tear Sheet - {report.month}")
    lines.append("")
    lines.append(f"Period: {report.start_date} to {report.end_date}")
    lines.append("")
    lines.append("## Summary")
    lines.append(f"- Total trades: {report.total_trades}")
    lines.append(f"- Closed trades: {report.closed_trades}")
    lines.append(f"- Wins / losses: {report.wins} / {report.losses}")
    lines.append(f"- Win rate: {report.win_rate:.1f}%")
    lines.append(f"- Net PnL: {report.net_pnl:+.2f}")
    lines.append(f"- Avg PnL / trade: {report.avg_pnl:+.2f}")
    lines.append(f"- Avg win / loss: {report.avg_win:+.2f} / {report.avg_loss:+.2f}")
    lines.append(f"- Profit factor: {report.profit_factor:.2f}" if report.profit_factor != float("inf") else "- Profit factor: inf")
    lines.append(f"- PnL on notional: {report.pnl_pct_on_notional:+.2f}%")
    lines.append(f"- Max drawdown: {report.max_drawdown:+.2f}")
    lines.append("")

    if report.best_trade:
        lines.append("## Best / Worst Trades")
        lines.append(
            f"- Best: {report.best_trade.get('symbol', 'N/A')} | pnl={float(report.best_trade.get('pnl') or 0.0):+.2f} | "
            f"reason={report.best_trade.get('exit_reason', '')}"
        )
        lines.append(
        f"- Worst: {report.worst_trade.get('symbol', 'N/A')} | pnl={float(report.worst_trade.get('pnl') or 0.0):+.2f} | "
            f"reason={report.worst_trade.get('exit_reason', '')}"
        )
        lines.append("")

    lines.append("## Symbol Breakdown")
    if report.symbols:
        lines.append("| Symbol | Trades | Win Rate | Net PnL | Avg PnL | PnL / Notional |")
        lines.append("| --- | ---: | ---: | ---: | ---: | ---: |")
        for symbol, stats in report.symbols.items():
            lines.append(
                f"| {symbol} | {stats['trades']} | {stats['win_rate']:.1f}% | {stats['net_pnl']:+.2f} | "
                f"{stats['avg_pnl']:+.2f} | {stats['pnl_pct_on_notional']:+.2f}% |"
            )
    else:
        lines.append("No closed trades in this month.")
    lines.append("")

    lines.append("## Benchmark Comparison")
    benchmark_month = report.benchmark.get("month") or {}
    benchmark_symbols = report.benchmark.get("benchmark_symbols", [])
    summary = report.benchmark.get("summary", {})
    if benchmark_month:
        lines.append("| Metric | Value |")
        lines.append("| --- | ---: |")
        lines.append(f"| Strategy return % | {float(benchmark_month.get('strategy_return_pct') or 0.0):+.2f}% |")
        for symbol in benchmark_symbols:
            ret_key = f"{symbol}_return_pct"
            excess_key = f"excess_vs_{symbol}_pct"
            benchmark_return = benchmark_month.get(ret_key)
            excess = benchmark_month.get(excess_key)
            lines.append(f"| {symbol} return % | {float(benchmark_return or 0.0):+.2f}% |")
            if excess is not None:
                lines.append(f"| Excess vs {symbol} % | {float(excess):+.2f}% |")
    else:
        lines.append("Benchmark data unavailable for this month.")

    if summary:
        lines.append("")
        lines.append("### Benchmark Summary")
        lines.append(f"- Months compared: {summary.get('months_compared', 0)}")
        for symbol in benchmark_symbols:
            lines.append(
                f"- Avg excess vs {symbol}: {float(summary.get(f'avg_excess_vs_{symbol}_pct', 0.0)):+.2f}%"
            )

    return "\n".join(lines).rstrip() + "\n"


def write_monthly_tearsheet(report: MonthlyTearsheet, output_path: Path) -> Path:
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(render_monthly_tearsheet(report), encoding="utf-8")
    return output_path


def build_repo(db_path: str) -> TradeRecordRepository:
    return TradeRecordRepository(TradeStore(db_path))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Generate a monthly tear sheet from persisted trade data")
    parser.add_argument("--db", default="data/trades.db", help="Path to SQLite trades database")
    parser.add_argument("--month", default=None, help="Target month in YYYY-MM format")
    parser.add_argument("--output", default=None, help="Output markdown path")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
    parser.add_argument(
        "--symbols",
        default="SPY,VTI",
        help="Comma-separated benchmark symbols to compare against",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    repo = build_repo(args.db)
    benchmark_symbols = [symbol.strip().upper() for symbol in str(args.symbols).split(",") if symbol.strip()]
    report = build_monthly_tearsheet(repo, month=args.month, benchmark_symbols=benchmark_symbols)

    if args.json:
        print(json.dumps(report.to_dict(), indent=2, default=str))
        return 0

    output_path = Path(args.output) if args.output else ROOT_DIR / "logs" / f"tearsheet_{report.month}.md"
    path = write_monthly_tearsheet(report, output_path)
    print(f"Saved tear sheet: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
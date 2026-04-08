#!/usr/bin/env python3
"""
Daily performance and strategy-decay report.

Reads trades_history.csv and compares recent behavior against baseline to flag
potential strategy decay.

Usage:
  python daily_performance_report.py
  python daily_performance_report.py --csv trades_history.csv --json
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, Tuple

import pandas as pd


def _parse_pnl_pct(value) -> float | None:
    if pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    s = str(value).strip()
    if not s:
        return None
    if s.endswith("%"):
        s = s[:-1]
    try:
        return float(s)
    except ValueError:
        return None


def load_closed_trades(csv_file: str) -> pd.DataFrame:
    path = Path(csv_file)
    if not path.exists():
        return pd.DataFrame()

    df = pd.read_csv(path)
    if "timestamp" not in df.columns or "side" not in df.columns:
        return pd.DataFrame()

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df[df["side"].astype(str).str.lower() == "sell"].copy()
    if "pnl_pct" in df.columns:
        df["pnl_pct_num"] = df["pnl_pct"].apply(_parse_pnl_pct)
    else:
        df["pnl_pct_num"] = None

    df = df.dropna(subset=["timestamp", "pnl_pct_num"]).copy()
    if df.empty:
        return df

    df["date"] = df["timestamp"].dt.date
    return df


def _stats(df: pd.DataFrame) -> Dict[str, float]:
    if df.empty:
        return {"trades": 0, "win_rate": 0.0, "pnl_total": 0.0, "pnl_per_trade": 0.0}

    pnl = df["pnl_pct_num"].astype(float)
    trades = len(pnl)
    wins = int((pnl > 0).sum())
    return {
        "trades": float(trades),
        "win_rate": (wins / trades) * 100.0 if trades else 0.0,
        "pnl_total": float(pnl.sum()),
        "pnl_per_trade": float(pnl.mean()) if trades else 0.0,
    }


def _slice_windows(df: pd.DataFrame, recent_days: int, baseline_days: int) -> Tuple[pd.DataFrame, pd.DataFrame]:
    if df.empty:
        return df, df

    last_ts = df["timestamp"].max()
    recent_start = last_ts - pd.Timedelta(days=recent_days)
    baseline_start = recent_start - pd.Timedelta(days=baseline_days)

    recent = df[df["timestamp"] >= recent_start].copy()
    baseline = df[(df["timestamp"] >= baseline_start) & (df["timestamp"] < recent_start)].copy()
    return recent, baseline


def evaluate_decay(recent: Dict[str, float], baseline: Dict[str, float]) -> Tuple[str, str]:
    if baseline["trades"] < 10 or recent["trades"] < 5:
        return "INSUFFICIENT_DATA", "Need at least baseline=10 and recent=5 trades"

    wr_drop = baseline["win_rate"] - recent["win_rate"]
    edge_drop = baseline["pnl_per_trade"] - recent["pnl_per_trade"]

    if wr_drop >= 12 or edge_drop >= 0.60:
        return "CRITICAL", f"Win rate drop {wr_drop:.1f} pts, edge drop {edge_drop:.2f}%/trade"
    if wr_drop >= 6 or edge_drop >= 0.30:
        return "WARNING", f"Win rate drop {wr_drop:.1f} pts, edge drop {edge_drop:.2f}%/trade"
    return "STABLE", f"Win rate delta {(-wr_drop):+.1f} pts, edge delta {(-edge_drop):+.2f}%/trade"


def build_report(df: pd.DataFrame) -> Dict:
    overall = _stats(df)
    recent_df, baseline_df = _slice_windows(df, recent_days=7, baseline_days=30)
    recent = _stats(recent_df)
    baseline = _stats(baseline_df)
    decay_level, decay_reason = evaluate_decay(recent, baseline)

    by_symbol = {}
    if not df.empty and "symbol" in df.columns:
        for symbol, group in df.groupby("symbol"):
            r_df, b_df = _slice_windows(group, recent_days=7, baseline_days=30)
            r = _stats(r_df)
            b = _stats(b_df)
            lvl, reason = evaluate_decay(r, b)
            by_symbol[str(symbol)] = {
                "recent": r,
                "baseline": b,
                "decay_level": lvl,
                "reason": reason,
            }

    return {
        "overall": overall,
        "recent_7d": recent,
        "baseline_30d": baseline,
        "decay_level": decay_level,
        "decay_reason": decay_reason,
        "symbols": by_symbol,
    }


def print_report(report: Dict) -> None:
    print("\n" + "=" * 64)
    print("  DAILY PERFORMANCE & DECAY REPORT")
    print("=" * 64)

    o = report["overall"]
    r = report["recent_7d"]
    b = report["baseline_30d"]
    print(f"Overall: trades={int(o['trades'])} win_rate={o['win_rate']:.1f}% pnl={o['pnl_total']:+.2f}%")
    print(f"Recent 7d: trades={int(r['trades'])} win_rate={r['win_rate']:.1f}% edge={r['pnl_per_trade']:+.2f}%/trade")
    print(f"Base 30d: trades={int(b['trades'])} win_rate={b['win_rate']:.1f}% edge={b['pnl_per_trade']:+.2f}%/trade")

    print("-" * 64)
    print(f"Decay status: {report['decay_level']}")
    print(f"Reason: {report['decay_reason']}")

    if report["symbols"]:
        print("-" * 64)
        print("By symbol:")
        for symbol, info in report["symbols"].items():
            rs = info["recent"]
            bs = info["baseline"]
            print(
                f"  {symbol}: {info['decay_level']} | "
                f"r7 wr={rs['win_rate']:.1f}% edge={rs['pnl_per_trade']:+.2f}% | "
                f"b30 wr={bs['win_rate']:.1f}% edge={bs['pnl_per_trade']:+.2f}%"
            )


def main() -> int:
    parser = argparse.ArgumentParser(description="Daily strategy-decay report")
    parser.add_argument("--csv", default="trades_history.csv", help="Trades csv path")
    parser.add_argument("--json", action="store_true", help="Print JSON")
    args = parser.parse_args()

    df = load_closed_trades(args.csv)
    if df.empty:
        print("No closed trades with parsable pnl_pct found. Report unavailable.")
        return 1

    report = build_report(df)
    if args.json:
        print(json.dumps(report, indent=2, default=str))
    else:
        print_report(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

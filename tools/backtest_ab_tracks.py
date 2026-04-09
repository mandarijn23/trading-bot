#!/usr/bin/env python3
"""A/B/C track backtest harness for stock bot strategy evolution.

Tracks:
- A: Technical baseline (BUY signal only)
- B: Baseline + external features present
- C: Baseline + external gate allow_entry()

This is a lightweight validation harness for relative comparison.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from typing import Dict, List
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import numpy as np
import pandas as pd

from stock_config import load_stock_config
from external_signals import ExternalSignalMonitor
from strategy import get_signal_enhanced

try:
    import yfinance as yf
except ImportError:
    yf = None


@dataclass
class TrackResult:
    name: str
    trades: int
    win_rate: float
    expectancy_pct: float
    pnl_total_pct: float


def _fetch(symbol: str, period: str, interval: str) -> pd.DataFrame:
    if yf is None:
        raise RuntimeError("yfinance is required for backtest_ab_tracks.py")

    df = yf.download(symbol, period=period, interval=interval, progress=False, auto_adjust=False, threads=False)
    if df is None or df.empty:
        return pd.DataFrame()

    df = df.reset_index()
    if hasattr(df.columns, "tolist"):
        df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns.tolist()]

    rename_map = {
        "Date": "timestamp",
        "Datetime": "timestamp",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    }
    df = df.rename(columns=rename_map)
    needed = ["timestamp", "open", "high", "low", "close", "volume"]
    if not all(col in df.columns for col in needed):
        return pd.DataFrame()

    out = df[needed].dropna().copy()
    for col in ["open", "high", "low", "close", "volume"]:
        out[col] = out[col].astype(float)
    out["timestamp"] = pd.to_datetime(out["timestamp"], errors="coerce")
    return out.dropna(subset=["timestamp"]).reset_index(drop=True)


def _simulate_track(df: pd.DataFrame, symbol: str, monitor: ExternalSignalMonitor, track: str) -> TrackResult:
    rets: List[float] = []
    lookahead = 4

    ext = monitor.get_snapshot(symbol)

    for i in range(220, len(df) - lookahead):
        window = df.iloc[: i + 1]
        signal, _details = get_signal_enhanced(window, rsi_period=14, oversold=35, overbought=65)
        if signal != "BUY":
            continue

        if track == "B":
            if ext.confidence <= 0:
                continue

        if track == "C":
            allowed, _ = monitor.allow_entry(ext)
            if not allowed:
                continue

        entry = float(df.iloc[i]["close"])
        exit_price = float(df.iloc[i + lookahead]["close"])
        ret_pct = ((exit_price - entry) / max(entry, 1e-9)) * 100.0
        rets.append(ret_pct)

    if not rets:
        return TrackResult(name=track, trades=0, win_rate=0.0, expectancy_pct=0.0, pnl_total_pct=0.0)

    arr = np.asarray(rets)
    trades = int(len(arr))
    wins = int((arr > 0).sum())
    win_rate = (wins / trades) * 100.0
    expectancy = float(arr.mean())
    pnl_total = float(arr.sum())
    return TrackResult(name=track, trades=trades, win_rate=win_rate, expectancy_pct=expectancy, pnl_total_pct=pnl_total)


def main() -> int:
    parser = argparse.ArgumentParser(description="Run A/B/C track backtest for strategy comparison")
    parser.add_argument("--symbols", nargs="*", help="Override symbols from config")
    parser.add_argument("--period", default="6mo", help="History period (yfinance format)")
    parser.add_argument("--interval", default="1h", help="History interval (yfinance format)")
    args = parser.parse_args()

    if yf is None:
        print("yfinance not installed; comparative backtest skipped.")
        return 0

    cfg = load_stock_config()
    symbols = args.symbols or list(cfg.symbols)
    monitor = ExternalSignalMonitor(cfg)

    print("=== A/B/C Track Backtest ===")
    all_results: Dict[str, List[TrackResult]] = {"A": [], "B": [], "C": []}

    for symbol in symbols:
        df = _fetch(symbol, period=args.period, interval=args.interval)
        if df.empty or len(df) < 260:
            print(f"{symbol}: skipped (insufficient bars)")
            continue

        print(f"{symbol}: bars={len(df)}")
        for track in ("A", "B", "C"):
            result = _simulate_track(df, symbol, monitor, track)
            all_results[track].append(result)

    print("\n--- Aggregated ---")
    for track in ("A", "B", "C"):
        rows = all_results[track]
        if not rows:
            print(f"Track {track}: no results")
            continue

        trades = sum(r.trades for r in rows)
        wins_weighted = sum((r.win_rate / 100.0) * r.trades for r in rows)
        wr = (wins_weighted / trades * 100.0) if trades else 0.0
        expectancy = float(np.mean([r.expectancy_pct for r in rows])) if rows else 0.0
        pnl_total = sum(r.pnl_total_pct for r in rows)
        print(f"Track {track}: trades={trades} win_rate={wr:.1f}% expectancy={expectancy:+.3f}% pnl_total={pnl_total:+.2f}%")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

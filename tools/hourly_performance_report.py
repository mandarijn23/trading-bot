#!/usr/bin/env python3
"""Hourly performance reporting using local-rendered Discord dashboards only."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import pandas as pd

ROOT_DIR = Path(__file__).resolve().parents[1]
for rel in ("utils", "config", "core", "models", "strategies"):
    p = str(ROOT_DIR / rel)
    if p not in sys.path:
        sys.path.insert(0, p)

from discord_alerts import DiscordAlerts


def _parse_pnl_pct(value) -> float | None:
    if pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    if text.endswith("%"):
        text = text[:-1]
    try:
        return float(text)
    except ValueError:
        return None


def load_closed_trades(csv_path: Path) -> pd.DataFrame:
    if not csv_path.exists():
        return pd.DataFrame()

    df = pd.read_csv(csv_path)
    if df.empty or "timestamp" not in df.columns:
        return pd.DataFrame()

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).copy()
    df = df.sort_values("timestamp").reset_index(drop=True)

    if "pnl_pct" in df.columns:
        df["pnl_pct_num"] = df["pnl_pct"].apply(_parse_pnl_pct)
    elif "pnl_pct_num" in df.columns:
        df["pnl_pct_num"] = df["pnl_pct_num"].apply(_parse_pnl_pct)
    else:
        df["pnl_pct_num"] = None

    return df


def calculate_metrics(df: pd.DataFrame) -> dict:
    if df.empty:
        return {
            "total_trades": 0,
            "win_count": 0,
            "loss_count": 0,
            "win_pct": 0,
            "avg_win": 0,
            "avg_loss": 0,
            "total_pnl_pct": 0,
        }

    sell_df = df[df["side"].astype(str).str.lower().isin(["sell", "exit"])].copy()
    if sell_df.empty:
        return {
            "total_trades": len(df),
            "win_count": 0,
            "loss_count": 0,
            "win_pct": 0,
            "avg_win": 0,
            "avg_loss": 0,
            "total_pnl_pct": 0,
        }

    sell_df = sell_df.dropna(subset=["pnl_pct_num"]).copy()
    wins = sell_df[sell_df["pnl_pct_num"] > 0]
    losses = sell_df[sell_df["pnl_pct_num"] < 0]

    win_count = len(wins)
    loss_count = len(losses)
    total_closed = win_count + loss_count

    return {
        "total_trades": len(df),
        "win_count": win_count,
        "loss_count": loss_count,
        "win_pct": (win_count / total_closed * 100) if total_closed > 0 else 0,
        "avg_win": float(wins["pnl_pct_num"].mean()) if len(wins) else 0.0,
        "avg_loss": float(losses["pnl_pct_num"].mean()) if len(losses) else 0.0,
        "total_pnl_pct": float(sell_df["pnl_pct_num"].sum()) if not sell_df.empty else 0.0,
    }


def _build_chart_panels(df: pd.DataFrame) -> list[tuple[str, list[float]]]:
    sell_df = df[df["side"].astype(str).str.lower().isin(["sell", "exit"])].copy()
    pnl_series = sell_df["pnl_pct_num"].fillna(0.0).astype(float).tolist()
    if not pnl_series:
        pnl_series = [0.0]

    cumulative = pd.Series(pnl_series).cumsum().astype(float).tolist()

    rolling_win = []
    window = 5
    for i in range(len(pnl_series)):
        segment = pnl_series[max(0, i - window + 1): i + 1]
        wins = sum(1 for x in segment if x > 0)
        rolling_win.append((wins / len(segment) * 100.0) if segment else 0.0)

    if not sell_df.empty:
        daily_counts = (
            sell_df.groupby(sell_df["timestamp"].dt.date)
            .size()
            .astype(float)
            .tolist()
        )
    else:
        daily_counts = [0.0]

    return [
        ("Trade PnL %", pnl_series[-120:]),
        ("Cumulative PnL %", cumulative[-120:]),
        ("Rolling Win Rate %", rolling_win[-120:]),
        ("Daily Closed Trades", daily_counts[-60:]),
    ]


def send_performance_report_to_discord(discord: DiscordAlerts, metrics: dict, df: pd.DataFrame) -> bool:
    fields = {
        "Total Trades": metrics["total_trades"],
        "Wins": f"{metrics['win_count']} ({metrics['win_pct']:.1f}%)",
        "Losses": metrics["loss_count"],
        "Avg Win": f"{metrics['avg_win']:.2f}%",
        "Avg Loss": f"{metrics['avg_loss']:.2f}%",
        "Total PnL": f"{metrics['total_pnl_pct']:+.2f}%",
    }

    color = 3066993 if metrics["total_pnl_pct"] >= 0 else 15158332
    mention_text = getattr(discord, "graph_mention", "").strip()
    panels = _build_chart_panels(df)

    return discord.send_dashboard(
        title="Hourly Trading Performance Dashboard",
        summary_fields=fields,
        chart_panels=panels,
        color=color,
        description="Local dashboard image report.",
        mention_text=mention_text,
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate and send hourly performance report")
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path(ROOT_DIR) / "trades_history.csv",
        help="Path to trades_history.csv",
    )
    args = parser.parse_args()

    df = load_closed_trades(args.csv)
    if df.empty:
        print("No trades found in CSV")
        return 1

    metrics = calculate_metrics(df)
    print(f"Metrics: {metrics['total_trades']} trades, {metrics['win_pct']:.1f}% win rate")

    discord = DiscordAlerts()
    if not discord.enabled:
        print("Discord not configured")
        return 1

    success = send_performance_report_to_discord(discord, metrics, df)
    if success:
        print("Performance report sent to Discord")
        return 0

    print("Failed to send report")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

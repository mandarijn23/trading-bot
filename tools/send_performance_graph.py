#!/usr/bin/env python3
"""Generate a trading performance graph and optionally send it to Discord.

This script uses QuickChart (chart rendering API) to avoid local plotting dependencies.
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC
from datetime import datetime
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote

import pandas as pd
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

ROOT_DIR = Path(__file__).resolve().parents[1]
for rel in ("utils", "config", "core", "models", "strategies"):
    p = str(ROOT_DIR / rel)
    if p not in sys.path:
        sys.path.insert(0, p)

from discord_alerts import discord  # noqa: E402


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
    if "timestamp" not in df.columns or "side" not in df.columns:
        return pd.DataFrame()

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df[df["side"].astype(str).str.lower() == "sell"].copy()
    if df.empty:
        return df

    if "pnl_pct" in df.columns:
        df["pnl_pct_num"] = df["pnl_pct"].apply(_parse_pnl_pct)
    else:
        df["pnl_pct_num"] = None

    df = df.dropna(subset=["timestamp", "pnl_pct_num"]).copy()
    if df.empty:
        return df

    df["date"] = df["timestamp"].dt.date
    return df


def summarize_daily(df: pd.DataFrame, days: int) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["date", "daily_pnl", "cum_pnl"])

    daily = (
        df.groupby("date", as_index=False)["pnl_pct_num"]
        .sum()
        .rename(columns={"pnl_pct_num": "daily_pnl"})
        .sort_values("date")
    )

    if len(daily) > days:
        daily = daily.tail(days).copy()

    daily["cum_pnl"] = daily["daily_pnl"].cumsum()
    daily["date_str"] = daily["date"].astype(str)
    return daily


def empty_daily_window(days: int) -> pd.DataFrame:
    """Build a zeroed day window when no closed trades exist yet."""
    today = datetime.now(UTC).date()
    count = max(1, days)
    rows = []
    for i in range(count - 1, -1, -1):
        d = today - timedelta(days=i)
        rows.append({"date": d, "daily_pnl": 0.0, "cum_pnl": 0.0, "date_str": str(d)})
    return pd.DataFrame(rows)


def build_chart_config(daily: pd.DataFrame) -> dict:
    labels = daily["date_str"].tolist()
    daily_pnl = [round(float(v), 3) for v in daily["daily_pnl"].tolist()]
    cum_pnl = [round(float(v), 3) for v in daily["cum_pnl"].tolist()]

    return {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "label": "Daily PnL %",
                    "data": daily_pnl,
                    "borderColor": "rgba(24,119,242,1)",
                    "backgroundColor": "rgba(24,119,242,0.2)",
                    "fill": False,
                    "lineTension": 0.2,
                },
                {
                    "label": "Cumulative PnL %",
                    "data": cum_pnl,
                    "borderColor": "rgba(0,153,102,1)",
                    "backgroundColor": "rgba(0,153,102,0.2)",
                    "fill": False,
                    "lineTension": 0.2,
                },
            ],
        },
        "options": {
            "title": {"display": True, "text": "Trading Test Performance"},
            "legend": {"display": True},
            "scales": {
                "yAxes": [{"ticks": {"beginAtZero": True}}],
            },
        },
    }


def render_chart_png(chart_config: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(chart_config, separators=(",", ":"))
    url = (
        "https://quickchart.io/chart?"
        f"w=1280&h=720&devicePixelRatio=2&format=png&backgroundColor=white&c={quote(payload)}"
    )

    retry = Retry(
        total=3,
        backoff_factor=0.8,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=frozenset(["GET"]),
        raise_on_status=False,
    )
    session = requests.Session()
    session.mount("https://", HTTPAdapter(max_retries=retry))

    response = session.get(url, timeout=20)
    response.raise_for_status()
    output_path.write_bytes(response.content)


def load_profile_state(state_file: Path) -> tuple[str, str]:
    if not state_file.exists():
        return "unknown", "unknown"

    state = {}
    for line in state_file.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        k, v = line.split("=", 1)
        state[k.strip()] = v.strip()

    cycle_day = state.get("CYCLE_DAY", "unknown")
    if cycle_day in {"1", "2"}:
        profile = "aggressive"
    elif cycle_day in {"3", "4"}:
        profile = "normal"
    else:
        profile = "unknown"
    return cycle_day, profile


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate and send multi-day performance graph")
    parser.add_argument("--csv", default="trades_history.csv", help="Path to trades csv")
    parser.add_argument("--days", type=int, default=14, help="Number of recent days to include")
    parser.add_argument("--output", default="logs/performance_graph.png", help="Output chart image path")
    parser.add_argument("--no-discord", action="store_true", help="Do not send to Discord")
    args = parser.parse_args()

    csv_path = Path(args.csv)
    output_path = Path(args.output)

    df = load_closed_trades(csv_path)
    has_closed_trades = not df.empty

    if has_closed_trades:
        daily = summarize_daily(df, max(1, args.days))
        if daily.empty:
            daily = empty_daily_window(max(1, args.days))
            has_closed_trades = False
    else:
        daily = empty_daily_window(max(1, args.days))

    render_chart_png(build_chart_config(daily), output_path)
    print(f"Saved graph: {output_path}")

    total_trades = len(df) if has_closed_trades else 0
    total_pnl = float(daily["daily_pnl"].sum())
    last_day = str(daily["date"].iloc[-1])
    cycle_day, profile = load_profile_state(Path("logs/profile_cycle_state.env"))

    if not args.no_discord:
        if not discord.enabled:
            print("Discord disabled; set DISCORD_WEBHOOK_URL to send graph.")
            return 0

        sent = discord.send_file(
            "Stock Bot Multi-Day Test Graph",
            {
                "Window": f"{len(daily)} trading day(s)",
                "Closed Trades": total_trades,
                "Cumulative PnL": f"{total_pnl:+.2f}%",
                "Data Status": "closed trades" if has_closed_trades else "no closed trades yet",
                "Cycle": f"day {cycle_day} ({profile})",
                "Last Day": last_day,
                "Generated": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
            },
            str(output_path),
            filename=output_path.name,
        )
        print(f"Discord graph sent: {sent}")
    else:
        print("Discord disabled; graph generated locally only.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

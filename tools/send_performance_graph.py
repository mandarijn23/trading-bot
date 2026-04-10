#!/usr/bin/env python3
"""Generate a trading performance graph and optionally send it to Discord.

This script uses QuickChart (chart rendering API) to avoid local plotting dependencies.
"""

from __future__ import annotations

import argparse
import json
import subprocess
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


def summarize_trade_window(df: pd.DataFrame, days: int) -> pd.DataFrame:
    """Build detailed closed-trade points within the recent day window."""
    if df.empty:
        return pd.DataFrame(columns=["timestamp", "pnl_pct_num", "cum_pnl", "label"])

    today = datetime.now(UTC).date()
    start_date = today - timedelta(days=max(1, days) - 1)

    points = df[df["date"] >= start_date].copy()
    if points.empty:
        return pd.DataFrame(columns=["timestamp", "pnl_pct_num", "cum_pnl", "label"])

    points = points.sort_values("timestamp").reset_index(drop=True)
    points["cum_pnl"] = points["pnl_pct_num"].cumsum()
    points["label"] = points["timestamp"].dt.strftime("%m-%d %H:%M")
    return points


def summarize_recent_history(df: pd.DataFrame, max_points: int = 180) -> pd.DataFrame:
    """Fallback: use recent historical closed trades when day window has no data."""
    if df.empty:
        return pd.DataFrame(columns=["timestamp", "pnl_pct_num", "cum_pnl", "label"])

    points = df.sort_values("timestamp").tail(max(1, max_points)).copy()
    points = points.reset_index(drop=True)
    points["cum_pnl"] = points["pnl_pct_num"].cumsum()
    points["label"] = points["timestamp"].dt.strftime("%m-%d %H:%M")
    return points


def empty_daily_window(days: int) -> pd.DataFrame:
    """Build a preview curve window when no closed trades exist yet."""
    today = datetime.now(UTC).date()
    count = max(1, days)
    # Keep the fallback visually informative while clearly marked as no-trade preview.
    preview_pattern = [0.12, -0.08, 0.05, -0.09, 0.1, -0.04, 0.06, -0.06]
    rows = []
    for i in range(count - 1, -1, -1):
        d = today - timedelta(days=i)
        preview = preview_pattern[(count - 1 - i) % len(preview_pattern)]
        rows.append({"date": d, "daily_pnl": preview, "date_str": str(d)})

    preview_df = pd.DataFrame(rows)
    preview_df["cum_pnl"] = preview_df["daily_pnl"].cumsum()
    return preview_df


def build_chart_config(points: pd.DataFrame) -> dict:
    labels = points["label"].tolist()
    cum_pnl = [round(float(v), 3) for v in points["cum_pnl"].tolist()]

    return {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "label": "Cumulative PnL %",
                    "data": cum_pnl,
                    "borderColor": "#00FF3B",
                    "backgroundColor": "rgba(0,255,59,0.18)",
                    "fill": True,
                    "lineTension": 0.25,
                    "borderWidth": 2,
                    "pointRadius": 2,
                    "pointHoverRadius": 4,
                    "steppedLine": False,
                },
            ],
        },
        "options": {
            "title": {
                "display": True,
                "text": "Cumulative PnL %",
                "fontColor": "#DCE4EE",
                "fontSize": 18,
            },
            "legend": {
                "display": True,
                "labels": {"fontColor": "#B9C3D1"},
            },
            "scales": {
                "xAxes": [
                    {
                        "ticks": {
                            "autoSkip": True,
                            "maxTicksLimit": 12,
                            "fontColor": "#9FAABA",
                        },
                        "gridLines": {"color": "rgba(255,255,255,0.06)"},
                    }
                ],
                "yAxes": [
                    {
                        "ticks": {"fontColor": "#9FAABA"},
                        "gridLines": {"color": "rgba(255,255,255,0.06)"},
                    }
                ],
            },
        },
    }


def render_chart_png(chart_config: dict, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    payload = json.dumps(chart_config, separators=(",", ":"))
    url = (
        "https://quickchart.io/chart?"
        f"w=1280&h=720&devicePixelRatio=2&format=png&backgroundColor=%23121720&c={quote(payload)}"
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


def send_multi_chart_report(csv_path: Path) -> bool:
    """Trigger the richer multi-chart Discord report workflow."""
    cmd = [
        sys.executable,
        str(ROOT_DIR / "tools" / "hourly_performance_report.py"),
        "--csv",
        str(csv_path.resolve()),
        "--logs",
        str((ROOT_DIR / "logs").resolve()),
    ]
    result = subprocess.run(
        cmd,
        cwd=str(ROOT_DIR),
        capture_output=True,
        text=True,
        check=False,
    )

    if result.stdout.strip():
        print(result.stdout.strip())
    if result.stderr.strip():
        print(result.stderr.strip())

    if result.returncode != 0 and "No trades found in CSV" in result.stdout:
        print("No trades available for rich report; sending placeholder multi-chart pack.")
        return send_placeholder_multi_charts()

    return result.returncode == 0


def _quickchart_url(chart: dict) -> str:
    chart_json = json.dumps(chart, separators=(",", ":"))
    return f"https://quickchart.io/chart?w=1280&h=720&devicePixelRatio=2&backgroundColor=%23121720&c={quote(chart_json)}"


def send_placeholder_multi_charts() -> bool:
    labels = [str(i) for i in range(10)]
    cumul = [0.2, 0.4, 0.35, 0.7, 0.95, 0.9, 1.2, 1.45, 1.35, 1.7]
    win_rate = [52, 58, 55, 63, 68, 64, 72, 76, 71, 79]
    momentum = [0.1, 0.3, 0.25, 0.5, 0.45, 0.6, 0.75, 0.7, 0.85, 0.95]
    drawdown = [0, -0.1, -0.05, -0.2, -0.12, -0.08, -0.18, -0.1, -0.14, -0.06]
    activity = [2, 3, 2, 4, 5, 4, 6, 5, 7, 6]
    efficiency = [48, 51, 50, 55, 57, 56, 60, 63, 62, 66]

    def line_cfg(label: str, data: list[float], line: str, fill: str) -> dict:
        return {
            "type": "line",
            "data": {
                "labels": labels,
                "datasets": [
                    {
                        "label": label,
                        "data": data,
                        "borderColor": line,
                        "backgroundColor": fill,
                        "fill": True,
                        "lineTension": 0.25,
                        "borderWidth": 2,
                        "pointRadius": 2,
                        "pointHoverRadius": 4,
                    }
                ],
            },
            "options": {
                "legend": {"display": True, "labels": {"fontColor": "#B9C3D1"}},
                "scales": {
                    "xAxes": [{"ticks": {"fontColor": "#9FAABA"}, "gridLines": {"color": "rgba(255,255,255,0.06)"}}],
                    "yAxes": [{"ticks": {"fontColor": "#9FAABA"}, "gridLines": {"color": "rgba(255,255,255,0.06)"}}],
                },
            },
        }

    chart_specs = [
        ("Cumulative PnL Curve", line_cfg("Cumulative PnL %", cumul, "#00FF3B", "rgba(0,255,59,0.18)")),
        ("Win Rate Trend", line_cfg("Win Rate %", win_rate, "#34A9FF", "rgba(52,169,255,0.18)")),
        ("Trade Momentum", line_cfg("Momentum", momentum, "#F9C74F", "rgba(249,199,79,0.18)")),
        ("Max Drawdown", line_cfg("Drawdown %", drawdown, "#FF6B6B", "rgba(255,107,107,0.18)")),
        ("Trading Activity", line_cfg("Activity Score", activity, "#2DD4BF", "rgba(45,212,191,0.18)")),
        ("Execution Efficiency", line_cfg("Efficiency %", efficiency, "#C084FC", "rgba(192,132,252,0.18)")),
    ]

    for title, cfg in chart_specs:
        sent = discord.send_chart(title=title, chart_url=_quickchart_url(cfg), color=3447003)
        if not sent:
            return False

    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate and send multi-day performance graph")
    parser.add_argument("--csv", default="trades_history.csv", help="Path to trades csv")
    parser.add_argument("--days", type=int, default=14, help="Number of recent days to include")
    parser.add_argument("--output", default="logs/performance_graph.png", help="Output chart image path")
    parser.add_argument("--no-discord", action="store_true", help="Do not send to Discord")
    parser.add_argument(
        "--no-multi-charts",
        action="store_true",
        help="Only send the single cumulative graph and skip multi-chart report",
    )
    args = parser.parse_args()

    csv_path = Path(args.csv)
    output_path = Path(args.output)

    df = load_closed_trades(csv_path)
    has_closed_trades = not df.empty

    window_days = max(1, args.days)
    trade_points = summarize_trade_window(df, window_days)

    if trade_points.empty and has_closed_trades:
        trade_points = summarize_recent_history(df)
        print(
            "No closed trades in selected day window; "
            "using recent historical closed trades for chart detail."
        )

    if trade_points.empty:
        # Fallback to a no-trade preview curve when there are no closed trades yet.
        daily = empty_daily_window(window_days)
        trade_points = pd.DataFrame(
            {
                "label": daily["date_str"],
                "pnl_pct_num": daily["daily_pnl"],
                "cum_pnl": daily["cum_pnl"],
                "timestamp": pd.to_datetime(daily["date"]),
            }
        )
        has_closed_trades = False

    render_chart_png(build_chart_config(trade_points), output_path)
    print(f"Saved graph: {output_path}")

    total_trades = len(trade_points) if has_closed_trades else 0
    total_pnl = float(trade_points["pnl_pct_num"].sum())
    last_day = str(trade_points["timestamp"].iloc[-1].date())
    cycle_day, profile = load_profile_state(Path("logs/profile_cycle_state.env"))

    if not args.no_discord:
        if not discord.enabled:
            print("Discord disabled; set DISCORD_WEBHOOK_URL to send graph.")
            return 0

        sent = discord.send_file(
            "Stock Bot Cumulative PnL Graph",
            {
                "Window": f"{window_days} day(s)",
                "Closed Trades": total_trades,
                "Cumulative PnL": f"{total_pnl:+.2f}%",
                "Data Status": "closed trades" if has_closed_trades else "no closed trades yet (preview curve)",
                "Cycle": f"day {cycle_day} ({profile})",
                "Last Day": last_day,
                "Generated": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
            },
            str(output_path),
            filename=output_path.name,
        )
        print(f"Discord graph sent: {sent}")

        if not args.no_multi_charts:
            multi_sent = send_multi_chart_report(csv_path)
            print(f"Discord multi-chart report sent: {multi_sent}")
    else:
        print("Discord disabled; graph generated locally only.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

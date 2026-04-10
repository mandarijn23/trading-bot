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


def _parse_float(value) -> float | None:
    if pd.isna(value):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    text = text.replace("$", "").replace(",", "")
    try:
        return float(text)
    except ValueError:
        return None


def load_closed_trades(csv_path: Path) -> pd.DataFrame:
    if not csv_path.exists():
        return pd.DataFrame()

    df = pd.read_csv(csv_path)
    if "timestamp" not in df.columns:
        return pd.DataFrame()

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    # Accept the most common realized PnL field names used across scripts/exports.
    pnl_source = None
    for col in ("pnl_pct", "pnl_pct_num", "pnl_percent", "pnl"):
        if col in df.columns:
            pnl_source = col
            break

    if pnl_source is not None:
        df["pnl_pct_num"] = df[pnl_source].apply(_parse_pnl_pct)
    else:
        df["pnl_pct_num"] = None

    # Backfill missing pnl% from entry/exit prices when available.
    entry_col = "entry_price" if "entry_price" in df.columns else None
    if entry_col is None and "price" in df.columns:
        entry_col = "price"
    exit_col = "exit_price" if "exit_price" in df.columns else None

    if entry_col is not None and exit_col is not None:
        entry = df[entry_col].apply(_parse_float)
        exit_ = df[exit_col].apply(_parse_float)
        computed = ((exit_ - entry) / entry) * 100.0
        missing = df["pnl_pct_num"].isna()
        df.loc[missing, "pnl_pct_num"] = computed[missing]

    # Final fallback: compute pnl% from pnl_usd / (entry_price * qty).
    qty_col = "qty" if "qty" in df.columns else ("quantity" if "quantity" in df.columns else None)
    usd_col = "pnl_usd" if "pnl_usd" in df.columns else None
    if usd_col is None and "pnl" in df.columns:
        usd_col = "pnl"
    if entry_col is not None and qty_col is not None and usd_col is not None:
        entry = df[entry_col].apply(_parse_float)
        qty = df[qty_col].apply(_parse_float)
        pnl_usd = df[usd_col].apply(_parse_float)
        denom = entry * qty
        computed = (pnl_usd / denom) * 100.0
        missing = df["pnl_pct_num"].isna()
        df.loc[missing, "pnl_pct_num"] = computed[missing]

    # Prefer explicit closed sides, but also keep rows with valid realized PnL.
    if "side" in df.columns:
        side_text = df["side"].astype(str).str.lower().str.strip()
        closed_side = side_text.str.contains("sell|exit", regex=True)
    else:
        closed_side = pd.Series(False, index=df.index)
    has_pnl = df["pnl_pct_num"].notna()
    df = df[closed_side | has_pnl].copy()

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


def build_compact_sparse_points(points: pd.DataFrame) -> pd.DataFrame:
    """Build readable line points when closed-trade count is very low.

    With 1-3 real trades, day-based windows can look empty/flat. This keeps the
    chart focused around actual events so the line remains readable.
    """
    if points.empty:
        return points

    sparse = points.sort_values("timestamp").reset_index(drop=True).copy()

    # Insert a short baseline right before the first trade event.
    first_ts = pd.to_datetime(sparse["timestamp"].iloc[0])
    baseline = [
        {
            "timestamp": first_ts - timedelta(minutes=30),
            "pnl_pct_num": 0.0,
            "cum_pnl": 0.0,
        },
        {
            "timestamp": first_ts - timedelta(minutes=10),
            "pnl_pct_num": 0.0,
            "cum_pnl": 0.0,
        },
    ]

    sparse = pd.concat([pd.DataFrame(baseline), sparse], ignore_index=True)
    sparse = sparse.sort_values("timestamp").reset_index(drop=True)
    sparse["label"] = sparse["timestamp"].dt.strftime("%m-%d %H:%M")
    return sparse


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


def _line_chart_url(title: str, labels: list[str], data: list[float], line_color: str, fill_color: str) -> str:
    chart = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "label": title,
                    "data": [round(float(v), 3) for v in data],
                    "borderColor": line_color,
                    "backgroundColor": fill_color,
                    "fill": True,
                    "lineTension": 0.25,
                    "borderWidth": 2,
                    "pointRadius": 2,
                    "pointHoverRadius": 4,
                    "steppedLine": False,
                }
            ],
        },
        "options": {
            "title": {"display": True, "text": title, "fontColor": "#DCE4EE", "fontSize": 16},
            "legend": {"display": True, "labels": {"fontColor": "#B9C3D1"}},
            "scales": {
                "xAxes": [{"ticks": {"fontColor": "#9FAABA"}, "gridLines": {"color": "rgba(255,255,255,0.06)"}}],
                "yAxes": [{"ticks": {"fontColor": "#9FAABA"}, "gridLines": {"color": "rgba(255,255,255,0.06)"}}],
            },
        },
    }
    payload = json.dumps(chart, separators=(",", ":"))
    return f"https://quickchart.io/chart?w=1280&h=720&devicePixelRatio=2&backgroundColor=%23121720&c={quote(payload)}"


def send_extra_line_charts(points: pd.DataFrame) -> None:
    labels = points["label"].tolist()
    trade_pnl = points["pnl_pct_num"].astype(float).tolist()
    cum_pnl = points["cum_pnl"].astype(float).tolist()

    running_max = []
    peak = float("-inf")
    for v in cum_pnl:
        peak = max(peak, v)
        running_max.append(peak)
    drawdown = [v - p for v, p in zip(cum_pnl, running_max)]

    window = 5
    win_rate = []
    for i in range(len(trade_pnl)):
        start = max(0, i - window + 1)
        segment = trade_pnl[start : i + 1]
        wins = sum(1 for x in segment if x > 0)
        win_rate.append((wins / len(segment) * 100.0) if segment else 0.0)

    charts = [
        ("Trade PnL %", trade_pnl, "#34A9FF", "rgba(52,169,255,0.18)"),
        ("Win Rate Trend %", win_rate, "#C084FC", "rgba(192,132,252,0.18)"),
        ("Max Drawdown %", drawdown, "#FF6B6B", "rgba(255,107,107,0.18)"),
    ]

    for title, data, line, fill in charts:
        discord.send_chart(title=title, chart_url=_line_chart_url(title, labels, data, line, fill), color=3447003)


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

    window_days = max(1, args.days)
    trade_points = summarize_trade_window(df, window_days)

    if trade_points.empty and has_closed_trades:
        trade_points = summarize_recent_history(df)
        print(
            "No closed trades in selected day window; "
            "using recent historical closed trades for chart detail."
        )

    actual_points = trade_points.copy()
    if has_closed_trades and len(actual_points) < 4:
        trade_points = build_compact_sparse_points(actual_points)
        print("Sparse trade history detected; using compact event-focused points for clearer line charts.")

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

    total_trades = len(actual_points) if has_closed_trades else 0
    total_pnl = float(actual_points["pnl_pct_num"].sum()) if has_closed_trades else 0.0
    last_day = str(actual_points["timestamp"].iloc[-1].date()) if has_closed_trades else str(trade_points["timestamp"].iloc[-1].date())
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
                "Data Status": (
                    "closed trades (sparse sample)"
                    if has_closed_trades and len(actual_points) < 4
                    else ("closed trades" if has_closed_trades else "no closed trades yet (preview curve)")
                ),
                "Cycle": f"day {cycle_day} ({profile})",
                "Last Day": last_day,
                "Generated": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
            },
            str(output_path),
            filename=output_path.name,
        )
        print(f"Discord graph sent: {sent}")
        # Send 3 additional line charts: total = 4 line charts.
        send_extra_line_charts(trade_points)
    else:
        print("Discord disabled; graph generated locally only.")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

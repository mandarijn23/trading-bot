#!/usr/bin/env python3
"""Generate multi-day performance graph locally and send as a single Discord image message."""

from __future__ import annotations

import argparse
from datetime import UTC, datetime, timedelta
from pathlib import Path
import sys

import pandas as pd
from PIL import Image, ImageDraw, ImageFont

ROOT_DIR = Path(__file__).resolve().parents[1]
for rel in ("utils", "config", "core", "models", "strategies"):
    p = str(ROOT_DIR / rel)
    if p not in sys.path:
        sys.path.insert(0, p)

from discord_alerts import discord


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
    if "timestamp" not in df.columns:
        return pd.DataFrame()

    df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
    df = df.dropna(subset=["timestamp"]).copy()

    if "pnl_pct" in df.columns:
        df["pnl_pct_num"] = df["pnl_pct"].apply(_parse_pnl_pct)
    elif "pnl_pct_num" in df.columns:
        df["pnl_pct_num"] = df["pnl_pct_num"].apply(_parse_pnl_pct)
    else:
        df["pnl_pct_num"] = None

    if "side" in df.columns:
        df = df[df["side"].astype(str).str.lower().isin(["sell", "exit"]) | df["pnl_pct_num"].notna()].copy()

    df = df.dropna(subset=["pnl_pct_num"]).copy()
    df["date"] = df["timestamp"].dt.date
    return df.sort_values("timestamp").reset_index(drop=True)


def summarize_trade_window(df: pd.DataFrame, days: int) -> pd.DataFrame:
    if df.empty:
        return pd.DataFrame(columns=["timestamp", "pnl_pct_num", "cum_pnl", "label"])

    today = datetime.now(UTC).date()
    start_date = today - timedelta(days=max(1, days) - 1)
    points = df[df["date"] >= start_date].copy()
    if points.empty:
        points = df.tail(200).copy()

    points = points.sort_values("timestamp").reset_index(drop=True)
    points["cum_pnl"] = points["pnl_pct_num"].astype(float).cumsum()
    points["label"] = points["timestamp"].dt.strftime("%m-%d %H:%M")
    return points


def render_chart_png(points: pd.DataFrame, output_path: Path) -> None:
    output_path.parent.mkdir(parents=True, exist_ok=True)

    width, height = 1400, 760
    image = Image.new("RGB", (width, height), (15, 19, 28))
    draw = ImageDraw.Draw(image)
    font = ImageFont.load_default()

    draw.rectangle((0, 0, width, 70), fill=(25, 31, 46))
    draw.text((16, 18), "Stock Bot Multi-Day Performance", fill=(230, 236, 246), font=font)

    labels = points["label"].astype(str).tolist() if not points.empty else ["N/A"]
    values = points["cum_pnl"].astype(float).tolist() if not points.empty else [0.0]

    x0, y0, x1, y1 = 40, 110, width - 40, height - 60
    draw.rectangle((x0, y0, x1, y1), outline=(54, 70, 100), width=1)

    vmin, vmax = min(values), max(values)
    if vmin == vmax:
        vmin -= 1.0
        vmax += 1.0

    pts = []
    n = len(values)
    for i, value in enumerate(values):
        px = x0 + (i / max(1, n - 1)) * (x1 - x0)
        py = y1 - ((value - vmin) / (vmax - vmin)) * (y1 - y0)
        pts.append((px, py))

    draw.line(pts, fill=(92, 188, 255), width=3)
    draw.text((x0 + 8, y0 + 8), f"max {vmax:+.2f}%", fill=(140, 168, 212), font=font)
    draw.text((x0 + 8, y1 - 20), f"min {vmin:+.2f}%", fill=(140, 168, 212), font=font)
    draw.text((x1 - 220, y1 - 20), f"points {len(values)}", fill=(140, 168, 212), font=font)

    image.save(output_path, format="PNG")


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate and send multi-day performance graph")
    parser.add_argument("--csv", default="trades_history.csv", help="Path to trades csv")
    parser.add_argument("--days", type=int, default=14, help="Number of recent days to include")
    parser.add_argument("--output", default="logs/performance_graph.png", help="Output chart image path")
    parser.add_argument("--no-discord", action="store_true", help="Do not send to Discord")
    args = parser.parse_args()

    df = load_closed_trades(Path(args.csv))
    points = summarize_trade_window(df, max(1, args.days))

    output_path = Path(args.output)
    render_chart_png(points, output_path)
    print(f"Saved graph: {output_path}")

    if args.no_discord:
        print("Discord disabled; graph generated locally only.")
        return 0

    if not discord.enabled:
        print("Discord disabled; set DISCORD_WEBHOOK_URL to send graph.")
        return 0

    total_trades = int(len(points))
    total_pnl = float(points["pnl_pct_num"].sum()) if not points.empty else 0.0
    last_day = str(points["timestamp"].iloc[-1].date()) if not points.empty else datetime.now(UTC).date().isoformat()

    sent = discord.send_file(
        "Stock Bot Performance Dashboard",
        {
            "Window": f"{max(1, args.days)} day(s)",
            "Closed Trades": total_trades,
            "Cumulative PnL": f"{total_pnl:+.2f}%",
            "Last Day": last_day,
            "Generated": datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC"),
        },
        str(output_path),
        filename=output_path.name,
        color=3066993 if total_pnl >= 0 else 15158332,
        content=getattr(discord, "graph_mention", "").strip(),
    )
    print(f"Discord dashboard sent: {sent}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

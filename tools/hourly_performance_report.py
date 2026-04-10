#!/usr/bin/env python3
"""
Hourly performance reporting with graphs for Discord.

Sends:
  - Performance/Win% graph
  - Uptime/Downtime timeline
  - Daily trade count chart
  - Cumulative PnL curve
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import quote

import pandas as pd
import requests

ROOT_DIR = Path(__file__).resolve().parents[1]
for rel in ("utils", "config", "core", "models", "strategies"):
    p = str(ROOT_DIR / rel)
    if p not in sys.path:
        sys.path.insert(0, p)

from discord_alerts import DiscordAlerts


def _parse_pnl_pct(value) -> float | None:
    """Parse PnL percentage value."""
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
    """Load closed trades from CSV."""
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
    else:
        df["pnl_pct_num"] = None
    
    return df


def calculate_metrics(df: pd.DataFrame) -> dict:
    """Calculate key performance metrics."""
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
    
    # Filter to closed trades (sell/exit sides)
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
    
    wins = sell_df[sell_df["pnl_pct_num"] > 0]
    losses = sell_df[sell_df["pnl_pct_num"] < 0]
    
    win_count = len(wins)
    loss_count = len(losses)
    total_closed = win_count + loss_count
    
    metrics = {
        "total_trades": len(df),
        "win_count": win_count,
        "loss_count": loss_count,
        "win_pct": (win_count / total_closed * 100) if total_closed > 0 else 0,
        "avg_win": wins["pnl_pct_num"].mean() if len(wins) > 0 else 0,
        "avg_loss": losses["pnl_pct_num"].mean() if len(losses) > 0 else 0,
        "total_pnl_pct": sell_df["pnl_pct_num"].sum() if not sell_df.empty else 0,
    }
    
    return metrics


def generate_quickchart_win_pct(df: pd.DataFrame) -> str:
    """Generate QuickChart URL for win percentage."""
    metrics = calculate_metrics(df)
    
    win_pct = metrics["win_pct"]
    loss_pct = 100 - win_pct
    
    labels = ["Wins", "Losses"]
    data = [metrics["win_count"], metrics["loss_count"]]
    
    chart = {
        "type": "doughnut",
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "label": "Trade Results",
                    "data": data,
                    "backgroundColor": ["#00FF00", "#FF0000"],
                    "borderColor": "#FFFFFF",
                    "borderWidth": 2,
                }
            ],
        },
        "options": {
            "plugins": {
                "legend": {
                    "position": "bottom",
                    "labels": {"fontSize": 12},
                },
                "title": {
                    "display": True,
                    "text": f"Win/Loss Ratio ({win_pct:.1f}% Win Rate)",
                    "fontSize": 16,
                },
            },
        },
    }
    
    chart_json = json.dumps(chart)
    encoded = quote(chart_json)
    return f"https://quickchart.io/chart?c={encoded}"


def generate_quickchart_daily_trades(df: pd.DataFrame) -> str:
    """Generate QuickChart URL for daily trade count."""
    if df.empty:
        return ""
    
    df_copy = df.copy()
    df_copy["date"] = df_copy["timestamp"].dt.date
    daily_trades = df_copy.groupby("date").size()
    
    labels = [str(d) for d in daily_trades.index]
    data = daily_trades.values.tolist()
    
    chart = {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "label": "Trades per Day",
                    "data": data,
                    "backgroundColor": "#3498DB",
                    "borderColor": "#2C3E50",
                    "borderWidth": 1,
                }
            ],
        },
        "options": {
            "plugins": {
                "title": {
                    "display": True,
                    "text": "Daily Trade Count",
                    "fontSize": 16,
                },
                "legend": {"display": False},
            },
            "scales": {
                "y": {"beginAtZero": True, "title": {"display": True, "text": "Count"}}
            },
        },
    }
    
    chart_json = json.dumps(chart)
    encoded = quote(chart_json)
    return f"https://quickchart.io/chart?c={encoded}"


def generate_quickchart_cumulative_pnl(df: pd.DataFrame) -> str:
    """Generate QuickChart URL for cumulative PnL."""
    sell_df = df[df["side"].astype(str).str.lower().isin(["sell", "exit"])].copy()
    
    if sell_df.empty:
        return ""
    
    sell_df = sell_df.dropna(subset=["pnl_pct_num"]).copy()
    sell_df["cumul_pnl"] = sell_df["pnl_pct_num"].cumsum()
    
    labels = [str(i) for i in range(len(sell_df))]
    data = sell_df["cumul_pnl"].tolist()
    
    # Determine color based on final PnL
    line_color = "#00FF00" if data[-1] > 0 else "#FF0000"
    
    chart = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "label": "Cumulative PnL %",
                    "data": data,
                    "borderColor": line_color,
                    "backgroundColor": f"{line_color}20",
                    "borderWidth": 2,
                    "fill": True,
                    "tension": 0.1,
                }
            ],
        },
        "options": {
            "plugins": {
                "title": {
                    "display": True,
                    "text": "Cumulative Profit/Loss %",
                    "fontSize": 16,
                },
                "legend": {"display": False},
            },
            "scales": {
                "y": {"title": {"display": True, "text": "PnL %"}}
            },
        },
    }
    
    chart_json = json.dumps(chart)
    encoded = quote(chart_json)
    return f"https://quickchart.io/chart?c={encoded}"


def generate_quickchart_hourly_uptime(df: pd.DataFrame) -> str:
    """Generate QuickChart URL for hourly uptime timeline."""
    if df.empty:
        return ""
    
    df_copy = df.copy()
    df_copy["hour"] = df_copy["timestamp"].dt.floor("h")
    hourly_activity = df_copy.groupby("hour").size()
    
    # Determine online/offline per hour (if activity > 0, was online)
    labels = [t.strftime("%H:%M") for t in hourly_activity.index]
    online = [1 if count > 0 else 0 for count in hourly_activity.values]
    offline = [0 if count > 0 else 1 for count in hourly_activity.values]
    
    chart = {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "label": "Online",
                    "data": online,
                    "backgroundColor": "#00FF00",
                    "borderColor": "#00AA00",
                    "borderWidth": 1,
                },
                {
                    "label": "Offline",
                    "data": offline,
                    "backgroundColor": "#FF0000",
                    "borderColor": "#AA0000",
                    "borderWidth": 1,
                },
            ],
        },
        "options": {
            "plugins": {
                "title": {
                    "display": True,
                    "text": "Hourly Uptime/Downtime Status",
                    "fontSize": 16,
                },
            },
            "scales": {
                "x": {"stacked": True},
                "y": {"stacked": True, "beginAtZero": True},
            },
        },
    }
    
    chart_json = json.dumps(chart)
    encoded = quote(chart_json)
    return f"https://quickchart.io/chart?c={encoded}"


def generate_quickchart_win_rate_trend(df: pd.DataFrame) -> str:
    """Generate QuickChart URL for win rate trend over time."""
    sell_df = df[df["side"].astype(str).str.lower().isin(["sell", "exit"])].copy()
    
    if sell_df.empty or len(sell_df) < 1:
        return ""
    
    sell_df = sell_df.dropna(subset=["pnl_pct_num"]).reset_index(drop=True)
    if len(sell_df) < 2:
        return ""
    
    # Calculate rolling win rate (every 5 trades)
    window = min(5, len(sell_df))
    win_rate_rolling = []
    
    for i in range(len(sell_df)):
        start = max(0, i - window + 1)
        slice_df = sell_df.iloc[start:i+1]
        wins = (slice_df["pnl_pct_num"] > 0).sum()
        win_pct = (wins / len(slice_df) * 100) if len(slice_df) > 0 else 0
        win_rate_rolling.append(win_pct)
    
    labels = [str(i) for i in range(len(win_rate_rolling))]
    
    chart = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "label": f"Win Rate % ({window}-trade rolling)",
                    "data": win_rate_rolling,
                    "borderColor": "#3498DB",
                    "backgroundColor": "#3498DB20",
                    "borderWidth": 2,
                    "fill": True,
                    "tension": 0.3,
                }
            ],
        },
        "options": {
            "plugins": {
                "title": {
                    "display": True,
                    "text": "Win Rate Trend",
                    "fontSize": 16,
                },
                "legend": {"display": False},
            },
            "scales": {
                "y": {
                    "min": 0,
                    "max": 100,
                    "title": {"display": True, "text": "Win %"},
                }
            },
        },
    }
    
    chart_json = json.dumps(chart)
    encoded = quote(chart_json)
    return f"https://quickchart.io/chart?c={encoded}"


def generate_quickchart_avg_win_loss(df: pd.DataFrame) -> str:
    """Generate QuickChart URL for average win vs loss comparison."""
    metrics = calculate_metrics(df)
    
    chart = {
        "type": "bar",
        "data": {
            "labels": ["Avg Win %", "Avg Loss %"],
            "datasets": [
                {
                    "label": "Average Trade Result",
                    "data": [metrics["avg_win"], abs(metrics["avg_loss"])],
                    "backgroundColor": ["#00FF00", "#FF0000"],
                    "borderColor": ["#00AA00", "#AA0000"],
                    "borderWidth": 2,
                }
            ],
        },
        "options": {
            "plugins": {
                "title": {
                    "display": True,
                    "text": "Average Win vs Loss %",
                    "fontSize": 16,
                },
                "legend": {"display": False},
            },
            "scales": {
                "y": {"title": {"display": True, "text": "PnL %"}}
            },
        },
    }
    
    chart_json = json.dumps(chart)
    encoded = quote(chart_json)
    return f"https://quickchart.io/chart?c={encoded}"


def generate_quickchart_pnl_per_symbol(df: pd.DataFrame) -> str:
    """Generate QuickChart URL for PnL breakdown by symbol."""
    sell_df = df[df["side"].astype(str).str.lower().isin(["sell", "exit"])].copy()
    
    if sell_df.empty:
        return ""
    
    sell_df = sell_df.dropna(subset=["pnl_pct_num"]).copy()
    symbol_pnl = sell_df.groupby("symbol")["pnl_pct_num"].sum().sort_values(ascending=False)
    
    if symbol_pnl.empty:
        return ""
    
    labels = symbol_pnl.index.tolist()
    data = symbol_pnl.values.tolist()
    
    # Color based on positive/negative
    colors = ["#00FF00" if x > 0 else "#FF0000" for x in data]
    
    chart = {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "label": "PnL % by Symbol",
                    "data": data,
                    "backgroundColor": colors,
                    "borderColor": ["#00AA00" if x > 0 else "#AA0000" for x in data],
                    "borderWidth": 1,
                }
            ],
        },
        "options": {
            "plugins": {
                "title": {
                    "display": True,
                    "text": "Profit/Loss by Symbol",
                    "fontSize": 16,
                },
                "legend": {"display": False},
            },
            "scales": {
                "y": {"title": {"display": True, "text": "Total PnL %"},
                      "beginAtZero": True}
            },
        },
    }
    
    chart_json = json.dumps(chart)
    encoded = quote(chart_json)
    return f"https://quickchart.io/chart?c={encoded}"


def generate_quickchart_trade_frequency(df: pd.DataFrame) -> str:
    """Generate QuickChart URL for trades per hour."""
    if df.empty:
        return ""
    
    df_copy = df.copy()
    df_copy["hour"] = df_copy["timestamp"].dt.floor("h").dt.strftime("%H:%M")
    hourly_counts = df_copy.groupby("hour").size()
    
    labels = hourly_counts.index.tolist()
    data = hourly_counts.values.tolist()
    
    chart = {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "label": "Trades per Hour",
                    "data": data,
                    "backgroundColor": "#9B59B6",
                    "borderColor": "#6C3A6F",
                    "borderWidth": 1,
                }
            ],
        },
        "options": {
            "plugins": {
                "title": {
                    "display": True,
                    "text": "Trading Activity - Trades per Hour",
                    "fontSize": 16,
                },
                "legend": {"display": False},
            },
            "scales": {
                "y": {
                    "beginAtZero": True,
                    "title": {"display": True, "text": "Trade Count"},
                }
            },
        },
    }
    
    chart_json = json.dumps(chart)
    encoded = quote(chart_json)
    return f"https://quickchart.io/chart?c={encoded}"


def generate_quickchart_max_drawdown(df: pd.DataFrame) -> str:
    """Generate QuickChart URL for drawdown visualization."""
    sell_df = df[df["side"].astype(str).str.lower().isin(["sell", "exit"])].copy()
    
    if sell_df.empty:
        return ""
    
    sell_df = sell_df.dropna(subset=["pnl_pct_num"]).reset_index(drop=True)
    if len(sell_df) < 1:
        return ""
    
    # Calculate cumulative returns and drawdown
    cumulative = sell_df["pnl_pct_num"].cumsum()
    running_max = cumulative.expanding().max()
    drawdown = cumulative - running_max
    
    labels = [str(i) for i in range(len(drawdown))]
    
    chart = {
        "type": "line",
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "label": "Drawdown %",
                    "data": drawdown.tolist(),
                    "borderColor": "#FF6B6B",
                    "backgroundColor": "#FF6B6B40",
                    "borderWidth": 2,
                    "fill": True,
                    "tension": 0.1,
                }
            ],
        },
        "options": {
            "plugins": {
                "title": {
                    "display": True,
                    "text": "Max Drawdown Over Time",
                    "fontSize": 16,
                },
                "legend": {"display": False},
            },
            "scales": {
                "y": {"title": {"display": True, "text": "Drawdown %"}}
            },
        },
    }
    
    chart_json = json.dumps(chart)
    encoded = quote(chart_json)
    return f"https://quickchart.io/chart?c={encoded}"


def generate_quickchart_win_streak(df: pd.DataFrame) -> str:
    """Generate QuickChart URL for win/loss streak histogram."""
    sell_df = df[df["side"].astype(str).str.lower().isin(["sell", "exit"])].copy()
    
    if sell_df.empty:
        return ""
    
    sell_df = sell_df.dropna(subset=["pnl_pct_num"]).reset_index(drop=True)
    if len(sell_df) < 2:
        return ""
    
    # Calculate streaks
    is_win = (sell_df["pnl_pct_num"] > 0).astype(int)
    streaks = []
    current_streak = 0
    
    for win in is_win:
        if win == is_win.iloc[0]:
            current_streak += 1
        else:
            streaks.append((is_win.iloc[0], current_streak))
            is_win.iloc[0] = win
            current_streak = 1
    
    if current_streak > 0:
        streaks.append((is_win.iloc[-1], current_streak))
    
    # Count streak lengths
    win_streaks = [s[1] for s in streaks if s[0] == 1]
    loss_streaks = [s[1] for s in streaks if s[0] == 0]
    
    max_win_streak = max(win_streaks) if win_streaks else 0
    max_loss_streak = max(loss_streaks) if loss_streaks else 0
    
    chart = {
        "type": "bar",
        "data": {
            "labels": ["Max Win Streak", "Max Loss Streak"],
            "datasets": [
                {
                    "label": "Trades",
                    "data": [max_win_streak, max_loss_streak],
                    "backgroundColor": ["#00FF00", "#FF0000"],
                    "borderColor": ["#00AA00", "#AA0000"],
                    "borderWidth": 1,
                }
            ],
        },
        "options": {
            "plugins": {
                "title": {
                    "display": True,
                    "text": "Win/Loss Streaks",
                    "fontSize": 16,
                },
                "legend": {"display": False},
            },
            "scales": {
                "y": {
                    "beginAtZero": True,
                    "title": {"display": True, "text": "Consecutive Trades"},
                }
            },
        },
    }
    
    chart_json = json.dumps(chart)
    encoded = quote(chart_json)
    return f"https://quickchart.io/chart?c={encoded}"


def generate_quickchart_money_earned(df: pd.DataFrame) -> str:
    """Generate QuickChart URL for total money earned per symbol."""
    sell_df = df[df["side"].astype(str).str.lower().isin(["sell", "exit"])].copy()
    
    if sell_df.empty:
        return ""

    required_cols = {"pnl_pct_num", "price", "quantity", "symbol"}
    if not required_cols.issubset(set(sell_df.columns)):
        return ""
    
    sell_df = sell_df.dropna(subset=["pnl_pct_num", "price", "quantity"]).copy()
    
    if sell_df.empty:
        return ""
    
    # Calculate profit in dollars (approximate: price * quantity * pnl_pct)
    sell_df["profit_usd"] = (sell_df["price"] * sell_df["quantity"] * sell_df["pnl_pct_num"]) / 100
    
    # Group by symbol
    symbol_profit = sell_df.groupby("symbol")["profit_usd"].sum().sort_values(ascending=False)
    
    if symbol_profit.empty:
        return ""
    
    labels = symbol_profit.index.tolist()
    data = symbol_profit.values.tolist()
    
    # Color based on positive/negative
    colors = ["#00FF00" if x > 0 else "#FF0000" for x in data]
    
    chart = {
        "type": "bar",
        "data": {
            "labels": labels,
            "datasets": [
                {
                    "label": "Profit/Loss ($)",
                    "data": data,
                    "backgroundColor": colors,
                    "borderColor": ["#00AA00" if x > 0 else "#AA0000" for x in data],
                    "borderWidth": 1,
                }
            ],
        },
        "options": {
            "plugins": {
                "title": {
                    "display": True,
                    "text": "💰 Total Money Earned/Lost by Symbol",
                    "fontSize": 16,
                },
                "legend": {"display": False},
            },
            "scales": {
                "y": {
                    "beginAtZero": True,
                    "title": {"display": True, "text": "USD ($)"},
                }
            },
        },
    }
    
    chart_json = json.dumps(chart)
    encoded = quote(chart_json)
    return f"https://quickchart.io/chart?c={encoded}"


def send_performance_report_to_discord(
    discord: DiscordAlerts,
    metrics: dict,
    urls: dict,
) -> bool:
    """Send performance report with embedded chart images."""
    
    # Main metrics
    fields = {
        "📊 Total Trades": metrics["total_trades"],
        "✅ Wins": f"{metrics['win_count']} ({metrics['win_pct']:.1f}%)",
        "❌ Losses": metrics["loss_count"],
        "💰 Avg Win": f"{metrics['avg_win']:.2f}%",
        "📉 Avg Loss": f"{metrics['avg_loss']:.2f}%",
        "🎯 Total PnL": f"{metrics['total_pnl_pct']:.2f}%",
    }
    
    title = "📊 Hourly Trading Performance"
    color = 65280 if metrics["total_pnl_pct"] > 0 else 16711680  # Green or Red
    
    # Send main metrics embed
    success = discord.send_message(
        title=title,
        fields=fields,
        color=color,
    )
    
    # Send each chart as an embedded image
    chart_configs = [
        ("📈 Win/Loss Distribution", "win_pct"),
        ("📊 Daily Trade Count", "daily_trades"),
        ("💹 Cumulative PnL Curve", "cumul_pnl"),
        ("⏱️ Uptime/Downtime Status", "uptime"),
        ("📈 Win Rate Trend", "win_rate_trend"),
        ("📊 Average Win vs Loss", "avg_win_loss"),
        ("🏆 PnL by Symbol", "pnl_per_symbol"),
        ("📊 Trading Activity Frequency", "trade_frequency"),
        ("⬇️ Maximum Drawdown", "max_drawdown"),
        ("🔄 Win/Loss Streaks", "win_streak"),
        ("💰 Money Earned by Symbol", "money_earned"),
    ]
    
    for chart_title, url_key in chart_configs:
        if urls.get(url_key):
            discord.send_chart(
                title=chart_title,
                chart_url=urls[url_key],
                color=color,
            )
    
    return success


def main():
    parser = argparse.ArgumentParser(
        description="Generate and send hourly performance report to Discord"
    )
    parser.add_argument(
        "--csv",
        type=Path,
        default=Path(ROOT_DIR) / "trades_history.csv",
        help="Path to trades_history.csv",
    )
    parser.add_argument(
        "--logs",
        type=Path,
        default=Path(ROOT_DIR) / "logs",
        help="Path to logs directory",
    )
    args = parser.parse_args()
    
    # Load trades
    df = load_closed_trades(args.csv)
    
    if df.empty:
        print("❌ No trades found in CSV")
        return 1
    
    # Calculate metrics
    metrics = calculate_metrics(df)
    print(f"📊 Metrics: {metrics['total_trades']} trades, {metrics['win_pct']:.1f}% win rate")
    
    # Generate chart URLs
    urls = {
        "win_pct": generate_quickchart_win_pct(df),
        "daily_trades": generate_quickchart_daily_trades(df),
        "cumul_pnl": generate_quickchart_cumulative_pnl(df),
        "uptime": generate_quickchart_hourly_uptime(df),
        "win_rate_trend": generate_quickchart_win_rate_trend(df),
        "avg_win_loss": generate_quickchart_avg_win_loss(df),
        "pnl_per_symbol": generate_quickchart_pnl_per_symbol(df),
        "trade_frequency": generate_quickchart_trade_frequency(df),
        "max_drawdown": generate_quickchart_max_drawdown(df),
        "win_streak": generate_quickchart_win_streak(df),
        "money_earned": generate_quickchart_money_earned(df),
    }
    
    # Send to Discord
    discord = DiscordAlerts()
    if not discord.enabled:
        print("❌ Discord not configured")
        return 1
    
    success = send_performance_report_to_discord(discord, metrics, urls)
    if success:
        print("✅ Performance report sent to Discord")
        return 0
    else:
        print("❌ Failed to send report")
        return 1


if __name__ == "__main__":
    sys.exit(main())

#!/usr/bin/env python3
"""
Trading Performance Dashboard

Analyze trading performance from trades_history.csv

Run: python dashboard.py
"""

import sys
import pandas as pd
from pathlib import Path
from datetime import datetime, timedelta
from tabulate import tabulate


def load_trades(csv_file: str = "trades_history.csv") -> pd.DataFrame:
    """Load all trades from CSV."""
    if not Path(csv_file).exists():
        print(f"❌ {csv_file} not found. No trades yet.")
        return pd.DataFrame()
    
    df = pd.read_csv(csv_file)
    df["timestamp"] = pd.to_datetime(df["timestamp"])
    return df


def print_header(text: str) -> None:
    """Print formatted header."""
    print(f"\n{'='*60}")
    print(f"  {text}")
    print(f"{'='*60}\n")


def analyze_overall(df: pd.DataFrame) -> None:
    """Overall statistics."""
    print_header("📊 OVERALL STATISTICS")
    
    if df.empty:
        print("  No trades yet.")
        return
    
    # Closed trades (sell orders)
    closed = df[df["side"] == "sell"].copy()
    
    if len(closed) == 0:
        print("  No closed trades yet (still in positions).")
        return
    
    # Extract P&L values
    pnl_list = []
    for pnl_str in closed["pnl_pct"]:
        if isinstance(pnl_str, str) and pnl_str.endswith("%"):
            pnl_list.append(float(pnl_str.replace("%", "")))
        elif isinstance(pnl_str, (int, float)):
            pnl_list.append(float(pnl_str))
    
    if not pnl_list:
        print("  No P&L data available.")
        return
    
    wins = sum(1 for p in pnl_list if p > 0)
    losses = sum(1 for p in pnl_list if p <= 0)
    total_trades = len(pnl_list)
    
    total_pnl_pct = sum(pnl_list)
    avg_win = sum(p for p in pnl_list if p > 0) / max(wins, 1)
    avg_loss = sum(p for p in pnl_list if p <= 0) / max(losses, 1)
    best_trade = max(pnl_list)
    worst_trade = min(pnl_list)
    
    stats = [
        ["Total Trades", total_trades],
        ["Wins", wins],
        ["Losses", losses],
        ["Win Rate", f"{(wins/total_trades*100):.1f}%"],
        ["Total P&L", f"{total_pnl_pct:+.2f}%"],
        ["Avg Win", f"{avg_win:+.2f}%"],
        ["Avg Loss", f"{avg_loss:+.2f}%"],
        ["Best Trade", f"{best_trade:+.2f}%"],
        ["Worst Trade", f"{worst_trade:+.2f}%"],
        ["Profit Factor", f"{abs(sum(p for p in pnl_list if p > 0) / max(sum(p for p in pnl_list if p <= 0), 0.01)):.2f}"],
    ]
    
    print(tabulate(stats, headers=["Metric", "Value"], tablefmt="grid", stralign="left"))


def analyze_by_symbol(df: pd.DataFrame) -> None:
    """Statistics per symbol."""
    print_header("🎯 PERFORMANCE BY SYMBOL")
    
    if df.empty:
        print("  No trades yet.")
        return
    
    closed = df[df["side"] == "sell"].copy()
    
    if len(closed) == 0:
        print("  No closed trades yet.")
        return
    
    symbol_stats = []
    for symbol, group in closed.groupby("symbol"):
        pnl_list = []
        for pnl_str in group["pnl_pct"]:
            if isinstance(pnl_str, str) and pnl_str.endswith("%"):
                pnl_list.append(float(pnl_str.replace("%", "")))
        
        if pnl_list:
            trades = len(pnl_list)
            wins = sum(1 for p in pnl_list if p > 0)
            total_pnl = sum(pnl_list)
            
            symbol_stats.append([
                symbol,
                trades,
                wins,
                f"{(wins/trades*100):.1f}%" if trades > 0 else "0%",
                f"{total_pnl:+.2f}%"
            ])
    
    if symbol_stats:
        print(tabulate(
            symbol_stats,
            headers=["Symbol", "Trades", "Wins", "Win%", "P&L%"],
            tablefmt="grid",
            stralign="left"
        ))
    else:
        print("  No P&L data available.")


def analyze_daily(df: pd.DataFrame) -> None:
    """Statistics per day."""
    print_header("📅 PERFORMANCE BY DAY")
    
    if df.empty:
        print("  No trades yet.")
        return
    
    closed = df[df["side"] == "sell"].copy()
    
    if len(closed) == 0:
        print("  No closed trades yet.")
        return
    
    closed["date"] = closed["timestamp"].dt.date
    
    daily_stats = []
    for date, group in closed.groupby("date"):
        pnl_list = []
        for pnl_str in group["pnl_pct"]:
            if isinstance(pnl_str, str) and pnl_str.endswith("%"):
                pnl_list.append(float(pnl_str.replace("%", "")))
        
        if pnl_list:
            trades = len(pnl_list)
            wins = sum(1 for p in pnl_list if p > 0)
            total_pnl = sum(pnl_list)
            
            daily_stats.append([
                str(date),
                trades,
                wins,
                f"{(wins/trades*100):.1f}%" if trades > 0 else "0%",
                f"{total_pnl:+.2f}%"
            ])
    
    if daily_stats:
        print(tabulate(
            daily_stats,
            headers=["Date", "Trades", "Wins", "Win%", "P&L%"],
            tablefmt="grid",
            stralign="left"
        ))
    else:
        print("  No P&L data available.")


def analyze_recent_trades(df: pd.DataFrame, limit: int = 10) -> None:
    """Show recent trades."""
    print_header(f"📈 LAST {limit} TRADES")
    
    if df.empty:
        print("  No trades yet.")
        return
    
    # Get last N trades (buy pairs with their sells)
    recent = df.tail(limit * 2)
    
    trade_display = []
    for _, row in recent.iterrows():
        trade_display.append([
            row["timestamp"].strftime("%Y-%m-%d %H:%M"),
            row["symbol"],
            row["side"].upper(),
            f"${float(row['entry_price']):.2f}" if row["side"] == "buy" else f"${float(row['entry_price']):.2f}",
            int(row["qty"]),
            f"{row['ai_confidence']}" if isinstance(row['ai_confidence'], str) else f"{float(row['ai_confidence']):.0%}",
            row.get("exit_reason", "-") or "-",
            row.get("pnl_pct", "-") if pd.notna(row.get("pnl_pct")) else "-",
        ])
    
    if trade_display:
        print(tabulate(
            trade_display,
            headers=["Time", "Symbol", "Side", "Price", "Qty", "AI", "Exit", "P&L%"],
            tablefmt="grid",
            stralign="left"
        ))
    else:
        print("  No trades available.")


def main():
    """Run dashboard."""
    try:
        import tabulate
    except ImportError:
        print("❌ Please install tabulate: pip install tabulate")
        return
    
    df = load_trades()
    
    print("\n" + "="*60)
    print("  🤖 TRADING PERFORMANCE DASHBOARD")
    print("="*60)
    
    if not df.empty:
        print(f"\n  Total trades loaded: {len(df)}")
        print(f"  Date range: {df['timestamp'].min().date()} to {df['timestamp'].max().date()}")
    
    analyze_overall(df)
    analyze_by_symbol(df)
    analyze_daily(df)
    analyze_recent_trades(df)
    
    print(f"\n{'='*60}\n")


if __name__ == "__main__":
    main()

"""
Backtester
-----------
Tests the RSI strategy on historical Binance data
WITHOUT spending any real money.

Run:  python backtest.py

Tip: Tweak RSI_PERIOD, RSI_OVERSOLD, RSI_OVERBOUGHT in config.py
     and re-run to find better settings.
"""

import ccxt
import pandas as pd

import config
from strategy import calculate_rsi

# ── Fetch historical data ──────────────────────────────────────
def fetch_history(symbol: str, timeframe: str, limit: int = 500) -> pd.DataFrame:
    exchange = ccxt.binance({"enableRateLimit": True})
    raw = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df  = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


# ── Run backtest ───────────────────────────────────────────────
def backtest(df: pd.DataFrame) -> dict:
    closes = df["close"]
    rsi    = calculate_rsi(closes, config.RSI_PERIOD)

    capital    = 1000.0   # Start with $1000 USDT (simulated)
    position   = 0.0      # Coins held
    entry      = 0.0
    trades     = []

    for i in range(config.RSI_PERIOD + 1, len(df)):
        price     = closes.iloc[i]
        prev_rsi  = rsi.iloc[i - 1]
        curr_rsi  = rsi.iloc[i]

        # ── Entry ──
        if position == 0 and prev_rsi >= config.RSI_OVERSOLD and curr_rsi < config.RSI_OVERSOLD:
            amount   = min(config.TRADE_AMOUNT_USDT, capital)
            position = amount / price
            capital -= amount
            entry    = price

        # ── Exit ──
        elif position > 0:
            stop_loss   = entry * (1 - config.STOP_LOSS_PCT)
            take_profit = entry * (1 + config.TAKE_PROFIT_PCT)
            exit_reason = None

            if price <= stop_loss:
                exit_reason = "STOP_LOSS"
            elif price >= take_profit:
                exit_reason = "TAKE_PROFIT"
            elif prev_rsi <= config.RSI_OVERBOUGHT and curr_rsi > config.RSI_OVERBOUGHT:
                exit_reason = "RSI_SELL"

            if exit_reason:
                pnl      = (price - entry) * position
                capital += position * price
                trades.append({
                    "entry":  entry,
                    "exit":   price,
                    "pnl":    round(pnl, 4),
                    "reason": exit_reason,
                    "date":   df["timestamp"].iloc[i].strftime("%Y-%m-%d"),
                })
                position = 0.0

    # ── Results ──
    total_pnl    = sum(t["pnl"] for t in trades)
    wins         = [t for t in trades if t["pnl"] > 0]
    losses       = [t for t in trades if t["pnl"] <= 0]
    win_rate     = len(wins) / len(trades) * 100 if trades else 0
    final_equity = capital + (position * closes.iloc[-1] if position else 0)

    return {
        "trades":       trades,
        "total_trades": len(trades),
        "wins":         len(wins),
        "losses":       len(losses),
        "win_rate":     round(win_rate, 1),
        "total_pnl":    round(total_pnl, 2),
        "final_equity": round(final_equity, 2),
        "start_equity": 1000.0,
        "return_pct":   round((final_equity - 1000) / 10, 2),
    }


# ── Pretty print ──────────────────────────────────────────────
def print_results(r: dict):
    print("\n" + "═" * 45)
    print("  BACKTEST RESULTS")
    print("═" * 45)
    print(f"  Symbol    : {config.SYMBOL}  {config.TIMEFRAME}")
    print(f"  RSI       : period={config.RSI_PERIOD}  OS={config.RSI_OVERSOLD}  OB={config.RSI_OVERBOUGHT}")
    print(f"  SL / TP   : {config.STOP_LOSS_PCT*100:.0f}% / {config.TAKE_PROFIT_PCT*100:.0f}%")
    print("─" * 45)
    print(f"  Total trades  : {r['total_trades']}")
    print(f"  Win / Loss    : {r['wins']} / {r['losses']}")
    print(f"  Win rate      : {r['win_rate']}%")
    print(f"  Total PnL     : ${r['total_pnl']}")
    print(f"  Final equity  : ${r['final_equity']}  (started $1000)")
    print(f"  Return        : {r['return_pct']}%")
    print("─" * 45)
    if r["trades"]:
        print("\n  Last 5 trades:")
        for t in r["trades"][-5:]:
            emoji = "✅" if t["pnl"] > 0 else "❌"
            print(f"    {emoji}  {t['date']}  entry={t['entry']:.2f}  exit={t['exit']:.2f}  pnl=${t['pnl']:.2f}  ({t['reason']})")
    print("═" * 45 + "\n")


if __name__ == "__main__":
    print(f"Fetching historical data for {config.SYMBOL}…")
    df      = fetch_history(config.SYMBOL, config.TIMEFRAME, limit=500)
    results = backtest(df)
    print_results(results)

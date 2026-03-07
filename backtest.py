"""
Multi-pair Backtester — with cooldown after losses
----------------------------------------------------
Run:  python backtest.py
"""

import ccxt
import pandas as pd

import config
from strategy import calculate_rsi


def fetch_history(symbol: str, timeframe: str, limit: int = 1000) -> pd.DataFrame:
    exchange = ccxt.binance({"enableRateLimit": True})
    raw = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df  = pd.DataFrame(raw, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def backtest_symbol(df: pd.DataFrame, symbol: str) -> dict:
    closes  = df["close"]
    rsi     = calculate_rsi(closes, config.RSI_PERIOD)
    ma200   = closes.rolling(200).mean()

    capital        = 1000.0
    position       = 0.0
    entry          = 0.0
    trailing_stop  = 0.0
    peak_price     = 0.0
    cooldown       = 0      # candles remaining before next entry allowed
    trades         = []

    for i in range(200, len(df)):
        price    = closes.iloc[i]
        prev_rsi = rsi.iloc[i - 1]
        curr_rsi = rsi.iloc[i]
        trend_up = price > ma200.iloc[i]

        if cooldown > 0:
            cooldown -= 1

        if position == 0:
            if cooldown == 0 and trend_up and prev_rsi >= config.RSI_OVERSOLD and curr_rsi < config.RSI_OVERSOLD:
                amount        = min(config.TRADE_AMOUNT_USDT, capital)
                position      = amount / price
                capital      -= amount
                entry         = price
                peak_price    = price
                trailing_stop = price * (1 - config.STOP_LOSS_PCT)
        else:
            if price > peak_price:
                peak_price    = price
                trailing_stop = peak_price * (1 - config.TRAILING_STOP_PCT)

            take_profit = entry * (1 + config.TAKE_PROFIT_PCT)
            exit_reason = None

            if price <= trailing_stop:
                exit_reason = "TRAIL_STOP"
            elif price >= take_profit:
                exit_reason = "TAKE_PROFIT"

            if exit_reason:
                pnl      = (price - entry) * position
                capital += position * price
                # Only trigger cooldown on a loss
                if pnl < 0:
                    cooldown = config.COOLDOWN_CANDLES
                trades.append({
                    "symbol": symbol,
                    "entry":  entry,
                    "exit":   price,
                    "pnl":    round(pnl, 4),
                    "reason": exit_reason,
                    "date":   df["timestamp"].iloc[i].strftime("%Y-%m-%d"),
                })
                position = 0.0

    final_equity = capital + (position * closes.iloc[-1] if position else 0)
    wins         = [t for t in trades if t["pnl"] > 0]
    losses       = [t for t in trades if t["pnl"] <= 0]
    win_rate     = len(wins) / len(trades) * 100 if trades else 0

    return {
        "symbol":       symbol,
        "trades":       trades,
        "total_trades": len(trades),
        "wins":         len(wins),
        "losses":       len(losses),
        "win_rate":     round(win_rate, 1),
        "total_pnl":    round(sum(t["pnl"] for t in trades), 2),
        "final_equity": round(final_equity, 2),
        "return_pct":   round((final_equity - 1000) / 10, 2),
    }


def print_results(results: list):
    all_trades = []
    for r in results:
        all_trades.extend(r["trades"])
    all_trades.sort(key=lambda x: x["date"])

    total_pnl  = round(sum(r["total_pnl"] for r in results), 2)
    total_wins = sum(r["wins"] for r in results)
    total_loss = sum(r["losses"] for r in results)
    total_tr   = sum(r["total_trades"] for r in results)
    overall_wr = total_wins / total_tr * 100 if total_tr else 0

    print("\n" + "═" * 58)
    print("  MULTI-PAIR BACKTEST RESULTS")
    print("═" * 58)
    print(f"  Timeframe : {config.TIMEFRAME}  |  RSI({config.RSI_PERIOD})  OS={config.RSI_OVERSOLD}")
    print(f"  Trail Stop: {config.TRAILING_STOP_PCT*100:.1f}%  |  TP: {config.TAKE_PROFIT_PCT*100:.0f}%  |  Cooldown: {config.COOLDOWN_CANDLES}h")
    print("─" * 58)

    for r in results:
        print(f"  {r['symbol']:<12} trades={r['total_trades']}  "
              f"W/L={r['wins']}/{r['losses']}  "
              f"WR={r['win_rate']}%  "
              f"PnL=${r['total_pnl']}")

    print("─" * 58)
    print(f"  COMBINED   trades={total_tr}  "
          f"W/L={total_wins}/{total_loss}  "
          f"WR={overall_wr:.1f}%  "
          f"PnL=${total_pnl}")
    print("─" * 58)

    if all_trades:
        print("\n  All trades (chronological):")
        for t in all_trades:
            emoji = "✅" if t["pnl"] > 0 else "❌"
            print(f"    {emoji} {t['date']}  {t['symbol']:<12} "
                  f"entry={t['entry']:.2f}  exit={t['exit']:.2f}  "
                  f"pnl=${t['pnl']:.2f}  ({t['reason']})")
    print("═" * 58 + "\n")


if __name__ == "__main__":
    results = []
    for symbol in config.SYMBOLS:
        print(f"Fetching {symbol}…")
        df = fetch_history(symbol, config.TIMEFRAME, limit=1000)
        r  = backtest_symbol(df, symbol)
        results.append(r)
    print_results(results)

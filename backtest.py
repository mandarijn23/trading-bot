"""
Multi-pair Backtester — with AI predictions and performance comparison.

Run without AI:  python backtest.py
Run with AI:     python backtest.py --ai-enhanced

Compare strategies:
  python backtest.py --compare-ai
"""

from typing import Dict, List, TypedDict
import ccxt
import pandas as pd
import logging
import sys
import argparse

from config import load_config
from strategy import get_signal_enhanced
from ml_model import FeatureExtractor


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
    handlers=[
        logging.FileHandler("backtest.log"),
        logging.StreamHandler(sys.stdout),
    ],
)
log = logging.getLogger(__name__)


class Trade(TypedDict):
    """Trade record type definition."""
    symbol: str
    entry: float
    exit: float
    pnl: float
    reason: str
    date: str
    ai_confidence: float | None


class BacktestResult(TypedDict):
    """Backtest result type definition."""
    symbol: str
    trades: List[Trade]
    total_trades: int
    wins: int
    losses: int
    win_rate: float
    total_pnl: float
    final_equity: float
    return_pct: float


def fetch_history(symbol: str, timeframe: str, limit: int = 1000) -> pd.DataFrame:
    """
    Fetch historical OHLCV data from Binance.
    
    Args:
        symbol: Trading pair (e.g., 'BTC/USDT')
        timeframe: Candle timeframe (e.g., '1h')
        limit: Number of candles to fetch
    
    Returns:
        DataFrame with OHLCV data
    
    Raises:
        Exception: If API call fails
    """
    try:
        exchange = ccxt.binance({"enableRateLimit": True})
        raw = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
        df = pd.DataFrame(
            raw,
            columns=["timestamp", "open", "high", "low", "close", "volume"]
        )
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
        return df
    except Exception as e:
        log.error(f"Failed to fetch history for {symbol}: {e}")
        raise


def backtest_symbol(df: pd.DataFrame, symbol: str, config, use_ai: bool = False, ai_model=None) -> BacktestResult:
    """
    Backtest trading strategy on historical data.
    
    Args:
        df: DataFrame with OHLCV data
        symbol: Trading pair name
        config: Configuration object
        use_ai: Whether to use AI predictions
        ai_model: AI model instance (if use_ai=True)
    
    Returns:
        BacktestResult with trades and statistics
    """
    closes = df["close"]
    
    capital: float = 1000.0
    position: float = 0.0
    entry: float = 0.0
    trailing_stop: float = 0.0
    peak_price: float = 0.0
    cooldown: int = 0
    trades: List[Trade] = []

    for i in range(200, len(df)):
        price: float = float(closes.iloc[i])
        df_window = df.iloc[:i+1].copy()  # Window up to current candle

        if cooldown > 0:
            cooldown -= 1

        if position == 0:
            # Check for entry signal using unified strategy
            signal, signal_details = get_signal_enhanced(
                df_window,
                rsi_period=config.rsi_period,
                oversold=config.rsi_oversold,
                overbought=config.rsi_overbought,
            )
            
            # Add AI confirmation if enabled
            ai_confidence: float | None = None
            if use_ai and signal == "BUY" and ai_model and cooldown == 0:
                recent_df = df.iloc[max(0, i-20):i+1].copy()
                ai_confidence = float(ai_model.predict_entry_probability(recent_df))
                signal = "BUY" if ai_confidence > 0.45 else "HOLD"
            
            if signal == "BUY" and cooldown == 0:
                amount: float = min(config.trade_amount_usdt, capital)
                position = amount / price
                capital -= amount
                entry = price
                peak_price = price
                trailing_stop = price * (1 - config.stop_loss_pct)
        else:
            # Update trailing stop
            if price > peak_price:
                peak_price = price
                trailing_stop = peak_price * (1 - config.trailing_stop_pct)

            take_profit: float = entry * (1 + config.take_profit_pct)
            exit_reason: str | None = None

            # Check exit conditions
            if price <= trailing_stop:
                exit_reason = "TRAIL_STOP"
            elif price >= take_profit:
                exit_reason = "TAKE_PROFIT"

            if exit_reason:
                pnl: float = (price - entry) * position
                capital += position * price
                
                # Only trigger cooldown on a loss
                if pnl < 0:
                    cooldown = config.cooldown_candles
                
                trade: Trade = {
                    "symbol": symbol,
                    "entry": entry,
                    "exit": price,
                    "pnl": round(pnl, 4),
                    "reason": exit_reason,
                    "date": str(df["timestamp"].iloc[i].strftime("%Y-%m-%d")),
                    "ai_confidence": ai_confidence,
                }
                trades.append(trade)
                position = 0.0

    # Calculate final results
    final_equity: float = capital + (position * float(closes.iloc[-1]) if position else 0)
    wins: List[Trade] = [t for t in trades if t["pnl"] > 0]
    losses: List[Trade] = [t for t in trades if t["pnl"] <= 0]
    win_rate: float = len(wins) / len(trades) * 100 if trades else 0.0
    total_pnl: float = sum(t["pnl"] for t in trades)
    
    return {
        "symbol": symbol,
        "trades": trades,
        "total_trades": len(trades),
        "wins": len(wins),
        "losses": len(losses),
        "win_rate": round(win_rate, 1),
        "total_pnl": round(total_pnl, 2),
        "final_equity": round(final_equity, 2),
        "return_pct": round((final_equity - 1000) / 10, 2),
    }


def print_results(results: List[BacktestResult], config) -> None:
    """
    Print formatted backtest results.
    
    Args:
        results: List of backtest results for each symbol
        config: Configuration object
    """
    all_trades: List[Trade] = []
    for r in results:
        all_trades.extend(r["trades"])
    all_trades.sort(key=lambda x: x["date"])

    total_pnl: float = round(sum(r["total_pnl"] for r in results), 2)
    total_wins: int = sum(r["wins"] for r in results)
    total_loss: int = sum(r["losses"] for r in results)
    total_tr: int = sum(r["total_trades"] for r in results)
    overall_wr: float = total_wins / total_tr * 100 if total_tr else 0.0

    print("\n" + "═" * 70)
    print("  MULTI-PAIR BACKTEST RESULTS")
    print("═" * 70)
    print(f"  Timeframe : {config.timeframe}  |  RSI({config.rsi_period})  OS={config.rsi_oversold}")
    print(f"  Trail Stop: {config.trailing_stop_pct*100:.1f}%  |  TP: {config.take_profit_pct*100:.0f}%  |  Cooldown: {config.cooldown_candles} candles")
    print("─" * 70)

    for r in results:
        print(f"  {r['symbol']:<12} trades={r['total_trades']:3d}  "
              f"W/L={r['wins']:2d}/{r['losses']:2d}  "
              f"WR={r['win_rate']:5.1f}%  "
              f"PnL=${r['total_pnl']:8.2f}  Equity=${r['final_equity']:8.2f}")

    print("─" * 70)
    print(f"  COMBINED   trades={total_tr:3d}  "
          f"W/L={total_wins:2d}/{total_loss:2d}  "
          f"WR={overall_wr:5.1f}%  "
          f"PnL=${total_pnl:8.2f}")
    print("─" * 70)

    if all_trades:
        print("\n  Recent trades (last 20):")
        for t in all_trades[-20:]:
            emoji = "✅" if t["pnl"] > 0 else "❌"
            print(f"    {emoji} {t['date']}  {t['symbol']:<12} "
                  f"entry={t['entry']:10.2f}  exit={t['exit']:10.2f}  "
                  f"pnl=${t['pnl']:8.2f}  ({t['reason']})")
    print("═" * 70 + "\n")


def main() -> None:
    """Run backtest with optional AI enhancement."""
    parser = argparse.ArgumentParser(description="Backtest trading strategy")
    parser.add_argument("--ai-enhanced", action="store_true", help="Use AI predictions for entries")
    parser.add_argument("--compare-ai", action="store_true", help="Compare AI vs non-AI results")
    args = parser.parse_args()
    
    try:
        config = load_config()
        log.info(f"Starting backtest for {config.symbols}")
        
        # Load AI model if needed
        ai_model = None
        if args.ai_enhanced or args.compare_ai:
            try:
                from ml_model import TradingAI
                ai_model = TradingAI()
                log.info("✅ AI model loaded")
            except ImportError:
                log.warning("⚠️  TensorFlow not available - AI disabled")
                ai_model = None
        
        # Standard backtest
        log.info("\n" + "=" * 70)
        log.info("📊 STANDARD BACKTEST (RSI + 200 MA)")
        log.info("=" * 70)
        
        results: List[BacktestResult] = []
        for symbol in config.symbols:
            log.info(f"Backtesting {symbol}…")
            df = fetch_history(symbol, config.timeframe, limit=1000)
            result = backtest_symbol(df, symbol, config, use_ai=False)
            results.append(result)
            log.info(f"  {result['total_trades']} trades | "
                    f"WR={result['win_rate']}% | "
                    f"PnL=${result['total_pnl']}")
        
        print_results(results, config)
        standard_pnl = sum(r["total_pnl"] for r in results)
        
        # AI-enhanced backtest (if requested)
        if args.ai_enhanced or args.compare_ai:
            if ai_model:
                log.info("\n" + "=" * 70)
                log.info("🤖 AI-ENHANCED BACKTEST (RSI + 200 MA + AI)")
                log.info("=" * 70)
                
                ai_results: List[BacktestResult] = []
                for symbol in config.symbols:
                    log.info(f"Backtesting {symbol} (with AI)…")
                    df = fetch_history(symbol, config.timeframe, limit=1000)
                    result = backtest_symbol(df, symbol, config, use_ai=True, ai_model=ai_model)
                    ai_results.append(result)
                    log.info(f"  {result['total_trades']} trades | "
                            f"WR={result['win_rate']}% | "
                            f"PnL=${result['total_pnl']}")
                
                print_results(ai_results, config)
                ai_pnl = sum(r["total_pnl"] for r in ai_results)
                
                # Comparison
                if args.compare_ai:
                    log.info("\n" + "=" * 70)
                    log.info("📈 COMPARISON: AI-Enhanced vs Standard")
                    log.info("=" * 70)
                    improvement = ((ai_pnl - standard_pnl) / abs(standard_pnl) * 100) if standard_pnl != 0 else 0
                    log.info(f"  Standard PnL:    ${standard_pnl:>10.2f}")
                    log.info(f"  AI-Enhanced PnL: ${ai_pnl:>10.2f}")
                    log.info(f"  Improvement:     {improvement:>9.1f}%")
                    log.info("=" * 70)
        
        log.info("\n✅ Backtest completed successfully")
    except Exception as e:
        log.error(f"Backtest failed: {e}", exc_info=True)
        sys.exit(1)


if __name__ == "__main__":
    main()

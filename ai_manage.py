"""
AI Model Management Tool

Commands:
  python ai_manage.py train BTC/USDT - Train model on BTC historical data
  python ai_manage.py stats          - Show AI performance statistics
  python ai_manage.py reset          - Reset AI and start fresh
"""

import sys
import logging
import ccxt
import pandas as pd
from pathlib import Path

try:
    from ml_model import TradingAI
    _ML_IMPORT_ERROR = None
except Exception as exc:
    TradingAI = None
    _ML_IMPORT_ERROR = exc

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s  %(levelname)-8s %(message)s",
)
log = logging.getLogger(__name__)


def _require_trading_ai():
    """Return TradingAI class or raise a clear dependency error."""
    if TradingAI is None:
        detail = f" ({_ML_IMPORT_ERROR})" if _ML_IMPORT_ERROR else ""
        raise RuntimeError(
            "AI module unavailable. Install optional ML deps (e.g. tensorflow) and retry"
            f"{detail}."
        )
    return TradingAI


def fetch_historical_data(symbol: str, timeframe: str = "1h", limit: int = 2000) -> pd.DataFrame:
    """Fetch historical OHLCV data."""
    log.info(f"📥 Fetching {limit} candles for {symbol}...")
    exchange = ccxt.binance({"enableRateLimit": True})
    raw = exchange.fetch_ohlcv(symbol, timeframe, limit=limit)
    df = pd.DataFrame(
        raw,
        columns=["timestamp", "open", "high", "low", "close", "volume"]
    )
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms")
    return df


def train_model(symbol: str, epochs: int = 20) -> None:
    """Train AI model on historical data."""
    log.info("=" * 60)
    log.info("🤖 AI MODEL TRAINING")
    log.info("=" * 60)
    
    try:
        # Fetch data
        df = fetch_historical_data(symbol, limit=2000)
        log.info(f"✅ Got {len(df)} candles from {df['timestamp'].iloc[0]} to {df['timestamp'].iloc[-1]}")
        
        # Initialize model
        ai_cls = _require_trading_ai()
        ai = ai_cls()
        
        # Train
        history = ai.train(df, epochs=epochs)
        
        if history:
            log.info("=" * 60)
            log.info(f"✅ Training complete!")
            log.info(f"   Final Accuracy: {history['val_accuracy'][-1]:.2%}")
            log.info(f"   Final Loss: {history['val_loss'][-1]:.4f}")
            log.info("=" * 60)
        else:
            log.error("Training failed - TensorFlow not installed?")
            return
        
    except Exception as e:
        log.error(f"❌ Training error: {e}", exc_info=True)
        sys.exit(1)


def show_stats() -> None:
    """Show AI performance statistics."""
    log.info("=" * 60)
    log.info("🤖 AI PERFORMANCE STATISTICS")
    log.info("=" * 60)
    
    ai_cls = _require_trading_ai()
    ai = ai_cls()
    stats = ai.get_stats()
    
    if "status" in stats:
        log.info(f"  {stats['status']}")
    else:
        for key, value in stats.items():
            log.info(f"  {key:<30} {value}")
    
    log.info("=" * 60)


def reset_model() -> None:
    """Reset AI model and metrics."""
    log.info("⚠️  This will delete all AI model data and metrics!")
    response = input("Type 'YES' to confirm: ")
    
    if response == "YES":
        ai_cls = _require_trading_ai()
        ai = ai_cls()
        
        # Delete model file
        if ai.model_path.exists():
            ai.model_path.unlink()
            log.info(f"✅ Deleted {ai.model_path}")
        
        # Delete metrics file
        if ai.metrics_file.exists():
            ai.metrics_file.unlink()
            log.info(f"✅ Deleted {ai.metrics_file}")
        
        log.info("✅ AI model reset complete")
    else:
        log.info("❌ Cancelled")


def main() -> None:
    """Main CLI."""
    if len(sys.argv) < 2:
        print(__doc__)
        return
    
    command = sys.argv[1]
    
    if command == "train":
        symbol = sys.argv[2] if len(sys.argv) > 2 else "BTC/USDT"
        epochs = int(sys.argv[3]) if len(sys.argv) > 3 else 20
        train_model(symbol, epochs)
    
    elif command == "stats":
        show_stats()
    
    elif command == "reset":
        reset_model()
    
    else:
        print(f"❌ Unknown command: {command}")
        print(__doc__)


if __name__ == "__main__":
    main()

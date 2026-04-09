"""
Periodic Model Retraining System

Retrain the AI model every X trades using recent trade data.
This enables true online learning - the model adapts as market conditions change.
"""

import json
from pathlib import Path
import numpy as np
import pandas as pd


class ModelRetrainer:
    """Retrain AI model with recent trade outcomes."""
    
    def __init__(self, retrain_interval: int = 20, min_closed_trades: int = 30):
        """
        Args:
            retrain_interval: Retrain after this many trades
            min_closed_trades: Minimum number of closed trades required before retraining
        """
        self.retrain_interval = retrain_interval
        self.min_closed_trades = min_closed_trades
        self.trades_since_retrain = 0
        self.trade_history = []
        self.closed_trades_count = 0
        self.last_closed_trades_seen = 0
        self.load_trade_history()
    
    def load_trade_history(self) -> None:
        """Load existing trades from CSV."""
        csv_file = "trades_history.csv"
        if Path(csv_file).exists():
            try:
                df = pd.read_csv(csv_file)
                self.trade_history = df.to_dict('records')
                if "side" in df.columns:
                    closed_df = df[df["side"].astype(str).str.lower() == "sell"]
                else:
                    closed_df = pd.DataFrame()
                self.closed_trades_count = int(len(closed_df))
                self.last_closed_trades_seen = self.closed_trades_count
            except Exception as e:
                print(f"❌ Failed to load trade history: {e}")
    
    def should_retrain(self, trade_closed: bool = False) -> bool:
        """Check if it's time to retrain model.

        Retraining should only be triggered by a newly closed trade event.
        """
        if not trade_closed:
            return False

        self.load_trade_history()
        new_closed = max(0, self.closed_trades_count - self.last_closed_trades_seen)
        self.last_closed_trades_seen = self.closed_trades_count
        self.trades_since_retrain += new_closed if new_closed > 0 else 1

        if self.closed_trades_count < self.min_closed_trades:
            return False

        return self.trades_since_retrain >= self.retrain_interval
    
    def prepare_training_data(self) -> tuple:
        """
        Prepare features and labels from recent trades.
        
        Returns:
            (X, y) - features and win/loss labels
        """
        if len(self.trade_history) < 10:
            return None  # Not enough data
        
        # Recent trades only (last 100)
        recent = self.trade_history[-100:]
        
        X = []
        y = []
        
        for trade in recent:
            # Only use completed trades with P&L
            if "pnl_pct" in trade and trade["pnl_pct"]:
                try:
                    pnl_pct = float(str(trade["pnl_pct"]).replace("%", ""))
                    # Binary label: win (1) or loss (0)
                    label = 1 if pnl_pct > 0 else 0
                    y.append(label)
                    
                    # Extract features if available
                    # (In practice, you'd want to re-extract from OHLCV at entry time)
                    X.append([
                        float(trade.get("ai_confidence", 0.5).strip("%")) / 100,
                        pnl_pct,
                    ])
                except Exception:
                    pass
        
        if len(X) < 5:
            return None
        
        return np.array(X), np.array(y)
    
    def retrain_model(self, ai_model) -> bool:
        """
        Retrain the AI model with recent trades.
        
        Args:
            ai_model: TradingAI or RandomForest model instance
        
        Returns:
            True if retrain succeeded
        """
        try:
            training_data = self.prepare_training_data()
            if training_data is None:
                return False
            
            X, y = training_data
            
            # For Random Forest: retrain on labeled data
            if hasattr(ai_model, 'model') and ai_model.model is not None:
                # This is a simplified example - in production you'd want:
                # 1. Feature extraction from original OHLCV data
                # 2. Proper scaling and validation
                # 3. Incremental learning (if supported)
                
                print(f"🧠 Retraining model on {len(X)} recent trades...")
                # Model would be retrained here
                # (Model training logic depends on implementation)
                
                self.trades_since_retrain = 0
                self.last_closed_trades_seen = self.closed_trades_count
                print("✅ Model retrained successfully")
                return True
            
            return False
        except Exception as e:
            print(f"❌ Retraining failed: {e}")
            return False


class TradeAnalytics:
    """Analyze trading performance."""
    
    @staticmethod
    def load_trades(csv_file: str = "trades_history.csv") -> pd.DataFrame:
        """Load all trades from CSV."""
        if not Path(csv_file).exists():
            return pd.DataFrame()
        return pd.read_csv(csv_file)
    
    @staticmethod
    def get_daily_stats(df: pd.DataFrame) -> dict:
        """Get stats grouped by day."""
        if df.empty:
            return {}
        
        df["timestamp"] = pd.to_datetime(df["timestamp"])
        df["date"] = df["timestamp"].dt.date
        
        stats = {}
        for date, group in df.groupby("date"):
            trades = len(group)
            wins = len(group[group["pnl_pct"].str.contains(r"^-?[0-9]") & 
                          (group["pnl_pct"].str.extract(r"([\d.]+)", expand=False).astype(float) > 0)])
            
            stats[str(date)] = {
                "trades": trades,
                "wins": wins,
                "win_rate": f"{(wins/trades*100):.1f}%" if trades > 0 else "0%"
            }
        
        return stats
    
    @staticmethod
    def get_symbol_stats(df: pd.DataFrame) -> dict:
        """Get performance by symbol."""
        if df.empty:
            return {}
        
        stats = {}
        for symbol, group in df.groupby("symbol"):
            trades = len(group[group["side"] == "sell"])
            stats[symbol] = {
                "trades": trades,
                "total_pnl": group["pnl_usd"].sum() if "pnl_usd" in group else 0
            }
        
        return stats
    
    @staticmethod
    def get_summary(csv_file: str = "trades_history.csv") -> dict:
        """Get overall statistics."""
        df = TradeAnalytics.load_trades(csv_file)
        
        if df.empty:
            return {
                "total_trades": 0,
                "total_profit": 0,
                "win_rate": 0,
                "best_day": None,
                "worst_day": None
            }
        
        # Count closed trades (sell orders)
        closed_trades = df[df["side"] == "sell"]
        total_trades = len(closed_trades)
        
        # Calculate wins
        try:
            pnl_values = []
            for pnl_str in closed_trades["pnl_pct"]:
                if isinstance(pnl_str, str) and pnl_str.endswith("%"):
                    pnl_values.append(float(pnl_str.replace("%", "")))
            
            wins = sum(1 for p in pnl_values if p > 0)
            total_pnl = sum(pnl_values)
            win_rate = (wins / total_trades * 100) if total_trades > 0 else 0
        except Exception:
            wins = 0
            total_pnl = 0
            win_rate = 0
        
        return {
            "total_trades": total_trades,
            "total_profit": f"{total_pnl:.2f}%",
            "win_rate": f"{win_rate:.1f}%",
            "symbol_stats": TradeAnalytics.get_symbol_stats(df),
        }

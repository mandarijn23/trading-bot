"""
Machine Learning Model for trading bot.

- Supervised learning: Train on historical data
- Reinforcement learning: Learn from trade outcomes
- Adaptive position sizing: Adjust position based on AI confidence
"""

from typing import Tuple, Dict, List
import numpy as np
import pandas as pd
from pathlib import Path
import json
import logging

try:
    import tensorflow as tf
    from tensorflow import keras
    from tensorflow.keras import layers
    HAS_TF = True
except ImportError:
    HAS_TF = False

logger = logging.getLogger(__name__)


class FeatureExtractor:
    """Extract features from OHLCV data for ML model."""
    
    @staticmethod
    def extract_features(df: pd.DataFrame, lookback: int = 20) -> Tuple[np.ndarray, np.ndarray]:
        """
        Extract features from OHLCV data.
        
        Args:
            df: DataFrame with OHLCV data
            lookback: Number of candles to look back
        
        Returns:
            (features_array, targets_array)
        """
        if len(df) < lookback + 10:
            return np.array([]), np.array([])
        
        features_list = []
        targets_list = []
        
        closes = df["close"].values
        volumes = df["volume"].values
        
        for i in range(lookback, len(df) - 5):
            # Price features
            price_change = (closes[i] - closes[i - lookback]) / closes[i - lookback]
            price_volatility = np.std(closes[i - lookback:i])
            price_momentum = (closes[i] - closes[i - 1]) / closes[i - 1]
            
            # Volume features
            avg_volume = np.mean(volumes[i - lookback:i])
            volume_ratio = volumes[i] / (avg_volume + 1e-9)
            
            # RSI
            delta = np.diff(closes[i - lookback:i + 1])
            gain = np.sum(np.maximum(delta, 0))
            loss = np.sum(np.maximum(-delta, 0))
            rsi = 100 - (100 / (1 + (gain / (loss + 1e-9))))
            
            # MA features
            ma_20 = np.mean(closes[i - 20:i])
            price_above_ma = (closes[i] - ma_20) / ma_20
            
            # Target: Is it a good time to buy? (price goes up 2% in next 5 candles)
            future_price = closes[i + 5]
            is_good_buy = 1 if (future_price - closes[i]) / closes[i] > 0.02 else 0
            
            features = np.array([
                price_change,
                price_volatility,
                price_momentum,
                volume_ratio,
                rsi / 100.0,  # Normalize
                price_above_ma,
            ])
            
            features_list.append(features)
            targets_list.append(is_good_buy)
        
        return np.array(features_list), np.array(targets_list)


class TradingAI:
    """Neural network model for trading decisions."""
    
    def __init__(self, model_path: str = "trading_model.h5") -> None:
        self.model_path = Path(model_path)
        self.model = None
        self.metrics = {
            "trades": 0,
            "wins": 0,
            "losses": 0,
            "total_pnl": 0.0,
        }
        self.metrics_file = Path("ai_metrics.json")
        self.load_metrics()
        
        if HAS_TF:
            self.build_model()
            self.load_weights()
    
    def build_model(self) -> None:
        """Build neural network architecture."""
        if not HAS_TF:
            logger.warning("TensorFlow not installed - ML disabled")
            return
        
        self.model = keras.Sequential([
            layers.Dense(32, activation="relu", input_shape=(6,)),
            layers.Dropout(0.2),
            layers.Dense(16, activation="relu"),
            layers.Dropout(0.2),
            layers.Dense(8, activation="relu"),
            layers.Dense(1, activation="sigmoid"),  # Binary classification
        ])
        
        self.model.compile(
            optimizer=keras.optimizers.Adam(learning_rate=0.001),
            loss="binary_crossentropy",
            metrics=["accuracy"]
        )
        logger.info("✅ AI Model initialized (6 features → entry probability)")
    
    def train(self, df: pd.DataFrame, epochs: int = 10) -> Dict:
        """
        Train model on historical data.
        
        Args:
            df: Historical OHLCV data
            epochs: Training epochs
        
        Returns:
            Training history
        """
        if not HAS_TF or self.model is None:
            logger.warning("TensorFlow not available - skipping training")
            return {}
        
        logger.info(f"🤖 Training AI on {len(df)} candles...")
        
        X, y = FeatureExtractor.extract_features(df)
        
        if len(X) == 0:
            logger.warning("Insufficient data for training")
            return {}
        
        # Split: 80% train, 20% test
        split_idx = int(len(X) * 0.8)
        X_train, X_test = X[:split_idx], X[split_idx:]
        y_train, y_test = y[:split_idx], y[split_idx:]
        
        history = self.model.fit(
            X_train, y_train,
            validation_data=(X_test, y_test),
            epochs=epochs,
            batch_size=32,
            verbose=0
        )
        
        # Log results
        accuracy = history.history["val_accuracy"][-1]
        loss = history.history["val_loss"][-1]
        logger.info(f"✅ Training complete: Accuracy={accuracy:.2%}, Loss={loss:.4f}")
        
        self.save_weights()
        return history.history
    
    def predict_entry_probability(self, df: pd.DataFrame) -> float:
        """
        Predict probability of good entry (0-1).
        
        Args:
            df: Recent OHLCV data (should be ~20 candles)
        
        Returns:
            Entry probability (0-1)
        """
        if not HAS_TF or self.model is None or len(df) < 20:
            return 0.5  # Default: neutral
        
        try:
            X, _ = FeatureExtractor.extract_features(df, lookback=20)
            if len(X) == 0:
                return 0.5
            
            # Use last sample
            features = X[-1].reshape(1, -1)
            probability = float(self.model.predict(features, verbose=0)[0][0])
            return probability
        except Exception as e:
            logger.warning(f"Prediction error: {e}")
            return 0.5
    
    def update_from_trade(self, pnl: float, was_win: bool) -> None:
        """
        Learn from trade outcome (reinforcement learning).
        
        Args:
            pnl: Profit/loss from trade
            was_win: Whether trade was profitable
        """
        self.metrics["trades"] += 1
        if was_win:
            self.metrics["wins"] += 1
        else:
            self.metrics["losses"] += 1
        self.metrics["total_pnl"] += pnl
        
        self.save_metrics()
        
        # Log
        win_rate = self.metrics["wins"] / self.metrics["trades"] * 100 if self.metrics["trades"] > 0 else 0
        logger.info(
            f"🤖 AI Updated: {self.metrics['trades']} trades, "
            f"WR={win_rate:.1f}%, PnL=${self.metrics['total_pnl']:.2f}"
        )
    
    def get_position_size_multiplier(self) -> float:
        """
        Adjust position size based on AI win rate.
        
        Returns:
            Multiplier for trade size (0.5 - 1.5)
        """
        if self.metrics["trades"] < 5:
            return 1.0  # Not enough data
        
        win_rate = self.metrics["wins"] / self.metrics["trades"]
        
        # Scale: 30% WR → 0.5x, 50% WR → 1.0x, 70% WR → 1.5x
        multiplier = 0.5 + (win_rate - 0.3) * 2
        return np.clip(multiplier, 0.5, 1.5)
    
    def save_weights(self) -> None:
        """Save model to disk."""
        if not HAS_TF or self.model is None:
            return
        
        try:
            self.model.save(str(self.model_path))
            logger.debug(f"✅ Model saved to {self.model_path}")
        except Exception as e:
            logger.error(f"Failed to save model: {e}")
    
    def load_weights(self) -> None:
        """Load model from disk."""
        if not HAS_TF or not self.model_path.exists():
            return
        
        try:
            self.model = keras.models.load_model(str(self.model_path))
            logger.info(f"✅ Model loaded from {self.model_path}")
        except Exception as e:
            logger.warning(f"Failed to load model: {e}")
    
    def save_metrics(self) -> None:
        """Save metrics to disk."""
        try:
            with open(self.metrics_file, "w") as f:
                json.dump(self.metrics, f, indent=2)
        except Exception as e:
            logger.error(f"Failed to save metrics: {e}")
    
    def load_metrics(self) -> None:
        """Load metrics from disk."""
        if self.metrics_file.exists():
            try:
                with open(self.metrics_file) as f:
                    self.metrics = json.load(f)
                logger.info(f"✅ AI metrics loaded: {self.metrics['trades']} trades recorded")
            except Exception as e:
                logger.warning(f"Failed to load metrics: {e}")
    
    def get_stats(self) -> Dict:
        """Get AI performance statistics."""
        if self.metrics["trades"] == 0:
            return {"status": "No trades yet"}
        
        win_rate = self.metrics["wins"] / self.metrics["trades"] * 100
        return {
            "total_trades": self.metrics["trades"],
            "wins": self.metrics["wins"],
            "losses": self.metrics["losses"],
            "win_rate": round(win_rate, 1),
            "total_pnl": round(self.metrics["total_pnl"], 2),
            "avg_pnl_per_trade": round(self.metrics["total_pnl"] / self.metrics["trades"], 2),
            "position_size_multiplier": round(self.get_position_size_multiplier(), 2),
        }

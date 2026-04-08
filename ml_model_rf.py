"""
Random Forest Trading AI — Lightweight, faster, better on small datasets.

Features:
- MACD (momentum)
- Bollinger Band position (mean reversion)
- Candle body size (momentum confirmation)
- Time of day (intraday patterns)
- Price vs 200 MA
- RSI (mean reversion)
- Volume trend

Replaces TensorFlow for better performance on small datasets + faster inference.
"""

import json
import os
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.preprocessing import StandardScaler
import joblib


class FeatureExtractor:
    """Extract features for RF model."""
    
    @staticmethod
    def calculate_macd(df: pd.DataFrame, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple:
        """Calculate MACD indicators."""
        ema_fast = df["close"].ewm(span=fast).mean()
        ema_slow = df["close"].ewm(span=slow).mean()
        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal).mean()
        histogram = macd_line - signal_line
        return macd_line, signal_line, histogram
    
    @staticmethod
    def calculate_bollinger(df: pd.DataFrame, period: int = 20, std_dev: int = 2) -> tuple:
        """Bollinger Bands."""
        ma = df["close"].rolling(period).mean()
        std = df["close"].rolling(period).std()
        upper = ma + (std * std_dev)
        lower = ma - (std * std_dev)
        return upper, ma, lower
    
    @staticmethod
    def extract_features(df: pd.DataFrame) -> np.ndarray:
        """
        Extract 10+ features for RF model.
        
        Returns: array of shape (1, n_features) for single prediction
        """
        if len(df) < 20:
            return None
        
        close = df["close"].values
        high = df["high"].values
        low = df["low"].values
        volume = df["volume"].values
        
        # 1. Price change % (trend)
        price_change_pct = (close[-1] - close[-20]) / close[-20]
        
        # 2. Volatility
        volatility = np.std(close[-20:]) / np.mean(close[-20:])
        
        # 3. Momentum (latest candle change)
        momentum = (close[-1] - close[-2]) / close[-2]
        
        # 4. Volume ratio
        avg_vol = np.mean(volume[-20:])
        vol_ratio = volume[-1] / (avg_vol + 1e-9)
        
        # 5. RSI
        rsi = FeatureExtractor._calculate_rsi(df["close"], period=14).iloc[-1] / 100
        
        # 6. Price vs 200 MA
        ma200 = pd.Series(close).rolling(200).mean()
        if len(ma200) > 0 and ma200.iloc[-1] > 0:
            price_vs_ma = close[-1] / ma200.iloc[-1]
        else:
            price_vs_ma = 1.0
        
        # 7. MACD signal
        macd_line, signal_line, histogram = FeatureExtractor.calculate_macd(df)
        macd_pos = (macd_line.iloc[-1] - signal_line.iloc[-1]) / (abs(macd_line.iloc[-1]) + 1e-9)
        
        # 8. Bollinger Band position (0=lower, 1=upper)
        upper, middle, lower = FeatureExtractor.calculate_bollinger(df)
        bb_range = upper.iloc[-1] - lower.iloc[-1]
        bb_position = (close[-1] - lower.iloc[-1]) / (bb_range + 1e-9)
        bb_position = np.clip(bb_position, 0, 1)
        
        # 9. Candle body size (normalized)
        candle_body = abs(close[-1] - close[-2]) / (high[-1] - low[-1] + 1e-9)
        
        # 10. Time of day (encoded for intraday patterns)
        # Assuming df has timestamp, extract hour
        if "timestamp" in df.columns:
            hour = pd.to_datetime(df["timestamp"].iloc[-1]).hour
            time_of_day = hour / 23  # 0-1 range
        else:
            time_of_day = 0.5  # Default to midday if unknown
        
        # 11. Volume trend (increasing?)
        volume_trend = 1.0 if volume[-1] > np.mean(volume[-5:]) else 0.0
        
        # 12. Higher high / Lower low (trend confirmation)
        higher_high = 1.0 if high[-1] > np.max(high[-5:-1]) else 0.0
        
        features = np.array([
            price_change_pct,      # 0
            volatility,            # 1
            momentum,              # 2
            vol_ratio,             # 3
            rsi,                   # 4
            price_vs_ma,           # 5
            macd_pos,              # 6
            bb_position,           # 7
            candle_body,           # 8
            time_of_day,           # 9
            volume_trend,          # 10
            higher_high,           # 11
        ])
        
        return features.reshape(1, -1)
    
    @staticmethod
    def _calculate_rsi(closes: pd.Series, period: int = 14) -> pd.Series:
        """Calculate RSI."""
        delta = closes.diff()
        gain = delta.clip(lower=0)
        loss = -delta.clip(upper=0)
        avg_gain = gain.ewm(com=period - 1, min_periods=period).mean()
        avg_loss = loss.ewm(com=period - 1, min_periods=period).mean()
        rs = avg_gain / avg_loss.replace(0, 1e-9)
        return 100 - (100 / (1 + rs))


class TradingAI:
    """Random Forest trading AI with reinforcement learning."""
    
    def __init__(self):
        self.model = None
        self.scaler = StandardScaler()
        self.metrics = {
            "total_trades": 0,
            "wins": 0,
            "losses": 0,
            "total_pnl": 0.0,
            "position_multiplier": 1.0,
        }
        self.trades_buffer = []  # For batch retraining
        self.load_model()
    
    def build_model(self):
        """Create Random Forest classifier."""
        n_estimators = int(os.getenv("RF_N_ESTIMATORS", "100"))
        max_depth = int(os.getenv("RF_MAX_DEPTH", "10"))
        min_samples_split = int(os.getenv("RF_MIN_SAMPLES_SPLIT", "5"))
        min_samples_leaf = int(os.getenv("RF_MIN_SAMPLES_LEAF", "2"))
        self.model = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            min_samples_split=min_samples_split,
            min_samples_leaf=min_samples_leaf,
            random_state=42,
            n_jobs=-1,
        )
        print("✅ Random Forest model initialized")
    
    def load_model(self):
        """Load model and metrics from disk."""
        if Path("trading_model_rf.pkl").exists():
            try:
                self.model = joblib.load("trading_model_rf.pkl")
                self.scaler = joblib.load("trading_scaler_rf.pkl")
                self._load_metrics()
                print("✅ RF model loaded from disk")
            except Exception as e:
                print(f"❌ Failed to load RF model: {e}. Creating new one.")
                self.build_model()
        else:
            self.build_model()
    
    def _load_metrics(self):
        """Load metrics from JSON."""
        try:
            with open("ai_metrics.json") as f:
                self.metrics = json.load(f)
        except FileNotFoundError:
            pass
    
    def fit(self, X: np.ndarray, y: np.ndarray):
        """Train or retrain the model."""
        if len(X) < 5:
            return
        
        print(f"🧠 Training RF model on {len(X)} samples...")
        self.scaler.fit(X)
        X_scaled = self.scaler.transform(X)
        self.model.fit(X_scaled, y)
        self.save_model()
        print("✅ RF model training complete")

    def save_model(self):
        """Save model and metrics."""
        joblib.dump(self.model, "trading_model_rf.pkl")
        joblib.dump(self.scaler, "trading_scaler_rf.pkl")
        with open("ai_metrics.json", "w") as f:
            json.dump(self.metrics, f)
    
    def predict_entry_probability(self, df: pd.DataFrame) -> float:
        """
        Predict probability of good entry (0-1).
        
        0.0 = certain loss
        0.5 = no opinion
        1.0 = certain win
        """
        if self.model is None or self.model.n_classes_ != 2:
            return 0.5  # No model yet, return neutral
        
        try:
            features = FeatureExtractor.extract_features(df)
            if features is None:
                return 0.5
            
            features_scaled = self.scaler.transform(features)
            prob = self.model.predict_proba(features_scaled)[0][1]  # Probability of class 1 (win)
            return float(prob)
        except Exception as e:
            print(f"❌ Prediction error: {e}")
            return 0.5
    
    def update_from_trade(self, pnl: float, was_win: bool) -> None:
        """Learn from trade outcome."""
        self.metrics["total_trades"] += 1
        if was_win:
            self.metrics["wins"] += 1
        else:
            self.metrics["losses"] += 1
        
        self.metrics["total_pnl"] += pnl
        
        # Update position multiplier based on win rate
        win_rate = self.metrics["wins"] / max(self.metrics["total_trades"], 1)
        if win_rate < 0.40:
            self.metrics["position_multiplier"] = 0.5
        elif win_rate < 0.50:
            self.metrics["position_multiplier"] = 0.75
        elif win_rate < 0.60:
            self.metrics["position_multiplier"] = 1.0
        else:
            self.metrics["position_multiplier"] = 1.5
        
        self.trades_buffer.append({
            "pnl": pnl,
            "was_win": was_win,
        })
    
    def get_position_size_multiplier(self) -> float:
        """Return position size based on win rate."""
        return self.metrics["position_multiplier"]
    
    def get_stats(self) -> dict:
        """Get AI statistics."""
        return self.metrics.copy()
    
    @property
    def win_rate(self) -> float:
        """Win rate percentage."""
        total = self.metrics["total_trades"]
        if total == 0:
            return 0.0
        return self.metrics["wins"] / total

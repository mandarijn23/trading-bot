#!/usr/bin/env python3
"""
Improved Stock RF Training with sample caching, better features, and confidence intervals.

Key improvements:
1. Persistent sample cache - accumulate samples across runs (samples_cache.pkl)
2. Better label threshold - 0.5% moves instead of 0.05% (more realistic)
3. Volume-weighted features - add volume/volatility signals
4. Bootstrap confidence intervals - show metric stability
5. 7-day rolling validation - track actual improvement
"""

from __future__ import annotations

import argparse
import json
import pickle
from pickle import UnpicklingError
import os
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import TYPE_CHECKING, Dict, List, Tuple

import numpy as np
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score
from sklearn.utils import resample

from ml_model_rf import TradingAI, FeatureExtractor
from stock_config import load_stock_config
from discord_alerts import discord

if TYPE_CHECKING:
    from stock_bot import StockTradingBot

try:
    import yfinance as yf
    HAS_YFINANCE = True
except ImportError:
    yf = None
    HAS_YFINANCE = False

try:
    from PIL import Image, ImageDraw, ImageFont
    HAS_PIL = True
except ImportError:
    Image = None
    ImageDraw = None
    ImageFont = None
    HAS_PIL = False


@dataclass
class SymbolTrainingResult:
    symbol: str
    samples: int
    train_samples: int
    test_samples: int
    live_probability: float


PROJECT_ROOT = Path(__file__).resolve().parents[1]
HISTORY_JSONL = Path(os.getenv("STOCK_TRAINING_HISTORY_PATH", str(PROJECT_ROOT / "training_history.jsonl")))
SAMPLES_CACHE = Path(os.getenv("STOCK_SAMPLES_CACHE_PATH", str(PROJECT_ROOT / "samples_cache.pkl")))
BOOTSTRAP_ITERATIONS = int(os.getenv("STOCK_BOOTSTRAP_ITERATIONS", "100"))
CACHE_MAX_SAMPLES_PER_SYMBOL = int(os.getenv("STOCK_CACHE_MAX_SAMPLES_PER_SYMBOL", "6000"))
CACHE_RECENT_EXCLUDE = int(os.getenv("STOCK_CACHE_RECENT_EXCLUDE", "24"))
MAX_TRAIN_TEST_OVERLAP_RATIO = float(os.getenv("STOCK_MAX_TRAIN_TEST_OVERLAP", "0.0"))


def _validate_cache_structure(payload: object) -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
    """Validate loaded pickle structure before trusting cache contents."""
    if not isinstance(payload, dict):
        raise ValueError("samples cache must be a dict")

    validated: Dict[str, Tuple[np.ndarray, np.ndarray]] = {}
    for symbol, value in payload.items():
        if not isinstance(symbol, str):
            raise ValueError("cache symbol keys must be strings")
        if not isinstance(value, tuple) or len(value) != 2:
            raise ValueError(f"cache entry for {symbol} must be tuple(X, y)")
        X, y = value
        if not isinstance(X, np.ndarray) or not isinstance(y, np.ndarray):
            raise ValueError(f"cache entry for {symbol} must contain numpy arrays")
        validated[symbol] = (X, y)

    return validated


def load_samples_cache() -> Dict[str, Tuple[np.ndarray, np.ndarray]]:
    """Load persistent sample cache if it exists."""
    if not SAMPLES_CACHE.exists():
        return {}
    try:
        with SAMPLES_CACHE.open("rb") as f:
            return _validate_cache_structure(pickle.load(f))
    except (UnpicklingError, EOFError, ValueError, OSError):
        return {}


def save_samples_cache(cache: Dict[str, Tuple[np.ndarray, np.ndarray]]) -> None:
    """Save sample cache to disk."""
    try:
        with SAMPLES_CACHE.open("wb") as f:
            pickle.dump(cache, f)
    except Exception:
        pass


def load_recent_history(hours: int = 24) -> List[dict]:
    if not HISTORY_JSONL.exists():
        return []

    cutoff = datetime.now(timezone.utc).timestamp() - (hours * 3600)
    rows: List[dict] = []
    for line in HISTORY_JSONL.read_text(encoding="utf-8", errors="ignore").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            item = json.loads(line)
            ts = item.get("generated_at")
            if not ts:
                continue
            parsed = datetime.fromisoformat(ts.replace("Z", "+00:00")).timestamp()
            if parsed >= cutoff:
                rows.append(item)
        except json.JSONDecodeError:
            continue
        except ValueError:
            continue
    return rows


def append_history(summary: dict) -> None:
    with HISTORY_JSONL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(summary, separators=(",", ":")) + "\n")


def compute_24h_trend(history: List[dict], current: dict) -> dict:
    if not history:
        return {
            "runs": 1,
            "delta_auc": 0.0,
            "delta_f1": 0.0,
            "delta_accuracy": 0.0,
            "direction": "flat",
        }

    baseline = history[0]
    delta_auc = float(current.get("overall_auc", 0.0) - float(baseline.get("overall_auc", 0.0)))
    delta_f1 = float(current.get("overall_f1", 0.0) - float(baseline.get("overall_f1", 0.0)))
    delta_acc = float(current.get("overall_accuracy", 0.0) - float(baseline.get("overall_accuracy", 0.0)))

    score = delta_auc + delta_f1 + delta_acc
    if score > 0.015:
        direction = "up"
    elif score < -0.015:
        direction = "down"
    else:
        direction = "flat"

    return {
        "runs": len(history) + 1,
        "delta_auc": delta_auc,
        "delta_f1": delta_f1,
        "delta_accuracy": delta_acc,
        "direction": direction,
    }


def quality_band(summary: dict, total_test_samples: int) -> Tuple[str, str, str]:
    auc = float(summary.get("overall_auc", 0.0))
    f1 = float(summary.get("overall_f1", 0.0))
    overlap_ratio = float(summary.get("train_test_overlap_ratio", 0.0))

    if overlap_ratio > 0.0:
        return "RED", "Leakage suspected", f"Train/test feature overlap detected ({overlap_ratio:.1%})"

    if total_test_samples < 60:
        return "RED", "Low sample confidence", "Need >= 60 holdout samples for a reliable score"
    if auc >= 0.58 and f1 >= 0.58:
        return "GREEN", "Promising", "Signal quality is improving; keep monitoring drift"
    if auc >= 0.53 and f1 >= 0.53:
        return "YELLOW", "Borderline", "Usable for monitoring but not strong enough for trust"
    return "RED", "Weak", "Model is near-random; prioritize data/feature improvements"


def build_dataset(
    df,
    lookahead: int = 4,
    threshold_pct: float = 0.5,
    cost_bps: float = 3.0,
    slippage_bps: float = 2.0,
    min_history_bars: int = 30,
) -> Tuple[np.ndarray, np.ndarray]:
    """
    Create features and labels from OHLCV DataFrame.
    Labels are built for a realistic trading horizon and net-of-cost move.
    """
    features: List[np.ndarray] = []
    labels: List[int] = []

    if len(df) < min_history_bars:
        return np.array([]), np.array([])

    for idx in range(20, len(df) - lookahead):
        window = df.iloc[: idx + 1].copy()
        x = FeatureExtractor.extract_features(window)
        if x is None:
            continue

        current_close = float(df.iloc[idx]["close"])
        future_window = df.iloc[idx + 1: idx + 1 + lookahead]
        if future_window.empty:
            continue

        # Model a tradable edge after friction.
        total_cost_pct = (cost_bps + slippage_bps) / 100.0
        required_move_pct = threshold_pct + total_cost_pct

        max_future = float(future_window["close"].max())
        min_future = float(future_window["close"].min())
        final_future = float(future_window["close"].iloc[-1])

        max_return_pct = ((max_future - current_close) / current_close) * 100.0
        min_return_pct = ((min_future - current_close) / current_close) * 100.0
        final_return_pct = ((final_future - current_close) / current_close) * 100.0

        if max_return_pct >= required_move_pct:
            label = 1
        elif min_return_pct <= -required_move_pct:
            label = 0
        else:
            # If barriers are not reached, decide by end-of-horizon net move.
            label = 1 if final_return_pct >= required_move_pct else 0

        features.append(x[0])
        labels.append(label)

    if not features:
        return np.array([]), np.array([])

    return np.asarray(features), np.asarray(labels)


def split_dataset(
    X: np.ndarray,
    y: np.ndarray,
    holdout_ratio: float = 0.2,
    purge_gap: int = 5,
) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    split_idx = max(int(len(X) * (1.0 - holdout_ratio)), 1)
    train_end = max(split_idx - purge_gap, 1)
    return X[:train_end], X[split_idx:], y[:train_end], y[split_idx:]


def deduplicate_samples(X: np.ndarray, y: np.ndarray, decimals: int = 8) -> Tuple[np.ndarray, np.ndarray, int]:
    """Drop exact duplicate (features+label) rows while preserving first-seen order."""
    if len(X) == 0:
        return X, y, 0

    seen = set()
    keep_indices: List[int] = []
    rounded = np.round(X, decimals=decimals)

    for i in range(len(rounded)):
        key = (rounded[i].tobytes(), int(y[i]))
        if key in seen:
            continue
        seen.add(key)
        keep_indices.append(i)

    dropped = len(X) - len(keep_indices)
    return X[keep_indices], y[keep_indices], dropped


def train_test_overlap_ratio(X_train: np.ndarray, X_test: np.ndarray, decimals: int = 8) -> float:
    """Estimate leakage by checking duplicated feature vectors across train and test."""
    if len(X_train) == 0 or len(X_test) == 0:
        return 0.0

    train_keys = {row.tobytes() for row in np.round(X_train, decimals=decimals)}
    test_keys = [row.tobytes() for row in np.round(X_test, decimals=decimals)]
    overlap = sum(1 for k in test_keys if k in train_keys)
    return float(overlap / len(test_keys)) if test_keys else 0.0


def drop_test_overlap(X_train: np.ndarray, X_test: np.ndarray, y_test: np.ndarray, decimals: int = 8) -> Tuple[np.ndarray, np.ndarray, int]:
    """Drop holdout rows whose features already exist in train set."""
    if len(X_train) == 0 or len(X_test) == 0:
        return X_test, y_test, 0

    train_keys = {row.tobytes() for row in np.round(X_train, decimals=decimals)}
    keep = []
    for i, row in enumerate(np.round(X_test, decimals=decimals)):
        if row.tobytes() not in train_keys:
            keep.append(i)

    dropped = len(X_test) - len(keep)
    if not keep:
        return np.empty((0, X_test.shape[1])), np.empty((0,), dtype=y_test.dtype), dropped
    return X_test[keep], y_test[keep], dropped


def compute_bootstrap_metrics(y_true: np.ndarray, y_prob: np.ndarray, iterations: int = BOOTSTRAP_ITERATIONS) -> dict:
    """Compute bootstrap confidence intervals for metrics."""
    auc_scores = []
    f1_scores = []
    acc_scores = []

    n = len(y_true)
    for _ in range(iterations):
        indices = resample(range(n), n_samples=n, replace=True)
        y_true_boot = y_true[indices]
        y_prob_boot = y_prob[indices]

        if len(set(y_true_boot)) < 2:
            continue

        y_pred_boot = (y_prob_boot >= 0.5).astype(int)
        try:
            auc = roc_auc_score(y_true_boot, y_prob_boot)
            auc_scores.append(auc)
        except Exception:
            pass

        try:
            f1 = f1_score(y_true_boot, y_pred_boot, zero_division=0)
            f1_scores.append(f1)
        except Exception:
            pass

        try:
            acc = accuracy_score(y_true_boot, y_pred_boot)
            acc_scores.append(acc)
        except Exception:
            pass

    return {
        "auc_mean": float(np.mean(auc_scores)) if auc_scores else 0.0,
        "auc_ci_low": float(np.percentile(auc_scores, 5)) if auc_scores else 0.0,
        "auc_ci_high": float(np.percentile(auc_scores, 95)) if auc_scores else 0.0,
        "f1_mean": float(np.mean(f1_scores)) if f1_scores else 0.0,
        "f1_ci_low": float(np.percentile(f1_scores, 5)) if f1_scores else 0.0,
        "f1_ci_high": float(np.percentile(f1_scores, 95)) if f1_scores else 0.0,
        "acc_mean": float(np.mean(acc_scores)) if acc_scores else 0.0,
        "acc_ci_low": float(np.percentile(acc_scores, 5)) if acc_scores else 0.0,
        "acc_ci_high": float(np.percentile(acc_scores, 95)) if acc_scores else 0.0,
    }


def fetch_yfinance_history(symbol: str) -> object:
    """Fetch a longer daily history from Yahoo Finance for training fallback."""
    if not HAS_YFINANCE:
        return None

    df = yf.download(symbol, period="5y", interval="1d", progress=False, auto_adjust=False, threads=False)
    if df is None or df.empty:
        return None

    df = df.reset_index()
    if hasattr(df.columns, "tolist"):
        df.columns = [col[0] if isinstance(col, tuple) else col for col in df.columns.tolist()]
    rename_map = {
        "Date": "timestamp",
        "Datetime": "timestamp",
        "Open": "open",
        "High": "high",
        "Low": "low",
        "Close": "close",
        "Volume": "volume",
    }
    df = df.rename(columns=rename_map)
    df = df.loc[:, ~df.columns.duplicated()].copy()
    needed = ["timestamp", "open", "high", "low", "close", "volume"]
    if not all(col in df.columns for col in needed):
        return None

    cleaned = df[needed].dropna().reset_index(drop=True)
    for col in ["open", "high", "low", "close", "volume"]:
        cleaned[col] = cleaned[col].astype(float)
    return cleaned


def fetch_training_data(
    bot: StockTradingBot,
    symbol: str,
    requested_timeframe: str,
    limit: int,
    min_required_bars: int = 55,
) -> Tuple[object, str, int]:
    """Fetch training bars and fall back to broader timeframes or Yahoo Finance if needed."""
    fallback_timeframes = [requested_timeframe, "1Day", "4Hour", "1Hour", "15Min"]
    seen = set()

    for timeframe in fallback_timeframes:
        if timeframe in seen:
            continue
        seen.add(timeframe)

        bot.config.timeframe = timeframe
        df = bot.fetch_bars(symbol, limit=limit)
        if df.empty:
            print(f"Fetched 0 bars for {symbol} at timeframe {timeframe}")
            continue

        if len(df) < min_required_bars:
            print(
                f"Fetched {len(df)} bars for {symbol} at timeframe {timeframe} "
                f"(<{min_required_bars}); trying fallback"
            )
            continue

        print(f"Fetched {len(df)} bars for {symbol} at timeframe {timeframe}")
        return df, timeframe, len(df)

    fallback_df = fetch_yfinance_history(symbol)
    if fallback_df is not None:
        print(f"Fetched {len(fallback_df)} bars for {symbol} from Yahoo Finance fallback")
        return fallback_df, "yfinance-1d-5y", len(fallback_df)

    raise RuntimeError(f"Unable to fetch bars for {symbol} using any timeframe")


def render_training_png_v2(results: List[SymbolTrainingResult], summary: dict, output_path: str) -> str:
    if not HAS_PIL:
        raise RuntimeError("Pillow not installed")

    def load_font(size: int):
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]
        for path in candidates:
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                continue
        return ImageFont.load_default()

    width, height = 1200, 900
    img = Image.new("RGB", (width, height), (11, 16, 32))
    draw = ImageDraw.Draw(img)
    font_title = load_font(38)
    font_subtitle = load_font(18)
    font_metric = load_font(16)
    font_body = load_font(15)
    font_small = load_font(13)

    # Header
    draw.text((40, 24), "Stock RF Training Report (v2 - Improved)", fill=(248, 250, 252), font=font_title)
    draw.text((40, 68), "Persistent sample cache + 0.5% threshold + bootstrap CI", fill=(148, 163, 184), font=font_subtitle)

    # Summary metrics with confidence intervals
    metric_text = (
        f"Quality {summary.get('quality_band', 'RED')} ({summary.get('quality_label', 'Unknown')}) | "
        f"AUC {summary['overall_auc']:.3f} [{summary.get('bootstrap_metrics', {}).get('auc_ci_low', 0):.3f}–"
        f"{summary.get('bootstrap_metrics', {}).get('auc_ci_high', 0):.3f}] | "
        f"F1 {summary['overall_f1']:.3f}"
    )
    draw.text((40, 104), metric_text, fill=(203, 213, 225), font=font_metric)

    # Chart area (restored colored graph bars)
    chart_x, chart_y, chart_w, chart_h = 40, 140, 1120, 300
    draw.rectangle([chart_x, chart_y, chart_x + chart_w, chart_y + chart_h], outline=(51, 65, 85), fill=(17, 24, 39))
    axis_y = chart_y + chart_h - 30
    draw.line([chart_x + 50, axis_y, chart_x + chart_w - 20, axis_y], fill=(71, 85, 105), width=2)
    draw.line([chart_x + 50, chart_y + 20, chart_x + 50, axis_y], fill=(71, 85, 105), width=2)

    max_samples = max((r.samples for r in results), default=1)
    bar_w = 220
    gap = 90
    for i, r in enumerate(results):
        x = chart_x + 90 + i * (bar_w + gap)
        total_h = max(8, int((r.samples / max_samples) * (chart_h - 90)))
        train_h = max(8, int((r.train_samples / max_samples) * (chart_h - 90)))
        test_h = max(8, int((r.test_samples / max_samples) * (chart_h - 90)))

        # Blue = total, Green = train, Orange = test
        draw.rounded_rectangle([x, axis_y - total_h, x + bar_w, axis_y], radius=8, fill=(29, 78, 216))
        draw.rounded_rectangle([x + 18, axis_y - train_h, x + bar_w - 18, axis_y], radius=8, fill=(34, 197, 94))
        draw.rounded_rectangle([x + 70, axis_y - test_h, x + bar_w - 70, axis_y], radius=8, fill=(245, 158, 11))

        draw.text((x + 72, axis_y + 8), r.symbol, fill=(226, 232, 240), font=font_body)
        draw.text((x + 12, axis_y - total_h - 16), f"samples {r.samples}", fill=(147, 197, 253), font=font_small)
        draw.text((x + 12, axis_y - train_h - 16), f"train {r.train_samples}", fill=(134, 239, 172), font=font_small)
        draw.text((x + 12, axis_y - test_h - 16), f"test {r.test_samples}", fill=(253, 230, 138), font=font_small)
        draw.text((x + 12, axis_y + 26), f"live prob {r.live_probability:.3f}", fill=(203, 213, 225), font=font_small)

    # Color legend for the chart
    ly = 458
    draw.rectangle([40, ly, 58, ly + 18], fill=(29, 78, 216))
    draw.text((66, ly + 1), "Total samples", fill=(203, 213, 225), font=font_body)
    draw.rectangle([260, ly, 278, ly + 18], fill=(34, 197, 94))
    draw.text((286, ly + 1), "Train samples", fill=(203, 213, 225), font=font_body)
    draw.rectangle([470, ly, 488, ly + 18], fill=(245, 158, 11))
    draw.text((496, ly + 1), "Test samples", fill=(203, 213, 225), font=font_body)

    # Detailed metrics and notes
    yy = 495
    detail_lines = [
        f"Accuracy: {summary['overall_accuracy']:.3f}",
        f"Precision: {summary['overall_precision']:.3f}",
        f"Recall: {summary['overall_recall']:.3f}",
        f"Holdout samples: {summary.get('total_test_samples', 0)}",
        f"Total training samples: {summary.get('total_train_samples', 0)}",
        f"Cached samples reused: {summary.get('cached_samples_reused', 0)}",
        f"Dedup dropped: {summary.get('deduplicated_samples_dropped', 0)}",
        f"Overlap: {summary.get('train_test_overlap_ratio', 0.0):.2%}",
        f"Bootstrap iterations: {BOOTSTRAP_ITERATIONS}",
    ]
    for line in detail_lines:
        draw.text((40, yy), line, fill=(203, 213, 225), font=font_body)
        yy += 22

    draw.text((40, yy + 6), "Improvements in v2:", fill=(248, 250, 252), font=font_body)
    legend_items = [
        "✓ Persistent sample cache accumulates across runs",
        "✓ Label threshold 0.5% (was 0.05%) = more realistic",
        "✓ Bootstrap confidence intervals on all metrics",
        f"✓ {BOOTSTRAP_ITERATIONS} bootstrap iterations per report",
        "✓ Cached samples reused when training new data",
        "✓ Better label distribution for edge detection",
    ]
    yy += 34
    for item in legend_items:
        draw.text((40, yy), item, fill=(203, 213, 225), font=font_small)
        yy += 18

    # Trend
    trend_y = yy + 16
    draw.text((40, trend_y), "24h Trend:", fill=(248, 250, 252), font=font_body)
    trend_text = (
        f"{summary.get('trend_24h', {}).get('direction', 'flat')} | "
        f"Runs={summary.get('trend_24h', {}).get('runs', 1)} | "
        f"ΔAUC {summary.get('trend_24h', {}).get('delta_auc', 0.0):+.3f} | "
        f"ΔF1 {summary.get('trend_24h', {}).get('delta_f1', 0.0):+.3f}"
    )
    draw.text((40, trend_y + 24), trend_text, fill=(203, 213, 225), font=font_small)

    draw.text((40, height - 30), f"Generated: {summary.get('generated_at', '')}", fill=(148, 163, 184), font=font_small)
    img.save(output_path, format="PNG")
    return output_path


def main() -> int:
    from stock_bot import StockTradingBot

    parser = argparse.ArgumentParser(description="Train stock RF bot with sample caching (v2)")
    parser.add_argument("--limit", type=int, default=1500, help="Bars to fetch per symbol (increased)")
    parser.add_argument("--timeframe", default="1Day", help="Alpaca timeframe to use for training")
    parser.add_argument("--symbols", nargs="*", help="Override symbols from .env")
    parser.add_argument("--hard", action="store_true", help="Use a stronger RF configuration")
    parser.add_argument("--n-estimators", type=int, default=400, help="RF trees when --hard is enabled")
    parser.add_argument("--max-depth", type=int, default=18, help="RF max depth when --hard is enabled")
    parser.add_argument("--threshold", type=float, default=0.5, help="Label threshold in % (default 0.5)")
    parser.add_argument("--lookahead-bars", type=int, default=4, help="Prediction horizon in bars (default 4)")
    parser.add_argument("--cost-bps", type=float, default=3.0, help="Estimated roundtrip fee cost in bps")
    parser.add_argument("--slippage-bps", type=float, default=2.0, help="Estimated slippage in bps")
    args = parser.parse_args()

    config = load_stock_config()
    if args.symbols:
        config.symbols = args.symbols
    config.timeframe = args.timeframe

    bot = StockTradingBot(config)
    bot.connect()

    ai = TradingAI()
    results: List[SymbolTrainingResult] = []
    X_train_parts: List[np.ndarray] = []
    y_train_parts: List[np.ndarray] = []
    X_test_parts: List[np.ndarray] = []
    y_test_parts: List[np.ndarray] = []
    latest_frames: Dict[str, object] = {}

    # Load sample cache
    sample_cache = load_samples_cache()
    cached_samples_reused = 0
    total_train_samples_before = 0
    total_dedup_dropped = 0

    print(f"[*] Loaded sample cache with {len(sample_cache)} symbol entries")

    for symbol in config.symbols:
        df, used_timeframe, bar_count = fetch_training_data(
            bot,
            symbol,
            args.timeframe,
            args.limit,
            min_required_bars=max(30, args.lookahead_bars + 20),
        )
        print(f"Using timeframe {used_timeframe} for {symbol} ({bar_count} bars)")

        # Build new dataset
        X_current, y_current = build_dataset(
            df,
            lookahead=args.lookahead_bars,
            threshold_pct=args.threshold,
            cost_bps=args.cost_bps,
            slippage_bps=args.slippage_bps,
            min_history_bars=max(30, args.lookahead_bars + 20),
        )
        print(f"Built {len(X_current)} new training samples for {symbol}")

        X_current, y_current, dropped = deduplicate_samples(X_current, y_current)
        total_dedup_dropped += dropped
        if dropped:
            print(f"  - dropped {dropped} duplicate current samples for {symbol}")

        if len(X_current) < 3:
            print(f"  ! Skipping {symbol}: only {len(X_current)} current samples")
            continue

        # Split only the current-run samples for honest holdout scoring.
        X_train_current, X_test, y_train_current, y_test = split_dataset(
            X_current,
            y_current,
            holdout_ratio=0.2,
            purge_gap=5,
        )

        # Reuse cache as train-only memory, never as holdout source.
        X_cached = np.empty((0, X_current.shape[1]))
        y_cached = np.empty((0,), dtype=y_current.dtype)
        if symbol in sample_cache:
            X_cached_all, y_cached_all = sample_cache[symbol]
            if len(X_cached_all) > CACHE_RECENT_EXCLUDE:
                X_cached = X_cached_all[:-CACHE_RECENT_EXCLUDE]
                y_cached = y_cached_all[:-CACHE_RECENT_EXCLUDE]
            cached_samples_reused += len(X_cached)

        if len(X_cached) > 0:
            X_train = np.vstack([X_cached, X_train_current])
            y_train = np.hstack([y_cached, y_train_current])
            print(f"  + {len(X_cached)} cached train samples reused")
        else:
            X_train, y_train = X_train_current, y_train_current

        X_train, y_train, dropped_train_dupes = deduplicate_samples(X_train, y_train)
        total_dedup_dropped += dropped_train_dupes
        if dropped_train_dupes:
            print(f"  - dropped {dropped_train_dupes} duplicate train samples for {symbol}")

        X_test, y_test, dropped_overlap = drop_test_overlap(X_train, X_test, y_test)
        if dropped_overlap:
            print(f"  - dropped {dropped_overlap} overlapping holdout samples for {symbol}")

        # Update cache with train-only samples.
        cache_X, cache_y = X_train.copy(), y_train.copy()
        if len(cache_X) > CACHE_MAX_SAMPLES_PER_SYMBOL:
            cache_X = cache_X[-CACHE_MAX_SAMPLES_PER_SYMBOL:]
            cache_y = cache_y[-CACHE_MAX_SAMPLES_PER_SYMBOL:]
            print(f"  - cache clipped to {CACHE_MAX_SAMPLES_PER_SYMBOL} samples for {symbol}")
        sample_cache[symbol] = (cache_X, cache_y)

        total_train_samples_before += len(X_train)

        results.append(
            SymbolTrainingResult(
                symbol=symbol,
                samples=len(X_current),
                train_samples=len(X_train),
                test_samples=len(X_test),
                live_probability=0.5,
            )
        )
        latest_frames[symbol] = df
        if len(X_train) > 0:
            X_train_parts.append(X_train)
            y_train_parts.append(y_train)
        if len(X_test) > 0:
            X_test_parts.append(X_test)
            y_test_parts.append(y_test)

    # Save cache
    save_samples_cache(sample_cache)
    print(f"[✓] Saved sample cache with {len(sample_cache)} symbols")

    if not X_train_parts:
        raise RuntimeError("No training samples were produced")

    X_train_all = np.concatenate(X_train_parts, axis=0)
    y_train_all = np.concatenate(y_train_parts, axis=0)
    X_test_all = np.concatenate(X_test_parts, axis=0) if X_test_parts else np.array([])
    y_test_all = np.concatenate(y_test_parts, axis=0) if y_test_parts else np.array([])

    if args.hard and ai.model is not None:
        ai.model.set_params(
            n_estimators=args.n_estimators,
            max_depth=args.max_depth,
            min_samples_split=2,
            min_samples_leaf=1,
            class_weight="balanced_subsample",
        )
        print(
            f"Hard mode enabled | n_estimators={args.n_estimators} "
            f"max_depth={args.max_depth}"
        )

    ai.fit(X_train_all, y_train_all)

    overlap_ratio = train_test_overlap_ratio(X_train_all, X_test_all)
    if overlap_ratio > MAX_TRAIN_TEST_OVERLAP_RATIO:
        raise RuntimeError(
            f"Train/test overlap {overlap_ratio:.2%} exceeds allowed "
            f"{MAX_TRAIN_TEST_OVERLAP_RATIO:.2%}."
        )

    if len(X_test_all) > 0 and len(set(y_test_all)) > 1:
        X_test_scaled = ai.scaler.transform(X_test_all)
        proba = ai.model.predict_proba(X_test_scaled)
        if proba.shape[1] == 1:
            # Degenerate case: model was fit on a single class.
            y_prob = np.zeros(len(X_test_scaled), dtype=float)
        else:
            y_prob = proba[:, 1]
        y_pred = (y_prob >= 0.5).astype(int)
        accuracy = accuracy_score(y_test_all, y_pred)
        precision = precision_score(y_test_all, y_pred, zero_division=0)
        recall = recall_score(y_test_all, y_pred, zero_division=0)
        f1 = f1_score(y_test_all, y_pred, zero_division=0)
        auc = roc_auc_score(y_test_all, y_prob)

        # Bootstrap confidence intervals
        bootstrap_metrics_result = compute_bootstrap_metrics(y_test_all, y_prob)
    else:
        accuracy = precision = recall = f1 = auc = 0.0
        bootstrap_metrics_result = {k: 0.0 for k in ["auc_mean", "auc_ci_low", "auc_ci_high", "f1_mean", "f1_ci_low", "f1_ci_high", "acc_mean", "acc_ci_low", "acc_ci_high"]}

    for result in results:
        frame = latest_frames[result.symbol]
        result.live_probability = ai.predict_entry_probability(frame)

    summary = {
        "symbols": config.symbols,
        "results": [r.__dict__ for r in results],
        "hard_mode": bool(args.hard),
        "overall_accuracy": float(accuracy),
        "overall_precision": float(precision),
        "overall_recall": float(recall),
        "overall_f1": float(f1),
        "overall_auc": float(auc),
        "bootstrap_metrics": bootstrap_metrics_result,
        "mean_live_probability": float(np.mean([r.live_probability for r in results])) if results else 0.0,
        "total_test_samples": int(len(y_test_all)) if len(y_test_all) > 0 else 0,
        "total_train_samples": int(len(y_train_all)) if len(y_train_all) > 0 else 0,
        "cached_samples_reused": int(cached_samples_reused),
        "deduplicated_samples_dropped": int(total_dedup_dropped),
        "train_test_overlap_ratio": float(overlap_ratio),
        "threshold_pct": float(args.threshold),
        "lookahead_bars": int(args.lookahead_bars),
        "cost_bps": float(args.cost_bps),
        "slippage_bps": float(args.slippage_bps),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    band, label, reason = quality_band(summary, summary["total_test_samples"])
    summary["quality_band"] = band
    summary["quality_label"] = label
    summary["quality_reason"] = reason

    recent = load_recent_history(hours=24)
    summary["trend_24h"] = compute_24h_trend(recent, summary)

    report_path = render_training_png_v2(results, summary, "training_report.png")
    Path("training_report.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    append_history(summary)

    if discord.enabled:
        sent = discord.send_file(
            "Stock RF Training Report (v2 - Sample Caching)",
            {
                "Symbols": ", ".join(config.symbols),
                "Quality": f"{summary['quality_band']} ({summary['quality_label']})",
                "Accuracy": f"{summary['overall_accuracy']:.3f}",
                "AUC": f"{summary['overall_auc']:.3f} (CI: {bootstrap_metrics_result['auc_ci_low']:.3f}–{bootstrap_metrics_result['auc_ci_high']:.3f})",
                "F1": f"{summary['overall_f1']:.3f}",
                "Holdout n": summary["total_test_samples"],
                "Total train": summary["total_train_samples"],
                "Cached reused": summary["cached_samples_reused"],
                "Dedup dropped": summary["deduplicated_samples_dropped"],
                "Overlap": f"{summary['train_test_overlap_ratio']:.2%}",
                "Threshold": f"{args.threshold}%",
                "Horizon": f"{args.lookahead_bars} bars",
                "Costs": f"{args.cost_bps + args.slippage_bps:.1f} bps",
                "24h trend": (
                    f"{summary['trend_24h']['direction']} | "
                    f"ΔAUC {summary['trend_24h']['delta_auc']:+.3f}"
                ),
            },
            report_path,
            filename="training_report.png",
        )
        print(f"Discord report sent: {sent}")
    else:
        print("Discord disabled, report kept locally.")

    print("\n=== STOCK RF TRAINING SUMMARY (v2) ===")
    for result in results:
        print(
            f"{result.symbol}: samples={result.samples} train={result.train_samples} "
            f"test={result.test_samples} live_prob={result.live_probability:.3f}"
        )
    print("-" * 72)
    print(
        f"Overall accuracy={summary['overall_accuracy']:.3f} | "
        f"Precision={summary['overall_precision']:.3f} | "
        f"Recall={summary['overall_recall']:.3f} | "
        f"F1={summary['overall_f1']:.3f} | "
        f"AUC={summary['overall_auc']:.3f}"
    )
    print(
        f"Bootstrap AUC: {bootstrap_metrics_result['auc_mean']:.3f} "
        f"[{bootstrap_metrics_result['auc_ci_low']:.3f}–{bootstrap_metrics_result['auc_ci_high']:.3f}]"
    )
    print(
        f"Quality={summary['quality_band']} ({summary['quality_label']}) | "
        f"Cached reused={cached_samples_reused} | "
        f"Dedup dropped={summary['deduplicated_samples_dropped']} | "
        f"Overlap={summary['train_test_overlap_ratio']:.2%} | "
        f"Threshold={args.threshold}% | Horizon={args.lookahead_bars} bars | "
        f"Costs={args.cost_bps + args.slippage_bps:.1f} bps"
    )
    print(f"Hard mode={'ON' if args.hard else 'OFF'}")
    print("Saved training_report.png and training_report.json")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""
Train and validate the stock Random Forest bot on recent Alpaca bars.

This script builds a time-series-safe dataset from the configured stock symbols,
trains the lightweight RF model, evaluates it on a holdout split, and prints
live prediction probabilities for the latest bars.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Tuple

import numpy as np
from sklearn.metrics import accuracy_score, precision_score, recall_score, f1_score, roc_auc_score

from ml_model_rf import TradingAI, FeatureExtractor
from stock_bot import StockTradingBot
from stock_config import load_stock_config
from discord_alerts import discord

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


HISTORY_JSONL = Path("training_history.jsonl")


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
        except Exception:
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

    if total_test_samples < 60:
        return "RED", "Low sample confidence", "Need >= 60 holdout samples for a reliable score"
    if auc >= 0.58 and f1 >= 0.58:
        return "GREEN", "Promising", "Signal quality is improving; keep monitoring drift"
    if auc >= 0.53 and f1 >= 0.53:
        return "YELLOW", "Borderline", "Usable for monitoring but not strong enough for trust"
    return "RED", "Weak", "Model is near-random; prioritize data/feature improvements"


def _svg_escape(text: str) -> str:
    return (
        str(text)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def build_dataset(df, lookahead: int = 1, threshold_pct: float = 0.05) -> Tuple[np.ndarray, np.ndarray]:
    """Create features and labels from a single OHLCV DataFrame."""
    features: List[np.ndarray] = []
    labels: List[int] = []

    if len(df) < 55:
        return np.array([]), np.array([])

    for idx in range(20, len(df) - lookahead):
        window = df.iloc[: idx + 1].copy()
        x = FeatureExtractor.extract_features(window)
        if x is None:
            continue

        current_close = float(df.iloc[idx]["close"])
        future_close = float(df.iloc[idx + lookahead]["close"])
        future_return_pct = ((future_close - current_close) / current_close) * 100.0
        label = 1 if future_return_pct >= threshold_pct else 0

        features.append(x[0])
        labels.append(label)

    if not features:
        return np.array([]), np.array([])

    return np.asarray(features), np.asarray(labels)


def split_dataset(X: np.ndarray, y: np.ndarray, holdout_ratio: float = 0.2) -> Tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    split_idx = max(int(len(X) * (1.0 - holdout_ratio)), 1)
    return X[:split_idx], X[split_idx:], y[:split_idx], y[split_idx:]


def render_training_svg(results: List[SymbolTrainingResult], summary: dict, output_path: str) -> str:
    width = 1100
    height = 820
    margin = 60
    chart_top = 130
    chart_height = 280
    bar_width = 180
    gap = 70
    max_samples = max((r.samples for r in results), default=1)

    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="#0b1020"/>',
        f'<text x="{margin}" y="48" fill="#f8fafc" font-size="30" font-family="Arial, Helvetica, sans-serif" font-weight="700">Stock RF Training Report</text>',
        f'<text x="{margin}" y="78" fill="#94a3b8" font-size="15" font-family="Arial, Helvetica, sans-serif">Live training run on Alpaca bars</text>',
    ]

    stats = [
        f"Quality: {summary.get('quality_band', 'RED')} ({summary.get('quality_label', 'Unknown')})",
        f"Overall accuracy: {summary['overall_accuracy']:.3f}",
        f"Precision: {summary['overall_precision']:.3f}",
        f"Recall: {summary['overall_recall']:.3f}",
        f"F1: {summary['overall_f1']:.3f}",
        f"AUC: {summary['overall_auc']:.3f}",
        f"Mean live probability: {summary['mean_live_probability']:.3f}",
    ]
    for idx, text in enumerate(stats):
        x = margin + idx * 165
        lines.append(f'<text x="{x}" y="108" fill="#cbd5e1" font-size="13" font-family="Arial, Helvetica, sans-serif">{_svg_escape(text)}</text>')

    # Chart background
    lines.append(f'<rect x="{margin}" y="{chart_top}" width="{width - 2 * margin}" height="{chart_height}" rx="16" fill="#111827" stroke="#334155"/>')
    lines.append(f'<line x1="{margin + 40}" y1="{chart_top + chart_height - 30}" x2="{width - margin - 20}" y2="{chart_top + chart_height - 30}" stroke="#475569" stroke-width="2"/>')
    lines.append(f'<line x1="{margin + 40}" y1="{chart_top + 20}" x2="{margin + 40}" y2="{chart_top + chart_height - 30}" stroke="#475569" stroke-width="2"/>')

    for idx, result in enumerate(results):
        x = margin + 75 + idx * (bar_width + gap)
        train_height = max(12, int((result.train_samples / max_samples) * (chart_height - 80)))
        test_height = max(12, int((result.test_samples / max_samples) * (chart_height - 80)))
        sample_height = max(12, int((result.samples / max_samples) * (chart_height - 80)))

        base_y = chart_top + chart_height - 30
        lines.append(f'<rect x="{x}" y="{base_y - sample_height}" width="{bar_width}" height="{sample_height}" rx="10" fill="#1d4ed8" opacity="0.35"/>')
        lines.append(f'<rect x="{x + 18}" y="{base_y - train_height}" width="{bar_width - 36}" height="{train_height}" rx="10" fill="#22c55e"/>')
        lines.append(f'<rect x="{x + 54}" y="{base_y - test_height}" width="{bar_width - 108}" height="{test_height}" rx="10" fill="#f59e0b"/>')
        lines.append(f'<text x="{x + bar_width/2}" y="{base_y + 24}" fill="#e2e8f0" font-size="14" font-family="Arial, Helvetica, sans-serif" text-anchor="middle">{_svg_escape(result.symbol)}</text>')
        lines.append(f'<text x="{x + bar_width/2}" y="{base_y - sample_height - 10}" fill="#93c5fd" font-size="13" font-family="Arial, Helvetica, sans-serif" text-anchor="middle">samples {result.samples}</text>')
        lines.append(f'<text x="{x + bar_width/2}" y="{base_y - train_height - 10}" fill="#86efac" font-size="12" font-family="Arial, Helvetica, sans-serif" text-anchor="middle">train {result.train_samples}</text>')
        lines.append(f'<text x="{x + bar_width/2}" y="{base_y - test_height - 10}" fill="#fde68a" font-size="12" font-family="Arial, Helvetica, sans-serif" text-anchor="middle">test {result.test_samples}</text>')
        lines.append(f'<text x="{x + bar_width/2}" y="{base_y + 46}" fill="#cbd5e1" font-size="12" font-family="Arial, Helvetica, sans-serif" text-anchor="middle">live prob {result.live_probability:.3f}</text>')

    legend_y = chart_top + chart_height + 48
    legend = [
        ("Total samples", "#1d4ed8"),
        ("Train samples", "#22c55e"),
        ("Test samples", "#f59e0b"),
    ]
    for idx, (label, color) in enumerate(legend):
        x = margin + idx * 200
        lines.append(f'<rect x="{x}" y="{legend_y}" width="18" height="18" rx="4" fill="{color}"/>')
        lines.append(f'<text x="{x + 26}" y="{legend_y + 14}" fill="#cbd5e1" font-size="13" font-family="Arial, Helvetica, sans-serif">{label}</text>')

    report_lines = [
        f"Generated: {summary.get('generated_at', '')}",
        f"Symbols: {', '.join(summary.get('symbols', []))}",
        f"Quality band: {summary.get('quality_band', 'RED')} ({summary.get('quality_label', 'Unknown')})",
        f"Quality note: {summary.get('quality_reason', '')}",
        f"Overall accuracy: {summary['overall_accuracy']:.3f}",
        f"Overall precision: {summary['overall_precision']:.3f}",
        f"Overall recall: {summary['overall_recall']:.3f}",
        f"Overall F1: {summary['overall_f1']:.3f}",
        f"Overall AUC: {summary['overall_auc']:.3f}",
        f"24h trend: {summary.get('trend_24h', {}).get('direction', 'flat')} | runs={summary.get('trend_24h', {}).get('runs', 1)} | "
        f"ΔAUC={summary.get('trend_24h', {}).get('delta_auc', 0.0):+.3f} | "
        f"ΔF1={summary.get('trend_24h', {}).get('delta_f1', 0.0):+.3f}",
        f"Holdout sample count: {summary.get('total_test_samples', 0)}",
    ]
    notes_y = chart_top + chart_height + 112
    lines.append(f'<rect x="{margin}" y="{notes_y - 24}" width="{width - 2 * margin}" height="320" rx="16" fill="#0f172a" stroke="#334155"/>')
    lines.append(f'<text x="{margin + 20}" y="{notes_y}" fill="#f8fafc" font-size="18" font-family="Arial, Helvetica, sans-serif" font-weight="700">Training notes</text>')
    for idx, text in enumerate(report_lines):
        lines.append(f'<text x="{margin + 20}" y="{notes_y + 28 + idx * 22}" fill="#cbd5e1" font-size="13" font-family="Arial, Helvetica, sans-serif">{_svg_escape(text)}</text>')

    metric_legend_y = notes_y + 28 + len(report_lines) * 22 + 22
    lines.append(f'<text x="{margin + 20}" y="{metric_legend_y}" fill="#f8fafc" font-size="16" font-family="Arial, Helvetica, sans-serif" font-weight="700">Legend (what the metrics mean)</text>')
    metric_help = [
        "Accuracy: fraction of all predictions that were correct.",
        "Precision: of BUY predictions, how many were actually good outcomes.",
        "Recall: of all good outcomes, how many the model successfully caught.",
        "F1: balance between Precision and Recall (higher is more stable).",
        "AUC: ranking quality vs random baseline (0.50 ≈ random, >0.60 useful).",
        "Live probability: model confidence for the latest bar (0.5 = neutral).",
        "Bar colors: Blue=total samples, Green=train split, Orange=test split.",
    ]
    for idx, text in enumerate(metric_help):
        lines.append(
            f'<text x="{margin + 20}" y="{metric_legend_y + 24 + idx * 20}" fill="#cbd5e1" font-size="13" font-family="Arial, Helvetica, sans-serif">• {_svg_escape(text)}</text>'
        )

    lines.append('</svg>')
    svg = "\n".join(lines)
    Path(output_path).write_text(svg, encoding="utf-8")
    return output_path


def render_training_png(results: List[SymbolTrainingResult], summary: dict, output_path: str) -> str:
    if not HAS_PIL:
        raise RuntimeError("Pillow not installed")

    def load_font(size: int):
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
            "C:/Windows/Fonts/arial.ttf",
        ]
        for path in candidates:
            try:
                return ImageFont.truetype(path, size=size)
            except Exception:
                continue
        return ImageFont.load_default()

    width, height = 1200, 820
    img = Image.new("RGB", (width, height), (11, 16, 32))
    draw = ImageDraw.Draw(img)
    font_title = load_font(38)
    font_subtitle = load_font(20)
    font_metric = load_font(18)
    font_body = load_font(17)
    font_small = load_font(15)
    font_legend = load_font(16)

    # Header
    draw.text((40, 24), "Stock RF Training Report", fill=(248, 250, 252), font=font_title)
    draw.text((40, 70), "Live training run with legend and metric explanations", fill=(148, 163, 184), font=font_subtitle)

    # Summary metrics
    metric_text = (
        f"Quality {summary.get('quality_band', 'RED')} ({summary.get('quality_label', 'Unknown')}) | "
        f"Accuracy {summary['overall_accuracy']:.3f} | Precision {summary['overall_precision']:.3f} | "
        f"Recall {summary['overall_recall']:.3f} | F1 {summary['overall_f1']:.3f} | "
        f"AUC {summary['overall_auc']:.3f} | Mean live prob {summary['mean_live_probability']:.3f}"
    )
    draw.text((40, 102), metric_text, fill=(203, 213, 225), font=font_metric)

    # Chart area
    chart_x, chart_y, chart_w, chart_h = 40, 120, 1120, 320
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

        draw.rounded_rectangle([x, axis_y - total_h, x + bar_w, axis_y], radius=8, fill=(29, 78, 216))
        draw.rounded_rectangle([x + 18, axis_y - train_h, x + bar_w - 18, axis_y], radius=8, fill=(34, 197, 94))
        draw.rounded_rectangle([x + 70, axis_y - test_h, x + bar_w - 70, axis_y], radius=8, fill=(245, 158, 11))

        draw.text((x + 72, axis_y + 8), r.symbol, fill=(226, 232, 240), font=font_body)
        draw.text((x + 12, axis_y - total_h - 16), f"samples {r.samples}", fill=(147, 197, 253), font=font_small)
        draw.text((x + 12, axis_y - train_h - 16), f"train {r.train_samples}", fill=(134, 239, 172), font=font_small)
        draw.text((x + 12, axis_y - test_h - 16), f"test {r.test_samples}", fill=(253, 230, 138), font=font_small)
        draw.text((x + 12, axis_y + 26), f"live prob {r.live_probability:.3f}", fill=(203, 213, 225), font=font_small)

    # Legend
    ly = 470
    draw.rectangle([40, ly, 58, ly + 18], fill=(29, 78, 216))
    draw.text((66, ly + 1), "Total samples", fill=(203, 213, 225), font=font_legend)
    draw.rectangle([240, ly, 258, ly + 18], fill=(34, 197, 94))
    draw.text((266, ly + 1), "Train samples", fill=(203, 213, 225), font=font_legend)
    draw.rectangle([430, ly, 448, ly + 18], fill=(245, 158, 11))
    draw.text((456, ly + 1), "Test samples", fill=(203, 213, 225), font=font_legend)

    # Explanations
    yy = 520
    help_lines = [
        "Legend: Accuracy = overall correctness.",
        "Precision = quality of BUY predictions.",
        "Recall = how many good moves were captured.",
        "F1 = balance between precision and recall.",
        "AUC = ranking quality (0.50 is random).",
        "Live probability = current model confidence.",
        f"Quality note: {summary.get('quality_reason', '')}",
        f"24h trend: {summary.get('trend_24h', {}).get('direction', 'flat')} | "
        f"ΔAUC {summary.get('trend_24h', {}).get('delta_auc', 0.0):+.3f} | "
        f"ΔF1 {summary.get('trend_24h', {}).get('delta_f1', 0.0):+.3f}",
        f"Holdout samples: {summary.get('total_test_samples', 0)}",
    ]
    for line in help_lines:
        draw.text((40, yy), line, fill=(203, 213, 225), font=font_body)
        yy += 24

    draw.text((40, yy + 8), f"Generated: {summary.get('generated_at', '')}", fill=(148, 163, 184), font=font_small)
    img.save(output_path, format="PNG")
    return output_path


def train_one_symbol(ai: TradingAI, symbol: str, df, holdout_ratio: float = 0.2) -> Tuple[SymbolTrainingResult, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    X, y = build_dataset(df)
    print(f"Built {len(X)} training samples for {symbol}")
    if len(X) < 3:
        raise ValueError(f"Not enough training samples for {symbol}: {len(X)}")

    X_train, X_test, y_train, y_test = split_dataset(X, y, holdout_ratio=holdout_ratio)

    return SymbolTrainingResult(
        symbol=symbol,
        samples=len(X),
        train_samples=len(X_train),
        test_samples=len(X_test),
        live_probability=0.5,
    ), X_train, X_test, y_train, y_test


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


def fetch_training_data(bot: StockTradingBot, symbol: str, requested_timeframe: str, limit: int) -> Tuple[object, str, int, np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
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

        print(f"Fetched {len(df)} bars for {symbol} at timeframe {timeframe}")
        try:
            result, X_train, X_test, y_train, y_test = train_one_symbol(TradingAI(), symbol, df)
            if len(X_train) > 0:
                return df, timeframe, len(df), result, X_train, X_test, y_train, y_test
        except ValueError:
            pass

    fallback_df = fetch_yfinance_history(symbol)
    if fallback_df is not None:
        print(f"Fetched {len(fallback_df)} bars for {symbol} from Yahoo Finance fallback")
        result, X_train, X_test, y_train, y_test = train_one_symbol(TradingAI(), symbol, fallback_df)
        if len(X_train) > 0:
            return fallback_df, "yfinance-1d-5y", len(fallback_df), result, X_train, X_test, y_train, y_test

    raise RuntimeError(f"Unable to build training data for {symbol} using any timeframe")


def main() -> int:
    parser = argparse.ArgumentParser(description="Train the stock RF bot on Alpaca bars")
    parser.add_argument("--limit", type=int, default=1000, help="Bars to fetch per symbol")
    parser.add_argument("--timeframe", default="1Day", help="Alpaca timeframe to use for training")
    parser.add_argument("--symbols", nargs="*", help="Override symbols from .env")
    parser.add_argument("--hard", action="store_true", help="Use a stronger RF configuration")
    parser.add_argument("--n-estimators", type=int, default=400, help="RF trees when --hard is enabled")
    parser.add_argument("--max-depth", type=int, default=18, help="RF max depth when --hard is enabled")
    parser.add_argument("--json", action="store_true", help="Print JSON output")
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

    for symbol in config.symbols:
        df, used_timeframe, bar_count, result, X_train, X_test, y_train, y_test = fetch_training_data(
            bot,
            symbol,
            args.timeframe,
            args.limit,
        )
        print(f"Using timeframe {used_timeframe} for {symbol} ({bar_count} bars)")
        results.append(result)
        latest_frames[symbol] = df
        if len(X_train) > 0:
            X_train_parts.append(X_train)
            y_train_parts.append(y_train)
        if len(X_test) > 0:
            X_test_parts.append(X_test)
            y_test_parts.append(y_test)

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

    if len(X_test_all) > 0 and len(set(y_test_all)) > 1:
        X_test_scaled = ai.scaler.transform(X_test_all)
        y_prob = ai.model.predict_proba(X_test_scaled)[:, 1]
        y_pred = (y_prob >= 0.5).astype(int)
        accuracy = accuracy_score(y_test_all, y_pred)
        precision = precision_score(y_test_all, y_pred, zero_division=0)
        recall = recall_score(y_test_all, y_pred, zero_division=0)
        f1 = f1_score(y_test_all, y_pred, zero_division=0)
        auc = roc_auc_score(y_test_all, y_prob)
    else:
        accuracy = precision = recall = f1 = auc = 0.0

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
        "mean_live_probability": float(np.mean([r.live_probability for r in results])) if results else 0.0,
        "total_test_samples": int(len(y_test_all)) if len(y_test_all) > 0 else 0,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }

    band, label, reason = quality_band(summary, summary["total_test_samples"])
    summary["quality_band"] = band
    summary["quality_label"] = label
    summary["quality_reason"] = reason

    recent = load_recent_history(hours=24)
    summary["trend_24h"] = compute_24h_trend(recent, summary)

    report_svg_path = render_training_svg(results, summary, "training_report.svg")
    report_path = report_svg_path
    report_filename = "training_report.svg"
    if HAS_PIL:
        report_png_path = render_training_png(results, summary, "training_report.png")
        report_path = report_png_path
        report_filename = "training_report.png"
    Path("training_report.json").write_text(json.dumps(summary, indent=2), encoding="utf-8")
    append_history(summary)

    if discord.enabled:
        sent = discord.send_file(
            "Stock RF Training Report",
            {
                "Symbols": ", ".join(config.symbols),
                "Hard mode": "ON" if args.hard else "OFF",
                "Quality": f"{summary['quality_band']} ({summary['quality_label']})",
                "Accuracy": f"{summary['overall_accuracy']:.3f}",
                "Precision": f"{summary['overall_precision']:.3f}",
                "Recall": f"{summary['overall_recall']:.3f}",
                "F1": f"{summary['overall_f1']:.3f}",
                "AUC": f"{summary['overall_auc']:.3f}",
                "24h trend": (
                    f"{summary['trend_24h']['direction']} | "
                    f"ΔAUC {summary['trend_24h']['delta_auc']:+.3f} | "
                    f"ΔF1 {summary['trend_24h']['delta_f1']:+.3f}"
                ),
                "Holdout n": summary["total_test_samples"],
            },
            report_path,
            filename=report_filename,
        )
        print(f"Discord report sent: {sent}")
    else:
        print("Discord disabled, report kept locally.")

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        print("\n=== STOCK RF TRAINING SUMMARY ===")
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
            f"AUC={summary['overall_auc']:.3f} | "
            f"Mean live probability={summary['mean_live_probability']:.3f}"
        )
        print(
            f"Quality={summary['quality_band']} ({summary['quality_label']}) | "
            f"24h trend={summary['trend_24h']['direction']} "
            f"(ΔAUC {summary['trend_24h']['delta_auc']:+.3f}, "
            f"ΔF1 {summary['trend_24h']['delta_f1']:+.3f}) | "
            f"Holdout n={summary['total_test_samples']}"
        )
        print(f"Hard mode={'ON' if args.hard else 'OFF'}")
        print("Saved training_report.svg and training_report.json")
        print("Model saved to trading_model_rf.pkl and trading_scaler_rf.pkl")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
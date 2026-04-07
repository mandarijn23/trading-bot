import json
import tempfile
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List, Tuple
import importlib.util

import numpy as np
import pandas as pd
import ccxt


ROOT = Path(__file__).resolve().parent
STRATEGY_PATH = ROOT / "strategy.py"


@dataclass
class TradeResult:
    symbol: str
    timeframe: str
    entry_time: pd.Timestamp
    exit_time: pd.Timestamp
    entry_price: float
    exit_price: float
    return_pct: float
    max_adverse_pct: float
    max_favorable_pct: float
    bars_held: int
    grade: str
    quality_score: float


def load_strategy_module(path: Path, module_name: str):
    spec = importlib.util.spec_from_file_location(module_name, str(path))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def load_strategy_with_replacements(replacements: Dict[str, str], module_name: str):
    src = STRATEGY_PATH.read_text(encoding="utf-8")
    for old, new in replacements.items():
        if old not in src:
            raise ValueError(f"Replacement token not found: {old}")
        src = src.replace(old, new)
    tmp = Path(tempfile.gettempdir()) / f"{module_name}.py"
    tmp.write_text(src, encoding="utf-8")
    return load_strategy_module(tmp, module_name)


def compress_df(df: pd.DataFrame, max_bars: int) -> pd.DataFrame:
    """Uniformly sample across full history to preserve multi-year coverage with fewer bars."""
    if len(df) <= max_bars:
        return df
    idx = np.linspace(0, len(df) - 1, max_bars).astype(int)
    return df.iloc[idx].reset_index(drop=True)


def fetch_ohlcv_paginated(
    exchange,
    symbol: str,
    timeframe: str,
    since_ms: int,
    until_ms: int,
    limit: int = 1000,
    max_batches: int = 200,
):
    all_rows = []
    cursor = since_ms
    tf_ms = exchange.parse_timeframe(timeframe) * 1000
    batches = 0

    while cursor < until_ms and batches < max_batches:
        try:
            batch = exchange.fetch_ohlcv(symbol, timeframe=timeframe, since=cursor, limit=limit)
        except Exception:
            break
        if not batch:
            break
        all_rows.extend(batch)
        batches += 1
        last_ts = batch[-1][0]
        next_cursor = last_ts + tf_ms
        if next_cursor <= cursor:
            break
        cursor = next_cursor
        time.sleep(exchange.rateLimit / 1000.0)

        # Stop if exchange returns future bars beyond requested until
        if last_ts >= until_ms:
            break

    if not all_rows:
        return pd.DataFrame(columns=["timestamp", "open", "high", "low", "close", "volume"])

    df = pd.DataFrame(all_rows, columns=["timestamp", "open", "high", "low", "close", "volume"])
    df = df.drop_duplicates(subset=["timestamp"]).sort_values("timestamp")
    df = df[df["timestamp"] <= until_ms]
    df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
    return df.reset_index(drop=True)


def simulate_trades(
    df: pd.DataFrame,
    symbol: str,
    timeframe: str,
    strategy_module,
    max_hold_bars: int = 72,
    signal_lookback_bars: int = 320,
) -> List[TradeResult]:
    if len(df) < 300:
        return []

    trades: List[TradeResult] = []
    position = None
    warmup = 220

    for i in range(warmup, len(df) - 1):
        start_i = max(0, i - signal_lookback_bars + 1)
        window = df.iloc[start_i : i + 1]
        row = df.iloc[i]

        signal_simple, details = strategy_module.get_signal_enhanced(window)

        if position is None:
            if signal_simple == "BUY":
                entry = float(row["close"])
                atr = max(float(getattr(details, "atr", 0.0)), 1e-9)
                stop = float(getattr(details, "stop_loss", entry - 1.8 * atr))
                target = float(getattr(details, "take_profit", entry + 3.0 * atr))
                partial_tp = float(getattr(details, "partial_take_profit", entry + 2.0 * atr))
                trailing_mult = float(getattr(details, "trailing_stop_atr", 2.5))
                grade = str(getattr(details, "trade_grade", "C"))
                qscore = float(getattr(details, "quality_score", 0.0))

                position = {
                    "entry_i": i,
                    "entry_time": row["timestamp"],
                    "entry": entry,
                    "stop": stop,
                    "target": target,
                    "partial_tp": partial_tp,
                    "trailing_mult": trailing_mult,
                    "atr": atr,
                    "peak": entry,
                    "partial_done": False,
                    "grade": grade,
                    "qscore": qscore,
                }

        else:
            high = float(row["high"])
            low = float(row["low"])
            close = float(row["close"])

            position["peak"] = max(position["peak"], high)
            trailing_stop = position["peak"] - (position["trailing_mult"] * position["atr"])
            position["stop"] = max(position["stop"], trailing_stop)

            exit_reason = None
            exit_price = None

            if low <= position["stop"]:
                exit_reason = "STOP"
                exit_price = position["stop"]
            elif high >= position["target"]:
                exit_reason = "TARGET"
                exit_price = position["target"]
            else:
                if (not position["partial_done"]) and high >= position["partial_tp"]:
                    position["partial_done"] = True
                    position["stop"] = max(position["stop"], position["entry"])

                if (i - position["entry_i"]) >= max_hold_bars:
                    exit_reason = "TIME"
                    exit_price = close

            if exit_reason:
                future_slice = df.iloc[position["entry_i"] : i + 1]
                worst = (float(future_slice["low"].min()) - position["entry"]) / position["entry"]
                best = (float(future_slice["high"].max()) - position["entry"]) / position["entry"]
                ret = (exit_price - position["entry"]) / position["entry"]

                trades.append(
                    TradeResult(
                        symbol=symbol,
                        timeframe=timeframe,
                        entry_time=position["entry_time"],
                        exit_time=row["timestamp"],
                        entry_price=position["entry"],
                        exit_price=float(exit_price),
                        return_pct=float(ret),
                        max_adverse_pct=float(worst),
                        max_favorable_pct=float(best),
                        bars_held=i - position["entry_i"],
                        grade=position["grade"],
                        quality_score=position["qscore"],
                    )
                )
                position = None

    return trades


def metrics_from_trades(trades: List[TradeResult]):
    if not trades:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "expectancy": 0.0,
            "profit_factor": 0.0,
            "max_drawdown": 0.0,
            "total_return": 0.0,
            "avg_hold_bars": 0.0,
        }

    rets = np.array([t.return_pct for t in trades])
    wins = rets[rets > 0]
    losses = rets[rets <= 0]
    wr = len(wins) / len(rets)
    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(losses.mean()) if len(losses) else 0.0
    exp = (wr * avg_win) - ((1 - wr) * abs(avg_loss))
    gross_win = float(wins.sum()) if len(wins) else 0.0
    gross_loss = float(abs(losses.sum())) if len(losses) else 0.0
    pf = gross_win / gross_loss if gross_loss > 0 else 0.0

    equity = np.cumprod(1 + rets)
    peak = np.maximum.accumulate(equity)
    dd = (equity - peak) / peak

    return {
        "trades": int(len(rets)),
        "win_rate": float(wr),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "expectancy": float(exp),
        "profit_factor": float(pf),
        "max_drawdown": float(dd.min()) if len(dd) else 0.0,
        "total_return": float(equity[-1] - 1.0),
        "avg_hold_bars": float(np.mean([t.bars_held for t in trades])),
    }


def monte_carlo(trades: List[TradeResult], runs: int = 5000, seed: int = 42):
    rng = np.random.default_rng(seed)
    base_rets = np.array([t.return_pct for t in trades], dtype=float)
    if len(base_rets) == 0:
        return {
            "runs": runs,
            "positive_run_probability": 0.0,
            "median_return": 0.0,
            "p05_return": 0.0,
            "p95_return": 0.0,
            "median_max_drawdown": 0.0,
        }

    run_returns = []
    run_dd = []

    for _ in range(runs):
        shuffled = rng.permutation(base_rets)

        # Randomize slippage + execution timing impact per trade
        # slippage_cost: 0.05% to 0.40% round-trip
        slip_cost = rng.uniform(0.0005, 0.0040, size=len(shuffled))
        # timing noise: emulate bar timing uncertainty
        timing_noise = rng.normal(0.0, 0.0015, size=len(shuffled))

        adj = shuffled - slip_cost + timing_noise

        equity = np.cumprod(1 + adj)
        peak = np.maximum.accumulate(equity)
        dd = (equity - peak) / peak

        run_returns.append(float(equity[-1] - 1.0))
        run_dd.append(float(dd.min()))

    arr_ret = np.array(run_returns)
    arr_dd = np.array(run_dd)

    return {
        "runs": runs,
        "positive_run_probability": float(np.mean(arr_ret > 0)),
        "median_return": float(np.median(arr_ret)),
        "p05_return": float(np.percentile(arr_ret, 5)),
        "p95_return": float(np.percentile(arr_ret, 95)),
        "median_max_drawdown": float(np.median(arr_dd)),
    }


def run_sensitivity(df_by_symbol: Dict[Tuple[str, str], pd.DataFrame], base_metrics: dict):
    # Slight threshold/filter perturbations around current settings.
    scenarios = {
        "base": {},
        "a_plus_tighter": {
            "if score >= 70 and trend >= 55 and vol_exp >= 55 and volume >= 55 and structure >= 55:":
            "if score >= 73 and trend >= 58 and vol_exp >= 58 and volume >= 58 and structure >= 58:"
        },
        "a_plus_looser": {
            "if score >= 70 and trend >= 55 and vol_exp >= 55 and volume >= 55 and structure >= 55:":
            "if score >= 67 and trend >= 52 and vol_exp >= 52 and volume >= 52 and structure >= 52:"
        },
        "low_vol_stricter": {
            "if atr_pct < 0.35:": "if atr_pct < 0.45:"
        },
        "low_vol_looser": {
            "if atr_pct < 0.35:": "if atr_pct < 0.25:"
        },
        "weak_volume_stricter": {
            "if vol_ratio < 0.75:": "if vol_ratio < 0.85:"
        },
        "weak_volume_looser": {
            "if vol_ratio < 0.75:": "if vol_ratio < 0.65:"
        },
    }

    # Use representative subset to keep sensitivity tractable.
    sampled = {}
    for i, key in enumerate(sorted(df_by_symbol.keys())):
        if i >= 8:
            break
        sampled[key] = compress_df(df_by_symbol[key], max_bars=2500)

    out = {}
    for name, repl in scenarios.items():
        if name == "base":
            mod = load_strategy_module(STRATEGY_PATH, "strategy_base_sensitivity")
        else:
            mod = load_strategy_with_replacements(repl, f"strategy_sensitivity_{name}")

        all_trades: List[TradeResult] = []
        for (symbol, tf), df in sampled.items():
            all_trades.extend(simulate_trades(df, symbol, tf, mod))

        m = metrics_from_trades(all_trades)
        out[name] = m

    base_exp = out["base"]["expectancy"]
    collapse_count = 0
    for name, m in out.items():
        if name == "base":
            continue
        if m["trades"] == 0 or m["expectancy"] <= 0:
            collapse_count += 1
            continue
        if base_exp > 0 and (m["expectancy"] < (0.5 * base_exp)):
            collapse_count += 1

    out_summary = {
        "scenarios": out,
        "collapse_count": collapse_count,
        "scenario_count_ex_base": len(out) - 1,
        "overfit_flag": collapse_count >= max(2, int(0.5 * (len(out) - 1))),
    }
    return out_summary


def build_forward_test_setup(base_metrics: dict, mc: dict):
    setup = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "paper_trading_mode": {
            "enabled": True,
            "duration_days": 30,
            "min_trades_required": 100,
            "objective": "Track live-paper metrics vs backtest baseline",
        },
        "live_simulation": {
            "enabled": True,
            "commission_model": "dynamic",
            "slippage_model": "randomized_between_0.05pct_and_0.40pct_round_trip",
            "execution_delay_bars": [0, 1],
        },
        "baseline_targets": {
            "expectancy": base_metrics["expectancy"],
            "win_rate": base_metrics["win_rate"],
            "profit_factor": base_metrics["profit_factor"],
            "max_drawdown": base_metrics["max_drawdown"],
            "mc_positive_run_probability": mc["positive_run_probability"],
        },
        "drift_alert_rules": {
            "expectancy_drop_pct": 30,
            "win_rate_drop_pct_points": 7,
            "profit_factor_min": 1.0,
            "max_drawdown_limit": min(-0.25, base_metrics["max_drawdown"] * 1.25),
        },
        "tracking_fields": [
            "timestamp",
            "symbol",
            "entry_price",
            "exit_price",
            "return_pct",
            "holding_bars",
            "trade_grade",
            "quality_score",
            "slippage_paid",
            "execution_delay_bars",
        ],
    }
    return setup


def run_validation():
    base_module = load_strategy_module(STRATEGY_PATH, "strategy_validation_base")

    exchange = ccxt.binance({"enableRateLimit": True})

    symbols = [
        "BTC/USDT",
        "ETH/USDT",
        "BNB/USDT",
        "SOL/USDT",
    ]

    now_ms = int(datetime.now(timezone.utc).timestamp() * 1000)
    start_2021_ms = int(pd.Timestamp("2021-01-01", tz="UTC").timestamp() * 1000)
    start_2023_ms = int(pd.Timestamp("2023-01-01", tz="UTC").timestamp() * 1000)
    start_2024_ms = int(pd.Timestamp("2024-01-01", tz="UTC").timestamp() * 1000)

    datasets: Dict[Tuple[str, str], pd.DataFrame] = {}

    print("[1/5] Fetching multi-asset, multi-year datasets...")

    # Pass A: multi-year coverage (4h from 2021)
    for sym in symbols:
        df = fetch_ohlcv_paginated(exchange, sym, "4h", start_2021_ms, now_ms, limit=1000, max_batches=120)
        if len(df) > 500:
            df = compress_df(df, max_bars=2200)
            datasets[(sym, "4h")] = df
            print(f"  fetched {sym} 4h bars={len(df)}")

    # Pass B: denser coverage (1h from 2023)
    for sym in symbols:
        df = fetch_ohlcv_paginated(exchange, sym, "1h", start_2023_ms, now_ms, limit=1000, max_batches=140)
        if len(df) > 500:
            df = compress_df(df, max_bars=2200)
            datasets[(sym, "1h")] = df
            print(f"  fetched {sym} 1h bars={len(df)}")

    print("[2/5] Running base large-scale backtest simulation...")
    all_trades: List[TradeResult] = []
    for (sym, tf), df in datasets.items():
        all_trades.extend(simulate_trades(df, sym, tf, base_module))

    # Pass C (if needed): add higher-frequency data to ensure >=300 trades
    if len(all_trades) < 300:
        print(f"  base trades={len(all_trades)}; expanding with 5m datasets...")
        extra_symbols = symbols[:4]
        for sym in extra_symbols:
            df = fetch_ohlcv_paginated(exchange, sym, "5m", start_2024_ms, now_ms, limit=1000, max_batches=260)
            if len(df) > 500:
                df = compress_df(df, max_bars=2800)
                datasets[(sym, "5m")] = df
                print(f"  fetched {sym} 5m bars={len(df)}")

        all_trades = []
        for (sym, tf), df in datasets.items():
            all_trades.extend(simulate_trades(df, sym, tf, base_module))

    if len(all_trades) < 300:
        print(f"  still only {len(all_trades)} trades; expanding with 1m datasets on top liquidity pairs...")
        extra_symbols = symbols[:2]
        for sym in extra_symbols:
            df = fetch_ohlcv_paginated(exchange, sym, "1m", start_2024_ms, now_ms, limit=1000, max_batches=220)
            if len(df) > 500:
                df = compress_df(df, max_bars=4000)
                datasets[(sym, "1m")] = df
                print(f"  fetched {sym} 1m bars={len(df)}")

        all_trades = []
        for (sym, tf), df in datasets.items():
            all_trades.extend(simulate_trades(df, sym, tf, base_module))

    close_fn = getattr(exchange, "close", None)
    if callable(close_fn):
        try:
            close_fn()
        except TypeError:
            pass

    print(f"[3/5] Aggregate trades generated: {len(all_trades)}")

    aggregate = metrics_from_trades(all_trades)
    by_asset = {}
    for sym in sorted(set(t.symbol for t in all_trades)):
        by_asset[sym] = metrics_from_trades([t for t in all_trades if t.symbol == sym])

    # Yearly / condition robustness slices from timestamps
    trades_df = pd.DataFrame(
        [
            {
                "symbol": t.symbol,
                "timeframe": t.timeframe,
                "entry_time": t.entry_time,
                "return_pct": t.return_pct,
            }
            for t in all_trades
        ]
    )

    yearly = {}
    if not trades_df.empty:
        trades_df["year"] = pd.to_datetime(trades_df["entry_time"]).dt.year
        for y in sorted(trades_df["year"].unique()):
            y_rets = trades_df.loc[trades_df["year"] == y, "return_pct"].to_numpy()
            yearly[str(y)] = metrics_from_trades(
                [
                    TradeResult("ALL", "mix", pd.Timestamp.utcnow(), pd.Timestamp.utcnow(), 1, 1 + r, r, 0, 0, 1, "A+", 0)
                    for r in y_rets
                ]
            )

    print("[4/5] Running Monte Carlo and sensitivity analyses...")
    mc = monte_carlo(all_trades, runs=750, seed=7)
    sensitivity = run_sensitivity(datasets, aggregate)
    forward_setup = build_forward_test_setup(aggregate, mc)

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "large_scale_backtest": {
            "assets_tested": sorted(list(set(k[0] for k in datasets.keys()))),
            "timeframes_tested": sorted(list(set(k[1] for k in datasets.keys()))),
            "datasets": len(datasets),
            "total_trades": len(all_trades),
            "aggregate": aggregate,
            "by_asset": by_asset,
            "yearly": yearly,
            "trade_count_target_300_met": len(all_trades) >= 300,
        },
        "monte_carlo": mc,
        "sensitivity_analysis": sensitivity,
        "forward_test_setup": forward_setup,
    }

    # Decision logic
    real_edge = (
        report["large_scale_backtest"]["trade_count_target_300_met"]
        and aggregate["expectancy"] > 0
        and aggregate["profit_factor"] > 1.05
        and mc["positive_run_probability"] >= 0.60
        and not sensitivity["overfit_flag"]
    )

    confidence = 0.50
    confidence += min(0.20, max(0.0, aggregate["expectancy"] * 20))
    confidence += 0.10 if aggregate["profit_factor"] > 1.1 else 0.0
    confidence += 0.10 if mc["positive_run_probability"] > 0.70 else 0.0
    confidence += 0.10 if not sensitivity["overfit_flag"] else -0.10
    confidence = max(0.05, min(0.95, confidence))

    weaknesses = []
    if len(all_trades) < 300:
        weaknesses.append("Insufficient trade count for robust significance")
    if aggregate["expectancy"] <= 0:
        weaknesses.append("Non-positive expectancy in large-scale run")
    if mc["positive_run_probability"] < 0.60:
        weaknesses.append("Monte Carlo robustness weak under slippage/timing randomization")
    if sensitivity["overfit_flag"]:
        weaknesses.append("Parameter sensitivity indicates potential overfitting")
    if aggregate["max_drawdown"] < -0.30:
        weaknesses.append("Drawdown too deep for stable deployment")

    recommendations = []
    if len(all_trades) < 300:
        recommendations.append("Expand asset universe or extend timeframe to increase statistical power")
    if aggregate["expectancy"] <= 0:
        recommendations.append("Revisit A+ entry criteria and especially stop/target asymmetry")
    if mc["positive_run_probability"] < 0.60:
        recommendations.append("Harden execution assumptions: tighter slippage controls and liquidity filters")
    if sensitivity["overfit_flag"]:
        recommendations.append("Reduce threshold complexity and re-center around broader robust ranges")

    report["verdict"] = {
        "edge_real": bool(real_edge),
        "confidence_level": confidence,
        "weaknesses_found": weaknesses,
        "recommended_adjustments": recommendations,
    }

    out_path = ROOT / "quant_validation_report.json"
    out_path.write_text(json.dumps(report, indent=2), encoding="utf-8")
    print("[5/5] Validation complete.")
    print(json.dumps(report["verdict"], indent=2))
    print(f"\nSaved full report to: {out_path}")


if __name__ == "__main__":
    run_validation()

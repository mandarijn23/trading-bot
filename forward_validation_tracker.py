import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd


ROOT = Path(__file__).resolve().parent
BASELINE_FILE = ROOT / "quant_validation_report.json"
TRADES_FILE = ROOT / "trades_history.csv"
OUT_FILE = ROOT / "forward_validation_status.json"


def load_baseline():
    if not BASELINE_FILE.exists():
        raise FileNotFoundError("quant_validation_report.json not found. Run quant_validation.py first.")
    return json.loads(BASELINE_FILE.read_text(encoding="utf-8"))


def compute_metrics(trades_df: pd.DataFrame):
    if trades_df.empty:
        return {
            "trades": 0,
            "win_rate": 0.0,
            "avg_win": 0.0,
            "avg_loss": 0.0,
            "expectancy": 0.0,
            "profit_factor": 0.0,
            "total_return": 0.0,
        }

    rets = trades_df["pnl_pct"].to_numpy(dtype=float) / 100.0
    wins = rets[rets > 0]
    losses = rets[rets <= 0]

    wr = len(wins) / len(rets)
    avg_win = float(wins.mean()) if len(wins) else 0.0
    avg_loss = float(losses.mean()) if len(losses) else 0.0
    exp = (wr * avg_win) - ((1 - wr) * abs(avg_loss))

    gross_win = float(wins.sum()) if len(wins) else 0.0
    gross_loss = float(abs(losses.sum())) if len(losses) else 0.0
    pf = gross_win / gross_loss if gross_loss > 0 else 0.0

    equity = (1 + pd.Series(rets)).cumprod()

    return {
        "trades": int(len(rets)),
        "win_rate": float(wr),
        "avg_win": avg_win,
        "avg_loss": avg_loss,
        "expectancy": float(exp),
        "profit_factor": float(pf),
        "total_return": float(equity.iloc[-1] - 1.0),
    }


def run_tracker(min_trades: int = 30):
    baseline = load_baseline()
    targets = baseline["forward_test_setup"]["baseline_targets"]
    alerts = baseline["forward_test_setup"]["drift_alert_rules"]

    if not TRADES_FILE.exists():
        status = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "WAITING_FOR_TRADES",
            "message": "No trades_history.csv found yet",
        }
        OUT_FILE.write_text(json.dumps(status, indent=2), encoding="utf-8")
        print(json.dumps(status, indent=2))
        return

    df = pd.read_csv(TRADES_FILE)
    if "pnl_pct" not in df.columns:
        status = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "status": "INVALID_TRADES_FILE",
            "message": "trades_history.csv missing pnl_pct column",
        }
        OUT_FILE.write_text(json.dumps(status, indent=2), encoding="utf-8")
        print(json.dumps(status, indent=2))
        return

    df = df.dropna(subset=["pnl_pct"])
    metrics = compute_metrics(df)

    drift_flags = []

    if metrics["trades"] >= min_trades:
        if targets["expectancy"] != 0:
            exp_drop_pct = (targets["expectancy"] - metrics["expectancy"]) / abs(targets["expectancy"]) * 100
            if exp_drop_pct > alerts["expectancy_drop_pct"]:
                drift_flags.append(f"Expectancy drift too large: {exp_drop_pct:.1f}%")

        wr_drop = (targets["win_rate"] - metrics["win_rate"]) * 100
        if wr_drop > alerts["win_rate_drop_pct_points"]:
            drift_flags.append(f"Win rate drift too large: {wr_drop:.2f} pp")

        if metrics["profit_factor"] < alerts["profit_factor_min"]:
            drift_flags.append("Profit factor below minimum")

    status = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "baseline_targets": targets,
        "current_live_metrics": metrics,
        "minimum_trades_for_validation": min_trades,
        "drift_flags": drift_flags,
        "pass": len(drift_flags) == 0 and metrics["trades"] >= min_trades,
    }

    OUT_FILE.write_text(json.dumps(status, indent=2), encoding="utf-8")
    print(json.dumps(status, indent=2))


if __name__ == "__main__":
    run_tracker()

#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${1:-/home/nas/trading-bot}"
PYTHON_BIN="$APP_DIR/.venv/bin/python"
LOG_FILE="$APP_DIR/hourly_train.log"
PERF_LOG="$APP_DIR/hourly_performance.log"

cd "$APP_DIR"

# Keep imports stable regardless of whether trainers live under models/.
export PYTHONPATH="$APP_DIR:$APP_DIR/core:$APP_DIR/models:$APP_DIR/strategies:$APP_DIR/utils:$APP_DIR/config${PYTHONPATH:+:$PYTHONPATH}"

{
  echo "=== $(date -u +'%Y-%m-%dT%H:%M:%SZ') hourly train & report start ==="
  
  # Hardened hourly training: v2 adds cache dedup + overlap checks.
  if "$PYTHON_BIN" models/train_stock_rf_v2.py --timeframe 15Min --limit 1500 --hard --n-estimators 500 --max-depth 20 --threshold 0.5 --lookahead-bars 4 --cost-bps 3 --slippage-bps 2; then
    echo "[OK] Hourly training completed"
  else
    echo "[WARN] Hourly training failed; resending latest chart"
    "$PYTHON_BIN" resend_training_report.py || true
  fi
  
  # Hourly performance report with graphs
  echo "[$(date -u +'%H:%M:%SZ')] Generating performance report..."
  if "$PYTHON_BIN" tools/hourly_performance_report.py \
      --csv "$APP_DIR/trades_history.csv" \
      --logs "$APP_DIR/logs"; then
    echo "[OK] Performance report sent to Discord"
  else
    echo "[WARN] Performance report failed"
  fi
  
  echo "=== $(date -u +'%Y-%m-%dT%H:%M:%SZ') hourly train & report end ==="
} >>"$LOG_FILE" 2>&1
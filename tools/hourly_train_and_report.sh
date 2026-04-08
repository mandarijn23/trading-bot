#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${1:-/home/nas/trading-bot}"
PYTHON_BIN="$APP_DIR/.venv/bin/python"
LOG_FILE="$APP_DIR/hourly_train.log"

cd "$APP_DIR"

{
  echo "=== $(date -u +'%Y-%m-%dT%H:%M:%SZ') hourly train start ==="
  # Hardened hourly training: v2 adds cache dedup + overlap checks.
  if "$PYTHON_BIN" train_stock_rf_v2.py --timeframe 15Min --limit 1500 --hard --n-estimators 500 --max-depth 20 --threshold 0.5 --lookahead-bars 4 --cost-bps 3 --slippage-bps 2; then
    echo "[OK] Hourly training completed"
  else
    echo "[WARN] Hourly training failed; resending latest chart"
    "$PYTHON_BIN" resend_training_report.py || true
  fi
  echo "=== $(date -u +'%Y-%m-%dT%H:%M:%SZ') hourly train end ==="
} >>"$LOG_FILE" 2>&1
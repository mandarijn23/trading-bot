#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${1:-/home/nas/trading-bot}"
PYTHON_BIN="$APP_DIR/.venv/bin/python"
LOG_FILE="$APP_DIR/logs/daily_profile_graph.log"

cd "$APP_DIR"
mkdir -p logs

if [[ ! -x "$PYTHON_BIN" ]]; then
  PYTHON_BIN="python"
fi

{
  echo "=== $(date -u +'%Y-%m-%dT%H:%M:%SZ') daily profile+graph start ==="

  "$APP_DIR/tools/rotate_stock_profile.sh" "$APP_DIR" apply

  # Prefer the newer multi-chart Discord report introduced with hourly reporting.
  if PYTHONPATH="core:models:strategies:utils:config:${PYTHONPATH:-}" \
      "$PYTHON_BIN" "$APP_DIR/tools/hourly_performance_report.py" \
        --csv "$APP_DIR/trades_history.csv" \
        --logs "$APP_DIR/logs"; then
    echo "[OK] New multi-chart report sent"
  else
    echo "[WARN] New report failed, falling back to legacy single graph"
    PYTHONPATH="core:models:strategies:utils:config:${PYTHONPATH:-}" \
      "$PYTHON_BIN" "$APP_DIR/tools/send_performance_graph.py" --days 14 --output "$APP_DIR/logs/performance_graph.png" || true
  fi

  echo "=== $(date -u +'%Y-%m-%dT%H:%M:%SZ') daily profile+graph end ==="
} >>"$LOG_FILE" 2>&1

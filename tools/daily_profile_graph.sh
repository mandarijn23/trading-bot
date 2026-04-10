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

  PYTHONPATH="core:models:strategies:utils:config:${PYTHONPATH:-}" \
    "$PYTHON_BIN" "$APP_DIR/tools/send_performance_graph.py" --days 14 --output "$APP_DIR/logs/performance_graph.png" || true

  echo "=== $(date -u +'%Y-%m-%dT%H:%M:%SZ') daily profile+graph end ==="
} >>"$LOG_FILE" 2>&1

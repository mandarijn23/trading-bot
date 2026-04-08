#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${1:-/home/nas/trading-bot}"
LOG_FILE="$APP_DIR/nas_repair.log"

exec >>"$LOG_FILE" 2>&1

echo "=== $(date -u +'%Y-%m-%dT%H:%M:%SZ') NAS repair start ==="
"$APP_DIR/nas_health_check.sh" "$APP_DIR" || {
  echo "Health check reported issues; trying service restart and recheck."
  sudo systemctl restart trading-bot-stock.service
  sleep 5
  "$APP_DIR/nas_health_check.sh" "$APP_DIR"
}
echo "=== $(date -u +'%Y-%m-%dT%H:%M:%SZ') NAS repair end ==="

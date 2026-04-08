#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${1:-/home/nas/trading-bot}"
SERVICE_NAME="trading-bot-stock.service"
BOT_CMD="$APP_DIR/run_stock_session.sh"
PYTHON_BIN="$APP_DIR/.venv/bin/python"

check_ok() {
  printf '[OK] %s\n' "$1"
}

check_warn() {
  printf '[WARN] %s\n' "$1"
}

check_fail() {
  printf '[FAIL] %s\n' "$1"
  return 1
}

if [ ! -d "$APP_DIR" ]; then
  check_fail "App dir not found: $APP_DIR"
  exit 1
fi

if [ ! -x "$BOT_CMD" ]; then
  check_fail "Runner missing or not executable: $BOT_CMD"
  exit 1
fi

if [ ! -x "$PYTHON_BIN" ]; then
  check_fail "Virtualenv Python missing: $PYTHON_BIN"
  exit 1
fi

if ! command -v systemctl >/dev/null 2>&1; then
  check_fail "systemctl not available"
  exit 1
fi

SERVICE_STATE=$(systemctl is-active "$SERVICE_NAME" 2>/dev/null || true)
if [ "$SERVICE_STATE" = "active" ]; then
  check_ok "Service active: $SERVICE_NAME"
else
  check_warn "Service state: ${SERVICE_STATE:-unknown}"
fi

DISK_USAGE=$(df -P "$APP_DIR" | awk 'NR==2 {gsub("%","",$5); print $5}')
if [ -n "$DISK_USAGE" ] && [ "$DISK_USAGE" -ge 90 ]; then
  check_warn "Disk usage high: ${DISK_USAGE}%"
else
  check_ok "Disk usage acceptable: ${DISK_USAGE:-unknown}%"
fi

if "$PYTHON_BIN" "$APP_DIR/paper_launch_check.py" --mode stocks >/tmp/trading-bot-preflight.log 2>&1; then
  check_ok "Paper preflight passed"
else
  check_warn "Paper preflight failed; see /tmp/trading-bot-preflight.log"
fi

if [ "$SERVICE_STATE" != "active" ]; then
  check_warn "Attempting service restart"
  sudo systemctl restart "$SERVICE_NAME"
  sleep 2
  NEW_STATE=$(systemctl is-active "$SERVICE_NAME" 2>/dev/null || true)
  if [ "$NEW_STATE" = "active" ]; then
    check_ok "Service restarted"
  else
    check_fail "Service restart failed"
    exit 1
  fi
fi

check_ok "Health check complete"

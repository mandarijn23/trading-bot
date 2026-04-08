#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${1:-/home/nas/trading-bot}"
SYSTEMD_DIR="${2:-/etc/systemd/system}"

ROOT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

UNIT_FILES=(
  "systemd/nas/trading-bot-stock.service"
  "systemd/nas/trading-bot-stock.timer"
  "systemd/nas/trading-bot-watchdog.service"
  "systemd/nas/trading-bot-watchdog.timer"
  "systemd/nas/trading-bot-daily-profile-graph.service"
  "systemd/nas/trading-bot-daily-profile-graph.timer"
  "systemd/nas/trading-bot-train-hourly.service"
  "systemd/nas/trading-bot-train-hourly.timer"
)

if [[ ! -d "$APP_DIR" ]]; then
  echo "[FAIL] App directory not found: $APP_DIR"
  exit 1
fi

if command -v git >/dev/null 2>&1; then
  git config --global --add safe.directory "$APP_DIR" || true
  echo "[OK] Marked $APP_DIR as a safe Git directory"
fi

echo "[INFO] Installing trading bot units into $SYSTEMD_DIR"
for unit in "${UNIT_FILES[@]}"; do
  src="$ROOT_DIR/$unit"
  dst="$SYSTEMD_DIR/$(basename "$unit")"
  if [[ ! -f "$src" ]]; then
    echo "[FAIL] Missing unit file: $src"
    exit 1
  fi
  sudo cp "$src" "$dst"
  echo "[OK] Installed $(basename "$unit")"
done

sudo systemctl daemon-reload

echo "[INFO] Enabling timers and primary service"
sudo systemctl enable --now trading-bot-stock.service
sudo systemctl enable --now trading-bot-watchdog.timer
sudo systemctl enable --now trading-bot-daily-profile-graph.timer
sudo systemctl enable --now trading-bot-train-hourly.timer

echo "[OK] NAS stack installed and enabled"
echo "[INFO] Verify with: systemctl status trading-bot-stock.service trading-bot-watchdog.timer trading-bot-daily-profile-graph.timer trading-bot-train-hourly.timer --no-pager"
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
SYSTEMD_DIR="$HOME/.config/systemd/user"
SERVICE_NAME="trading-bot-stock-local.service"

mkdir -p "$SYSTEMD_DIR"
cp "$APP_DIR/systemd/$SERVICE_NAME" "$SYSTEMD_DIR/$SERVICE_NAME"

systemctl --user daemon-reload
systemctl --user enable "$SERVICE_NAME"
systemctl --user restart "$SERVICE_NAME"

echo "Service installed and started: $SERVICE_NAME"
echo "Logs: journalctl --user -u $SERVICE_NAME -f"
echo "Status: systemctl --user status $SERVICE_NAME"

#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$APP_DIR"

LOCK_FILE="/tmp/trading-bot-stock.lock"
exec 9>"$LOCK_FILE"
flock -n 9 || exit 0

if [ -f ".venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
fi

PYTHON_BIN="$(pwd)/.venv/bin/python"
if [ ! -x "$PYTHON_BIN" ]; then
  PYTHON_BIN="python"
fi

export PYTHONPATH="core:models:strategies:utils:config:${PYTHONPATH:-}"
exec "$PYTHON_BIN" core/stock_bot.py

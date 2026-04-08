#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")"

LOCK_FILE="/tmp/trading-bot-stock.lock"
exec 9>"$LOCK_FILE"
flock -n 9 || exit 0

if [ -f ".venv/bin/activate" ]; then
  # shellcheck disable=SC1091
  source ".venv/bin/activate"
fi

exec "$(pwd)/.venv/bin/python" stock_bot.py

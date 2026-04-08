#!/usr/bin/env bash
set -euo pipefail

BOT_DIR="/home/nas/trading-bot"
LOGS_DIR="${BOT_DIR}/logs"
mkdir -p "${LOGS_DIR}"

# Generate report with timestamp
REPORT_FILE="${LOGS_DIR}/report_$(date +%Y%m%d_%H%M%S).md"

{
    echo "# Trading Bot Report - $(date)"
    echo ""
    echo "## Service Status"
    systemctl status trading-bot-stock.service 2>&1 | head -10
    echo ""
    echo "## Recent Logs"
    journalctl -u trading-bot-stock --no-pager -n 30
    echo ""
    echo "## Code Quality"
    echo "- ML Model: $(grep -q 'from ml_model_rf import' bot.py && echo '✅ GOOD' || echo '❌ BAD')"
    echo "- Lock State: $(grep -q 'asyncio.Lock()' bot.py && echo '✅ GOOD' || echo '❌ BAD')"
    echo ""
    echo "## Memory Usage"
    ps aux | grep stock_bot.py | grep -v grep || echo "Not running"
} > "${REPORT_FILE}"

# Also keep a latest copy
cp "${REPORT_FILE}" "${LOGS_DIR}/latest.md"

# Git push
cd "${BOT_DIR}"
git add logs/ bot.log 2>/dev/null || true
git add stock_bot.log 2>/dev/null || true

if ! git diff --cached --quiet 2>/dev/null; then
    git commit -m "📊 Hourly logs - $(date '+%Y-%m-%d %H:%M:%S')" 2>/dev/null || true
    git push origin master 2>/dev/null || echo "Push failed at $(date)"
fi

echo "✅ Logs pushed at $(date)"

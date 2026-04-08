#!/bin/bash
set -e

BOT_DIR="/home/nas/trading-bot"
LOGS_DIR="${BOT_DIR}/logs"
REPORT_FILE="${LOGS_DIR}/report_$(date '+%Y%m%d_%H%M%S').md"

mkdir -p "${LOGS_DIR}"

# Export SSH key for git to use
export GIT_SSH_COMMAND="ssh -i /root/.ssh/id_ed25519 -o StrictHostKeyChecking=no"

{
    echo "# Trading Bot Report - $(date)"
    echo ""
    echo "## Service Status"
    systemctl status trading-bot-stock 2>&1 | head -15
    echo ""
    echo "## Recent Trades (BUY signals)"
    grep "BUY signal" "${BOT_DIR}/stock_bot.log" 2>/dev/null | tail -10 || echo "No trades yet"
    echo ""
    echo "## Recent Exits"
    grep -E "EXIT|TRAIL_STOP|TAKE_PROFIT" "${BOT_DIR}/stock_bot.log" 2>/dev/null | tail -10 || echo "No exits yet"
    echo ""
    echo "## Recent Errors"
    tail -20 "${BOT_DIR}/stock_bot.log" 2>/dev/null | grep -i "error" | tail -5 || echo "No errors"
} > "${REPORT_FILE}"

cp "${REPORT_FILE}" "${LOGS_DIR}/latest.md"

cd "${BOT_DIR}"
git add logs/ stock_bot.log 2>/dev/null || true
git diff --cached --quiet 2>/dev/null || (git commit -m "📊 Hourly logs - $(date '+%Y-%m-%d %H:%M:%S')" && git push origin master)

echo "✅ Pushed - $(date)"

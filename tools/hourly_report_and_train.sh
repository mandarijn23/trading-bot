#!/bin/bash
# Hourly performance and training report wrapper
# This runs both hourly training checks and performance reporting

set -eo pipefail

export PYTHONPATH="${PYTHONPATH}:/opt/trading-bot/models:/opt/trading-bot/core:/opt/trading-bot/strategies:/opt/trading-bot/utils:/opt/trading-bot/config"

REPO_DIR="/opt/trading-bot"
VENV_PYTHON="${REPO_DIR}/.venv/bin/python"
LOGS_DIR="${REPO_DIR}/logs"

# Ensure logs directory exists
mkdir -p "${LOGS_DIR}"

# Log file for this execution
EXEC_LOG="${LOGS_DIR}/hourly_$(date +%Y%m%d_%H%M%S).log"

{
    echo "[$(date)] Starting hourly report and training check..."
    
    # Run training check (v2 trainer)
    echo "[$(date)] Running training check..."
    cd "${REPO_DIR}"
    ${VENV_PYTHON} models/train_stock_rf_v2.py 2>&1 || {
        echo "[$(date)] ⚠️  Training check failed, continuing with performance report..."
    }
    
    # Run performance reporting
    echo "[$(date)] Running performance report..."
    ${VENV_PYTHON} tools/hourly_performance_report.py \
        --csv "${REPO_DIR}/trades_history.csv" \
        --logs "${LOGS_DIR}" 2>&1 || {
        echo "[$(date)] ⚠️  Performance report failed"
    }
    
    echo "[$(date)] Hourly report complete"
    
} >> "${EXEC_LOG}" 2>&1

exit 0

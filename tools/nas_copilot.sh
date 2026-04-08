#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${1:-/home/nas/trading-bot}"
ACTION="${2:-}"
SERVICE_NAME="trading-bot-stock.service"
SERVICE_UNIT="${SERVICE_NAME}"
TIMER_UNIT="trading-bot-stock.timer"
DAILY_SERVICE_UNIT="trading-bot-daily-profile-graph.service"
DAILY_TIMER_UNIT="trading-bot-daily-profile-graph.timer"
HEALTH_CHECK="$APP_DIR/nas_health_check.sh"
REPAIR_SCRIPT="$APP_DIR/nas_repair.sh"
PRECHECK="$APP_DIR/paper_launch_check.py"
PYTHON_BIN="$APP_DIR/.venv/bin/python"
AI_BOOTSTRAP="$APP_DIR/nas_ai_bootstrap.sh"
AI_MODEL="${AI_MODEL:-qwen2.5:3b}"
AI_FALLBACK_MODEL="${AI_FALLBACK_MODEL:-phi3:mini}"

usage() {
  cat <<EOF
Usage: $0 [app_dir] <action>

Allowed actions:
  status       Show service and timer status
  health       Run NAS health check
  repair       Run approved repair loop
  preflight    Run stock paper-trading preflight
  ai-bootstrap Install Ollama and pull the lightweight NAS models
  ai-status    Show Ollama status and installed models
  ai-test      Run a short Ollama test prompt
  ai-pull-primary   Pull the primary NAS model
  ai-pull-fallback  Pull the fallback NAS model
  logs         Show recent service logs
  daily-status Show daily profile+graph timer status
  restart      Restart the stock service
  daily-run    Run profile rotation + graph push now
  stop         Stop the stock service
  start        Start the stock service
EOF
}

run_confirmed() {
  local label="$1"
  shift
  local cmd=("$@")

  printf 'Planned action: %s\n' "$label"
  printf 'Command: '
  printf '%q ' "${cmd[@]}"
  printf '\n'
  if [ "${COPILOT_ASSUME_YES:-0}" = "1" ]; then
    echo 'Auto-approved via COPILOT_ASSUME_YES=1.'
    "${cmd[@]}"
    return
  fi
  read -r -p 'Type YES to run: ' answer
  if [ "$answer" != "YES" ]; then
    echo 'Cancelled.'
    exit 1
  fi
  "${cmd[@]}"
}

if [ -z "$ACTION" ]; then
  usage
  exit 1
fi

case "$ACTION" in
  status)
    systemctl status "$SERVICE_UNIT" --no-pager || true
    systemctl status "$TIMER_UNIT" --no-pager || true
    ;;
  health)
    run_confirmed "NAS health check" "$HEALTH_CHECK" "$APP_DIR"
    ;;
  repair)
    run_confirmed "NAS repair loop" "$REPAIR_SCRIPT" "$APP_DIR"
    ;;
  preflight)
    run_confirmed "Stock preflight" "$PYTHON_BIN" "$PRECHECK" --mode stocks
    ;;
  ai-bootstrap)
    run_confirmed "Install Ollama and pull NAS AI models" "$AI_BOOTSTRAP" "$APP_DIR"
    ;;
  ai-status)
    run_confirmed "Check Ollama status" bash -lc 'command -v ollama >/dev/null 2>&1 && { echo "Installed models:"; ollama list; } || { echo "ollama is not installed"; exit 1; }'
    ;;
  ai-test)
    run_confirmed "Run Ollama test prompt" ollama run "$AI_MODEL" "Summarize the NAS trading bot status and give one safe next repair step."
    ;;
  ai-pull-primary)
    run_confirmed "Pull primary NAS model" ollama pull "$AI_MODEL"
    ;;
  ai-pull-fallback)
    run_confirmed "Pull fallback NAS model" ollama pull "$AI_FALLBACK_MODEL"
    ;;
  logs)
    journalctl -u "$SERVICE_UNIT" -n 100 --no-pager || true
    ;;
  daily-status)
    systemctl status "$DAILY_SERVICE_UNIT" --no-pager || true
    systemctl status "$DAILY_TIMER_UNIT" --no-pager || true
    ;;
  daily-run)
    run_confirmed "Run daily profile+graph now" sudo systemctl start "$DAILY_SERVICE_UNIT"
    ;;
  restart)
    run_confirmed "Restart stock service" sudo systemctl restart "$SERVICE_UNIT"
    ;;
  stop)
    run_confirmed "Stop stock service" sudo systemctl stop "$SERVICE_UNIT"
    ;;
  start)
    run_confirmed "Start stock service" sudo systemctl start "$SERVICE_UNIT"
    ;;
  *)
    usage
    exit 1
    ;;
esac

#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${1:-/home/nas/trading-bot}"
ACTION="${2:-apply}"
ENV_FILE="$APP_DIR/.env"
STATE_FILE="$APP_DIR/logs/profile_cycle_state.env"
SERVICE_NAME="trading-bot-stock.service"

if [[ "$APP_DIR" == "--help" || "$APP_DIR" == "-h" ]]; then
  ACTION="help"
fi

usage() {
  cat <<EOF
Usage: $0 [app_dir] [action]

Actions:
  apply    Apply today's profile in a 4-day cycle (default)
  status   Show current cycle state and active profile
  force-a  Force aggressive profile now (no cycle update)
  force-n  Force normal profile now (no cycle update)
  help     Show this help

Cycle behavior:
  Day 1-2: aggressive
  Day 3-4: normal
  Repeat...

Notes:
  - Script stores cycle state in: logs/profile_cycle_state.env
  - It only advances once per calendar day.
  - It restarts trading-bot-stock.service after apply if systemd is available.
EOF
}

if [[ "$ACTION" == "help" ]]; then
  usage
  exit 0
fi

if [[ ! -d "$APP_DIR" ]]; then
  echo "[FAIL] App directory not found: $APP_DIR"
  exit 1
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "[FAIL] Missing env file: $ENV_FILE"
  exit 1
fi

mkdir -p "$(dirname "$STATE_FILE")"

escape_sed_replacement() {
  printf '%s' "$1" | sed -e 's/[&|]/\\&/g'
}

set_env_key() {
  local key="$1"
  local value="$2"
  local escaped
  escaped="$(escape_sed_replacement "$value")"

  if grep -q "^${key}=" "$ENV_FILE"; then
    sed -i "s|^${key}=.*|${key}=${escaped}|" "$ENV_FILE"
  else
    printf '%s=%s\n' "$key" "$value" >> "$ENV_FILE"
  fi
}

apply_profile_values() {
  local profile="$1"

  set_env_key "STOCK_DYNAMIC_SELECTION" "true"
  set_env_key "STOCK_UNIVERSE_SYMBOLS" "SPY,QQQ,VOO,IWM,DIA,XLK,XLF,XLE,SMH,NVDA,AAPL,MSFT,AMZN,META,TSLA,AMD,GOOGL"
  set_env_key "STOCK_TIMEFRAME" "15Min"
  set_env_key "STOCK_CHECK_INTERVAL" "60"
  set_env_key "STOCK_LOG_LEVEL" "INFO"
  set_env_key "STOCK_LOG_MAX_MB" "10"
  set_env_key "STOCK_LOG_BACKUP_COUNT" "7"
  set_env_key "STOCK_PAPER_TRADING" "true"

  if [[ "$profile" == "aggressive" ]]; then
    set_env_key "STOCK_DYNAMIC_SYMBOL_COUNT" "6"
    set_env_key "STOCK_SELECTION_REFRESH_CYCLES" "8"
    set_env_key "STOCK_TRADE_AMOUNT" "25.0"
    set_env_key "STOCK_MAX_OPEN_POS" "3"
    set_env_key "STOCK_MIN_AI_CONFIDENCE" "0.40"
    set_env_key "STOCK_STOP_LOSS" "0.035"
    set_env_key "STOCK_TAKE_PROFIT" "0.07"
    set_env_key "STOCK_TRAILING_STOP" "0.025"
    set_env_key "STOCK_MIN_DOLLAR_VOLUME" "1500000"
    set_env_key "STOCK_MIN_ATR_PCT" "0.004"
    set_env_key "STOCK_MAX_ATR_PCT" "0.10"
  else
    set_env_key "STOCK_DYNAMIC_SYMBOL_COUNT" "4"
    set_env_key "STOCK_SELECTION_REFRESH_CYCLES" "15"
    set_env_key "STOCK_TRADE_AMOUNT" "20.0"
    set_env_key "STOCK_MAX_OPEN_POS" "2"
    set_env_key "STOCK_MIN_AI_CONFIDENCE" "0.45"
    set_env_key "STOCK_STOP_LOSS" "0.03"
    set_env_key "STOCK_TAKE_PROFIT" "0.05"
    set_env_key "STOCK_TRAILING_STOP" "0.02"
    set_env_key "STOCK_MIN_DOLLAR_VOLUME" "2000000"
    set_env_key "STOCK_MIN_ATR_PCT" "0.003"
    set_env_key "STOCK_MAX_ATR_PCT" "0.08"
  fi
}

restart_service_if_available() {
  if command -v systemctl >/dev/null 2>&1; then
    if systemctl list-unit-files | grep -q "^${SERVICE_NAME}"; then
      echo "[INFO] Restarting ${SERVICE_NAME} to apply new profile"
      sudo systemctl restart "$SERVICE_NAME"
      return
    fi
  fi
  echo "[WARN] systemd service ${SERVICE_NAME} not found; restart manually if needed"
}

load_state() {
  LAST_APPLIED_DATE=""
  CYCLE_DAY="0"

  if [[ -f "$STATE_FILE" ]]; then
    # shellcheck disable=SC1090
    source "$STATE_FILE"
  fi

  LAST_APPLIED_DATE="${LAST_APPLIED_DATE:-}"
  CYCLE_DAY="${CYCLE_DAY:-0}"
}

save_state() {
  local date="$1"
  local cycle_day="$2"

  cat > "$STATE_FILE" <<EOF
LAST_APPLIED_DATE=$date
CYCLE_DAY=$cycle_day
EOF
}

profile_for_cycle_day() {
  local d="$1"
  if [[ "$d" == "1" || "$d" == "2" ]]; then
    echo "aggressive"
  else
    echo "normal"
  fi
}

print_status() {
  load_state
  local today
  today="$(date +%F)"
  local next_day
  if [[ "$CYCLE_DAY" -eq 0 ]]; then
    next_day=1
  else
    next_day=$(( (CYCLE_DAY % 4) + 1 ))
  fi

  echo "[INFO] Today: $today"
  echo "[INFO] Last applied date: ${LAST_APPLIED_DATE:-<none>}"
  echo "[INFO] Current cycle day: ${CYCLE_DAY}"
  echo "[INFO] Next cycle day: ${next_day} ($(profile_for_cycle_day "$next_day"))"

  echo "[INFO] Active env keys:"
  grep -E '^STOCK_(DYNAMIC_SELECTION|DYNAMIC_SYMBOL_COUNT|SELECTION_REFRESH_CYCLES|TRADE_AMOUNT|MAX_OPEN_POS|MIN_AI_CONFIDENCE|STOP_LOSS|TAKE_PROFIT|TRAILING_STOP|MIN_DOLLAR_VOLUME|MIN_ATR_PCT|MAX_ATR_PCT)=' "$ENV_FILE" || true
}

apply_cycle_profile() {
  load_state
  local today
  today="$(date +%F)"

  if [[ "$LAST_APPLIED_DATE" == "$today" ]]; then
    local profile
    profile="$(profile_for_cycle_day "$CYCLE_DAY")"
    echo "[INFO] Profile already applied for today ($today): day $CYCLE_DAY -> $profile"
    return 0
  fi

  local next_day
  next_day=$(( (CYCLE_DAY % 4) + 1 ))
  local profile
  profile="$(profile_for_cycle_day "$next_day")"

  echo "[INFO] Applying cycle day $next_day profile: $profile"
  apply_profile_values "$profile"
  save_state "$today" "$next_day"
  restart_service_if_available
  echo "[OK] Applied profile: $profile (cycle day $next_day)"
}

force_profile() {
  local profile="$1"
  echo "[INFO] Forcing profile now: $profile"
  apply_profile_values "$profile"
  restart_service_if_available
  echo "[OK] Forced profile: $profile"
}

case "$ACTION" in
  apply)
    apply_cycle_profile
    ;;
  status)
    print_status
    ;;
  force-a)
    force_profile "aggressive"
    ;;
  force-n)
    force_profile "normal"
    ;;
  *)
    usage
    exit 1
    ;;
esac

#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${1:-/home/nas/trading-bot}"
PRIMARY_MODEL="${PRIMARY_MODEL:-qwen2.5:3b}"
FALLBACK_MODEL="${FALLBACK_MODEL:-phi3:mini}"

check_cmd() {
  command -v "$1" >/dev/null 2>&1
}

echo "[INFO] NAS AI bootstrap starting for $APP_DIR"

if ! check_cmd curl; then
  echo "[FAIL] curl is required to install Ollama"
  exit 1
fi

if ! check_cmd ollama; then
  echo "[INFO] Ollama not found; installing"
  curl -fsSL https://ollama.com/install.sh | sh
else
  echo "[OK] Ollama already installed"
fi

if ! check_cmd ollama; then
  echo "[FAIL] Ollama installation did not complete"
  exit 1
fi

echo "[INFO] Pulling primary model: $PRIMARY_MODEL"
ollama pull "$PRIMARY_MODEL"

echo "[INFO] Pulling fallback model: $FALLBACK_MODEL"
ollama pull "$FALLBACK_MODEL"

echo "[INFO] Installed models:"
ollama list

echo "[INFO] Testing primary model with a short prompt"
ollama run "$PRIMARY_MODEL" "Reply with one short sentence confirming that the NAS repair assistant is ready."

echo "[OK] NAS AI bootstrap complete"
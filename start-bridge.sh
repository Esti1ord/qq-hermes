#!/usr/bin/env bash
set -euo pipefail

BASE_DIR="${QQ_HERMES_BASE_DIR:-/home/roxy/qq-hermes}"
if [ -f "$BASE_DIR/scripts/load_env.sh" ]; then
  # shellcheck source=/home/roxy/qq-hermes/scripts/load_env.sh
  source "$BASE_DIR/scripts/load_env.sh" "$BASE_DIR/.env"
fi
BASE_DIR="${QQ_HERMES_BASE_DIR:-$BASE_DIR}"
PYTHON_BIN="${QQ_HERMES_PYTHON:-$BASE_DIR/venv/bin/python}"
HOST="${QQ_HERMES_HOST:-0.0.0.0}"
PORT="${QQ_HERMES_PORT:-8765}"
APP="${QQ_HERMES_APP:-bridge:app}"

cd "$BASE_DIR"

if [ ! -x "$PYTHON_BIN" ]; then
  printf 'start-bridge: Python interpreter not executable: %s\n' "$PYTHON_BIN" >&2
  exit 1
fi

mkdir -p "$BASE_DIR/logs"

if [ -z "${BRIDGE_INBOUND_TOKEN:-}" ]; then
  printf 'start-bridge: BRIDGE_INBOUND_TOKEN is not set; /onebot and /test inbound auth stays disabled.\n' >&2
fi

exec "$PYTHON_BIN" -m uvicorn "$APP" --host "$HOST" --port "$PORT"

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"
TMP_DIR="$ROOT_DIR/tmp"
LOG_FILE="$TMP_DIR/onepitch-local.log"
BACKEND_PORT="${ONEFILE_BACKEND_PORT:-8000}"
FRONTEND_PORT="${ONEFILE_FRONTEND_PORT:-3000}"
BACKEND_URL="http://127.0.0.1:${BACKEND_PORT}"
FRONTEND_URL="http://127.0.0.1:${FRONTEND_PORT}/"

export ONEFILE_LOCAL_MODE="${ONEFILE_LOCAL_MODE:-1}"
export ONEFILE_OPS_ENABLED="${ONEFILE_OPS_ENABLED:-1}"
export ONEFILE_ENV="${ONEFILE_ENV:-development}"
export NEXT_PUBLIC_ONEFILE_LOCAL_MODE="${NEXT_PUBLIC_ONEFILE_LOCAL_MODE:-1}"
export NEXT_PUBLIC_API_BASE_URL="${NEXT_PUBLIC_API_BASE_URL:-$BACKEND_URL}"

mkdir -p "$TMP_DIR"
: >"$LOG_FILE"

log() {
  printf "%s\n" "$*" | tee -a "$LOG_FILE"
}

fail() {
  log "Error: $*"
  log "Log: $LOG_FILE"
  exit 1
}

command_exists() {
  command -v "$1" >/dev/null 2>&1
}

pid_on_port() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null | head -n 1 || true
}

command_for_pid() {
  local pid="$1"
  if [[ -z "$pid" ]]; then
    return 0
  fi
  ps -p "$pid" -o command= 2>/dev/null || true
}

is_backend_pid() {
  local command_line="$1"
  [[ "$command_line" == *"uvicorn"* && "$command_line" == *"backend.main:app"* ]]
}

is_frontend_pid() {
  local command_line="$1"
  [[ "$command_line" == *"next dev"* || "$command_line" == *"next-server"* || "$command_line" == *"next"* ]]
}

wait_for_url() {
  local url="$1"
  local label="$2"
  local attempts=60
  for _ in $(seq 1 "$attempts"); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 0.5
  done
  fail "$label did not become ready at $url"
}

open_ops() {
  if command_exists open; then
    open "$FRONTEND_URL" >/dev/null 2>&1 || true
  fi
}

cleanup() {
  if [[ -n "${BACKEND_PID:-}" ]]; then
    kill "$BACKEND_PID" 2>/dev/null || true
  fi
  if [[ -n "${FRONTEND_PID:-}" ]]; then
    kill "$FRONTEND_PID" 2>/dev/null || true
  fi
}
trap cleanup EXIT INT TERM

command_exists python3 || fail "python3 is not installed or not on PATH."
command_exists node || fail "node is not installed or not on PATH."
command_exists npm || fail "npm is not installed or not on PATH."
command_exists lsof || fail "lsof is required for port checks."
command_exists curl || fail "curl is required for readiness checks."

existing_backend_pid="$(pid_on_port "$BACKEND_PORT")"
existing_frontend_pid="$(pid_on_port "$FRONTEND_PORT")"

if [[ -n "$existing_backend_pid" || -n "$existing_frontend_pid" ]]; then
  backend_command="$(command_for_pid "$existing_backend_pid")"
  frontend_command="$(command_for_pid "$existing_frontend_pid")"
  backend_ok=0
  frontend_ok=0
  [[ -n "$existing_backend_pid" ]] && is_backend_pid "$backend_command" && backend_ok=1
  [[ -n "$existing_frontend_pid" ]] && is_frontend_pid "$frontend_command" && frontend_ok=1

  if [[ "$backend_ok" == "1" && "$frontend_ok" == "1" ]]; then
    log "OnePitch already appears to be running."
    log "  Backend PID:  $existing_backend_pid"
    log "  Frontend PID: $existing_frontend_pid"
    log "Opening: $FRONTEND_URL"
    open_ops
    exit 0
  fi

  if [[ -n "$existing_backend_pid" && "$backend_ok" != "1" ]]; then
    fail "Port $BACKEND_PORT is already used by another process: $backend_command"
  fi
  if [[ -n "$existing_frontend_pid" && "$frontend_ok" != "1" ]]; then
    fail "Port $FRONTEND_PORT is already used by another process: $frontend_command"
  fi
fi

cd "$ROOT_DIR"
log "Starting OnePitch local diagnosis workspace..."
log "Log: $LOG_FILE"
log "Backend:  $BACKEND_URL"
log "Frontend: $FRONTEND_URL"

python3 -m uvicorn backend.main:app --host 127.0.0.1 --port "$BACKEND_PORT" >>"$LOG_FILE" 2>&1 &
BACKEND_PID="$!"

cd "$FRONTEND_DIR"
npm run dev -- --hostname 127.0.0.1 --port "$FRONTEND_PORT" >>"$LOG_FILE" 2>&1 &
FRONTEND_PID="$!"

wait_for_url "$BACKEND_URL/health" "Backend"
wait_for_url "$FRONTEND_URL" "Frontend"

log "OnePitch is ready."
log "Opening: $FRONTEND_URL"
open_ops

wait "$BACKEND_PID" "$FRONTEND_PID"

#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="/Users/joesun/Desktop/OneFile"

if [[ ! -d "$ROOT_DIR" ]]; then
  echo "Cannot find OnePitch project directory:"
  echo "$ROOT_DIR"
  echo
  echo "Press any key to close."
  read -r -n 1
  exit 1
fi

cd "$ROOT_DIR"

if [[ ! -x "$ROOT_DIR/scripts/start-local.sh" ]]; then
  chmod +x "$ROOT_DIR/scripts/start-local.sh"
fi

echo "Starting OnePitch local diagnosis workspace..."
echo "Project: $ROOT_DIR"
echo

"$ROOT_DIR/scripts/start-local.sh"

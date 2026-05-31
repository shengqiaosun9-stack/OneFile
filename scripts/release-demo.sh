#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"

cd "$ROOT_DIR"

echo "[1/8] Running backend tests..."
python3 -m pytest backend/tests -q

echo "[2/8] Running online readiness guard..."
if [[ "${ONEPITCH_AI_PROVIDER:-deepseek}" == "deepseek" && -z "${DEEPSEEK_API_KEY:-}" ]]; then
  echo "Online readiness failed: missing DEEPSEEK_API_KEY."
  exit 1
fi
export ONEPITCH_AI_PROVIDER="${ONEPITCH_AI_PROVIDER:-deepseek}"
export DEEPSEEK_BASE_URL="${DEEPSEEK_BASE_URL:-https://api.deepseek.com}"
export DEEPSEEK_MODEL="${DEEPSEEK_MODEL:-deepseek-v4-flash}"
if [[ -z "${ONEPITCH_STORAGE_BACKEND:-}" ]]; then
  tmp_data_dir="$(mktemp -d)"
  cleanup_tmp_data() {
    rm -rf "$tmp_data_dir"
  }
  trap cleanup_tmp_data EXIT
  export ONEFILE_DATA_DIR="$tmp_data_dir"
fi
bash "$ROOT_DIR/scripts/check-online-readiness.sh"
if [[ -n "${tmp_data_dir:-}" ]]; then
  unset ONEFILE_DATA_DIR
  trap - EXIT
  cleanup_tmp_data
fi

echo "[3/8] Running frontend lint..."
cd "$FRONTEND_DIR"
npm run lint

echo "[4/8] Running frontend build..."
npm run build

echo "[5/8] Running impeccable UI gate..."
npm run check:impeccable

cd "$ROOT_DIR"

echo "[6/8] Running repository secret scan..."
bash "$ROOT_DIR/scripts/check-secrets.sh" repo

echo "[7/8] Checking git state..."
branch="$(git rev-parse --abbrev-ref HEAD)"
if [[ "$branch" != "main" ]]; then
  echo "Error: release-demo.sh must run on branch 'main' (current: $branch)."
  exit 1
fi

if ! git rev-parse --verify origin/main >/dev/null 2>&1; then
  echo "Error: origin/main not found. Set remote first."
  exit 1
fi

ahead="$(git rev-list --count origin/main..main)"
if [[ "$ahead" -eq 0 ]]; then
  echo "No new commits to push. Deployment triggers only when main has new commits."
  exit 0
fi

echo "[8/8] Pushing main to trigger Netlify + Render auto deploy..."
git push origin main

echo "Release completed. Monitor platform logs for rollout status."

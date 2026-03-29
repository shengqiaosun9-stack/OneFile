#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"

cd "$ROOT_DIR"

echo "[1/5] Running backend tests..."
python3 -m pytest backend/tests -q

echo "[2/5] Running frontend lint..."
cd "$FRONTEND_DIR"
npm run lint

echo "[3/5] Running frontend build..."
npm run build

cd "$ROOT_DIR"

echo "[4/5] Checking git state..."
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

echo "[5/5] Pushing main to trigger Netlify + Render auto deploy..."
git push origin main

echo "Release completed. Monitor platform logs for rollout status."

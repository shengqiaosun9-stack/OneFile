#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FRONTEND_DIR="$ROOT_DIR/frontend"

cd "$ROOT_DIR"

echo "[1/8] Running backend tests..."
python3 -m pytest backend/tests -q

echo "[2/8] Running AI readiness guard (must avoid fallback)..."
if [[ -z "${HUNYUAN_API_KEY:-}" ]]; then
  echo "AI readiness failed: missing HUNYUAN_API_KEY."
  exit 1
fi

tmp_data_dir="$(mktemp -d)"
cleanup_tmp_data() {
  rm -rf "$tmp_data_dir"
}
trap cleanup_tmp_data EXIT

export ONEFILE_DATA_DIR="$tmp_data_dir"
export ONEFILE_AUTH_DEBUG_CODES="1"
python3 - <<'PY'
import sys

from fastapi.testclient import TestClient

from backend.main import app

client = TestClient(app)
email = "release-check@onefile.app"

start_resp = client.post("/v1/auth/login/start", json={"email": email})
if start_resp.status_code != 200:
    print(f"AI readiness failed: auth start returned {start_resp.status_code}", file=sys.stderr)
    sys.exit(1)

start_payload = start_resp.json()
challenge_id = str(start_payload.get("challenge_id", "")).strip()
debug_code = str(start_payload.get("debug_code", "")).strip()
if not challenge_id or not debug_code:
    print("AI readiness failed: debug login code unavailable, cannot verify auth session.", file=sys.stderr)
    sys.exit(1)

verify_resp = client.post(
    "/v1/auth/login/verify",
    json={"email": email, "challenge_id": challenge_id, "code": debug_code},
)
if verify_resp.status_code != 200:
    print(f"AI readiness failed: auth verify returned {verify_resp.status_code}", file=sys.stderr)
    sys.exit(1)

generate_resp = client.post(
    "/v1/project/generate",
    json={"raw_input": "发布前 AI 就绪检查：把一句话结构化成项目对象"},
)
if generate_resp.status_code != 200:
    print(f"AI readiness failed: generate endpoint returned {generate_resp.status_code}", file=sys.stderr)
    sys.exit(1)

generate_payload = generate_resp.json()
if bool(generate_payload.get("used_fallback", True)):
    print(
        "AI readiness failed: /v1/project/generate returned used_fallback=true. "
        "Please verify HUNYUAN_API_KEY and provider connectivity.",
        file=sys.stderr,
    )
    sys.exit(1)

print("AI readiness check passed: /v1/project/generate used_fallback=false")
PY
unset ONEFILE_DATA_DIR
unset ONEFILE_AUTH_DEBUG_CODES
trap - EXIT
cleanup_tmp_data

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

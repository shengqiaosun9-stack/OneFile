#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

fail() {
  echo "online readiness failed: $1" >&2
  exit 1
}

provider="${ONEPITCH_AI_PROVIDER:-${ONEFILE_AI_PROVIDER:-deepseek}}"
storage_backend="${ONEPITCH_STORAGE_BACKEND:-json}"

if [[ "$provider" == "deepseek" ]]; then
  [[ -n "${DEEPSEEK_API_KEY:-}" ]] || fail "missing DEEPSEEK_API_KEY"
  [[ -n "${DEEPSEEK_MODEL:-}" ]] || fail "missing DEEPSEEK_MODEL"
fi

if [[ "$storage_backend" == "postgres" ]]; then
  [[ -n "${DATABASE_URL:-}" ]] || fail "missing DATABASE_URL for postgres storage"
fi

python3 - <<'PY'
import os
import sys

from fastapi.testclient import TestClient

from backend.main import app
from backend.repository import get_store_repository

repo = get_store_repository()
store = repo.load_store()
repo.save_store(store)

client = TestClient(app)

health = client.get("/health")
if health.status_code != 200:
    print(f"health returned {health.status_code}", file=sys.stderr)
    sys.exit(1)

diagnosis = client.post(
    "/v1/bp/diagnoses",
    json={
        "name": "线上就绪检查项目",
        "founder_name": "OnePitch",
        "tagline": "用于验证 DeepSeek、存储和 BP 诊断链路是否可用",
        "stage": "prototype",
        "current_resource_need": ["园区材料", "技术验证"],
        "raw_material": "这是发布前检查材料：项目已经完成原型，需要生成14页标准BP清单，并识别材料缺口。",
    },
)
if diagnosis.status_code != 200:
    print(f"bp diagnosis returned {diagnosis.status_code}: {diagnosis.text}", file=sys.stderr)
    sys.exit(1)

payload = diagnosis.json()
if len(payload.get("pages", [])) != 14:
    print("bp diagnosis did not return 14 pages", file=sys.stderr)
    sys.exit(1)

provider = (os.getenv("ONEPITCH_AI_PROVIDER") or os.getenv("ONEFILE_AI_PROVIDER") or "").strip().lower()
has_deepseek_key = bool(os.getenv("DEEPSEEK_API_KEY"))
if provider == "deepseek" and has_deepseek_key and not bool(payload.get("used_ai", False)):
    print(f"DeepSeek was configured but BP diagnosis fell back: {payload.get('fallback_reason')}", file=sys.stderr)
    sys.exit(1)

if os.getenv("ONEFILE_LOCAL_MODE", "").strip().lower() not in {"1", "true", "yes", "on"}:
    ops = client.get("/v1/ops/bp/projects")
    if ops.status_code == 200:
        print("ops bp endpoint should not be public in non-local mode", file=sys.stderr)
        sys.exit(1)

print("online readiness passed")
PY

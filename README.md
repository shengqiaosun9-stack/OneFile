# OnePitch

OnePitch is a user-facing **AI/OPC project diagnosis and BP checklist workspace**. Project teams can paste messy materials, generate a diagnosis report, preview a 14-page external communication BP checklist, identify missing materials, and request human service support. The internal `/ops/bp` workspace receives those submissions for follow-up and delivery.

- Frontend: Next.js + shadcn/ui
- Backend: FastAPI + JSON storage
- Default mode: local-first, no production deployment required for MVP validation
- AI is optional; the first BP diagnosis flow uses local mock/rule generation

## Product Flow
1. `/`: explain OnePitch and start a project diagnosis.
2. `/diagnose`: paste project materials and generate a diagnosis.
3. `/diagnose/{token}`: view the public diagnosis report.
4. `/diagnose/{token}/bp`: preview the 14-page BP checklist.
5. `/diagnose/{token}/gaps`: review missing materials and likely resource-side questions.
6. `/diagnose/{token}/service`: request human support.
7. `/ops/bp`: review submitted projects internally and move them through service delivery.

## Run Locally

Recommended one-command local start:

```bash
python -m pip install -r requirements.txt
cd frontend && npm install && cd ..
./scripts/start-local.sh
```

Open: `http://127.0.0.1:3000/`

Local mode sets:

```bash
ONEFILE_LOCAL_MODE=1
ONEFILE_OPS_ENABLED=1
NEXT_PUBLIC_ONEFILE_LOCAL_MODE=1
```

The backend writes to `data/projects.json`. Before each save it creates a best-effort timestamped backup in `data/backups/` and keeps the latest 50 backups.

### 1) Backend
```bash
python -m pip install -r requirements.txt
# 可选：真实邮箱验证码（Resend）
# export ONEFILE_AUTH_DEBUG_CODES=0
# export ONEFILE_RESEND_API_KEY=...
# export ONEFILE_RESEND_FROM_EMAIL="OneFile <noreply@yourdomain.com>"
# AI 结构化（混元，生产建议必配）
# export HUNYUAN_API_KEY=...
# 可选覆盖
# export HUNYUAN_BASE_URL="https://api.hunyuan.cloud.tencent.com/v1"
# export HUNYUAN_MODEL="hunyuan-turbos-latest"
uvicorn backend.main:app --reload --port 8000
```

### 2) Frontend
```bash
cd frontend
npm install
BACKEND_API_URL=http://127.0.0.1:8000 npm run dev
```

Open: `http://127.0.0.1:3000/`

### 3) Secret safety (required once per clone)
```bash
./scripts/install-git-hooks.sh
./scripts/check-secrets.sh repo
```

Use `.env.example` / `frontend/.env.example` as templates, and keep real secrets only in local `.env*` files (ignored by git).

## Public Card Shell

The old public product-card routes still exist as auxiliary preview/share tools:

- `/library`
- `/projects/{id}`
- `/cards/{id}`
- `/share/{id}`

BP diagnosis data is stored in separate `bp_*` collections. Ops CRM data remains in `ops_*`. Neither should appear in public project-card APIs or public pages unless explicitly exported later.

## Production Deploy (Legacy Demo Tier)

Production deployment is no longer the primary workflow. Keep this section only if you need to demo the old public project-card shell online.

Target architecture:
- Frontend: Netlify (`frontend` 目录)
- Backend: Render free web service

One-time setup:
1. Deploy backend on Render with:
   - Build: `pip install -r requirements.txt`
   - Start: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
   - Health: `/health`
   - Env:
     - `ONEFILE_ENV=production`
     - `ONEFILE_AUTH_DEBUG_CODES=1`
     - `ONEFILE_SESSION_COOKIE_SECURE=1`
     - `HUNYUAN_API_KEY=...`
2. Deploy frontend on Netlify:
   - Base directory: `frontend`
   - Build: `npm run build`
   - Publish: `.next`（若 Netlify 自动识别 Next.js 配置可用默认）
   - Env:
     - `BACKEND_API_URL=https://<your-render-backend>.onrender.com`
     - `NEXT_PUBLIC_DEMO_MODE=1`

Reference configs: `deploy/render.yaml`, `deploy/README.md`

### One-click release

After both platforms are connected to `main` auto-deploy, run:

```bash
./scripts/release-demo.sh
```

The script runs:
1. `python3 -m pytest backend/tests -q`
2. backend AI readiness check (`used_fallback` must be false)
3. `cd frontend && npm run lint`
4. `cd frontend && npm run build`
5. `cd frontend && npm run check:impeccable`
6. repository secret scan (`./scripts/check-secrets.sh repo`)
7. push `main` to trigger Netlify + Render deploy

## Verification

```bash
# Backend tests
python -m pytest backend/tests -q

# Frontend lint + build + e2e
cd frontend
npm run check:smoke

# Impeccable UI gate (no new visual regressions)
npm run check:impeccable
```

## Data
- Source of truth: `data/projects.json`
- Includes clean demo records (public + private)
- Render free tier may recycle instances and lose runtime file changes.
- Use `/library` -> `导出我的备份` as periodic backup.

## Troubleshooting (Deploy)
- Backend 5xx:
  - Check Render logs: import error, missing env, startup command mismatch.
  - Verify health endpoint: `GET /health`.
- Frontend 502 / API error:
  - Check `BACKEND_API_URL` in Netlify.
  - Confirm backend URL is reachable and HTTPS.
- Session/login invalid:
  - Ensure backend has `ONEFILE_SESSION_COOKIE_SECURE=1` in production.
  - Confirm frontend and backend are both served over HTTPS.
- Frequent 429 on OTP:
  - Current limits are in backend env (`ONEFILE_AUTH_START_MAX_PER_HOUR`, `ONEFILE_AUTH_START_MAX_PER_IP_HOUR`).
  - Raise values only if real traffic proves it is too strict.
- WeChat in-app open issue (no custom domain stage):
  - Prefer poster + QR distribution.
  - If link fails in WeChat, copy link and open in system browser.

## Upgrade path (Demo -> Real)
1. Turn off debug OTP and use real email:
   - `ONEFILE_AUTH_DEBUG_CODES=0`
   - `ONEFILE_AUTH_EMAIL_PROVIDER=resend`
   - `ONEFILE_RESEND_API_KEY=...`
   - `ONEFILE_RESEND_FROM_EMAIL=...`
2. Replace JSON storage with persistent DB when moving beyond demo tier.

## Quality Gates (process policy)
Every UI/product iteration should pass this gate order:
1. `using-superpowers`
2. `brainstorming`
3. `writing-plans`
4. `plan-eng-review`
5. `plan-design-review` + `ui-ux-pro-max` + `impeccable`
6. `verification-before-completion`
7. `requesting-code-review`

## Impeccable Gate (local)
- Rules: `frontend/impeccable/gate.rules.json`
- Baseline: `frontend/impeccable/baseline.json`
- Report output: `frontend/test-results/impeccable-report.json`
- Commands:
  - `cd frontend && npm run check:impeccable`
  - `cd frontend && npm run check:impeccable:baseline` (only after intentional design refactor)

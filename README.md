# OneFile

OneFile is now reset to a clean **shadcn-first** product baseline:
- Frontend: Next.js + shadcn/ui
- Backend: FastAPI + JSON storage
- No Streamlit runtime

## Product Flow
1. Landing / email login
2. Public project library (3-4 cards per row)
3. Project detail (update + advanced edit + share toggle)
4. Share page (read-only + CTA back to create)
5. Create page (single input as default path)

## Run Locally

### 1) Backend
```bash
python -m pip install -r requirements.txt
# 可选：真实邮箱验证码（Resend）
# export ONEFILE_AUTH_DEBUG_CODES=0
# export ONEFILE_RESEND_API_KEY=...
# export ONEFILE_RESEND_FROM_EMAIL="OneFile <noreply@yourdomain.com>"
uvicorn backend.main:app --reload --port 8000
```

### 2) Frontend
```bash
cd frontend
npm install
BACKEND_API_URL=http://127.0.0.1:8000 npm run dev
```

Open: `http://127.0.0.1:3000`

## Production Deploy (Demo Tier)

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
2. `cd frontend && npm run lint`
3. `cd frontend && npm run build`
4. push `main` to trigger Netlify + Render deploy

## Verification

```bash
# Backend tests
python -m pytest backend/tests -q

# Frontend lint + build + e2e
cd frontend
npm run check:smoke
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

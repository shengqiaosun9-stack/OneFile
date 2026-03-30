# OneFile Deployment (Netlify + Render, Demo Tier)

This folder provides a low-cost demo deployment baseline:
- Frontend: Netlify (project root directory `frontend`)
- Backend: Render Web Service (free tier, ephemeral disk)

## 1) Backend on Render

Use `deploy/render.yaml` with Blueprint deploy, or configure manually:

- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
- Health Check Path: `/health`

Required environment variables:

- `ONEFILE_ENV=production`
- `ONEFILE_AUTH_DEBUG_CODES=1`
- `ONEFILE_SESSION_COOKIE_SECURE=1`
- `HUNYUAN_API_KEY=...` (Render secret, required for cloud AI structuring)

Optional (when switching to real email OTP):

- `ONEFILE_AUTH_EMAIL_PROVIDER=resend`
- `ONEFILE_RESEND_API_KEY=...`
- `ONEFILE_RESEND_FROM_EMAIL=OneFile <noreply@yourdomain.com>`

Optional AI override:

- `HUNYUAN_BASE_URL=...` (defaults to `https://api.hunyuan.cloud.tencent.com/v1`)
- `HUNYUAN_MODEL=...` (defaults to `hunyuan-turbos-latest`)

## 2) Frontend on Netlify

- Base directory: `frontend`
- Build Command: `npm run build`
- Publish directory: `.next` (if Netlify auto-detects Next.js settings, keep default)
- Environment Variable:
  - `BACKEND_API_URL=https://<your-render-backend>.onrender.com`
  - `NEXT_PUBLIC_DEMO_MODE=1`

## 3) Continuous deployment

- Render and Netlify both connect to this repo and track `main`.
- Use the release script to run gates before push:

```bash
./scripts/release-demo.sh
```

The script includes:
- backend tests
- backend AI readiness guard (fails release if structuring falls back to local rules)
- frontend lint
- frontend build
- `frontend` impeccable UI gate (`npm run check:impeccable`)
- repository secret scan before push

Recommended once per local clone:

```bash
./scripts/install-git-hooks.sh
```

## 4) Demo-tier data caveat

Render free instances can restart and lose filesystem changes.
Use in-app backup export (`/library` -> 导出我的备份) as a safety fallback.

## 5) No-domain WeChat fallback (current stage)

Without a custom domain, WeChat in-app link opening may be unstable.
Use the share poster and QR code as the primary distribution path, and provide copy-link guidance for opening in system browser.

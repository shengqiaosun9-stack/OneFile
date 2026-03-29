# OneFile Deployment (Vercel + Render, Demo Tier)

This folder provides a low-cost demo deployment baseline:
- Frontend: Vercel (project root directory `frontend`)
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

Optional (when switching to real email OTP):

- `ONEFILE_AUTH_EMAIL_PROVIDER=resend`
- `ONEFILE_RESEND_API_KEY=...`
- `ONEFILE_RESEND_FROM_EMAIL=OneFile <noreply@yourdomain.com>`

## 2) Frontend on Vercel

- Root Directory: `frontend`
- Build Command: `npm run build`
- Environment Variable:
  - `BACKEND_API_URL=https://<your-render-backend>.onrender.com`
  - `NEXT_PUBLIC_DEMO_MODE=1`

## 3) Continuous deployment

- Render and Vercel both connect to this repo and track `main`.
- Use the release script to run gates before push:

```bash
./scripts/release-demo.sh
```

## 4) Demo-tier data caveat

Render free instances can restart and lose filesystem changes.
Use in-app backup export (`/library` -> 导出我的备份) as a safety fallback.

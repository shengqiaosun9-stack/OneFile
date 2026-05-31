# OnePitch Online Deployment

第一版线上架构：

- Frontend: Netlify, deploys the Next.js app in `frontend/`.
- Backend: Render or Railway, runs `uvicorn backend.main:app`.
- Database: Supabase Postgres, used as a JSONB store through `onepitch_store`.
- AI: DeepSeek OpenAI-compatible Chat Completions.

Do not put `DEEPSEEK_API_KEY` or `DATABASE_URL` in source code. Set them as platform environment variables.

## 1) Supabase Postgres

Create a Supabase project and copy the pooled or direct Postgres connection string.

The backend creates this table automatically on first read/write:

```sql
create table if not exists onepitch_store (
  id text primary key,
  schema_version integer not null,
  payload jsonb not null,
  updated_at timestamptz not null default now()
);
```

To import your local JSON data once:

```bash
DATABASE_URL="postgresql://..." \
python3 -m backend.scripts.import_json_store_to_postgres --source data/projects.json
```

## 2) Backend on Render or Railway

Build command:

```bash
pip install -r requirements.txt
```

Start command:

```bash
uvicorn backend.main:app --host 0.0.0.0 --port $PORT
```

Health check path:

```text
/health
```

Required environment variables:

```env
ONEFILE_ENV=production
ONEFILE_LOCAL_MODE=0
ONEFILE_OPS_ENABLED=1
ONEFILE_OPS_ADMIN_EMAILS=your-admin@example.com
ONEFILE_AUTH_DEBUG_CODES=0
ONEFILE_SESSION_COOKIE_SECURE=1

ONEPITCH_AI_PROVIDER=deepseek
DEEPSEEK_API_KEY=...
DEEPSEEK_BASE_URL=https://api.deepseek.com
DEEPSEEK_MODEL=deepseek-v4-flash

ONEPITCH_STORAGE_BACKEND=postgres
DATABASE_URL=...
```

Optional real email OTP:

```env
ONEFILE_AUTH_EMAIL_PROVIDER=resend
ONEFILE_RESEND_API_KEY=<set as secret>
ONEFILE_RESEND_FROM_EMAIL=OnePitch <noreply@yourdomain.com>
```

## 3) Frontend on Netlify

Current `netlify.toml` builds from `frontend/` and uses `@netlify/plugin-nextjs`.

Set Netlify environment variables in the UI or CLI:

```env
BACKEND_API_URL=https://your-backend-service.example.com
NEXT_PUBLIC_DEMO_MODE=0
```

`BACKEND_API_URL` is server-side only for Next.js API route proxies. Do not put DeepSeek or database secrets in Netlify unless backend logic is moved into Next.js later.

## 4) Release checks

Before pushing a production release:

```bash
python3 -m pytest backend/tests -q
cd frontend && npm run lint && npm run build
cd ..
bash scripts/check-secrets.sh repo
```

With production-like environment variables available:

```bash
bash scripts/check-online-readiness.sh
```

The online readiness check verifies:

- backend health;
- selected storage can read/write;
- public BP diagnosis returns 14 pages;
- DeepSeek is used when `ONEPITCH_AI_PROVIDER=deepseek` and `DEEPSEEK_API_KEY` is present;
- Ops BP endpoints are not public when local mode is off.

## 5) Deployment caveats

- Netlify hosts the frontend only; Python FastAPI still needs Render, Railway, Fly, or another backend host.
- Supabase is accessed only from the backend. Do not expose service credentials to browser code.
- The first online storage version is a JSONB store to preserve current local data shape. Normalize into relational tables later only after real usage stabilizes.

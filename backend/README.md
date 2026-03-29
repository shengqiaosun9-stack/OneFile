# OneFile Backend API

FastAPI backend for OneFile frontend migration.

## Run

```bash
uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

## Deploy (Render demo tier)

- Build Command: `pip install -r requirements.txt`
- Start Command: `uvicorn backend.main:app --host 0.0.0.0 --port $PORT`
- Health Check Path: `/health`
- Required env:
  - `ONEFILE_ENV=production`
  - `ONEFILE_AUTH_DEBUG_CODES=1`
  - `ONEFILE_SESSION_COOKIE_SECURE=1`

## Environment

- `ONEFILE_ENV` (`development`/`production`)
- `ONEFILE_CTA_TOKEN_TTL_DAYS` (default `7`, range `1-30`)
- `ONEFILE_AUTH_CODE_TTL_MINUTES` (default `10`, range `3-30`)
- `ONEFILE_AUTH_CODE_MAX_ATTEMPTS` (default `5`, range `1-10`)
- `ONEFILE_AUTH_START_MAX_PER_HOUR` (default `8`, range `2-50`)
- `ONEFILE_AUTH_START_MAX_PER_IP_HOUR` (default `20`, range `4-200`)
- `ONEFILE_AUTH_SESSION_TTL_DAYS` (default `14`, range `1-30`)
- `ONEFILE_SESSION_COOKIE_SECURE` (production 建议 `1`)
- `ONEFILE_AUTH_EMAIL_PROVIDER` (`resend`)
- `ONEFILE_RESEND_API_KEY`
- `ONEFILE_RESEND_FROM_EMAIL` (例如 `OneFile <noreply@yourdomain.com>`)
- `ONEFILE_GROWTH_WINDOW_DEFAULT_DAYS` (default `14`)
- `ONEFILE_GROWTH_WINDOW_MAX_DAYS` (default `60`, min `7`, max `120`)
- `ONEFILE_INTERVENTION_WINDOW_DEFAULT_DAYS` (default `30`)
- `ONEFILE_INTERVENTION_WINDOW_MAX_DAYS` (default `90`, min `7`, max `120`)

## Endpoints

- `POST /v1/auth/login`
- `POST /v1/auth/login/start`
- `POST /v1/auth/login/verify`
- `GET /v1/auth/me`
- `POST /v1/auth/logout`
- `GET /v1/backup/export`
- `GET /v1/projects`
- `GET /v1/portfolio`
- `POST /v1/projects`
- `GET /v1/projects/{id}`
- `PATCH /v1/projects/{id}`
- `POST /v1/projects/{id}/update`
- `PATCH /v1/projects/{id}/share`
- `DELETE /v1/projects/{id}`
- `GET /v1/share/{id}`
- `POST /v1/share/{id}/cta`
- `POST /v1/uploads/bp-extract`
- `GET /v1/metrics/growth?days=14`
- `GET /v1/metrics/growth/projects/{id}?days=14`
- `GET /v1/metrics/growth/projects?days=14&limit=10`
- `POST /v1/reports/weekly`
- `GET /v1/interventions/learning?days=30`

## Migration

```bash
python -m backend.scripts.migrate_store --source data/projects.json
```

The script upgrades store schema to `v3`, normalizes legacy event/project payloads, and writes a timestamped backup beside the source file.

## Test

```bash
python3 -m pytest backend/tests -q
```

Data storage remains `data/projects.json`.

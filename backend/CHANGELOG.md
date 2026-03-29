# Backend Changelog

## 2026-03-27 · Release Candidate Track

### Added
- Phase D APIs:
  - `GET /v1/portfolio`
  - `POST /v1/reports/weekly`
  - `GET /v1/interventions/learning`
- Growth dashboard extensions:
  - `GET /v1/metrics/growth/projects`
  - source/ref breakdowns
  - share-to-7d-update ratio
  - update quality aggregates
- Conversion tracking hardening:
  - `cta_token` TTL
  - replay prevention
  - `share_conversion_skipped` reason events
- Config layer (`backend/config.py`) with env-driven bounds
- Store migration utility (`backend/migrations.py`, `backend/scripts/migrate_store.py`)

### Changed
- `update` response now includes:
  - `quality_feedback`
  - `evolution_explanation`
- `share cta` response now includes:
  - `expires_in_days`
  - `expires_at`

### Quality
- Backend automated tests expanded to Phase A-D + release-readiness scenarios.

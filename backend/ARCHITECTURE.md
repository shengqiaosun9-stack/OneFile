# OneFile Backend Architecture (Release Candidate)

## Scope

This backend provides the productization core for OneFile:
- Project lifecycle (`create/update/share`)
- Evolution engine projection (`updates` as source of truth)
- Share growth funnel (`view -> cta -> create/update`)
- Portfolio / weekly reporting / intervention learning (Phase D)

## Layers

1. API Layer (`backend/main.py`)
- FastAPI routes and request validation.
- Consistent service error mapping via `ServiceError` -> JSON error envelope.

2. Service Layer (`backend/service.py`)
- Command/query orchestration.
- Event emission for every meaningful state transition.
- Growth and learning aggregations.

3. Repository Layer (`backend/repository.py`)
- Storage abstraction for store read/write and event lookup by payload key.
- Current implementation: JSON-backed repository.

4. Domain Model (`project_model.py`)
- Schema normalization and projection logic.
- `updates` signal parsing, action loop evolution, intervention derivation.

5. Storage (`storage.py`)
- JSON store persistence (`data/projects.json`) with safe tmp-file replace.

## Core Event Model

High-signal events currently used by runtime and analytics:
- Lifecycle: `project_created`, `project_updated`, `next_action_completed`
- Intervention: `intervention_triggered`, `intervention_resolved`
- Share: `share_published`, `share_unpublished`, `share_viewed`, `share_cta_clicked`
- Conversion: `share_conversion_attributed`, `share_conversion_skipped`
- Operations views: `portfolio_viewed`, `weekly_report_generated`, `intervention_learning_viewed`

## Phase D Capabilities

1. Portfolio API (`GET /v1/portfolio`)
- Owner-only project portfolio snapshot.
- Returns summary KPIs, stage distribution, and per-project operating cards.

2. Weekly Report API (`POST /v1/reports/weekly`)
- Generates weekly markdown report from owner projects + updates.
- Supports explicit `week_start` (`YYYY-MM-DD`) and default current-week Monday.

3. Intervention Learning API (`GET /v1/interventions/learning`)
- Aggregates intervention trigger/resolve outcomes in time window.
- Returns effectiveness by type and suggested best strategy.

## Release Readiness Controls

- Config layering via `backend/config.py` (env-based bounds for token TTL and windows).
- Migration utility via `backend/migrations.py` + CLI entrypoint.
- Regression tests covering:
  - Conversion attribution/TTL/replay
  - Growth funnel and breakdown metrics
  - Phase D endpoints and failure paths
  - Migration and config bounds

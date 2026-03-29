# OneFile Product System (Reset Baseline)

## Positioning
OneFile helps founders turn ideas into **structured, evolving project assets**.

## Core Experience
1. Landing + email login
2. Public Project Library as default home
3. Detail page for reading and updating project evolution
4. Share page for external reading and growth CTA
5. Create flow with low-friction AI-first input

## Information Architecture
- Landing: value statement + email entry + explore public projects
- Library: card grid, view detail, share entry, create entry
- Detail: state, timeline updates, share toggle, advanced edit
- Share: read-only narrative, return-to-library, create-my-project CTA
- Create: title + single main input + generation

## Data Truth Rules
- `data/projects.json` remains the storage source.
- Frontend renders backend projections only.
- Private projects are owner-only in library listing.
- Share page access is `public` or `owner_preview`.
- `updates[]` is treated as evolution truth for timeline display.

## API Surface
- `POST /v1/auth/login`
- `GET /v1/projects`
- `POST /v1/projects`
- `GET /v1/projects/{id}`
- `PATCH /v1/projects/{id}`
- `POST /v1/projects/{id}/update`
- `PATCH /v1/projects/{id}/share`
- `DELETE /v1/projects/{id}`
- `GET /v1/share/{id}`
- `POST /v1/share/{id}/cta`

Optional response fields:
- `used_fallback?: boolean`
- `warning?: string`

## Build Constraints
- Frontend design system must stay shadcn-based.
- No Streamlit reintroduction.
- No local JSON bypass in frontend; use backend APIs only.

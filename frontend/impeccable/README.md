# OneFile Impeccable Gate

This folder defines the local "impeccable gate" for OneFile UI quality checks.

## Files

- `gate.rules.json`: machine-readable rules for core page consistency checks
- `baseline.json`: accepted baseline fingerprints (used to block only new regressions)
- `baseline-report.json`: current baseline issue snapshot (human-readable)

## Commands

From `frontend/`:

```bash
npm run check:impeccable
```

This generates `test-results/impeccable-report.json` and fails when new issues are introduced.

To refresh baseline intentionally:

```bash
npm run check:impeccable:baseline
```

## Mapping with `ui-ux-pro-max`

To avoid duplicate/conflicting checks:

- `ui-ux-pro-max`: design strategy, IA consistency, interaction guidance
- `impeccable gate`: enforceable repo-local constraints (tokens, anti-drift, palette, required structures)

Use both in the same release gate:

`lint -> build -> check:impeccable`

## Scope

The gate currently enforces:

- visual token presence for Landing/Library/Detail/Share
- CSS semantic rule presence for onefile/landing styles
- anti-dashboard wording drift in core pages
- allowed hex palette in `src/app/globals.css`

This is a quality gate only. It does not auto-fix code.

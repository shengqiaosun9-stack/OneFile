# OnePitch Object Grammar

## Product identity

OnePitch is not a dashboard, not a form builder, and not a doc editor.
It is a brand system that turns fuzzy founder input into a sendable project object.
Public surfaces should feel darker, denser, and more display-worthy than internal editing surfaces.

## Allowed core objects

### 1. Prompt Bar
- Purpose: trigger first-time generation in one move.
- Order: short framing line -> optional title hint -> primary input -> one primary action.
- Max interactions: one primary action, one supporting hint.
- Must not contain: stacked helper panels, multi-step forms, settings toggles, secondary CTA rows.

### 2. Example Object Card
- Purpose: preview what the generated object feels like and reduce input hesitation.
- Order: summary -> title and audience meta -> one context sentence -> one primary action -> one lightweight secondary link.
- Max interactions: one primary button, one text link.
- Must not contain: timestamp chips, status dashboards, extra badges, multiple stacked buttons, internal management actions.
- Showcase rule: examples should be presented as a curated carousel with one dominant center object and subdued side previews.

### 3. Project Card Surface
- Purpose: public-facing project object for reading, sharing, and deciding whether to continue.
- Order: summary -> title -> context and status -> action zone.
- Max interactions: one dominant share action, two secondary actions.
- Must not contain: admin controls, settings drawers, form-builder chrome, dense metadata tables, analytics summaries.

### 4. Poster Surface
- Purpose: compressed propagation object for scanning and sharing.
- Order: summary -> project identity -> compressed support info -> QR code and CTA.
- Max interactions: none inside the poster itself.
- Must not contain: field grids larger than 2x2, form controls, long paragraphs, timeline UI.
- Surface rule: poster uses the public dark brand shell, not a screenshot of the card page.

## Explicitly forbidden objects
- pricing table
- feature comparison
- settings panel
- admin sidebar
- analytics widget
- FAQ stack
- large white-card form
- three-column equal-height feature cards
- dashboard sidebar
- stat strip as a hero substitute

## Current page mapping
- Landing Hero -> Prompt Bar
- Landing examples -> Example Object Card
- `/card/[id]` -> Project Card Surface
- Poster preview/download -> Poster Surface

## Drift policy
If a new UI block cannot be described as one of the four objects above, it should not be added until the object grammar is extended deliberately.

# OnePitch Interaction States

## Prompt Bar
- `default`: quiet surface, one dominant action, no competing links inside the object.
- `focused`: border and field emphasis increase; background remains calm.
- `typing`: character count updates, no additional UI appears.
- `loading`: primary action locks, wording changes, surrounding UI stays stable.
- `submitting`: primary action locks, wording changes, surrounding UI stays stable.
- `failed`: inline failure is allowed, but the object must stay stable.
- `generated`: control hands off to the generated object; Prompt Bar should not become a wizard.

## Example Object Card
- `rest`: summary dominates, meta and scenario stay visibly secondary.
- `hover`: slight elevation or contrast lift; no major transform.
- `selected`: center object opens fully, actions become readable, side previews remain visibly subordinate.

## Project Card Surface
- `rest`: summary-first reading order remains obvious.
- `ready`: public object is readable and shareable.
- `share-ready`: action zone foregrounds propagation without adding admin chrome.
- `owner`: editing affordances may appear, but sharing remains the dominant action.
- `shared`: share actions and copy feedback remain clear without introducing admin chrome.
- `claimable`: lightweight ownership hint is allowed; hard auth walls are not.

## Poster Surface
- `preview`: rendered object is static, centered, and scanable.
- `download-ready`: QR code and CTA remain the only clear action anchors.

## General state constraints
- Hover must clarify, not entertain.
- Focus states must be stronger than hover states.
- Loading must never introduce layout shift.
- No object may expose more than one visually primary action at a time.

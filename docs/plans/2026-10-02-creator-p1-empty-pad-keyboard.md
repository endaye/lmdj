# P1 focused empty-Pad recording

Independent review R3 reproduces that Enter and Space on a focused empty Pad
never reach the capture input controller: both key guards require an assigned
or already capturing Pad. Admit enabled empty-Pad capture in those guards and
keep the native keydown event, physical Pad mapping and repeat suppression.

## Declared files and verification

- `apps/creator-web/src/components/pad_surface.tsx`
- `apps/creator-web/test/pad_surface_keyboard.test.tsx`
- `docs/plans/2026-10-02-creator-p1-empty-pad-keyboard.md`

Retain both Enter/Space failures before fixing the guards. Assert actual React
Pad handlers forward one press and one release with the same native keydown,
ignore repeat and never open a picker. Run the existing input/capture suites,
TypeScript and staged scope before commit. Synthetic keyboard tests establish
handler forwarding; actual browser activation and device capture are separate.

## Version Management

Version impact: deferred to the coordinated P1 candidate settlement.
Reason: restore Creator's existing accessible Pad activation without allocating
a Product Build or changing a public Contract in this Task.

Documentation impact: none
Reason: implement the existing keyboard recording intent; no new flow, portal
identity or architecture boundary is introduced.

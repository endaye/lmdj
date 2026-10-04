# Slot Task lifecycle fixture convergence

The unchanged T2 Runtime Source guarantees recovering after a synthetic lifecycle
edge whose native AudioContext stays running. The old fixture waited for the
transient interrupted/Audio suspended projection and could miss it entirely.
The committed569 Linux full journey failed at that wait; a reduced unchanged
source artifact also failed on the hidden leg and eventually replaced its
generation. Retain both raw failures. Adopt the already verified T1/integration
fixture contract; do not modify Product lifecycle behavior.

## Declared files and verification

- `tests/platform/web/creator/creator_web_lifecycle.spec.mjs`
- `docs/plans/2026-10-02-creator-p1-slot-lifecycle-fixture.md`

Keep blur, hidden, focus, visible and both fresh loop toggles. After each edge
require exact recovering, then the cleared idle Pad outcome and a native Enter
that produces the real started outcome; an uncleared latch would toggle off.
Require Audio running after each fresh started press. Preserve every timeout
and all other lifecycle journeys. Run this complete reduced packaged journey
against the unchanged clean569 distribution, Node syntax and staged scope before
commit. Then recompute own keys and run the complete committed Creator lane.

## Version Management

Version impact: none. Only the test precondition/observable changes; no Product
manifest, artifact Source or runtime behavior changes. P1 debt is settled in T8.

Documentation impact: none
Reason: fixture-only lifecycle observation of the existing public contract; no
portal Source fact changes. This is automation, not physical Safari acceptance.

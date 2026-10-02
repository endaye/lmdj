# Streaming adopts the reviewed first-touch parent

Merge T1 aa556273 into streaming Source2fdd75f9. Retain the streaming availability
guard while adopting deferred cold touch/pen wake on owned release, primary
pointer validation and cancellation. Keep the typed native event fields and
all T1 activation/refusal/owner-loss tests; retain per-slot availability cases.
The shared proof observer restores only its own transport proxy. No T6 capture
or T7 System code is introduced.

## Declared files and verification

- `apps/creator-web/src/runtime/input_controller.ts`
- `apps/creator-web/test/input_controller.test.ts`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `docs/plans/2026-10-01-creator-p1-first-use.md`
- `docs/plans/2026-10-01-creator-p1-fixture-transport-ownership.md`
- `docs/plans/2026-10-01-creator-p1-touch-activation.md`
- `docs/plans/2026-10-02-creator-p1-owner-loss-held-press.md`
- `docs/plans/2026-10-02-creator-p1-primary-pointer-proof.md`
- `docs/plans/2026-10-02-creator-p1-streaming-touch-parent.md`
- `tests/platform/web/creator/creator_web_lifecycle.spec.mjs`
- `tests/platform/web/creator/creator_web_sequence.spec.mjs`
- `tests/platform/web/creator/creator_web_takeover.spec.mjs`
- `tests/platform/web/creator/fixtures/creator_audio.mjs`

Run complete Creator units, TypeScript, staged scope and the complete current
portal before committing. Native first-touch and full streaming/reload/manual
Project plus selected committed batch lanes remain required before shipping.

## Version Management

Version impact: none. Preserve retainedmain71 identities; coordinatedP1 debt
is settled only in T8. No release, Creator deployment or Channel promotion.

Documentation impact: required
Affected portal page: /hosts/creator-web/. Reason: truthful musical first-touch
and recovery documentation inherited from the reviewed T1 parent.

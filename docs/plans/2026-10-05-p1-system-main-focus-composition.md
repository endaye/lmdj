# P1 System: actual Main ancestry and immediate return focus

Relates to #1665. Compose the System head
`a3d4a381c6eb85be7438f7b677f6bea17f3dabb3` with actual protected Main
`9964cda1f471b77ec29e62155e44c7e0bf944895`, which contains the T6 squash.
Both genuine overlap conflicts retain the exact already-composed System head
bytes before the narrowly declared focus repair below. The resolved Git tree
before repair is identical to the former head tree. No imported Main behavior
or identity is rewritten.

## Declared files

- `apps/creator-web/src/app.tsx`: resolve the actual overlap, then restore
  System entry focus within the return gesture. The entry remains mounted;
  queuing focus for a later animation frame can steal a new EQ gesture,
  causing its blur handler to commit the first step or losing its key events.
- `apps/creator-web/test/workspace_shell.test.tsx`: the lowest-tier regression
  holds the next animation frame, focuses the next creative control, then
  asserts that pending navigation work leaves that focus intact.
- `apps/docs-site/docs/hosts/creator-web.mdx`: resolve the actual documentation
  overlap and document the immediate return-focus behavior.
- This plan.

All remaining staged merge entries retain the former head exactly. This is a
real Main merge, not a synthetic parent or a rewritten squash commit.

## Verification

The original complete Creator lane failed at the Sample tone journey with
high EQ +0.5 dB and low EQ -0.5 dB instead of its exact committed values.
Its raw log and trace are retained. The unchanged original case on the same
packaged artifact also failed while waiting for revision 6. Both are failures,
not completion evidence. The new component regression fails against the
deferred focus callback because the System entry takes the next control's
focus; it must pass after this repair. No budget or journey assertion changes.

- Focus regression, System tests and complete Creator lower tests.
- Creator TypeScript/Vite build.
- Staged and committed `tests/build/ci_change_scope_test.py`.
- Official `scripts/docs-site.sh check` for the current documented behavior.
- On the clean committed head, complete canonical Creator and Web Runtime
  recipes, including the original Sample tone commit/cancel/refuse/fail/reopen
  journey and System transport/focus journey. Diagnose reductions separately
  from whole-lane completion.

Push the new actual ancestry head normally. Obtain a fresh current-head review,
resolve actual findings, and verify live body evidence, protection and all
conversations before guarded squash. Old head reviews and failed collector
attempts do not attest this head.

## Version Management

Version impact: none. This repairs the existing System implementation and
imports existing protected Main identities. Coordinated P1 version settlement
and a new immutable Product snapshot remain the separate T8 Task.

## Documentation impact

Documentation impact: required.
Affected portal pages: /hosts/creator-web/

The current Host page explains when return focus settles. This Task does not
allocate a Product Build or supply physical Safari/iPad/MIDI/hearing acceptance,
installed-offline integration acceptance, release or deployment evidence.

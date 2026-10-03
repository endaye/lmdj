# P1 cancellable capture startup

Independent review reproduces microphone startup waiting forever for a browser
resume promise while release and cancel wait for a handle that cannot arrive.
Give the capture owner an AbortSignal during startup. Release/cancel abort that
startup; the Source closes its owned context and stops its controller without
waiting for resume. Resource cleanup still finishes before the take reaches
review. Capture waits for cold touch's legal Runtime activation before creating
another microphone context; canceled activation creates no resources. A late
master-capture acquisition retains startup ownership until its late handle has
finished stopping, including when no Runtime activation promise is needed.

## Declared files and verification

- `apps/creator-web/src/capture/pad_capture.ts`
- `apps/creator-web/src/capture/pad_capture_sources.ts`
- `apps/creator-web/src/app.tsx`
- `apps/creator-web/test/pad_capture_sources.test.ts`
- `docs/plans/2026-10-01-creator-p1-capture-startup-cancellation.md`

Retain the original independent pending-resume negative evidence. Test release
and cancel against an actually non-settling resume promise, with far-side
controller stop, context close, released resources and no commitment. Verify
that pending cold touch activation creates no microphone context. A separate
negative proves that cancellation must retain ownership while master acquisition
and its stop are pending; no discard/new take may bypass that barrier. Keep the
complete existing capture, unit and TypeScript checks; run scope admission for
the new files before committing. Packaged proofs and independent review follow
on the final committed head. No timeout or acceptance leg is weakened.

## Version Management

Version impact: deferred to the approved coordinated P1 version settlement Task.
Reason: correct a local Creator resource lifecycle; allocate no Product Build or
public Contract in this Task.

Documentation impact: none
Reason: capture intent and user-facing behavior remain as documented; this
change fulfills the existing release/cancel resource ownership requirement.

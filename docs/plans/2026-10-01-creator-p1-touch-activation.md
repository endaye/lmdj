# P1 first-touch audio activation

Independent review identifies that a trusted touch/pen pointerdown does not
grant HTML user activation. Cold audio must wait for that owned pointer's
native pointerup. Keep the activation promise with the adapter gesture identity;
invoke the existing Runtime wake synchronously at release, including release
outside the Pad. Cancel, blur and disposal retire the promise without waking.
Running audio continues to trigger immediately on press. A released one-shot
retains its first admission; released gates never start late. Bind release and
cancel to each actual Sample gesture key when several pointers share a Pad.
Wait for each gesture's activation before entering the serialized Sample queue,
so a held cold touch cannot block another Pad that has legally activated.

## Declared files and verification

- `apps/creator-web/src/runtime/input_controller.ts`
- `apps/creator-web/test/input_controller.test.ts`
- `apps/docs-site/docs/hosts/creator-web.mdx`
- `docs/plans/2026-10-01-creator-p1-touch-activation.md`

Retain the five pre-fix failures. Verify exact native release wake, outside-Pad
release, same-Pad pointer ownership, inverse release ordering, cancellation, refusal/retry, immediate
running press and released gate suppression. Run the complete Creator unit suite,
TypeScript, scope and current portal checks before committing. Complete selected
packaged Host proofs and independent current-head review follow on the committed
head. These fixtures do not establish physical iPad or Safari listening acceptance.

## Version Management

Version impact: deferred to the approved coordinated P1 version settlement Task.
Reason: this Task corrects Creator input lifecycle without allocating a Product
Build or changing public Contracts. The final candidate receives a new identity
and immutable snapshot after the integrated source is settled.

Documentation impact: required
Affected portal pages: /hosts/creator-web/
Reason: document the distinct cold touch release and running press behavior.

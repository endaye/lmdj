# Stage 9 H2 Switch-Boundary Flush Implementation Plan

**Issue:** #376
**Design authority:** SR-D11 and SR-D23 in
`docs/prd/decisions/2026-08-23-sequence-recording-semantics.md`

## Outcome

After the Audio Runtime acknowledges a requested next-Bar Pattern activation,
the shared Web Runtime Session issues exactly one Facade flush before it
publishes that acknowledgement to Host observers. Creator and the diagnostic
Web Host can then continue recording into the activated Pattern without
predicting authority or entering a terminal failure.

## Implementation

1. Retain the authoritative pending switch identity returned by
   `sequence.record.switch-request`, including session, Pattern, activation
   frame, and Runtime generation.
2. Accept only the matching `sequence.bar_boundary` notification. Ignore stale,
   reordered, and duplicate notifications, and reserve the boundary before
   enqueueing its flush.
3. Put the generated-command flush on the existing serialized Runtime action
   lane. Publish the Bar-boundary event to Host listeners only after the Facade
   reports the requested Pattern as active.
4. Clear retained switch authority when an explicit flush, stop, new begin, or
   terminal lifecycle supersedes it.
5. Make Creator's reducer accept a boundary only when the queried Facade status
   confirms the pending Pattern is active.
6. Extend unit and packaged-browser journeys through boundary acknowledgement,
   continued recording, stop, reload, and committed-event inspection.

## Verification

- Web Runtime Session unit test proves exact-one flush and rejection of
  reordered/duplicate boundaries.
- Creator reducer and Playwright coverage prove no optimistic selection and no
  terminal ErrorPanel after the first post-boundary input.
- Formal Web Runtime Host Playwright coverage proves events commit to the old
  and new Patterns on their respective sides of the boundary, survive stop,
  and remain visible after reload.
- Run the affected Node/Vitest/browser suites, Core fast and stress tiers,
  dependency/active-tree/version checks, and Architecture Portal check.

## Version Management

Version impact: deferred to integration Issue #379. This functional Task
affects Web Runtime Platform, Web Runtime Host, Creator Web Host, and Product
behavior, but it does not independently allocate or reuse a Product Build or
change their manifests. #379 performs the fresh integrated identity audit.

## Documentation Impact

Documentation impact: required. Update the Stage 9 review disposition and
acceptance ledger plus current Portal routes `/hosts/web-runtime/`,
`/hosts/creator-web/`, and `/product/workflows/`. The corrected immutable
Product Build snapshot remains owned by #380 after #379 allocates the integrated
identity; this Task must not rewrite the existing `1.0.37.0` snapshot.

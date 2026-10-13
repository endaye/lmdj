# Headered Performance gesture status

Relates to #2124. C1 prerequisite; separate from its Creator consumer changes.

## Premise and scope

At main `613e23c26bb0ae54dccd75003b8858ac484b0faf`, headered begin/event
maintains `recording_fx` and `recording_filter_binding`, but active status counts
only legacy `open_fx`. The durable read path also omits `open_filter`.
The defect is outstanding; no successor changes these producers or the query.
The existing Portal makes unclosed FX gesture counts a Facade-owned fact.

Count the owning profile's bindings and include the independent Filter in both
active and durable status. Frozen-only controls are sounding state, not open
gestures. This changes no admission, playback, persistence format or protocol
shape. Creator's existing far-side count assertions must remain strict.

## Declared files

- `packages/application-facade/src/application.cpp`
- `tests/core/facade/performance_gesture_admission_test.cpp`
- `apps/docs-site/docs/core/modules/application-facade.mdx`
- `docs/plans/2026-10-13-performance-headered-gesture-status.md`

## Verification

Rebuilt RED→GREEN `facade.performance_gesture_admission`: begin mapping, new
FX engage/move/release, independent Filter, mixed active/frozen-only state,
durable read-only reattach, stop and legacy counts. Run owning Performance
session/admission/replay tests and Portal check. No full candidate claim.

## Version Management

Version impact: compatible Application Facade PATCH debt, correcting existing
status values without changing public shape or ABI; no Product allocation.

## Documentation impact

Documentation impact: required.
Affected portal pages: /core/modules/application-facade/

## Results

- RED: rebuilt admission suite failed at the new `count() == 2U` assertion.
- GREEN: admission, session and replay owning suites pass (3/3). The same test
  also reads the durable checkpoint through a fresh Application before/after
  each release and Stop; frozen-only state is excluded.
- Portal check passed on this tree. No thresholds or journey legs changed.
- Pitfall impact: none; the source invariant is captured by the regression.
- Precommit refresh remains `613e23c26bb0ae54dccd75003b8858ac484b0faf`.

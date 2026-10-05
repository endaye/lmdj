# Correct the current and future Creator offline manifest boundary

## Problem and Task

Independent complete-source review of offline head `89b3bcf6936489ed98c2239240ea7ff21ca5b662`
found that the Platform portal incorrectly requires an offline worker for the
already published favicon Host MAJOR. The actual Native gate and generated
inventory intentionally retain that published inventory; exactly one worker is
required only for the following offline Host MAJOR. Correct this one paragraph
in an isolated documentation Task. This finding is separate from the previously
deferred Perform capture documentation finding; the earlier offline review
missed it, and the original report and current finding remain retained.

## Declared files

- `apps/docs-site/docs/core/modules/web-runtime-platform.mdx`
- `docs/plans/2026-10-05-p1-offline-inventory-portal-boundary.md`

## Verification

Read the actual `manifest_gate.cpp` boundary, current generated Creator assets,
and original `manifest_gate_test.cpp` current-ready/future-exact-worker assertions.
Authenticate all preexisting tracked blobs outside the two declared files against
the original head; Native, JavaScript, packager, identities and immutable snapshots
remain exact. Run staged ownership75 and whitespace checks and the full unchanged
`scripts/docs-site.sh install` and `check` entry points against the entire staged
source in a normal authorized Linux worktree at the actual parent. Authenticate
its source/index/tree and all original full logs/exits before committing this exact
tested tree. Portal tests/build/routes detect broken docs inputs, not semantic
truth; the source-bound reading above establishes the corrected statement.

## Version Management

Version impact: none. This corrects one source fact and records its evidence.
No Product, Module, Host, Provider or Contract identity is allocated or edited.

## Documentation impact

Documentation impact: required
Affected portal pages: /core/modules/web-runtime-platform/
Reason: the offline inventory starting boundary must match the actual Native gate
and generated current manifest. No diagram or immutable historical snapshot changes.

## Acceptance boundaries

This Task does not prove browser offline installation/update, real-device audio,
whole-P1 acceptance or a full source-head batch. Subsequent dependency composition
must use real ancestry and recalculate keys; earlier review/adoption is not transferred.

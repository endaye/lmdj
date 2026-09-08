# T2b — Deterministic Host preparation inputs

Part of the [result-driven delivery plan](2026-09-09-lmdj-result-driven-delivery.md).
Implements the Host/version/changelog half of local preparation. This is not a
complete Product allocation, version PR, release candidate or deployment.

## Declared files

- `tools/canary/preparation.py`
- `tests/build/ci_canary_preparation_test.py`
- This plan.
- `docs/plans/2026-09-09-lmdj-result-driven-delivery.md` (progress and live evidence).

Recollect exact Git inputs and validate the terminal assessment history before
generating any proposed bytes. Apply the highest per-Host batch impact once:
patch/minor only. Consume an adequate same-major committed pre-bump; reject
insufficient, backwards, unexplained or major pre-bumps with a correction
diagnostic. Leave unchanged Hosts byte-identical. Candidate source code never
executes, and dirty files must not substitute for pinned Git inputs.

Return explicit Host manifest/changelog edits with original byte digests and
lengths, never write the caller's tree. Emit one canonical prepared entry per
changed Host, allocation date (not release date), assessed base/target, input
and assessment digests, exact commit links, dependency effects and escaped
user-facing prose. Append without rewriting existing bytes; reject occupied
version headings and existing machine entry identities. Published corrections
need separate addenda, never replacement. No invented historical versions or
PR references; authenticated PR review input collection is still outstanding.

The consumer must perform occupancy/fencing and expected-tree checks, canonical
Product/Assembly/lock/identity/snapshot generation, ordinary reviewed version PR,
post-squash coverage and snapshot witness verification before treating these
Host edits as an allocation. Do not hand-generate Product or lock identities in
this library. Its output explicitly records those unmet obligations. Tests apply
only the proposed Host edits in temporary repositories, never this active tree.

## Verification

Start with a missing-module red. Real temporary Git repositories cover independent
patch/minor/none, adequate and insufficient pre-bumps, stale assessment versus
fresh Git, replay, dirty-tree immunity, symlink rejection, occupied versions,
immutable prior changelog bytes and hostile Markdown/HTML/machine-marker prose.
Retain full assessment/planner tests; run all CI contract tests, staged ownership,
Portal check and final committed-range/PR declarations. These tests do not prove
semantic AI truth, provider execution, Product allocation or remote publication.

## Version Management

Version impact: none
Reason: internal preparation tooling; actual Host manifests, Product/Assembly
and frozen snapshots are unchanged. Fixture versions are not allocations.

## Documentation Impact

Documentation impact: none
Reason: internal library without operator CLI/workflow or current Portal facts;
changelog routes and allocation commands remain subsequent Tasks.

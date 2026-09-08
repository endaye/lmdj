# Merged review run identity compatibility

## Declared files

- `scripts/ci/review_merge_map.py`
- `tests/build/ci_review_merge_map_test.py`
- `.agents/pitfalls/fake-tool-stub-strictness.md`
- This plan.

## Defect and bounded fix

Actions may return an empty `pull_requests` array after merge. Requiring that
array to retain its association rejects otherwise authenticated scope evidence.
Use the exact-attempt run's `head_sha` equal to the reviewed PR head (never the
squash merge SHA). A nonempty association must still name that PR and head;
missing or malformed association is rejected. An empty list supplies no proof.

The caller still obtains the record from the live merged PR's bot COMMENT,
binds repository/PR/head, and verifies completed producer/publisher jobs,
trusted workflow source/main control, historical policy and actual same-run
scope artifact equal to the COMMENT record. No PR permission is added and no
reader-side workaround or schema change is introduced.

## Evidence and verification

Read-only Actions API observations on 2026-09-08: run 34151840695 is the original
PR review entry for #797, head `19233383272c9c770cb98d34aa8f7e44327c29b2`;
run 34152096875 is #798's closed mapping entry, head
`897b3096361ec9ac19acb03ff8b67ede3e96ff0d`. Both return empty PR association
arrays after merge. The closed map run is not evidence of a successful review
producer. Neither observation proves successful publication or O1 acceptance.

Lowest-tier regression: historical empty association through real validator,
wrong exact head, nonempty wrong PR and another PR's otherwise valid artifact.
The empty-list fixture and far-side wrong-artifact rejection fail before the
fix. Run mapping tests, all CI contract tests and ownership after staging.
No live write, fault injection, release or product test execution occurs here.
Full real backend -> publication -> merged map acceptance remains O1.

Pitfall impact: recurrence of `fake-tool-stub-strictness`, recorded with the
actual original review run API evidence. Mapping regressions cover this narrow
shape; the existing broader escalation #726 remains open and is not absorbed.

## Documentation Impact

Documentation impact: none

Reason: Internal CI evidence compatibility only; no Portal routes or product
source facts change.

## Version Management

Version impact: none

Reason: No Product, Module, Provider or Contract version change.

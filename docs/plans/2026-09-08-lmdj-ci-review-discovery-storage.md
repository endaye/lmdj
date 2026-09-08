# Fixed PR Review discovery storage

This Task records one separate durable discovery journal. It does not enable
automatic triggers, initialize storage, send reports, or execute product tests.

## Declared files

- `scripts/ci/review_discovery_storage.json`
- `tests/build/ci_review_discovery_storage_test.py`
- This plan.

## Reservation and historical boundary

An all-state paginated Issue inventory completed successfully before a single
reservation POST. Fresh GET confirmed Issue #849 OPEN with exact empty template
`<!-- lmdj-ci-journal-uninitialized-v1 -->` followed by a newline and zero comments.
Its actual GraphQL node is `I_kwDOTK_1fs8AAAABQKj2dQ`. The separate epoch is
`review-discovery-20260908-issue849`. No checkpoint or tested baseline was created.
The existing controller workflow ID is `352307416`; the stable Actions Bot node
is `MDM6Qm90NDE4OTgyODI=`. Main scheduler #807 and report outbox #817 remain separate
and unchanged. No permission or branch-protection mutation is included.

The first merged serial review producer is PR #795, commit
`0bcb14e9ada890f4c0e6b549f72dcdce05cf9c1c`, at `2026-09-07T18:29:09Z`.
Its actual workflow source contains Review fallback and the honest final result
artifact. Use that historical floor, not the future bridge activation time.
PR Review workflow ID is `352327391`. These are observed audit identities, not
newly allocated product versions. Every discovered attempt still requires its
own source, repository, workflow and receipt authentication; the floor is not
proof that a review succeeded. Artifact age alone cannot establish absence.

The independently implemented discovery runtime reads this fixed committed
manifest. Actual initialization and remote recovery must be verified separately
under the existing writer lock before automatic discovery is enabled. This Task
does not claim that missing callbacks have already been recovered.

## Verification

Run the inventory test, existing discovery protocol and storage tests, staged
ownership and whitespace checks, final committed-range classification, docs-static
and the required Portal check. Record actual results before shipping; local
inventory checks do not authenticate the live remote journal or prove cutover.

Local results: 6 new inventory tests and 44 existing discovery tests passed;
7 existing recovery-storage tests and 66 staged ownership tests passed.
Portal check ran: 54 tests passed, three failed because this isolated worktree
lacks glob, gray-matter and cheerio; downstream validation/build did not run.
The precommit docs-static invocation had an empty committed range and is not
evidence for the new files; rerun against the final nonempty commit before push.

## Documentation Impact

Documentation impact: none

Reason: internal inactive storage inventory only; no Portal route or current
automatic testing behavior changes. T5 owns current operational documentation.

## Version Management

Version impact: none

Reason: CI configuration only; no product identity allocation, tag, Release,
publication, deployment or Channel promotion.

Pitfall impact: none — apply existing identity, authorization-error and full
journey guidance; do not treat a reservation as initialized or recovered storage.

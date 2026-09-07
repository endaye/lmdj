# Fixed isolated O1 recovery storage inventory

## Task and declared files

Add `scripts/ci/o1_recovery_storage.json`,
`tests/build/ci_o1_recovery_storage_test.py`, and this plan only. The manifest
contains exactly scheduler, outbox and claim roles, each the existing six-field
Runtime config. No helper, arbitrary path input, denylist or protocol change.
Future consumers must read the fixed reviewed manifest; this Task does not wire
initialization, fault injection or execution.

## Actual reserved identities

Root reserved and independently verified these objects. This Task also performed
a read-only GraphQL reread: repository `endaye/lmdj`, numeric ID `1286600062`,
and all three exact Issue nodes were OPEN, zero comments, with body exactly
`<!-- lmdj-ci-journal-uninitialized-v1 -->` plus one newline.

| Role | Issue | Node ID | Configured epoch |
| --- | --- | --- | --- |
| scheduler | [824](https://github.com/endaye/lmdj/issues/824) | `I_kwDOTK_1fs8AAAABQJ5ORQ` | `o1-recovery-scheduler-20260908-issue824` |
| outbox | [825](https://github.com/endaye/lmdj/issues/825) | `I_kwDOTK_1fs8AAAABQJ5UMQ` | `o1-recovery-outbox-20260908-issue825` |
| claim | [826](https://github.com/endaye/lmdj/issues/826) | `I_kwDOTK_1fs8AAAABQJ5bLA` | `o1-claim-20260908-issue826` |

All roles retain existing workflow ID `352307416`, path
`.github/workflows/self-test-report.yml`, and Actions bot numeric ID `41898282`,
node `MDM6Qm90NDE4OTgyODI=`. Repository and stable bot/workflow authority are
shared; Issue numbers, node IDs and epochs must independently differ. These are
recorded platform facts, not guessed product or release identities.

These are reservation-time observations, not a claim that all objects remain
empty. Root separately dispatched scheduler initialization run `34162815456/1`
at control `dc1e57622136b019aab1a514298ff252a0c32ae6`; its result was pending
verification when this record was prepared. That operation is outside this Task.

Reservation is not initialization. No checkpoint, journal event, durable claim,
tested baseline or fault-recovery proof is created by this manifest. Epochs are
configured namespaces, not evidence they already exist remotely. Before
any later authorized initialization, reread exact empty objects and all required
authentication facts; do not substitute this dated reservation for live checks.

## Verification and boundary

Run `python3 tests/build/ci_o1_recovery_storage_test.py`: closed role/field shape,
non-boolean numeric IDs, separately distinct numbers/nodes/epochs, exact recorded
roles, shared existing authority and actual Runtime constructor compatibility
with an API that rejects every request. Run complete `ci_*_test.py` contracts
with pinned actionlint, staged ownership, cached whitespace and final committed
range docs-static. Attempt Portal check before commit and disclose dependency
failures rather than claiming a Portal build. No new merge gate is introduced.

Local results: seven targeted tests and 66 staged ownership tests passed;
complete CI contracts passed with pinned actionlint. Portal check ran: 54 tests
passed and three failed because this isolated worktree lacks `glob`,
`gray-matter` and `cheerio`; subsequent Portal build stages were not reached.
These checks do not initialize storage or prove any remote recovery transition.

Local commit only, HOLD shipping until root review and the docs-only O1 window
permit it. No remote write, initialization, dispatch or fault exercise occurs
in this Task. Claim and response-loss acceptance remain separate journeys.

## Documentation Impact

Documentation impact: none — internal reserved CI configuration; no current
automatic behavior, Portal page, diagram or product source fact changes.

## Version Management

Version impact: none — no Product Build, Module, Provider or Contract version
allocation; no release operation.

Pitfall impact: none — static identity constraints and actual reservation are
explicit; no new platform incident or recovery result is inferred.

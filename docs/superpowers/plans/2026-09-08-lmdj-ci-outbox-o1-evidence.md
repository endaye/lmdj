# Incremental CI O1: actual outbox delivery and replay

## Task and declared files

This evidence ledger is the sole declared file. It records an authorized manual
platform journey, not completion of incremental CI cutover. No implementation,
workflow, permission, Issue mutation or product testing is part of this Task.

## Exact execution boundary

All three runs used attempt 1 and control
`e7e02851d6d29e40ebc164686d353c83ca7b8dd9` (PR #818). The actual workflow
`.github/workflows/self-test-report.yml` has ID `352307416`. Each run's complete
three-job API inventory showed `Incremental batch controller` success and both
`Self-test report` and `Execute incremental batch` skipped. The scheduler
reconcile step was skipped; the isolated outbox reporting step succeeded.

| Operation | Exact run | Controller job | Whole-run completion (UTC) |
| --- | --- | --- | --- |
| Initialize | [34158667427/1](https://github.com/endaye/lmdj/actions/runs/34158667427/attempts/1) | 101855721737 | 2026-09-07 20:15:15 |
| First report | [34158764724/1](https://github.com/endaye/lmdj/actions/runs/34158764724/attempts/1) | 101855996041 | 2026-09-07 20:16:56 |
| Explicit replay | [34158836074/1](https://github.com/endaye/lmdj/actions/runs/34158836074/attempts/1) | 101856207635 | 2026-09-07 20:17:48 |

Each whole run completed successfully, independently of its job outcome. Actual
first/replay logs show `REPORT_OPERATION=report-review`, review run
`34156734074`, attempt `1`, and no scheduler request. These were separate manual
dispatches, not an automatic trigger chain or a rerun of an old attempt.

## Initialize a separate empty outbox

[Issue #817](https://github.com/endaye/lmdj/issues/817), fixed node
`I_kwDOTK_1fs8AAAABQJfE_Q`, was reserved with the exact empty marker and zero
comments before initialization. Its configured epoch is
`o1-report-outbox-20260908-issue817`. Independent post-run GraphQL reads found
the same OPEN Issue, zero comments and a checkpoint with head and pending null.
Its last editor was Bot `MDM6Qm90NDE4OTgyODI=` (`github-actions`), edited at
`2026-09-07T20:15:09Z`; the body writer bound the initialize run, control,
repository, Issue, workflow and controller job exactly. No tested baseline was
created by this initialization.

Scheduler #807 still had four comments and its older observer writer
`34156325323/1`, last edited `2026-09-07T19:38:52Z`. That is evidence against an
initialization write to scheduler state, together with its skipped scheduler
step. There was no independent complete byte-for-byte scheduler snapshot
immediately before and after this dispatch, so that stronger claim is not made.

## Real failed review to durable business receipt

The input review [34156734074/1](https://github.com/endaye/lmdj/actions/runs/34156734074/attempts/1)
belongs to PR #812's historical head
`b589400ee4c251cecefd65f54d9b46a11e08f99a`. Its actual retained receipts report
GLM runtime failure, Kimi invalid output and Grok runtime failure. The status is
`not-reviewed`; deterministic `none` scope for its explanatory ledger is not an
AI approval or a product verdict.

Complete GraphQL pagination of #817 found exactly four unedited bot comments,
all authored by the stable bot ID above, with null editor and lastEditedAt:
generation 0 `queue`, 1 `claim`, 2 `ack`, 3 `delivered`. The claim was a
`create-issue` operation. Every event binds first-report executor
`34158764724/1` and the configured outbox epoch. The delivery ID is
`f7128d62f6d02cc9c6ca679e8091c3e0585c9066dafaf87e4e762f19a63bed23`.

The exact observation is:

```text
812/b589400ee4c251cecefd65f54d9b46a11e08f99a/34156734074/1/9567bf33908d778cfe307f5357bd361157387458a8e2a805c6fa5c0dc4bc603c
```

Independent read-only calculation verified every event digest and previous
pointer, and the checkpoint head
`1dc67de1800ab22ae43d01d29d9e467bb902849df1d33451fd4f0d8c9f35dedf` with pending
null. Hashes are corruption checks, not signatures: writer trust still comes
from controlled repository automation and authenticated API metadata.

Both ack and delivered contain the exact receipt `{issue_number:819,
comment_id:null}`. [Business Issue #819](https://github.com/endaye/lmdj/issues/819),
node `I_kwDOTK_1fs8AAAABQJhWSQ`, was created by `github-actions[bot]` (numeric
ID `41898282`) at `2026-09-07T20:16:42Z`. Its actual body equals both frozen
queue and claim bodies byte for byte. It has assignee `endaye`, labels
`self-test`, `type:bug`, `area:ci-release`, and zero comments. Its title and body
explicitly describe review infrastructure unavailability, not a product defect
or PR merge blocker. An all-state, fully paginated self-test Issue inventory
found one matching backend-unavailable bucket, #819.

## Replay far-side evidence

The root retained before/after JSON snapshots of #819 (identity, title, body,
state, labels, assignees and comment count) and #817 (identity, checkpoint body,
comment count and updated timestamp). Independent `diff -u` checks found no
differences after the explicit replay succeeded. #819 still has zero comments;
#817 still has the original four events and checkpoint writer from the first
report, not the replay. This proves no additional delivery or observation was
recorded for this exact input. The snapshots do not claim a separately archived
byte-for-byte copy of every comment body before and after replay.

## Remaining acceptance boundaries

- No crash, lost HTTP response, read-visibility delay or claim-before-send death
  was injected. This journey does not prove all unknown-write recovery cases;
  uncertain claims remain a separate read-only reconciliation/operator boundary.
- Historical legacy reporting has not been fully migrated behind this outbox.
  Cross-process POST fencing is claimed only for this new manual path; all
  writers must be migrated before claiming universal protection.
- Product failure and mixed-failure/debt Issue reporting, terminal bootstrap
  settlement, genuine none/focused intervals, multiple-merge coalescing, paused
  debt recovery, explicit candidate execution, completion/tick continuation and
  final daily-trigger retirement remain separate real journeys. This ledger
  does not complete the overall CI simplification goal or authorize cutover.
- No release, publication, deployment or Channel promotion occurred.

## Verification

Task checks: staged ownership, docs-static, whitespace and declared-file review.
Portal check is attempted and its result reported without silently installing
dependencies or claiming a Portal build. No new gate or weakened test threshold
is introduced. Actual run/Issue facts above were independently reread through
the GitHub API; the replay snapshot comparison is local read-only verification,
not a substitute for the original platform execution.

Staged `python3 tests/build/ci_change_scope_test.py`: 66 passed.
`scripts/architecture-portal.sh check`: 54 tests passed, three failed because
the isolated worktree lacks installed Portal dependencies. No Portal pass,
downstream validation or build is claimed. The initial docs-static invocation
compared the unchanged base before commit; final committed-range verification
is required separately and does not rely on that empty-range pass.

## Documentation Impact

Documentation impact: none — explanatory acceptance ledger only; no Portal
routes, projected identities, diagrams or current product source facts change.

## Version Management

Version impact: none — no Product Build, Module, Provider or Contract identity
allocation. Run, Issue and Git identifiers are evidence, not release versions.

Pitfall impact: none — existing whole-journey and real-platform-evidence guidance
applied; no newly discovered platform invariant beyond this recorded acceptance.

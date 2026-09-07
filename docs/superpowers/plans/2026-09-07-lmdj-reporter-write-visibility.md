# Reporter write visibility: fail closed on uncertain persistence

Base: `d360d3805f21a18ec75d86bb0fc69cda747e9d9d`.
Task branch: `fix/ci-report-write-visibility`.
Status: local implementation; production rollout and real rehearsal remain separate.

## Observed defect and scope

Real Actions rehearsal 34134692783 created isolated issue 771 at 14:45:35Z;
immediate replay created duplicate 772 at 14:45:36Z. Both had the correct real
github-actions[bot]/Bot author and identical key/observation. The label-filtered
read path did not observe the first write in time. Later label and direct reads
showed both; root closed the two exact test issues. The evidence does not
distinguish GitHub cache delay from replica/filter-index delay. The client bug
is assuming a negative list authorizes another POST. No bot check is weakened.

Declared files (one reviewable Task):

- `scripts/ci/self_test_report.py`
- `tests/build/ci_self_test_report_test.py`
- `docs/superpowers/plans/2026-09-07-lmdj-reporter-write-visibility.md`

Root exclusively owns the temporary rehearsal branch/harness cleanup repair.
No workflow, required check, protection, runner host, product test, self-test
verdict, release identity or artifact schema is changed by this Task.

## Minimal mechanism

1. Remove the automatic retry around the complete read/decide/write operation.
   Each create-issue/create-comment POST is sent only once. Explicit 403/429
   refusals propagate without POST retry; 0/5xx or malformed responses permit
   only read-only recovery. Normal read API backoff remains unchanged.
2. Validate positive integer ID (not bool), original trusted bot author and
   exact observation marker in successful responses. Require the real dedupe
   list path to expose the unique bucket and the exact acknowledged issue/
   comment ID plus observation before declaring success.
3. Read immediately, then at most three more times after 1, 4 and 10 seconds.
   Only positive visibility passes, never elapsed time. GET no-cache is an
   advisory header, not a consistency guarantee. Existing bounded transport
   retries can add their own 5/20-second read backoff.
4. For a lost or malformed response with no usable ID, only one trusted bucket
   and one trusted observation may recover the result. Otherwise stop with
   WriteVisibilityError; never repeat the POST.
5. Keep a small per-client, per-process receipt map of trusted bucket IDs and
   observed issue-body/comment IDs. If later lists regress, perform bounded
   read-only confirmation or stop; never create a replacement issue/comment.
6. Duplicate trusted buckets, duplicate observation receipts, changed IDs and
   malformed lists fail closed. A non-list response is not an empty result.
7. WriteVisibilityError stops the entire CLI/reconcile process, rather than
   being swallowed while later batches attempt more writes. Independent invalid
   artifact/schema cases retain their existing per-run reporting-error behavior.

## Explicit limit: no distributed exactly-once claim

Receipts are deliberately in memory, not a new persistent controller. A process
that crashes after sending a POST can leave a write whose receipt is unknown;
a new process with a negative list cannot prove that write did not occur.
No strict cross-process/crash exactly-once guarantee is claimed. An unresolved
write's diagnostic retains key/observation and known IDs; an operator must
inspect real persistence before retrying in a new process. This does not make
a missing report a pass and does not alter the underlying self-test verdict.
Future automatic restart/reconciliation may need durable pending-write authority
if a stronger cross-process guarantee is required; it is outside this minimal
repair. Do not present the bounded controlled drill as that stronger proof.

## Verification and handoff

Unit tests model list visibility independently from durable writes, including
multi-read delay, permanent invisibility, 0/5xx/lost/malformed responses, strict
positive IDs, same-process list regression, duplicate buckets/observations,
bot author changes and immediate whole-process abort. Assert actual POST count,
not just the final in-memory issue count. No unit test calls the real API.

Run python3 -S tests/build/ci_self_test_report_test.py and all ci_*_test.py,
stage only these files, run staged ownership, and inspect cached diff/check.
Root reviews and owns commit/push/PR/shipping and the next real Actions drill,
whose trusted checkout must pin the exact reviewed fix commit. The original
failed drill is not rewritten into a passing record. No local agent remote
mutations or production cutover are authorized by this implementation alone.

Local results: reporter 72/72, complete ci_* 856/856 (python3 -S), staged
ownership 66/66 and cached whitespace checks pass. No workflow YAML changed;
no product/native build or remote API mutation was run for this repair.
The new real Actions rehearsal is still pending and cannot be inferred from
these fake-based unit tests.

## Version Management

Version impact: none — reporting transport safety only; no product, module,
provider, contract, build or release identity changes.

## Documentation impact

Documentation impact: none — no portal pages, diagrams, projected identities,
product behavior or release policy change. This plan records the operational
consistency boundary of the narrow reporter repair.

Pitfall impact: none — write/list visibility handling is now an explicit tested
code invariant. The real failure evidence and remaining cross-process limit are
recorded above; the controlled-acceptance process correctly stopped the cutover.

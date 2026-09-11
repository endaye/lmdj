# Authenticate full review-comment locations

## Task and cause

Repair current-head review eligibility for PR #1243 without changing its audio
source. Exact head: `0158f213ab5596ba18070c74ccde82779d4d36ff`.

The original PR Contract and PR Review entry failures were HTTP 403 while
reading PR metadata, before product tests or model dispatch. Bounded reruns
recovered without permission changes; the old logs do not distinguish a rate
limit from another access failure. Run `34633148497`, attempt 2 then completed
all three PR Review jobs, with review `5182428209` and two findings. The
current-head reader still rejected it: `published finding differs from
authentic model artifact`.

Live read-only API comparison identifies a separate deterministic cause:
`/pulls/1243/reviews/5182428209/comments` returns legacy position fields but
omits `line`, `side`, and `original_line`. Fetching the same comments by exact
ID (`3992461160`, `3992461169`) returns RIGHT-side original lines 986 and 916.
The fixture incorrectly put the detail-only fields on the list response.
The API contracts are documented at
<https://docs.github.com/en/rest/pulls/reviews#list-comments-for-a-pull-request-review>
and <https://docs.github.com/en/rest/pulls/comments#get-a-review-comment-for-a-pull-request>.

## Declared files

- `scripts/ci/review_wait.py`
- `tests/build/ci_review_wait_test.py`
- `.agents/pitfalls/fake-tool-stub-strictness.md`
- `docs/plans/2026-09-12-pr-review-comment-hydration.md`

One Conventional Commit. Read the complete per-review inventory, then fetch
each exact numeric comment ID from the canonical repository endpoint. Bind
list/detail identity, bot, review, original head, path and body before checking
the full original RIGHT-side line against the authentic model artifact. Never
infer a line from legacy position, omit findings, or replace authentic review
with a waiver. Preserve missing/tampered/duplicate/unavailable refusal.

## Verification

1. Reproduce failure with a real-shaped legacy list and separate detail fixture
   through the actual publisher -> archive -> reader journey, including v2.
2. Verify wrong detail ID/review/bot/head/path/body/line/side, missing details,
   duplicate inventory and incomplete reads remain non-eligible. No writes.
3. Run review wait, failure report, pipeline and scope/codec suites; stage the
   declared files and run the ownership suite after adding the plan.
4. Run the patched read-only helper against the same real run/attempt and head.
   This validates review evidence, not the substantive disposition of findings.
5. Independent exact-head review, ordinary guarded Task shipping, then repeat
   the live reader check from merged code. Do not merge PR #1243 as part of this
   infrastructure repair. Its findings require recorded technical dispositions.

No required CI check or permission change is added. The new regression catches
using a legacy list projection as a full comment-location record, while retaining
the complete existing artifact and identity verification journey.

## Version Management

Version impact: none
Reason: repair a read-only CI evidence consumer; no product, public Contract,
Module, Provider, Assembly or release identity changes.

## Documentation Impact

Documentation impact: none
Reason: the existing current-head authentication rule is unchanged; only the
GitHub endpoint used to obtain its already-required comment location is fixed.
No current portal fact or operation changes.

## Pitfall and evidence

The fake-tool-stub-strictness recurrence is recorded against the failing real
attempt. Existing escalation #726 remains open; this narrow endpoint-shape
repair does not settle its broader typed polling scope.

Original 403 and reader failures remain historical evidence. Verification and
shipping receipts will be appended; no Kimi, accounting or audio changes belong
to this Task.

Author verification before commit: the new real-shaped v2 test failed with the
original reader (1 failure, exit 1). After repair, `ci_review_wait_test.py`
passed 53 tests, `ci_review_failure_report_test.py` 46, `ci_review_scope_test.py`
49 and `ci_review_scope_codec_test.py` 10, all exit 0 with no skips.
`ci_review_pipeline_test.py` passed 40 tests with its one explicit pinned-runtime
integration skip, exit 0; no claim of new provider execution follows from that
suite. The patched read-only helper against PR #1243's unchanged exact head
and real run `34633148497` attempt 2 returned `eligible: true`, empty diagnostics,
both authentic findings retained, and exit 0. No waiver was used.

Both PR Contract runs recovered. Rerunning the duplicate same-concurrency-group
run interrupted the other run's Documentation impact job; that exact canceled
job was subsequently rerun sequentially. Final runs `34633148643` attempt 2
and `34633224521` attempt 3 succeeded. Their CI contract lane was correctly
unselected for the audio-only diff; no skipped lane is counted as a pass.

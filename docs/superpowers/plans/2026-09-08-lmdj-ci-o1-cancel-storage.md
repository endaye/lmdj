# O1 cancellation storage assignment

## Task and declared files

This Task changes only `scripts/ci/o1_recovery_storage.json`, the matching exact
identity assertion in `tests/build/ci_o1_recovery_storage_test.py`, and this plan,
on isolated branch `feat/ci-o1-cancel-storage`, based on
`aca410cbc2bdeb8a31c01e0a4ceb1df9d6269979`. It assigns the reviewed cancellation
diagnostic fresh storage, without resetting the previous claim journal or
changing the scheduler/outbox roles. It does not initialize or dispatch a run.

## Actual reservation and preservation

An all-state paginated Issue inventory found no existing cancellation storage.
One reservation POST created [Issue #840](https://github.com/endaye/lmdj/issues/840).
A separate GET confirmed OPEN, zero comments, exact body
`<!-- lmdj-ci-journal-uninitialized-v1 -->` followed by one newline, and node
`I_kwDOTK_1fs8AAAABQKYSiQ`. The assigned epoch is
`o1-claim-cancel-20260908-issue840`. Repository, bot and existing workflow
authority remain unchanged; no additional permission is required or granted.
An empty Issue/checkpoint does not authenticate an epoch: the reviewed committed
role assignment and ordinary authenticated transport remain necessary.

Old claim journal #826 remains intact. Its actual claim-before-output run
`34166438455/1` exited 87 without product execution or artifacts. Ordinary
settlement `34166543480/1` recorded all 16 suites missing before advancing
processed progress; fresh replay `34166702231/1` retained complete state and
remote records unchanged. After the genuine one-document merge #839,
settlement-only observer `34166959881/1` retained every missing-debt object,
request and result, changing only pending main, generation and its observe
event. This observation did not execute or claim completion of the pending
document interval. It does not prove real GitHub cancellation.

Do not delete, close, reset or migrate old journal contents. The existing
scheduler #824 and outbox #825 entries remain byte-equivalent JSON objects.
The automatic main journal #807 and report outbox #817 are not targets of this
assignment. No baseline, health or passed test is inferred from reservation.

## Subsequent controlled operation boundaries

After actual merge, reread the committed manifest and the live reserved Issue.
Only then may the existing authorized initializer establish an empty checkpoint
with its independently authenticated bot writer. A fresh exact-main diagnostic
may claim the full inventory only after the existing global old-run audit.
The separate C2 workflow wiring must verify readiness and isolate a bounded
hosted waiter; this Task adds neither that workflow nor cancellation code.

Cancel only the independently verified exact diagnostic parent run after its
durable claim and active waiter are observed. Never cancel another batch, use
force-cancel, change host permissions or infer terminal cancellation from a
successful API response. Ordinary fresh settlement/replay must retain all
unexecuted suite debt after the actual cancelled conclusion. Those remote legs
are still outstanding and cannot be replaced by local fixture results.

## Verification

Run the existing storage-manifest and claim-probe contracts, check that only the
three intended claim fields differ, and retain staged ownership and whitespace
checks. Run the required Portal check and report dependency failures honestly;
do not claim a pass for stages that did not execute. Classify the clean final
committed range before shipping; this control configuration is not docs-none.
Independent current-head review and actual protection checks precede authorized
expected-head squash merge. Keep both worktree and old journal intact.

Local verification: 7 storage tests, 24 claim-probe tests and 66 staged ownership
tests passed; complete CI discovery with pinned actionlint passed 1,514 tests
without skips. Portal check ran 57 initial tests: 54 passed and three failed
because this isolated worktree lacks `glob`, `gray-matter` and `cheerio`.
Subsequent Portal stages did not run. No Portal pass or remote cancellation is
claimed. Final committed-range classification is checked before shipping.

## Version Management

Version impact: none — internal diagnostic storage assignment; no product,
module, Host, Provider or Contract identity changes and no version allocation.

## Documentation Impact

Documentation impact: none — no Portal pages or product behavior change.

Pitfall impact: none — apply existing fixed-identity, response-loss and complete
journey guidance; the planned controlled boundary is not a new product defect.
No tag, Release, deployment, publication or Channel promotion is performed.

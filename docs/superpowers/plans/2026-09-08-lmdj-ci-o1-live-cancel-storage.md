# O1 live executor-cancellation storage reservation

## Task and declared files

Reserve a new isolated claim role for a separately authorized attempt to cancel
an actually running diagnostic waiter. This Task changes only:

- `scripts/ci/o1_recovery_storage.json`
- `tests/build/ci_o1_recovery_storage_test.py`
- This plan.

No workflow, diagnostic adapter, waiter duration, runtime policy or permission
changes. No product tests, initialization, dispatch, cancellation or release
operation belongs to this Task. Initially all shipping was on HOLD. After the
root reviewed the three-file reservation and independently read back #857,
push and PR creation were authorized; merge, initialization, dispatch and
cancellation remain separate root-owned boundaries.

## Version Management

Version impact: none — a diagnostic storage binding allocates no product,
module, provider or contract version.

## Documentation Impact

Documentation impact: none

Reason: only an isolated diagnostic Issue identity changes; no
product, public execution interface, test policy or Portal fact is changed.
Existing recovery/cancellation guarantees are not broadened by the reservation.

## Reservation evidence and fixed authority

Complete all-state Issue pagination found no unused reviewed claim role.
The existing diagnostic Issues #824, #825, #826 and #840 had respectively
1, 3, 6 and 5 comments. The empty-comment #836 is a business report, not a
reviewed storage role. Existing #840 must not be cleared, reinitialized or reused.

One authorized Issue creation produced #857 at `2026-09-08T00:40:42Z`.
Independent REST GET and GraphQL reads confirmed:

- Repository: `endaye/lmdj`, numeric ID `1286600062`, default branch `main`.
- Issue: `857`, node `I_kwDOTK_1fs8AAAABQLLT3w`, OPEN, author `endaye`.
- Exact body: `<!-- lmdj-ci-journal-uninitialized-v1 -->` followed by one newline.
- Zero comments; GraphQL editor and lastEditedAt both null.
- Existing writer workflow: `352307416`, active
  `.github/workflows/self-test-report.yml`.
- Existing trusted bot: `MDM6Qm90NDE4OTgyODI=` (unchanged).
- New assigned epoch: `o1-claim-cancel-live-20260908-issue857`.

Only claim number/node/epoch migrate. Scheduler #824 and outbox #825 retain
their exact complete existing records. This is reserved uninitialized storage,
not a checkpoint, claim, tested baseline or cancellation result.

## Preserved history and later acceptance legs

Issue #840 retains its five original records and epoch
`o1-claim-cancel-20260908-issue840`; the prior #826 history is also untouched.
The previous parent run `34168119615/1` reached an API cancelled terminal state,
but its waiter logged natural expiry and exit 1 before that terminal state.
Its settlement and replay remain valid observations; it does **not** establish
interruption of a running waiter. See the existing incremental O1 evidence ledger.

The later root-owned, separately authorized journey must retain every leg:

1. Ship the reviewed binding, read back exact main identity, and initialize
   only #857. Confirm empty checkpoint and no comments/baseline.
2. Dispatch one main-pinned, attempt-1 diagnostic. Verify closed readiness,
   all three authenticated observe/admit/claim records, the full sixteen-suite
   bootstrap request, exact executor identity and no execute output/artifact.
3. As soon as the diagnostic controller is completed and the independent waiter
   is actually `in_progress`, capture the exact parent/job identities and have
   the root promptly send **one normal cancel** to that parent. Do not spend the
   remaining 285-second window on unrelated audits; do not wait for expiry.
4. Verify real parent and waiter cancelled statuses **and** logs demonstrating
   interruption before natural expiry/exit 1. A cancellation acknowledgement,
   API label alone, process exit, timeout or synthetic fixture cannot pass this leg.
5. Snapshot the complete journal before and after cancellation; preserve the
   original claim and confirm no product execution. A fresh ordinary settle
   must record all sixteen missing/debt outcomes and clear only the active slot.
6. A separate ordinary settle replay must leave complete state and journal
   unchanged. Preserve any unresolved evidence instead of repeating a write.

No force-cancel, other run cancellation, runner permission/sysctl change,
timeout extension or automatic retry is authorized. If the live window is missed,
retain that failure honestly and request the next explicitly scoped decision.

## Verification

The seven existing manifest tests retain closed six-field roles, distinct
numbers/nodes/epochs, unchanged shared authority and real Runtime compatibility
without API calls. First update the exact expected claim tuple to demonstrate
the old manifest is red; then change only its three identity values to go green.
Run claim/cancellation tests, complete CI inventory, staged ownership and diff
checks. Portal check is attempted before commit; unavailable local dependencies
remain explicit and do not justify installing unrelated packages.

Local results:

- Exact tuple regression first failed against #840, then all 7 manifest tests
  passed after the three-field binding change.
- Claim adapter: 24 tests passed. Cancellation adapter: 15 tests passed.
- Complete CI inventory: 1641 tests passed without skips; log
  `/tmp/lmdj-live-cancel-storage-ci.log`.
- Staged new-file ownership: 66 tests passed; cached diff check passed.
- Portal check was attempted: 54 tests passed / 3 failed because this isolated
  worktree lacks `glob`, `gray-matter` and `cheerio`. Later Portal stages did not
  run. Log `/tmp/lmdj-live-cancel-storage-portal.log`; this is not a Portal pass.
  No dependencies or unrelated files were installed or changed.

### Refreshed shipping verification

The isolated Task was rebased without conflict onto current `origin/main`
`aadb309c` after the central CI fixes, preserving the same manifest and exact
tuple test. The interval is no longer a pure two-Host batch. The named central
CI full rule selects all fourteen lanes; its manifest-path diagnostic is
covered by that rule, not an unknown ownership exemption.

- Manifest 7, claim 24 and cancellation 15 targeted tests passed again.
- Complete CI inventory: 1654 tests passed without skips, recorded in
  `/tmp/lmdj-live-cancel-storage-final-ci.log`.
- Locked Portal dependencies were installed with `npm ci`; no lockfile or
  other tracked dependency file changed. The earlier missing-dependency result
  above remains historical, not the current verification result.
- Full Portal check passed: 65 tests, facts and release documentation checks,
  typecheck, production build and 42 routes with valid internal links; log
  `/tmp/lmdj-live-cancel-storage-final-portal.log`.
- All 66 tracked/staged ownership tests and nonempty committed-range
  `docs_static` passed; final cached whitespace checks passed.
- A fresh API read still found #857 OPEN with its exact newline template,
  expected node and zero comments. This read is not initialization evidence.

No initialization, dispatch or cancellation has occurred in this Task. Before
authorized shipping, the only remote mutation was the empty Issue reservation.

Pitfall disposition: the existing acceptance-journey and synthetic-side-effect
guidance is applied; this binding does not claim to fix the prior timing race.

# Durable candidate BUILD reservations

Delivery base: `7edb533cfd957eadc8d1122f1fc129d8412e1c9f`.
Reapply Task `21ab02fdaa689d34999c1e41380417c213136dec`, preserving the
newer passive Git reader, bounded journal writer and persistent request aliases.

## Task

Reserve one immutable new BUILD number before any cut edits. Use the existing
owner-only, fsync/atomic-replace, live-process/thread single-writer journal
mechanism with an explicitly enrolled, repository-bound catalogue. Resume
must never reconstruct missing reservations or consume a second number.
The catalogue records every reservation permanently, including failed ones.
Derive the historical floor from complete original-baseline Product manifest
history, including reverted/merged-away allocations, not just current BUILD.
Keep the original Milestone/Minor and reset PATCH to zero. Compare exact frozen
candidate inputs before every reservation or pre-cut resume.
Compare the observed main history floor too: allocation followed by revert
cannot hide a competing consumed number behind identical endpoint files.
Both first reservation and resume refuse this conflict without renumbering.

Declared files:

- tools/release/candidate.py
- tests/build/release_candidate_test.py
- CMakeLists.txt
- apps/docs-site/docs/operations/version-and-release.mdx
- docs/plans/2026-09-13-release-candidate-reservation.md

This is a durable reservation primitive, not a completed candidate adapter.
The trusted parent still owes original-authority/main authentication, accepted
baseline CI, canonical shared storage enrollment, duplicate request alias
resolution, actual version/Assembly/lock edits, snapshot, reviewed cut PR,
post-squash witness and exact target proof. No new release command, real Build
allocation, provider call, CI dispatch, signing or deployment is activated.
Manual allocators outside the shared catalogue are not serialized by its local
lock; main/cut competition must also be reconciled at the guarded PR boundary.

## Verification

Use real temporary Git histories and local filesystem/process transitions.
Successful baseline reservation and restart must preserve exact stored bytes;
each failure must retain the prior catalogue and make no externally visible
allocation. Exercise higher historical BUILD then revert, PATCH reset, docs
motion, changed source, rebound scope, missing/unsafe/corrupt catalogue,
second writer, crash after fsynced save and failure before save. Run the
registered candidate/input/journal/driver suites, staged ownership and Portal.

Original-stack results remain historical, not current-head acceptance.
Current delivery evidence:

- Direct `python3 tests/build/release_candidate_test.py`: 20/20, 29.781s,
  exit 0; `/tmp/lmdj-candidate-reservation-delivery-tests-v1.log`.
- Exact-base historical scan of `7edb533cfd957eadc8d1122f1fc129d8412e1c9f`
  returned BUILD floor 56 without enrolling storage or changing worktree status,
  exit 0; `/tmp/lmdj-candidate-reservation-delivery-exact-base-v1.log`.
  This reads local committed history, not authenticated GitHub main or an
  actually allocated candidate.
- Independent reviewer `/root/release_journal_review` inspected all five files,
  including unchanged journal writer / passive Git dependencies, with no
  actionable finding. Independently ran two recovery cases: 2/2, 1.809s,
  exit 0 (missing catalogue with only lock refuses enrollment; real process
  exit resumes the original number). Diff check passed. This is not owner
  adoption or live PR merge eligibility.
- Registered CTest selection
  `^build\.release_(candidate|candidate_inputs|orchestration|orchestration_driver)$`:
  4/4, 51.87s, exit 0. Actual child populations: reservation 20, inputs 16,
  journal 21 and driver 32; all passed without skips. The original 30-second
  per-suite budgets remain unchanged; CTest ran before the Portal build.
  Log: `/tmp/lmdj-candidate-reservation-delivery-ctest-v1.log`; actual child
  output: `build/core/dev/Testing/Temporary/LastTest.log` in this worktree.
- After staging all five declared files, ownership/admission suite passed
  74/74 in 6.411s, exit 0:
  `/tmp/lmdj-candidate-reservation-delivery-scope-v1.log`.
- Node 22 locked dependencies and `scripts/docs-site.sh check`: 144/144 tests,
  no skips, 47 pages and built routes verified, exit 0:
  `/tmp/lmdj-candidate-reservation-delivery-docs-v1.log`. The generated
  `apps/docs-site/build/operations/version-and-release/index.html` also contains
  the enrollment, history-competition and no-renumber statements; explicit
  output check exit 0:
  `/tmp/lmdj-candidate-reservation-delivery-rendered-v1.log`.
  This is local rendering, not live doc-site publication or a Product snapshot.

No real BUILD reservation or storage enrollment, release, deployment, remote
CI dispatch or provider operation is performed. Pitfall disposition: source
regressions fully express this primitive's persistence/history invariants;
no new process-only ledger rule is claimed.

## Version Management

Version impact: none

Reason: reservation implementation only; no real Product Build or Assembly change.

## Documentation Impact

Documentation impact: required

Affected portal pages: /operations/version-and-release/

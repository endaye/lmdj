# Live-control exact-retry applied receipt

Status: native regression verified; current-head review and shipping are separate
transitions.

## Outcome and refreshed premises

Creator follow-up W1 PR #2083 requires the documented `applied` boolean in
every successful `performance.live.control` response. At refreshed main
`a584859883b4d22f78e62a3990b6f9e8ec26b589`, the Facade's fresh response includes
that field, but its exact completed-command replay omits it. The Web boundary
in PR head `285ddbb2e59c8dd84b34573cd7fdfad783b809d2` correctly rejects the
incomplete success shape. The omission remains outstanding; P1's live-control
producer and bounded command ledger are already delivered and are retained.

Authority: the approved D0 live-control encoding decision and the Creator
Desktop Final follow-up Goal. `accepted` and actual `applied` are distinct;
an exact retry retains its original identity and never admits a second input.
The current callback progress supplies `applied`, as it does for the existing
fresh response. This restores a required receipt field; it introduces no new
product behavior, retry window, generation or authoring operation.

## Declared files and implementation

- `packages/application-facade/src/application.cpp`: in the already verified
  completed-command replay branch, read the existing live-control snapshot and
  compare its applied control sequence to the completed command's sequence.
- `tests/core/facade/performance_gesture_admission_test.cpp`: keep every
  existing case and add a real Engine/Adapter/Application regression. The same
  command must report false before the callback and true after an actual render,
  retaining command/epoch/sequence/generation and admitting no duplicate input.
- `docs/plans/2026-10-13-live-control-retry-applied.md`: this Task and its results.

The isolated branch is `fix/live-control-retry-applied`, based on the refreshed
main above. W1's existing PR and other owners' worktrees remain their own Tasks.

## Lowest-tier verification and defect oracles

1. Add the real-engine receipt regression and rebuild its whole existing
   `facade.performance_gesture_admission` registration. With the old producer,
   the named replay-field assertion must fail. Retain its actual build exit and
   the owning failure; source inspection alone is not this RED evidence.
2. Restore the required producer field, rebuild the actual production-linked
   target, and run the whole gesture-admission and operation-contract suites.
   Keep their original component timeout and all pre-existing journey legs.
3. Verify the same command before and after a genuine 128-frame callback,
   including unchanged accepted control sequence and the matching applied mask.
   A fake sink transition does not establish that callback boundary.
4. Run the new-file change-scope tests and final ownership/declaration checks.
   Independent current-head review, conversation/conflict protection and guarded
   merge follow `issue-done`; no full-CI or strict-update gate is introduced.

Shared-host heavy tests run after the already scheduled R-H and D03 windows.
Stop on an unexpected build/test failure; retain the evidence and repair its
cause without widening timeouts, reducing the suites or changing the contract.
Native component evidence does not establish Web deployment, hearing, physical
acceptance, optimized timing or full-candidate verification.

## Version Management

Version impact: application-facade PATCH compatibility repair. No public C++
layout, C ABI, Contract ID or manifest identity changes. Allocation remains in
the Goal's V1 settlement Task; this Task allocates no Product Build or snapshot.

## Documentation impact

Documentation impact: none. This restores the already documented accepted /
applied distinction and required live-control receipt, without changing portal
routes, diagrams, product identities or documented architecture/API behavior.

## Pitfall impact

None: this product-logic omission is directly captured by the receipt regression.
The existing parity and journey guidance applies; no process gate or ledger
entry is added merely to restate executable source behavior.

## Verification results

The premise was rechecked at integration revision
`9f44298c98b190c20443c79cd62d19045ee06e41`: intervening Release tooling and
Product Build allocation changes do not modify the owning Core source, tests
or build wiring. A subsequent precommit refresh at
`e2d3aaf740d08e917867a6594c689b97e0d3da2b` contains another independent
candidate allocation with the same owning inputs and governance unchanged.
Exact W1 head and the remaining receipt omission are retained.

On the owned arm64 macOS worktree, ordinary UID 501, Debug and sanitizer `none`:

- `bash scripts/core.sh configure dev`: exit 0.
- Rebuilt the complete gesture-admission target with the old producer: exit 0.
  Its whole CTest registration returned exit 8 at
  `performance_gesture_admission_test.cpp:2653`, `retry.contains("applied")`.
  This is the intended missing-field regression, not a timeout or unrelated
  failing case. Its original source, object, binary and full logs are preserved.
- Applied the four added producer lines and rebuilt the gesture-admission and
  operation-contract targets: exit 0, with the production translation unit
  actually recompiled and the gesture executable relinked.
- `ctest --preset dev --parallel 1 --verbose --no-tests=error -R
  '^facade\.performance_(gesture_admission|operation_contract)$'`: exit 0,
  both complete registrations passed, no skips, original 30-second budgets.
  The unchanged new test object links the corrected production object; its real
  128-frame Engine callback and no-readmission checks are part of this run.
- The pre-staging change-scope suite passed all 77 tests. The same ownership
  gate must also pass after these three declared paths enter the staged index.

Full receipts and baseline custody are in the external evidence directory
`live-control-retry-applied-native-window-20261012T1919` under the Root
checkpoints. Independent Source review found no blocker; review eligibility,
findings, live protection and shipping are checked against the committed head.
Web integration, deployment, optimized timing, full-candidate and physical /
hearing acceptance remain outside these Native receipts.

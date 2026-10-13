# Replay failure and exact-retry regression recovery

## Current premises

Base: `9fb83ce0f70de1bc9114711bf9e854dfa6bb7081`, freshly fetched from
`origin/main` on 2026-10-13. The old unmerged `b87e9c92` Task contains nine
files. Its legacy-only rejection policy expired when PR #2044
(`d21ea97c71da281f89ac78238f6fcceb8b03e638`) added headered replay, typed
Filter and Pad gates. PR #2068
(`a4923f20f78ba6780d1265882669b8a00a762de4`) subsequently delivered profile
consistency preflight for direct projection callers. Neither policy is
implemented again here.

Three valid legacy regression journeys from the old Task remain absent from
the current owning tests. Application still checks replay identity and playing
exclusion before loading, clears a completed active replay before loading a new
target, and propagates loader/Cooker errors. Existing Replay tests cover a
normal-path collision/exclusion, Truth deletion followed by Stop, and ordinary
exact retry; they do not combine missing paths with identity priority, retry
after Truth deletion, or completed replay with load/target failure and recovery.
The Operation Contract suite checks malformed UUID and extra-key priority;
the C API suite exercises a happy legacy replay. Runtime-consumer tests check
adapter linkage, and the gesture suite does not dispatch replay begin.

The coverage audit enumerated replay/controller consumers and read owning test
bodies and their complete `main()` call lists at the stated revision. A
known-present direct profile-refusal body/call is the positive control for the
same inspection. This is a bounded missing-regression finding, not a newly
observed production defect or a claim about every possible Host journey.

## Task and declared files

One Task, one Conventional Commit:
`test(facade): retain replay failure and exact-retry regressions`.

- `tests/core/facade/performance_replay_test.cpp`
- `docs/plans/2026-10-13-replay-failure-retry-regressions.md`

Recover only the three valid legacy journeys. Keep all existing test bodies,
calls and deadlines. Remove the old unrelated header fixture from the
missing-target test: the target is absent and the surviving Performance is
ordinary valid legacy data. Production sources and public interfaces retain
their current behavior.

## Acceptance and lowest-tier verification

The complete `facade.performance_replay` component registration owns these
facts; build `lmdj_facade_performance_replay_tests` and run
`ctest --preset dev --output-on-failure -R '^facade\.performance_replay$'`.

1. Begin legacy replay; a same-ID request with a missing path still returns
   `DUPLICATE_ID`, and a different-ID request is excluded by the original active
   replay. Delete its Performance Truth; exact original retry still succeeds
   using the original revision and one original controller begin.
2. Complete the original replay; new-ID begin on either a missing bundle or a
   corrupt manifest preserves the original loader envelope. A subsequent valid
   begin succeeds without another status lookup on the completed replay.
3. Complete the original replay; begin for an absent Performance preserves
   `NOT_FOUND` and `Performance does not exist`. A subsequent valid begin
   succeeds without another status lookup on the completed replay.

Both `performance.list` and replay begin share `ProjectStore::load`, so error
parity alone could agree on a shared wrong error. The test independently checks
`INVALID_PROJECT`, the missing-directory versus corrupt-JSON message, and the
exact failing path, as well as full envelope parity. These closed fixture
expectations are the independent oracle.

Bounded causal mutations must rebuild the actual changed translation unit:
load before identity admission; give both loader consumers the same wrong
error; alter missing-target Cooker failure; omit completed-active cleanup.
Each must fail in the recovered test that owns the changed fact. Save working
bytes externally, restore with a strictly newer mtime, inspect the rebuild's
exit and compile line, and rerun the entire owning suite on restored artifacts.
The shared-loader mutation must retain caller parity while the absolute oracle
rejects the wrong result.

Before shipping, run the new-plan ownership check, staged whitespace/file
inspection, PR body lint and documentation declaration checks. Record actual
results below. Candidate/full Core, stress, ASAN, coverage, browser, physical
and release verification remain unexecuted by this component-test Task.

## Version Management

Version impact: none — only tests and their implementation plan change; no
public ABI, persisted grammar, manifest, Assembly or Product identity changes.

## Documentation Impact

Documentation impact: none — the plan documents a test recovery Task; no
Architecture Portal page, diagram, projected identity or product behavior is
changed.

## Pitfall Impact

Pitfall impact: none — the existing shipping rules for stale premises,
acceptance journeys, independent parity oracles and fresh mutation restoration
are applied. No new process defect or observed recurrence is asserted.

## Main refresh before commit

Fresh main advanced to `2a5ec35f6bc1433539fc7064c30be756d779ae29`
with PR #2114: four Creator decision/plan/Portal/pitfall paths. The complete
intervening path inventory was inspected; it changes no Replay producer,
consumer, owning test or build input and none of the Task's governing files.
All three missing regression dispositions remain valid; no duplicate recovery
landed. The verified component artifact retains its original implementation
base, and this unrelated documentation merge creates no rebase/full-CI gate.

## Actual verification

Actual outcomes at the stated base:

- `scripts/core.sh configure dev`: exit 0. Fresh one-job build of
  `lmdj_facade_performance_replay_tests`: exit 0.
- Complete `facade.performance_replay`: exit 0, all 30 called bodies (the
  original 27 and the recovered three), 0.69 seconds, unchanged 30-second
  registration deadline.
- Load-before-identity mutation: actual Application translation-unit rebuild
  exit 0; suite exit 8 at new test line 1063, expected `DUPLICATE_ID`.
- Shared-loader-error mutation: actual Project Store translation-unit rebuild
  exit 0; suite exit 8 at new test line 1116, absolute loader-message oracle.
  The preceding full error-parity assertion at line 1112 passed on the shared
  wrong result, demonstrating why parity needs the independent oracle.
- Missing-target-error mutation: actual Cooker translation-unit rebuild exit 0;
  suite exit 8 at new test line 1152, expected `NOT_FOUND`.
- Omitted completed-active cleanup mutation: actual Application translation-unit
  rebuild exit 0; suite exit 8 at new test line 1127, post-valid-begin
  `status_calls == 1`.
- Every restoration wrote the externally preserved working bytes with a fresh
  mtime after waiting more than one second; each restore rebuild exited 0 and
  compiled the mutated translation unit. Each restored complete suite exited
  0; the final restoration passed in 0.52 seconds. Production bytes match the
  original source snapshots. These are deliberate causal REDs, not unresolved
  product failures.
- New-plan staged ownership: `python3 tests/build/ci_change_scope_test.py`,
  exit 0, all 77 tests. Advisory lane selection is focused with
  `core_asan core_coverage core_ubuntu docs_static`; complete product lanes
  remain unexecuted here.

Logs, exact process exits, source snapshots and mutation receipts are retained
locally under `worktree-finish-20261013/replay-regressions/`.
The original nine-file branch remains preserved: this Task does not establish
whole-patch main retention for obsolete code, documentation or historical proof.

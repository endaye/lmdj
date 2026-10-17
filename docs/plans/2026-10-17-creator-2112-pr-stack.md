# Creator #2112 PR stack

Date: 2026-10-17
Parent: #2112. First feature: #2232 (Creator COUNT-IN / S7).

## Authority and integration boundary

The user authorized continuing #2112 development as a stack of PRs while the
current main release and deployments finish. This turn authorizes implementation,
verification, Conventional Commits, branch pushes and PR creation. It excludes
merging into main, automatic merging, release, deployment and resource cleanup.
Keep every layer a Draft PR during this hold. A branch push or a passing test
does not end the hold.

Use ordinary Git branches with explicit PR bases: the first layer targets main;
each later layer targets the preceding branch. This is a dependency chain, not
GitHub native stack metadata or a Graphite submission. Each layer has its own
isolated worktree, declared files and Task verification. The user's instruction
permits dependent branches to start from their predecessor instead of main.
No global Git/CI governance or protection is changed for this work.

The starting main and first Task base are
`e47b02510ef144a518163978d42b44b50558d36b`. The stack coordinator owns base
changes. Preserve published history and other worktrees; cascading rebases need
explicit coordination and current-head evidence. After a future authorized
squash, rebase descendants onto the actual introducing main commit and verify
the resulting changes before considering the next merge.

## Refreshed premises

- S6 scheduled recording is delivered by #2202 and the terminal-owner follow-up
  by #2223. Import is delivered by #2266; #2225 is closed. Do not implement those
  again. The remaining Pattern order is S7 (#2232), S3 (#2233), S5 (#2234).
- `apps/creator-web/src/state/seq_snap_preference.ts` and
  `test/seq_snap_preference.test.ts` are a positive control for a device-only
  IndexedDB preference: database `lmdj.creator.host`, store `settings`, serialized
  writes, bounded reads, exact-value validation and default fallback.
- At the pinned base, the state directory and App's preference imports/effects
  have no COUNT-IN preference module or consumer. The Sequence SETUP controls
  expose SEQ SNAP and METRONOME. S7 must add its own numeric `0 | 1 | 2` preference
  at `count-in.v1`; the existing native capability is not this UI delivery.
- The current PR review target and receipt validators require a main-target
  non-draft PR (`.github/scripts/pr_review_target.py`,
  `scripts/ci/review_scope.py`, `scripts/ci/review_wait.py`). Upper-layer or Draft
  checks cannot be reported as eligible independent review. Record review as
  pending, preserve findings, and obtain valid current-head independent review
  before any future merge. This feature stack does not adapt CI control code.
- Original device/listening requirements and complete count-in acceptance remain
  attached to #2232 and #1221. Layer completion is not Issue closure.

## Layer 1 — COUNT-IN preference persistence

Branch: `feat/creator-count-in-preference`; PR base: `main`.
One Task / one Conventional Commit. Partial delivery of #2232.

Declared files:

- `apps/creator-web/src/state/count_in_preference.ts` (new)
- `apps/creator-web/test/count_in_preference.test.ts` (new)
- `docs/plans/2026-10-17-creator-2112-pr-stack.md` (new)

Deliver a Host-only numeric Off/1/2 preference, default Off, in the existing
IndexedDB settings database under `count-in.v1`. Exact numeric values round-trip;
unavailable, corrupt and unreadable storage falls back to Off. Writes serialize
and settle only after the transaction commits or fails. A read waits for earlier
writes but has the existing five-second boot bound. Other settings remain intact.
No Project Truth, UI control, recording request or metronome behavior changes in
this layer; these require the next consumer Task.

Lowest-tier verification:

- Existing SEQ SNAP preference tests on the unchanged base establish the local
  harness. New COUNT-IN tests assert exact raw IndexedDB key/value, committed
  round-trips, corrupt/default/error boundaries, rapid writes, read-after-write,
  transaction settlement and preservation of other settings. Raw store reads are
  the independent oracle for storage identity and numeric encoding.
- `npm --prefix apps/creator-web test -- run test/count_in_preference.test.ts
  test/seq_snap_preference.test.ts test/metronome_preference.test.ts
  test/last_project.test.ts` covers the shared settings database's existing users.
- From `apps/creator-web`, `npx --no-install tsc --noEmit -p tsconfig.json`
  verifies the new Host source against the actual TypeScript project.
- After staging, `python3 tests/build/ci_change_scope_test.py` verifies new-path
  ownership; inspect `git diff --cached --check` and the exact staged inventory.
- On the committed clean head, `scripts/local-ci.sh --base-ref origin/main
  --list --json` classifies the complete range. PR body lint and the declaration
  check validate the actual PR body before publication.

No new required gate is added. The new tests catch a wrong persisted choice,
setting-key collision, failed-write queue poisoning or an early durability claim.
No Core/Wasm/browser/device result is claimed for this unconsumed utility.

## Subsequent layers

1. Complete S7 over Layer 1: wire late-hydration protection, SETUP Off/1/2,
   stopped-only scheduled recording, cancellation settlement, BPM/Pattern locks,
   playable Pad Press/Release, truthful status/Record lamp and native cue to JS
   metronome handoff. Before editing, refresh the public S6 API and freeze the
   exact App/state/controls/overview/metronome/tests/Portal file list. Keep every
   Record/cue/applied-or-cancel/Stop/Truth/reopen/PCM journey leg.
2. S3 starts with its recording-segment design addendum, then separately verified
   producer and consumer Tasks. S5 follows with actual cross-Pattern phase
   publication; a UI enum is not delivery. Freeze each Task's files and lowest
   tests at its actual predecessor head.
3. ASSIGN, BPM I2b then I2c, meter, capture/WAV duration and remaining UI Tasks
   join the same stack at declared, verified boundaries. Check shared App,
   Sequence, Sample, Perform, SDK and Portal ownership before each layer.
4. Keep version debt per Task. The historical settlement #2247/#2274 is already
   delivered. Final Product allocation/snapshot #2237 requires the formal
   verified-main candidate process after implementation integration; do not
   allocate a release identity from unmerged stack code. #1221 retains the final
   same-candidate 35-screen, device and listening acceptance.

This is the integration order, not a claim that later layers have started or
that their exact implementation files have been approved by an earlier draft.

## Version Management

Version impact: none for Layer 1 — an unconsumed, Host-internal preference utility
with no public API, dependency, manifest, persisted Project Contract or Product
identity change. The existing Host settings database schema version is unchanged.
Later user-visible S7 behavior assesses Creator Host version impact in that Task;
all further module/API/ABI debts are recorded at their actual layers.

## Documentation Impact

Documentation impact: none for Layer 1 — current product/Portal behavior is
unchanged; this implementation plan and internal preference utility have no
Portal projection. The consuming S7 layer must update `/hosts/creator-web/`,
`/hosts/creator-interactions/` and `/platform/input/` for its actual behavior and
run the owning Portal check. Product allocation retains its snapshot obligation.

## Pitfall Impact

Pitfall impact: none — new behavior is specified by its preference tests. Follow
the existing async-assertion and far-side evidence guidance; no new process
failure is established by this Task.

## Execution evidence

- Base rechecked before commit: live main remains
  `e47b02510ef144a518163978d42b44b50558d36b`.
- Unchanged baseline: the SEQ SNAP, metronome and last-Project preference suites
  passed 21/21. With the new COUNT-IN suite, the same four-file selection passes
  52/52 (31 new tests). TypeScript `tsc --noEmit` passes.
- Independent-key proof: temporarily changed the implementation key to
  `count-in.v2` in a separate Vitest process. All three approved-key assertions
  failed at the raw `count-in.v1` read (undefined rather than numeric 0/1/2).
  Restored the source with a fresh mtime and reran the complete four-file
  selection: 52/52 passed. The targeted mutant selected three tests and left
  the other tests unselected; that run is deliberate negative evidence.
- Staged-path ownership passes 76/76, including explicit ownership and top-level
  admission for all three new paths. Final committed-range classification, PR
  publication and current-head review are recorded separately after their results.
  Packaged browser, full Creator proof, Core, Portal and physical acceptance have
  not run for this unconsumed utility. The full S7 user journey remains open.
- main remains outside this turn's merge authority.

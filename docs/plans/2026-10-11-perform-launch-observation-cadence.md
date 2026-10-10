# Perform and Sequence early-Bar observation cadence

Status: both original complete Chromium journeys passed; committed-head full Creator lane and current-head review remain pending.

## Task and declared files

Observe the existing early-Bar precondition often enough to enter its narrow
window. This Task changes only the observation cadence of the existing Perform
Launch and Sequence Pattern-switch journeys.

Declared files:

- `tests/platform/web/creator/creator_web_perform.spec.mjs`
- `tests/platform/web/creator/creator_web_sequence.spec.mjs`
- `docs/plans/2026-10-11-perform-launch-observation-cadence.md`
- `.agents/pitfalls/live-phase-polling-alias.md`

No product behavior, DSP, transport producer, schema, clock, predicate window,
timeout, retry, skip, fixture, or journey leg changes.

## Refreshed premises and ownership

Fresh `origin/main` and this isolated worktree's initial base are
`4a2b26f03a1e628882e907c92a9b9411b48e110d`. The failure was observed in the
complete Creator run at frozen history head
`21f28e056f28540b09c453475c203716c38a3226`. Both target specs are byte-identical
between those revisions; the history Task has no changes in either file.

The new playing-state switch journeys were delivered by #1992, merge
`a98ae01c4`; their transport operation and far-side assertions must be retained.
The outstanding defect is that both early-Bar polls omit intervals. Installed
Playwright 1.62.1 uses `[100, 250, 500, 1000]` and then repeats the final
one-second wait. No successor at the refreshed base changes those helpers.

The live open PRs #2000 and #2001 do not edit either target spec. Local ownership
inspection also found retained staged changes in the same files:

- `p1-current-finalization`: older Perform master-capture and Sequence
  diagnostics-navigation sections; no live local terminal.
- `p1-first-gesture-metronome`: older Perform helper/recovery sections; one live
  local terminal, `term_28b0d3b9-ab85-4621-84e0-12096d3b56af`, at the preserved
  merging worktree. Its actual metadata has `agentWait: null`; this does not
  establish absence of an owner.

Root explicitly coordinated this Task's new early-Bar sections after reading
those nonoverlapping hunks. Neither retained worktree, index, branch nor terminal
is modified. The local inventory omits remote hosts; their absence from that
inventory is not represented as conflict-free ownership. This Task uses the
new isolated `fix/perform-launch-observation-cadence` worktree with no main
upstream and preserves all earlier evidence and worktrees.

## Actual failure reduction

The real Project reads in both traces show 120 BPM, unchanged during each
failing leg. At 48,000 frames/second, a 4/4 bar is 96,000 frames (two seconds).
The existing strict early window is `[0, 19,200)` (400 ms).

| Observed poll | Samples | Sampled phase range | Early matches | Engine frame progression |
| --- | ---: | ---: | ---: | --- |
| Perform Launch first early-Bar poll | 32 | 19,200–93,440 | 0 | 369,920–1,786,624 |
| Sequence third early-Bar poll | 32 | 19,712–95,488 | 0 | 1,128,960–2,545,664 |

All failing-poll responses are successful, playing, idle, with no pending switch,
publication or error. Origins remain 349,184 for Perform and 1,010,176 for
Sequence. Receipt timestamps imply approximately 48,025 and 47,998 frames/second,
respectively. The engine progresses; missing fields or a stalled clock do not
explain either failure.

Actual waits settle near one second, sampling alternating phases outside the
two-second bar's first fifth. For Sequence, the first two early-Bar polls did
pass, the queued-stop cancellation was asserted and the switch into Pattern 02
was applied before the third poll failed at the return-switch precondition.
All 32 third-poll phases miss the window; it is not a transport refusal.

Measured inspect callback costs were 5.791–156.778 ms (median 11.126 ms) for
Perform, and 7.718–28.875 ms (median 11.129 ms) for the failed Sequence poll.
An explicit repeated 50 ms interval gives about 61 ms at those medians, and
about 207 ms including the largest observed callback, below the 400 ms window.
This fixes the established sampling alias without claiming unbounded future
latency can never exhaust the existing 30-second deadline.

The raw producer in `control_runtime.cpp` emits snake_case `runtime_frame` and
`origin_frame`; these tests intentionally inspect raw transport. Audio Runtime
defines a 48 kHz transport clock and PPQ 960. The formulas and schema match the
actual producer; no Core or tempo-transition implementation change is warranted
by these failures.

The original trace ZIPs, contexts, decoded actual responses and calculations
are retained outside Git under
`/Users/endaye/Projects/lmdj-followup-evidence/2026-10-11-master-consumer/`:

- `perform-launch-earlybar-21f-readonly/`: trace SHA-256
  `6c30ed7677773e0a0cab81c3567688479f6d0399fb6864d9db54bc1b741ab3e2`.
- `sequence-earlybar-21f-readonly/`: trace SHA-256
  `f99caf3491d4d23629ec51a708ec3bf7a501dc3f5265ac3ed8635bf6af75743c`.

These are read-only reductions of original receipts, not replacement responses,
forced-clock fixtures or a mirror test. The cause is specific to the test's
observation policy; no additional gate is introduced.

## Verification and acceptance

Lowest draft checks are `node --check` on both specs and `git diff --check`.
These establish syntax only, not browser behavior. Root's frozen complete
Creator run ended at 2026-10-10 18:21:30 UTC with exit 1: eight groups, 127
cases, 114 passed, two early-Bar observations failed and 11 existing
capability skips. The original five #1936 failure cases passed within the
main Chromium group; the whole lane remains failed. Actual head stayed
`21f28e056f28540b09c453475c203716c38a3226` and source stayed clean. The log
SHA-256 is `3faafb52151ae0a02f14593871a564064fa22aaaf33ea7497d77a3fe368d0cb1`.
The complete result and retained artifacts are under
`2026-10-11-overview-latency/complete-creator-20261010T175616Z/` in the
external evidence root.

After the Core heavy window closed, Root freshly built the native CLI and
Creator Wasm/UI at the unchanged product-source parent
`4a2b26f03a1e628882e907c92a9b9411b48e110d`. The official real Project fixture
was generated with that CLI and packed twice byte-identically: SHA-256
`66262c9187cb264a006e29d077751186acdeb02a30fc4bc497482049297e938f`.
The first package attempt stopped with exit 2 because this test-only draft was
uncommitted; no browser ran in that attempt. Root retained the four own draft
files in an exact-path stash, packaged the actually clean parent with exit 0,
and restored all four files byte-identically with an empty index. The stash
and failed attempt remain retained; the clean-source requirement was not bypassed.
The resulting manifest SHA-256 is
`0fef387aa9b1b65225f9c40db6b261cc9b492198733cd0c3807ccebc354a0e99`.

The owned verified server then ran both original full Chromium cases through
the unchanged Playwright command, one worker: **2 passed, exit 0**, no retries
or skipped journey legs. This verifies the changed specs against the rebuilt
parent product runtime; it does not claim a candidate-head full lane result.
The original Perform and Sequence case and transition deadlines remained intact.
Evidence, exact source/artifact identities, raw logs, actual output directory
and restoration receipts are retained under
`2026-10-11-perform-launch-observation-cadence/` in the external evidence root:
`focused-20261010T185807Z/` (retained setup failure and successful build/fixture),
`clean-package-20261010T190935Z/`, and `resumed-20261010T191011Z/`.
No full Creator PASS key exists for this Task yet.

Before committing, run the two existing complete Chromium cases against a
reliably rebuilt native-packaged Host, owned server and fresh real Project
fixture. Preserve the build exit status, source/artifact identities, failure
traces and actual test result. Use the existing Playwright entry point with
`--project=chromium --workers=1`, both declared specs and a grep selecting:

- `Perform Launch selects while stopped and queues, withdraws and applies
  without Performance recording`
- `Record-off ticket loss reconciles the same command; Pattern switch and
  stopped Record survive reopen`

Perform acceptance retains empty-slot refusal, stopped selection and reload,
playing queue, withdrawal, applied switch, stop, exact transport identities,
unchanged Project Truth and no Performance recording. Keep the strict phase
predicate, 30-second transitions and 180-second case limit.

Sequence acceptance retains first-gesture recording, dropped Record-off ticket
reconciliation with the same command identity, early queue, stop cancellation,
restart, forward switch, return switch, stopped snapshot reload, alternate
Pattern recording, exactly-once commits, final stop and persisted reopen of
both Patterns. Keep all far-side assertions, the strict phase predicate,
30-second transitions and 240-second case limit.

The focused result is Task verification only. Before merge, the committed head
must also satisfy its selected Creator batch-only lane obligation. Root's
history Task must integrate this fix before its new complete Creator proof;
neither the failed frozen run nor a later focused pass is a full lane pass.
No Portal, Core, browser, build, commit, push or PR action has been performed
for this draft at plan creation.

## Documentation impact

Documentation impact: none. Only test observation cadence changes; current
product behavior, portal source facts, routes, diagrams and identities remain
unchanged. This plan records the test defect and pending verification.

## Version Management

Version impact: none. No Product Build, Host, Module, Provider, Contract or
Assembly source or identity changes in this test-only Task.

## Pitfall impact

Pitfall impact: required — `.agents/pitfalls/live-phase-polling-alias.md`.
Installed framework polling cadence and live periodic-window observations are
process knowledge beyond product logic. The two failed cases from this one
complete run constitute one recurrence. Existing Creator environment-closure
and browser-profile entries, and the Web Host fake-driver frame-count entry,
cover different mechanisms and are retained. No generic gate is added.

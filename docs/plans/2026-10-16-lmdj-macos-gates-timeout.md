# macOS primary job budget calibration (#2283)

Status: owner-approved implementation, 2026-10-16. Relates to #2283.

## Premises and authority

At task start, the task checkout and refreshed `origin/main` were both
`f608cd14d693d4910fc90628e07b42634f06235a`. `git fetch origin main` was run
before diagnosis and again before implementation. The worker read #2283 and
all comments before other work, plus #2278's later cache and CI evidence.

Precommit refresh advanced `origin/main` to
`1990c61586b181bb785f774364bb695df813c560` through #2321's Product Build
allocation and #2323's snapshot witness. The workflow, composite actions,
Core entry point and both dominant stress sources are unchanged across that
range. No successor delivers this budget change; the dispositions below
remain valid. The owned checkout stays based on `f608cd14` and does not absorb
the unrelated Product allocation or immutable snapshots.

- Outstanding: `macos-primary` still has a 30-minute limit. The latest M1 job
  `116906584110` takes 1774 s with 100% cache hits: only 26 s of whole-job
  margin. ASan native CTest consumes 1497.37 s; core CTest 144.94 s; the two
  configure/build phases together 51.38 s. CTests use 95.7% of the gates step.
- Already delivered: #2272 merged
  `b5f5d78ac553477134c0ebfaa70ffb930733f784`, parallelizing the independent
  count-in rounds while retaining all 1037 cases. The first later M1 pass
  selects this merge. Its implementation remains unchanged at the refreshed
  base; this Task does not repeat it. Eight subsequent M1 jobs pass their
  233 core and 229 native ASan tests in 1468–1774 s overall.
- Verified cause in the detailed timeout runs: serial ASan native CTest takes
  1691.18–1710.95 s, including 624.81–629.06 s in count-in stress. Their
  combined configure/build windows are only 35.53–46.97 s, with cache hits
  above 98%. Every retrieved execution uses build parallelism 3. Changing
  that compiler bound cannot materially remove this test workload.
- Verified comparison at the same selected target
  `183f90241c6d4d7499433cb78a44e3197f03a21d`: M1 job `116842395250` native
  CTest is 1414.87 s versus M4 job `116794145441` at 931.61 s. M1 takes
  483.26 s longer testing but 151.59 s less building. Candidate-store stress,
  count-in stress and web-control runtime account for 320.07 s of the test
  difference. These are cross-host observations, not an isolated hardware
  benchmark; load, thermal and filesystem effects remain unmeasured.
- Attribution of the count-in reduction to #2272 is supported by source and
  selected-target history, not a new isolated causal experiment here. Other
  nearby changes intervene. The current M1 variance cause is still unknown.
- The latest selected M1 target `d9686f341df478dc020acfc263df6a07017fd36a`
  differs from the initial audit base `f608cd14` only in `tools/release/verification.py` and
  `tests/build/release_verification_carrier_test.py`, outside this native
  selection. It supports the premise audit, not an exact-current-head pass.
- Unknown/separate: three executed job logs return HTTP 404. Their missing
  phase timings remain unknown. The missing/blocked issue buckets named in
  #2283 contain separate historical runs and are not cleared by this Task.
  Root-cause optimization remains with #2306 and #2284.

The owner selected "A：上限调到 40 分钟" in the coordinator session on
2026-10-16. Dispatch `ctx_3c12abf25ada` relayed that decision and authorized
one commit, push and PR, with no merge. The coordinator explicitly owns
`scripts/docs-site.sh check` on a fresh clone of the exact pushed head on
another machine, recording its result in the PR; it stays pending here.
The M1 is a live CI runner, so no local build, CTest, sanitizer, complete lane
or Portal check is authorized. No old batch rerun or new batch dispatch is
part of this Task.

## Task M1 — Calibrate the job hang detector

Change only `macos-primary.timeout-minutes` from 30 to 40 in `ci.yml`.
Keep every test selection, CTest budget, parallelism value, queue, runner
label and `macos-fallback` unchanged. The budget is a hang detector, not a
performance target. If any M1 `Run macOS Core gates` step exceeds 35 minutes,
re-evaluate through test optimization, not another limit increase. This is
an operator trigger, not an additional automated gate.

Declared files:

1. `.github/workflows/ci.yml` — the one primary budget literal.
2. `tests/build/ci_workflow_topology_test.py` — the existing policy pin and
   an actionable failure message. No new required check is introduced.
3. `docs/plans/2026-10-16-lmdj-macos-gates-timeout.md` — this evidence and plan.
4. `docs/prd/decisions/2026-10-16-macos-gates-job-budget.md` — owner budget
   decision, measured cause, retained optimization ownership and trigger.
5. `docs/design/2026-08-11-risk-based-ci-gating-design.md` — its two macOS
   primary budget references.
6. `apps/docs-site/docs/operations/testing-and-proof.mdx` — current operation
   guidance, preserving the existing fallback semantics.
7. `.agents/pitfalls/facade-surface-test-budget-headroom.md` — this recurrence
   of a fixed lane budget exhausting margin as measured test work grows.
   Its existing escalation #657 remains open; no new generic timing gate.

The existing topology pin catches reverting the authorized primary budget
without a measured owner decision. Mutation: set only this workflow literal
back to 30, run the focused policy-pin test and require its `macos-primary`
assertion to fail; restore the saved 40-minute bytes with a fresh mtime, then
require the focused test to pass. Python runs use `-B` in fresh processes;
no native artifact is involved.

Lowest-tier verification:

- `python3 -B tests/build/ci_workflow_topology_test.py` — topology and budgets.
- `python3 -B tests/build/ci_build_acceleration_test.py` — capacity queues,
  bounded compilation, cache and workload preservation.
- `python3 -B tests/build/ci_runner_fallback_test.py` — routing and semantic
  failure/fallback behavior.
- `python3 -B tests/build/ci_pitfall_ledger_test.py` — recurrence schema.
- `python3 -B tests/build/ci_change_scope_test.py` after staging the new files
  — explicit path ownership and admission.
- `python3 tests/build/ci_pr_body_lint.py --body-file <body>` and
  `scripts/local-ci.sh --declaration-only --pr-body <body>` — the exact PR body.
- Workflow byte comparison against the base with exactly the one literal
  replacement; `git diff --cached --check`; exact staged/committed file list.

Verification completed before commit (all stated passes exit 0):

- Baseline topology: 63 tests passed before edits.
- Updated topology: 63 tests; acceleration: 14; fallback: 28; pitfall ledger:
  15; staged ownership/scope: 76. Total: 196 contract tests passed.
- Mutation: the focused budget-pin test exited 1 at the `macos-primary`
  subtest with the intended `why`/`remedy` after changing only 40 back to 30.
  Restoring the saved bytes with a fresh mtime made the same test pass
  (one test, exit 0). No native compilation was used.
- Byte comparison proves `ci.yml` equals its base plus exactly that one
  budget replacement; fallback and every other workflow byte are retained.
- The local `--list --json` classifier reports full scope because this is a
  central CI control-plane file; listing runs no lanes and clears no complete
  verification debt. Body validation results are recorded in the PR.

Portal check and post-change real CI evidence remain pending coordinator
verification; a local contract pass is not native runtime, full-candidate or
release acceptance.

## Version Management

Version impact: none
Reason: CI hang-detection budget and its documentation only; no Product,
Module, Provider, Host or Contract identity changes.

## Documentation Impact

Documentation impact: required
Affected portal pages: /operations/testing-and-proof
Reason: the portal explicitly documents the primary job's timeout and
infrastructure fallback boundary. The coordinator will run its full check
on another machine against the exact pushed head.

## Complete 14-day job inventory

Snapshot: Self-test Report runs created in
`2026-10-02T15:20:04Z..2026-10-16T15:20:04Z`. Fifteen individual UTC-date
queries each returned fewer than 1000 runs and exactly their API total count;
this avoids GitHub's filtered-list cap. The exact window has 4270 runs and
6413 checks. Every CheckSuite's pagination was exhausted. The October 2
boundary scan covered 226 earlier runs and six earlier-started jobs; none
started after the window boundary. The Core CI standalone listing returned
zero runs: its self-test executions use the reusable workflow caller.

77 primary jobs: 66 M1, one M4 Pro, ten skipped with no runner. API conclusions
are 62 success, four cancelled, one failure, ten skipped; all attempt 1.
64 execution logs were retrieved. Missing logs:

- `111733842843`: disk-full annotation, no steps returned.
- `114219743514`, `115816189648`: 30-minute-limit annotations; the gates step
  has no completion timestamp. Their phases and cache results are unknown.

Job success alone is not semantic success: jobs `111370400694`, `111419663245`,
`111449467952`, `111485721248` report a failing ASan candidate-store stress;
`114777996060` reports ASan provider.stem_split and web-control failures;
`114840121958` reports an ASan web-control failure. Cancelled job `115942282428`
also fails provider.conformance in both configurations. These failures are
retained, not repaired or cleared by the budget decision.

Core phases are unexecuted in five otherwise API-successful jobs:
`114526163121`, `114566437302`, `114624683436` stop in preflight with
`stable Web Runtime Host command is missing: proof`; `115094741190` and
`115136103896` stop at the Cardputer copied-version assertion. Their ASan
phases still execute. They are not complete Core Proof passes.

Times below are seconds. Configure/build starts at the first CMake output
and ends at CTest start (subsecond startup omitted, ASan target checks included).
CTest values are its printed totals. Core preflight/post-test proof steps are
outside these phase columns but inside the gates step. All 64 logs show
`CMAKE_BUILD_PARALLEL_LEVEL=3`; CTest totals match serial per-test sums to
rounding. Dashes mean unknown or unexecuted, never zero-cost success.
M1 = `endaye-mbp-m1`; M4 = `endaye-mbp-m4-pro`. Each pair identifies the direct
Actions URL `https://github.com/endaye/lmdj/actions/runs/RUN/job/JOB`.


| UTC start | run / job | runner | result | job / gates s | core cfg+build / ctest s | ASan cfg+build / native ctest s | ccache hits/calls |
|---|---|---|---|---|---|---|---|
| 10-02T17:57 | 37037025368 / 110947132218 | M1 | success | 986.0 / 951.0 | 11.2 / 87.7 | 22.1 / 812.5 | 484/484 |
| 10-02T20:17 | 37053317740 / 110998852648 | M1 | success | 986.0 / 951.0 | 10.1 / 88.9 | 42.3 / 792.0 | 470/484 |
| 10-02T23:28 | 37071379300 / 111059149780 | M1 | success | 1240.0 / 1208.0 | 21.1 / 146.5 | 32.5 / 984.8 | 484/484 |
| 10-03T03:57 | 37091669450 / 111117073556 | M1 | success | 1051.0 / 1023.0 | 10.2 / 88.0 | 99.9 / 807.9 | 404/490 |
| 10-04T04:12 | 37175164581 / 111359576561 | none | skipped | — / — | — / — | — / — | — |
| 10-04T06:10 | 37179244207 / 111370400694 | M1 | success | 702.0 / 676.0 | 9.7 / 87.7 | 23.2 / 538.3 | 486/490 |
| 10-04T08:31 | 37185774437 / 111389587354 | M1 | success | 1074.0 / 1043.0 | 13.6 / 89.5 | 38.2 / 882.6 | 487/490 |
| 10-04T12:32 | 37196072182 / 111419663245 | M1 | success | 684.0 / 644.0 | 9.8 / 87.9 | 20.3 / 509.7 | 484/484 |
| 10-04T15:33 | 37206297217 / 111449467952 | M1 | success | 904.0 / 830.0 | 16.5 / 114.4 | 37.7 / 638.8 | 484/484 |
| 10-04T19:00 | 37218254860 / 111485721248 | M1 | success | 905.0 / 878.0 | 10.3 / 88.9 | 203.8 / 557.9 | 265/490 |
| 10-04T22:27 | 37231144928 / 111525749270 | M1 | success | 1032.0 / 1003.0 | 10.8 / 88.6 | 21.9 / 865.2 | 490/490 |
| 10-05T03:10 | 37249896958 / 111577554530 | M1 | success | 1066.0 / 1041.0 | 11.0 / 89.6 | 46.4 / 875.7 | 478/500 |
| 10-05T13:01 | 37298765758 / 111733842843 | M1 | failure | 1161.0 / — | — / — | — / — | — |
| 10-05T17:49 | 37335567539 / 111857342386 | M1 | success | 1015.0 / 984.0 | 9.8 / 90.6 | 19.7 / 845.9 | 500/500 |
| 10-05T22:50 | 37371804087 / 111976295860 | M1 | success | 1017.0 / 987.0 | 10.3 / 91.0 | 20.1 / 846.3 | 500/500 |
| 10-06T02:08 | 37392223898 / 112044870404 | M1 | success | 1030.0 / 1002.0 | 10.5 / 90.3 | 21.2 / 862.8 | 500/500 |
| 10-06T05:11 | 37406907265 / 112092602367 | M1 | success | 1049.0 / 1015.0 | 10.6 / 88.3 | 23.0 / 874.8 | 500/500 |
| 10-06T11:51 | 37445366455 / 112215196845 | M1 | success | 1081.0 / 1036.0 | 10.4 / 86.4 | 20.4 / 901.6 | 500/500 |
| 10-06T15:13 | 37468821900 / 112295338281 | M1 | success | 1113.0 / 995.0 | 10.0 / 88.0 | 21.7 / 856.8 | 500/500 |
| 10-06T20:58 | 37514252559 / 112450846515 | M1 | success | 1012.0 / 987.0 | 10.0 / 84.3 | 21.0 / 854.4 | 500/500 |
| 10-07T07:44 | 37576667995 / 112653469000 | M1 | success | 1112.0 / 1082.0 | 17.6 / 108.5 | 34.2 / 896.2 | 496/500 |
| 10-07T11:26 | 37600586101 / 112732429760 | M1 | success | 1020.0 / 990.0 | 10.2 / 84.6 | 21.4 / 856.4 | 500/500 |
| 10-07T18:35 | 37650891633 / 112905480125 | M1 | success | 1257.0 / 1232.0 | 10.2 / 89.8 | 35.3 / 1078.9 | 495/500 |
| 10-07T21:40 | 37676506324 / 112987393933 | M1 | success | 1009.0 / 985.0 | 10.1 / 85.6 | 20.0 / 852.5 | 500/500 |
| 10-08T02:53 | 37710535649 / 113097965617 | M1 | success | 1302.0 / 1269.0 | 10.8 / 110.1 | 32.1 / 1093.8 | 500/500 |
| 10-08T06:09 | 37726646487 / 113148901643 | M1 | success | 1152.0 / 1118.0 | 10.7 / 92.8 | 21.5 / 975.7 | 500/500 |
| 10-08T09:30 | 37742880826 / 113203266036 | M1 | success | 1390.0 / 1365.0 | 16.7 / 93.8 | 117.7 / 1117.1 | 433/502 |
| 10-08T12:55 | 37766643266 / 113279710613 | M1 | success | 1198.0 / 1092.0 | 14.7 / 100.0 | 34.5 / 922.8 | 498/502 |
| 10-08T18:12 | 37805561137 / 113417287834 | M1 | success | 1169.0 / 1143.0 | 10.2 / 88.1 | 151.2 / 875.8 | 358/504 |
| 10-08T21:06 | 37841986379 / 113541458322 | none | skipped | — / — | — / — | — / — | — |
| 10-09T02:21 | 37871989093 / 113638902403 | none | skipped | — / — | — / — | — / — | — |
| 10-09T04:12 | 37881252499 / 113666120361 | none | skipped | — / — | — / — | — / — | — |
| 10-09T15:36 | 37936249334 / 113845904901 | M1 | success | 1194.0 / 1138.0 | 12.3 / 87.6 | 26.0 / 994.2 | 504/504 |
| 10-09T19:22 | 37962926335 / 113938907717 | M1 | success | 1762.0 / 1729.0 | 20.9 / 93.6 | 33.4 / 1560.3 | 503/504 |
| 10-09T23:54 | 37992583270 / 114038595257 | M1 | success | 1776.0 / 1748.0 | 21.3 / 124.9 | 45.9 / 1531.2 | 504/504 |
| 10-10T03:53 | 38013878581 / 114103063314 | M1 | success | 1270.0 / 1231.0 | 11.8 / 92.0 | 86.2 / 1022.8 | 461/504 |
| 10-10T07:19 | 38026788349 / 114142809957 | M1 | success | 1173.0 / 1108.0 | 11.6 / 94.7 | 30.8 / 953.0 | 503/504 |
| 10-10T11:18 | 38040330863 / 114181715956 | M1 | success | 1595.0 / 1553.0 | 19.4 / 97.2 | 41.1 / 1373.1 | 501/504 |
| 10-10T15:19 | 38053049380 / 114219743514 | M1 | cancelled | 2100.0 / — | — / — | — / — | — |
| 10-10T19:04 | 38068960168 / 114266072988 | M1 | success | 1506.0 / 1474.0 | 13.5 / 97.2 | 120.2 / 1223.7 | 434/504 |
| 10-11T18:30 | 38156734089 / 114526163121 | M1 | success | 1139.0 / 1108.0 | — / — | 163.2 / 942.1 | 108/253 |
| 10-11T22:06 | 38169883553 / 114566437302 | M1 | success | 1014.0 / 976.0 | — / — | 26.4 / 946.6 | 252/253 |
| 10-12T03:07 | 38190643198 / 114624683436 | M1 | success | 1026.0 / 1002.0 | — / — | 26.3 / 971.5 | 253/253 |
| 10-12T05:55 | 38201343415 / 114658942610 | M1 | success | 1374.0 / 1350.0 | 13.8 / 95.8 | 122.6 / 1098.2 | 438/504 |
| 10-12T09:23 | 38217544467 / 114709237785 | M1 | success | 1125.0 / 1100.0 | 10.5 / 89.7 | 23.2 / 959.2 | 504/504 |
| 10-12T12:35 | 38238760719 / 114777996060 | M1 | success | 1198.0 / 1108.0 | 12.2 / 94.8 | 97.6 / 884.1 | 458/504 |
| 10-12T15:24 | 38256968028 / 114840121958 | M1 | success | 1095.0 / 1024.0 | 13.9 / 101.8 | 23.7 / 862.6 | 504/504 |
| 10-12T18:16 | 38277208241 / 114907431344 | M1 | success | 1118.0 / 1093.0 | 10.7 / 89.2 | 34.3 / 941.8 | 500/504 |
| 10-12T21:23 | 38296940628 / 114976506081 | M1 | success | 1137.0 / 1111.0 | 11.7 / 93.8 | 29.2 / 957.5 | 502/504 |
| 10-13T00:31 | 38317363368 / 115041229072 | M1 | success | 1114.0 / 1088.0 | 10.7 / 92.1 | 23.0 / 944.1 | 504/504 |
| 10-13T03:55 | 38333590212 / 115094741190 | M1 | success | 1022.0 / 997.0 | — / — | 50.8 / 943.1 | 242/253 |
| 10-13T06:35 | 38347891408 / 115136103896 | M1 | success | 1128.0 / 1101.0 | — / — | 45.4 / 1051.7 | 247/253 |
| 10-13T09:32 | 38363512454 / 115185475858 | M1 | success | 1166.0 / 1141.0 | 10.6 / 90.9 | 33.8 / 987.2 | 501/504 |
| 10-13T13:17 | 38385920278 / 115269153982 | M1 | success | 1241.0 / 1141.0 | 10.8 / 97.0 | 25.3 / 990.0 | 500/504 |
| 10-13T16:55 | 38416841255 / 115368000135 | M1 | success | 1321.0 / 1295.0 | 12.3 / 92.9 | 109.5 / 1062.1 | 428/504 |
| 10-13T20:28 | 38447169273 / 115473547522 | M1 | success | 1159.0 / 1128.0 | 10.7 / 91.2 | 24.7 / 983.1 | 500/504 |
| 10-13T22:27 | 38476805724 / 115573010715 | none | skipped | — / — | — / — | — / — | — |
| 10-14T02:29 | 38490244712 / 115615031559 | M1 | success | 1180.0 / 1154.0 | 12.1 / 91.0 | 24.5 / 1009.0 | 504/504 |
| 10-14T06:11 | 38508675218 / 115681268004 | M1 | success | 1339.0 / 1275.0 | 10.5 / 94.1 | 22.1 / 1130.6 | 504/504 |
| 10-14T09:29 | 38528927161 / 115740894924 | M1 | success | 1248.0 / 1210.0 | 11.0 / 100.7 | 30.2 / 1049.7 | 497/504 |
| 10-14T13:35 | 38552647643 / 115816189648 | M1 | cancelled | 2101.0 / — | — / — | — / — | — |
| 10-14T17:40 | 38588990296 / 115942282428 | M1 | cancelled | 1915.0 / 1889.0 | 12.2 / 125.7 | 34.8 / 1711.0 | 524/530 |
| 10-14T22:08 | 38619404365 / 116053993315 | M1 | cancelled | 1904.0 / 1873.0 | 10.8 / 127.5 | 24.7 / 1691.2 | 529/530 |
| 10-15T03:31 | 38662185311 / 116188198978 | M1 | success | 1577.0 / 1541.0 | 12.3 / 127.6 | 42.7 / 1339.4 | 525/530 |
| 10-15T05:30 | 38681181819 / 116250210548 | M1 | success | 1530.0 / 1492.0 | 11.6 / 127.8 | 28.3 / 1305.1 | 526/530 |
| 10-15T08:25 | 38698356107 / 116304189493 | M1 | success | 1568.0 / 1533.0 | 11.1 / 137.7 | 23.8 / 1341.8 | 530/530 |
| 10-15T10:25 | 38719608028 / 116372461834 | none | skipped | — / — | — / — | — / — | — |
| 10-15T10:32 | 38720208142 / 116375165917 | none | skipped | — / — | — / — | — / — | — |
| 10-15T12:33 | 38734583501 / 116423965712 | none | skipped | — / — | — / — | — / — | — |
| 10-15T18:16 | 38776156275 / 116567448487 | M1 | success | 1478.0 / 1447.0 | 10.8 / 129.7 | 25.8 / 1263.2 | 526/530 |
| 10-15T21:16 | 38800878861 / 116653110743 | M1 | success | 1468.0 / 1439.0 | 10.9 / 127.5 | 27.0 / 1255.4 | 526/530 |
| 10-15T23:28 | 38822441807 / 116726334590 | none | skipped | — / — | — / — | — / — | — |
| 10-16T01:18 | 38826569407 / 116744214963 | M1 | success | 1574.0 / 1549.0 | 11.9 / 125.0 | 30.6 / 1362.6 | 526/530 |
| 10-16T03:23 | 38842939814 / 116794145441 | M4 | success | 1320.0 / 1265.0 | 36.0 / 118.0 | 162.8 / 931.6 | 277/530 |
| 10-16T07:17 | 38860143940 / 116842395250 | M1 | success | 1653.0 / 1619.0 | 13.3 / 136.9 | 33.8 / 1414.9 | 526/530 |
| 10-16T10:29 | 38880015551 / 116906584110 | M1 | success | 1774.0 / 1716.0 | 15.3 / 144.9 | 36.1 / 1497.4 | 530/530 |
| 10-16T13:37 | 38908604815 / 117000671463 | none | skipped | — / — | — / — | — / — | — |

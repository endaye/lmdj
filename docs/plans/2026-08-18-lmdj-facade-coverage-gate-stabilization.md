# LMDJ Application Facade Coverage Gate Stabilization Plan

> **For agentic workers:** Follow repository `AGENTS.md` and execute the approved plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

> **Revised 2026-08-18 after Task 1.** The measurement invalidated this plan's
> original premise (that covered *lines* move between runs) and its proposed fix
> (a stress-tier label exclusion). Both are recorded in
> [`2026-08-18-facade-coverage-gate-measurement.md`](../quality/2026-08-18-facade-coverage-gate-measurement.md).
> Tasks 2 and 3 below are rewritten; the original text is preserved in this
> file's history, not silently replaced.

**Goal:** Stop the `application-facade` coverage gate from failing Pull
Requests at random, and make a genuine coverage regression distinguishable
from noise — which today it is not, because the measurement itself is
nondeterministic and the floor sits inside the noise band. This is triage item
C1 and the machine list's top ready task, filed there with the explicit
demand that the chosen option state what it gives up.

**Architecture:** Test tooling and policy only — the coverage ctest preset in
`CMakePresets.json`, the enforced floors in
`tests/quality/core-coverage-thresholds.json`, and their canonical statement
in `docs/quality/core-test-policy.md`. No Core Module source, no test source,
no Contract, no Product identity. The gate script
`tests/quality/coverage_gate.py` is correct as written and is not changed:
the defect is in what it is asked to measure, not in how it compares.

**Tech Stack:** CMake presets / ctest label filters, LLVM source coverage
(profraw → profdata → lcov union), Python gate, Bash entry point
`scripts/core-coverage.sh`.

## Current state (verified against `main` at `3b416a23`, 2026-08-18)

- The enforced floor is `packages/application-facade/: lines 84` in
  `tests/quality/core-coverage-thresholds.json`, compared exactly
  (`coverage_gate.py:112`, `Decimal` comparison, no tolerance).
- The measurement is nondeterministic. The coverage test preset
  (`CMakePresets.json:129-136`) excludes exactly one test **by name** —
  `^audio\.realtime_spsc_stress$` — so the only other stress-tier test in the
  repository, `facade.c_api_stress`
  (`packages/application-facade/CMakeLists.txt:184-188`, `TIER stress`,
  `LABELS abi concurrency`), still runs under coverage. Thread interleavings
  decide which lines it touches, and the covered-line count moves ±4 lines
  between runs on identical source.
- ±4 lines on 4,061 facade lines is ±0.10%, and the floor sits at 84.00%
  against a measured 84.04%. One Stage 8 run measured 83.94% and failed; the
  next measured 84.04% and passed. Any PR can be stopped by this at random,
  and a genuine 4-line regression is indistinguishable from noise.
- `docs/quality/core-test-policy.md` §Coverage Thresholds is the canonical
  statement of the enforced ratchet and duplicates the JSON floors. It rules:
  floors "must not be lowered merely to make CI green", and any change
  "requires a reviewed measurement and policy update, not an ad hoc threshold
  edit". This plan is that reviewed measurement and policy update.
- The policy's Deterministic Seeds section governs PRNGs. It cannot help
  here: thread scheduling is not seedable, so `facade.c_api_stress` can never
  be made a deterministic coverage source no matter how it is seeded.

## What Task 1 measured, and what it changed

Full evidence in
[`2026-08-18-facade-coverage-gate-measurement.md`](../quality/2026-08-18-facade-coverage-gate-measurement.md).

**The line count does not vary.** Five local runs on an unchanged tree gave an
identical 3422/4070 every time, and a per-file comparison found no facade file
whose covered lines moved. The variance is entirely in branches, in exactly the
two files `facade.c_api_stress` reaches: `src/application.cpp` (759↔760) and
`src/c_api.cpp` (67↔68).

**So the risk is the opposite shape from what triage recorded.** The metric that
varies (branches) has 3.4592 points of headroom and cannot reach its floor; the
metric with 0.0786 points of headroom (lines) does not vary. One facade line is
worth 0.0246 points, so the line gate breaks on about four lines of newly
uncovered code. **The line gate is too tight, not noisy.**

**The proposed fix also does not run.** Replacing the preset's name exclusion
with `exclude.label: ^stress$` fails with
`coverage module signature count does not match object count: 32 != 33`, because
`lmdj_application_c_api_stress_tests` is itself a coverage object
(`CMakeLists.txt:109`) and produces no `.profraw` once its test is excluded.
The sibling `lmdj_realtime_engine_stress_tests` is **not** a coverage object,
so the two stress tests were never symmetric and the original plan's
"unifies an existing precedent" claim was wrong.

**What stays open.** Triage's Stage 8 observation (83.94% then 84.04%, a
four-line move) was on Ubuntu CI, and five local macOS runs did not reproduce
it. macOS and Ubuntu do not even measure the same file set — `CMakeLists.txt`
adds two Apple-only coverage objects. Whether Ubuntu line counts vary is
therefore unanswered, and it is the input the floor decision needs, because CI
is the platform that enforces the gate.

**Revised approach: establish the CI-side behaviour first, then set the floor
from it.** No floor moves until there is same-revision Ubuntu evidence. This
keeps the test policy's rule intact — a floor moves only on a reviewed
measurement, on the platform that enforces it.

## Global Constraints

- Execute only on `fix/facade-coverage-gate` in
  `/Users/endaye/Projects/lmdj/.worktrees/facade-coverage-gate`. Never
  implement on `main`.
- Do not change `tests/quality/coverage_gate.py`, any test source, any Core
  Module source, or any test's tier or labels.
- The floor may move only to a **measured** deterministic value, recorded in
  a dated measurement document, with the policy table and the JSON updated in
  the same commit. No floor moves on an estimate.
- Floors other than `packages/application-facade/` change only if the
  measurement shows the stress exclusion moved them too (the only other
  stress test is already excluded by name, so no movement is expected — but
  the measurement decides, not the expectation).
- Every Task is one reviewable Conventional Commit. Before every commit:
  verify the branch is not `main`; run the Task-specific verification and
  `scripts/architecture-portal.sh check`; stage only declared files; inspect
  `git diff --cached --name-status` and `git diff --cached --check`; after
  committing inspect `git show --name-status --oneline HEAD`.
- This plan authorizes local commits only. Push, PR creation, merge, tag,
  Release, publication, deployment and Channel promotion each require
  separate explicit authorization.

## Tasks

### Task 1 — Measure the noise, then prove the determinism

No committed change yet; this task produces the evidence every later number
stands on.

- [x] With the preset unchanged, run `scripts/core-coverage.sh check` five
      times on identical source. Record per-run facade covered/total lines
      and the per-file diffs between runs, confirming the fluctuation
      localizes to files reachable from `facade.c_api_stress`.
- [x] Apply the label exclusion locally (not committed) and run five more
      times. Requirement: the facade covered-line count is **identical across
      all five runs**. If any residual nondeterminism remains, stop and
      report — the plan's premise is wrong and the exclusion alone is not the
      fix.
- [x] Quantify the trade: per-file list and total count of facade lines that
      lose coverage credit under the exclusion, and the resulting
      deterministic facade percentage on this machine.
- [x] Write the measurement record as
      `docs/quality/2026-08-18-facade-coverage-gate-measurement.md`: machine
      and toolchain identity, all ten runs' numbers, the per-file diff, the
      deterministic value, and the floor it implies.

**Done 2026-08-18.** Five baseline runs are recorded; the five post-exclusion
runs could not be produced because the exclusion does not run at all (Finding 2).
The record covers both outcomes and is the commit for this Task.

### Task 2 — Establish whether Ubuntu line counts vary

- [x] Collect every retained `core-coverage` job on `main` and extract each
      run's facade line numbers with its revision. Where two runs share a
      revision, their difference is the CI variance; where they do not, record
      the numbers per revision without inferring variance from them.
- [x] If same-revision Ubuntu runs disagree on covered lines, the CI
      measurement is nondeterministic and the defect is noise after all —
      report before proposing any fix, because the fix then has to target
      whatever makes Ubuntu differ from macOS.
- [x] If they agree, or if no same-revision pair exists, obtain one: this
      branch's own Pull Request selects the `core_coverage` lane through the
      `tests/quality/` rule in `scripts/ci/scope_policy.json`, so a change
      under that directory produces a fresh Ubuntu measurement to compare
      against the retained one.
- [x] Extend the measurement record with the Ubuntu series and its conclusion.

**Done 2026-08-18.** Answered by re-running job `95185530769` at its own
revision `801fa450` rather than by scanning history: the re-run
(`95690337280`) reproduced 3413/4061 lines **and** 1031/1542 branches exactly.
Ubuntu is deterministic in both metrics, so C1's premise of random failures
does not hold on the enforcing platform.

### Task 3 — Blocked: the remaining question is a policy decision

Task 2's answer removed the defect this plan was written to fix. On Ubuntu the
measurement is deterministic in lines and branches, so a gate failure at the
0.0433-point margin is a true signal that a change lowered facade line
coverage, not a random stop.

What is left is a judgement, not an implementation: **a ratchet floor with
about two lines of headroom catches regressions precisely, and also fails any
change that adds two uncovered lines to this package.** Whether that is the
margin this project wants is a policy call, and
`docs/quality/core-test-policy.md` forbids lowering a floor "merely to make CI
green" — with the noise justification gone, no implementation argument remains
to lower it.

- [x] Take the margin question to a decision row rather than settling it here.
- [x] Change a threshold only after that decision, recording it against this
      measurement.

**Resolved 2026-08-18 by the product owner:** the floor number is not the
point; the real work is raising coverage to the policy's 90% target and
ratcheting the floor upward afterwards. Superseded by
[`2026-08-18-lmdj-facade-coverage-raise.md`](2026-08-18-lmdj-facade-coverage-raise.md);
no threshold moved under this plan.

### Task 4 — Close the ledger

Done 2026-08-18 alongside filing machine task C6: C1 is recorded in both
ledgers as invalidated by measurement and superseded by the coverage-raise
plan.

- [x] Mark C1 closed in `docs/quality/2026-08-17-machine-task-todo.md` with the
      measured numbers, recording that triage's description of the defect was
      corrected by measurement.
- [x] Update triage C1 in
      `docs/quality/2026-08-16-outstanding-work-before-stage9.md` the same way.

**Verification:** `scripts/architecture-portal.sh check`;
`git diff --cached --check`.

## Version Management

**Version impact: none.** Coverage presets, threshold data, and quality
policy are unversioned repository tooling and governance. No Core Module,
Provider, Host, Contract or Product identity changes; no Product Build is
allocated. The floor change itself is governed by the test policy's
reviewed-measurement rule, which this plan and its measurement document
satisfy.

## Documentation impact

**Documentation impact: none.** No portal route states the facade floor or
the coverage tier selection; the canonical statement lives in
`docs/quality/core-test-policy.md`, which Task 2 updates in the same commit
as the behaviour it describes. `scripts/architecture-portal.sh check` runs
before every commit regardless.

## Out of scope

- Raising any floor toward the long-term targets table — that ratchets after
  sustained behavioral coverage lands, not here.
- Changing what `core-asan` or `proof` run; stress execution ownership is
  untouched.
- `coverage_gate.py` semantics, including its exact comparison — a tolerance
  parameter would re-legitimize noise instead of removing it.
- The stress-tier label exclusion, and any change to the coverage object list
  it would require — Task 1 showed it does not run as written and targets
  branch variance, which is not the live risk.
- C2, B3, B4, C4, C5 — separate ledger rows, separate plans.

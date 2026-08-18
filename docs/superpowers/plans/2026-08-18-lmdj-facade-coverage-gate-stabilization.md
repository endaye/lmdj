# LMDJ Application Facade Coverage Gate Stabilization Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

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

## The decision, and what each option gives up

Triage offers two shapes. They are not equivalent.

**Rejected: lower the floor below the observed noise floor.** This keeps the
nondeterministic measurement and just widens the dead zone around it — a
genuine regression of several lines stays invisible, permanently, and the
noise band itself is only characterized by two observations (83.94, 84.04),
so any specific number would be a guess. A floor lowered while the
measurement stays noisy is exactly the "lowered merely to make CI green" the
policy forbids.

**Chosen: make the measurement deterministic, then recalibrate the floor to
the deterministic value.** Exclude the stress tier from the coverage preset
by **label** (`^stress$`), replacing the name-specific exclusion that already
exists for the sibling test — the repository has exactly two stress-tier
tests, one of which is already excluded, so this unifies an existing
precedent rather than inventing a policy. The tier maps to a ctest label via
`cmake/LmdjTesting.cmake:42`, and the preset schema already uses a label
filter elsewhere (`CMakePresets.json:121`).

**What this gives up, stated per the machine-list requirement:** facade lines
exercised **only** by `facade.c_api_stress` stop earning coverage credit, and
the recalibrated floor will be lower than 84 if those lines exist. They are
not lost to verification — `core-asan` runs `full` then `stress` on every PR,
so the stress test still executes and still blocks; it just no longer counts
toward a percentage. The exchange is: the gate stops measuring
stress-reachable lines, and in return a **one-line** regression in the
deterministic remainder becomes real signal instead of noise. Task 1
quantifies exactly how many lines change status before anything is committed.

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

- [ ] With the preset unchanged, run `scripts/core-coverage.sh check` five
      times on identical source. Record per-run facade covered/total lines
      and the per-file diffs between runs, confirming the fluctuation
      localizes to files reachable from `facade.c_api_stress`.
- [ ] Apply the label exclusion locally (not committed) and run five more
      times. Requirement: the facade covered-line count is **identical across
      all five runs**. If any residual nondeterminism remains, stop and
      report — the plan's premise is wrong and the exclusion alone is not the
      fix.
- [ ] Quantify the trade: per-file list and total count of facade lines that
      lose coverage credit under the exclusion, and the resulting
      deterministic facade percentage on this machine.
- [ ] Write the measurement record as
      `docs/quality/2026-08-18-facade-coverage-gate-measurement.md`: machine
      and toolchain identity, all ten runs' numbers, the per-file diff, the
      deterministic value, and the floor it implies.

**Verification:** the record exists and contains ten runs; the five
post-exclusion runs are identical. Commit is the measurement document only.

### Task 2 — Exclude the stress tier by label and recalibrate the floor

- [ ] In `CMakePresets.json`, replace the coverage test preset's
      name-exclusion `^audio\.realtime_spsc_stress$` with the label
      exclusion `^stress$`.
- [ ] Set `packages/application-facade/` lines in
      `tests/quality/core-coverage-thresholds.json` to the measured
      deterministic value, truncated to the integer style the ratchet table
      already uses. Touch the branch floor only if the measurement moved it.
- [ ] Update the enforced-ratchet table and its narrative in
      `docs/quality/core-test-policy.md` in the same commit: the facade row's
      new floor, and one sentence recording that coverage measurement
      excludes the stress tier because thread scheduling is not a
      deterministic coverage source, while `core-asan` continues to own
      stress execution.
- [ ] Confirm no other floor in the JSON changed value against Task 1's
      with-exclusion measurements.

**Verification:** `scripts/core-coverage.sh check` passes twice locally with
byte-identical facade totals; `python3 tests/build/version_test.py`;
`bash tests/build/test_active_tree.sh`; `scripts/architecture-portal.sh
check`. The PR's own `core-coverage` lane is the CI-equivalent Ubuntu
evidence, matching how the original ratchet was measured on both platforms.

### Task 3 — Close the ledger

- [ ] Mark C1 done in `docs/quality/2026-08-17-machine-task-todo.md`, naming
      the commits and the measured numbers.
- [ ] Update triage C1 in
      `docs/quality/2026-08-16-outstanding-work-before-stage9.md` the same
      way, including what the exclusion gave up.

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
- C2, B3, B4, C4, C5 — separate ledger rows, separate plans.
